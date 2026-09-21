#!/usr/bin/env python3
"""Label every Fish1 soma with its published MECE brain region.

    ~/fish1-venv/bin/python tools/fish1_regions.py

Writes data/raw/fish1/soma_regions.v704.parquet: one row per soma (lore id),
with the level-0, level-1 and level-2 MECE region id and label.

WHAT THIS IS, AND WHAT PART OF IT IS OURS

The region masks are published, world-readable and not ours:
gs://fish1-public/mece{0,1,2,3}_231218, uint64 segmentations on the EM grid at
512 x 512 x 30 nm, with human-readable names in segment_properties. They are
the Z-Brain reference atlas (Randlett et al. 2015) warped onto this specimen by
ANTs, as the Fish1 preprint's Methods describe, and are documented in the
FishExplorer companion paper.

What is OURS is the join: no released table says which region a soma is in, so
this samples the mask at the soma's own published centroid. soma pt_position is
at 8 x 8 x 30 nm (client.materialize.get_table_metadata("somas")
["voxel_resolution"]), the masks are at 512 x 512 x 30 nm, so x and y are
divided by 64 and z is used as is. A soma whose centroid falls on region 0 is
outside every mask and is recorded as unlabelled rather than guessed at.

Chunks are downloaded once each and every soma inside one is sampled from it,
because 187,052 point queries would be 187,052 HTTPS requests.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "raw", "fish1")

BUCKET = "precomputed://gs://fish1-public/"
LEVELS = ("mece0_231218", "mece1_231218", "mece2_231218")
CHUNK = np.array([32, 32, 512])
SOMA_TO_MECE = np.array([64, 64, 1])       # 8x8x30 nm soma voxels -> 512x512x30 nm
THREADS = 16


def labels(layer):
    import json, urllib.request
    url = ("https://storage.googleapis.com/fish1-public/%s/segment_properties/info" % layer)
    with urllib.request.urlopen(url, timeout=120) as r:
        d = json.load(r)
    ii = d["inline"]
    vals = [p for p in ii["properties"] if p["type"] == "label"][0]["values"]
    return {int(i): v for i, v in zip(ii["ids"], vals)}


def sample(layer, mv):
    from cloudvolume import CloudVolume
    vol = CloudVolume(BUCKET + layer, mip=0, use_https=True, progress=False,
                      fill_missing=True, parallel=False)
    bounds = np.array(vol.mip_shape(0)[:3])
    ch = mv // CHUNK
    keys, inv = np.unique(ch, axis=0, return_inverse=True)
    out = np.zeros(len(mv), dtype="uint64")
    done = [0]

    def one(k):
        i = int(k)
        c = keys[i]
        lo = c * CHUNK
        hi = np.minimum(lo + CHUNK, bounds)      # the last chunk of each axis
        blk = np.asarray(vol[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]])[..., 0]
        m = np.nonzero(inv == i)[0]
        p = mv[m] - lo
        out[m] = blk[p[:, 0], p[:, 1], p[:, 2]]
        done[0] += 1
        if done[0] % 500 == 0:
            print("    %s: %d/%d chunks" % (layer, done[0], len(keys)), flush=True)

    with ThreadPoolExecutor(THREADS) as ex:
        list(ex.map(one, range(len(keys))))
    return out


def main():
    s = pd.read_parquet(os.path.join(RAW, "somas.v704.parquet"))
    p = np.stack(s.pt_position.values).astype("int64")
    mv = p // SOMA_TO_MECE
    df = pd.DataFrame({"id": s.id.to_numpy("int64")})
    for lv, layer in enumerate(LEVELS):
        out = os.path.join(RAW, "region_l%d.v704.npy" % lv)
        if os.path.exists(out):
            v = np.load(out)
        else:
            print("  sampling %s over %d somas" % (layer, len(mv)), flush=True)
            v = sample(layer, mv)
            np.save(out, v)
        lab = labels(layer)
        df["l%d_id" % lv] = v.astype("int64")
        df["l%d" % lv] = [lab.get(int(x), "") for x in v]
        print("  level %d: %d somas labelled, %d outside every mask"
              % (lv, int((v != 0).sum()), int((v == 0).sum())), flush=True)
    df.to_parquet(os.path.join(RAW, "soma_regions.v704.parquet"), index=False)
    print("  wrote data/raw/fish1/soma_regions.v704.parquet")
    print(df.l0.value_counts().to_string())


if __name__ == "__main__":
    sys.exit(main())
