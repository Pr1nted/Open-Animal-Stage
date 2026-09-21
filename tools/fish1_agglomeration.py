#!/usr/bin/env python3
"""Fish1's wiring from the public automated agglomeration seg_241003_agg241003.

    ~/fish1-venv/bin/python tools/fish1_agglomeration.py somas      # soma -> agg id
    ~/fish1-venv/bin/python tools/fish1_agglomeration.py synapses   # bulk synapses
    ~/fish1-venv/bin/python tools/fish1_agglomeration.py all

Writes, under data/raw/fish1/agg241003/ (gitignored):

    soma_agg.parquet        one row per soma (lore id) -> agglomeration id at
                            its published centroid (0 = no segment there)
    by_id/<k>.shard         the eight by_id shards, downloaded verbatim
    syn_<k>.npz             each shard decoded: pre agg id, post agg id, type

Then `tools/fish1_export.py --wiring agglomeration-241003` builds the package
from them. Everything here is anonymous: gs://fish1-public is world-readable,
and no CAVE token is involved.

WHY THIS EXISTS

At CAVE materialization 704 Fish1's axons are unproofread, so a presynaptic
endpoint lands on a soma-bearing ChunkedGraph root about 2% of the time and no
sense reaches a motor neuron (docs/fish1-mapping.md). The same synapses are
released in bulk keyed by segment ids of the AUTOMATED AGGLOMERATION
seg_241003_agg241003, in which the agglomerator has already merged axon
fragments into much larger objects -- or so it was hoped. That is not
proofreading: merge errors add false connections and split errors remove true
ones.

MEASURED 2026-09-21: it does not help. The bulk layer holds exactly the CAVE
synapses (29,474,316, ids 0..29,474,315; type 1 on exactly the 15,883,209
synapses CAVE tags inhibitory), and the agglomeration is essentially the
segmentation the ChunkedGraph was seeded from: a presynaptic endpoint lands on a
soma-bearing segment 1.60% of the time (v704: 1.83%), both ends 0.72% (v704:
0.80%), and no sensory channel reaches a motor neuron. The presynaptic side is
spread over 7.19 million segments, median 2 synapses each. The sensory ganglion
cells' own segments carry almost no synapses at all (all 346 olfactory cells:
82 presynaptic; trigeminal 2; lateral line 3; vagal 1) -- their central axons
are not attached to their somata in either segmentation.

THE JOIN

No released table maps a soma to an agglomeration id, so the join is ours, the
same kind of join as tools/fish1_regions.py: the agglomeration is sampled at
each soma's published centroid. somas.pt_position is at 8 x 8 x 30 nm; the
layer's finest scale (mip 0) is 16 x 16 x 30 nm with voxel offset 0, so x and y
are halved and z is used as is. Checked on 1,500 random somas: the zero rate
(3.1%) is exactly the set whose v704 pt_root_id is also 0, and mip 3 and mip 4
return the same id as mip 0 for 99.8% of them, so the scale is right. mip 0 is
used anyway, being the definition.

THE BULK SYNAPSES

syn_241003_agg241003_reorient_axde_ei.precomputed is a neuroglancer
precomputed annotation layer of LINE annotations (pre point, post point) in
8 x 8 x 30 nm, one uint32 property `type`, and four relationships:
pre_synaptic_cell, pre_synaptic_site, post_synaptic_cell, post_synaptic_site.
Relationships are only stored in the by_id index, so the by_id shards are read
whole (8 files, 1.83 GB) rather than queried per cell.
"""
import argparse
import os
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "raw", "fish1")
OUT = os.path.join(RAW, "agg241003")

SEG = "precomputed://gs://fish1-public/seg_241003_agg241003"
SYN_URL = ("https://storage.googleapis.com/fish1-public/"
           "syn_241003_agg241003_reorient_axde_ei.precomputed")
SOMA_VOXEL_NM = np.array([8.0, 8.0, 30.0])
N_SHARDS = 8                  # by_id shard_bits 3
MINISHARD_BITS = 12           # by_id minishard_bits
RELATIONSHIPS = ("pre_synaptic_cell", "pre_synaptic_site",
                 "post_synaptic_cell", "post_synaptic_site")
THREADS = 48


def retry(fn, what, tries=10, base=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                       # 503s, resets
            if i == tries - 1:
                raise
            w = min(120, base * 1.6 ** i)
            print("    %s failed (%d/%d): %s; sleeping %.0fs"
                  % (what, i + 1, tries, str(e)[:120].replace("\n", " "), w), flush=True)
            time.sleep(w)


# ------------------------------------------------------------------ somas

def somas(version=704):
    """Soma -> agglomeration id, at mip 0, one chunk per soma. Resumable: work
    is done in blocks of 5,000 somas and each block is saved as it finishes."""
    import pandas as pd
    from cloudvolume import CloudVolume
    out = os.path.join(OUT, "soma_agg.parquet")
    if os.path.exists(out):
        print("  %s exists" % os.path.relpath(out, ROOT))
        return
    part = os.path.join(OUT, "soma_agg_parts")
    os.makedirs(part, exist_ok=True)
    s = pd.read_parquet(os.path.join(RAW, "somas.v%d.parquet" % version))
    p = np.stack(s.pt_position.values).astype("float64")
    vol = CloudVolume(SEG, mip=0, use_https=True, progress=False,
                      fill_missing=True, parallel=False)
    res = np.array(vol.resolution, dtype="float64")
    if tuple(vol.voxel_offset) != (0, 0, 0):
        raise SystemExit("unexpected voxel offset %s" % (vol.voxel_offset,))
    vox = np.floor(p * SOMA_VOXEL_NM / res).astype("int64")
    print("  mip 0 at %s nm; %d somas" % (res.tolist(), len(vox)), flush=True)

    def one(q):
        return retry(lambda: int(np.asarray(
            vol[q[0]:q[0] + 1, q[1]:q[1] + 1, q[2]:q[2] + 1])[0, 0, 0, 0]),
            "sample %s" % (q.tolist(),))

    B = 5000
    t0 = time.time()
    for b in range(0, len(vox), B):
        f = os.path.join(part, "b%06d.npy" % b)
        if os.path.exists(f):
            continue
        with ThreadPoolExecutor(THREADS) as ex:
            ids = np.array(list(ex.map(one, vox[b:b + B])), dtype="uint64")
        np.save(f + ".tmp.npy", ids)
        os.replace(f + ".tmp.npy", f)
        print("  somas %d/%d, %.0fs" % (min(b + B, len(vox)), len(vox), time.time() - t0),
              flush=True)
    ids = np.concatenate([np.load(os.path.join(part, "b%06d.npy" % b))
                          for b in range(0, len(vox), B)])
    pd.DataFrame({"id": s.id.to_numpy("int64"), "agg_id": ids,
                  "pt_root_id_v704": s.pt_root_id.to_numpy("uint64")}
                 ).to_parquet(out, index=False)
    print("  wrote %s: %d somas, %d on no segment"
          % (os.path.relpath(out, ROOT), len(ids), int((ids == 0).sum())))


# --------------------------------------------------------------- synapses

def download(k):
    import urllib.request
    d = os.path.join(OUT, "by_id")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "%d.shard" % k)
    if os.path.exists(f):
        return f
    url = "%s/by_id/%d.shard" % (SYN_URL, k)

    def get():
        tmp = f + ".part"
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        req = urllib.request.Request(url, headers={"Range": "bytes=%d-" % have})
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "ab") as w:
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                w.write(b)
        os.replace(tmp, f)
    retry(get, "download shard %d" % k)
    return f


def decode_shard(k):
    """One by_id shard -> (annotation id, pre cell, post cell, type).

    neuroglancer_uint64_sharded_v1: a raw shard index of 2**minishard_bits
    [start, end) uint64 pairs relative to its own end; each minishard index is
    gzip'd uint64 [3, n] (delta ids, delta offsets, sizes); each chunk is
    gzip'd. A by_id chunk is one annotation: LINE geometry (6 float32), the
    uint32 `type`, then per relationship a uint32 count and that many uint64
    ids, in the order the info lists them."""
    out = os.path.join(OUT, "syn_%d.npz" % k)
    if os.path.exists(out):
        return out
    f = download(k)
    buf = np.memmap(f, dtype="uint8", mode="r")
    hdr = 16 << MINISHARD_BITS
    idx = np.frombuffer(buf[:hdr], dtype="<u8").reshape(-1, 2)
    ids, pre, post, typ = [], [], [], []
    multi = {r: 0 for r in RELATIONSHIPS}
    empty = {r: 0 for r in RELATIONSHIPS}
    t0 = time.time()
    for m, (a, b) in enumerate(idx):
        if b <= a:
            continue
        mi = np.frombuffer(zlib.decompress(bytes(buf[hdr + a:hdr + b]), 16 + zlib.MAX_WBITS),
                           dtype="<u8").reshape(3, -1)
        cid = np.cumsum(mi[0])
        off = np.zeros(mi.shape[1], dtype="uint64")
        pos = 0
        for i in range(mi.shape[1]):
            pos += int(mi[1, i])
            off[i] = pos
            pos += int(mi[2, i])
        for i in range(mi.shape[1]):
            s0 = hdr + int(off[i])
            raw = zlib.decompress(bytes(buf[s0:s0 + int(mi[2, i])]), 16 + zlib.MAX_WBITS)
            t = int.from_bytes(raw[24:28], "little")
            p = 28
            cells = []
            for r in RELATIONSHIPS:
                c = int.from_bytes(raw[p:p + 4], "little")
                v = np.frombuffer(raw[p + 4:p + 4 + 8 * c], dtype="<u8")
                p += 4 + 8 * c
                if c == 0:
                    empty[r] += 1
                elif c > 1:
                    multi[r] += 1
                cells.append(int(v[0]) if c else 0)
            if p != len(raw):
                raise SystemExit("shard %d: annotation %d has %d trailing bytes"
                                 % (k, int(cid[i]), len(raw) - p))
            ids.append(int(cid[i]))
            pre.append(cells[0])
            post.append(cells[2])
            typ.append(t)
        if m % 512 == 511:
            print("    shard %d: %d/%d minishards, %d annotations, %.0fs"
                  % (k, m + 1, len(idx), len(ids), time.time() - t0), flush=True)
    np.savez(out + ".tmp.npz", id=np.array(ids, "uint64"), pre=np.array(pre, "uint64"),
             post=np.array(post, "uint64"), type=np.array(typ, "uint32"),
             multi=np.array([multi[r] for r in RELATIONSHIPS]),
             empty=np.array([empty[r] for r in RELATIONSHIPS]))
    os.replace(out + ".tmp.npz", out)
    print("  shard %d: %d annotations; relationships with >1 id %s, with none %s"
          % (k, len(ids), multi, empty), flush=True)
    return out


def synapses(procs=4):
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(procs) as ex:
        list(ex.map(decode_shard, range(N_SHARDS)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("somas", "synapses", "all"))
    ap.add_argument("--materialization", type=int, default=704,
                    help="which cached somas table to read positions from")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.what in ("somas", "all"):
        somas(a.materialization)
    if a.what in ("synapses", "all"):
        synapses()
    return 0


if __name__ == "__main__":
    sys.exit(main())
