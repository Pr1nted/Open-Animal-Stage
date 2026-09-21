"""The OAS1 species package, written and checked, for the three fly exporters.

    tools/export_female_fly.py   FlyWire 783, from Open Fly's own web export
    tools/export_larva.py        Winding et al. (2023), L1 larva
    tools/export_male_fly.py     MaleCNS v1.0

docs/species-format.md is the contract; this module is the one place that
writes it, so the three flies cannot drift into three dialects of it.

`make_groups` is Open Fly's `open_fly/decode.py::make_groups`, copied line for
line rather than re-derived: the female's 39 groups must come out byte-for-byte
the neurons Open Fly deals, and the male and larva must be dealt by the same
rule for the pairing to mean anything. The export of the female checks the copy
against Open Fly's shipped groups every time it runs.
"""
import hashlib
import json
import os
import struct

import numpy as np

MENU_SIZES = {"e": 12, "p": 12, "w": 8, "n": 7}
MODULES = "epwn"
PARTITION_SEED = 783
WINDOW_MS = 200

# Shiu et al. (2024), as Open Fly runs them, plus w_gap for the format.
PARAMS = {"dt": 0.1, "t_mbr": 20.0, "tau": 5.0, "v_0": -52.0, "v_th": -45.0,
          "v_rst": -52.0, "t_rfc": 2.2, "t_dly": 1.8, "w_syn": 0.275,
          "f_poi": 250, "w_gap": 0.0}

SIGNALS = ("reward", "harm", "reserve", "threat")

# THE FLYWIRE RULE, as Open Fly's model applies it. Shiu et al.'s signed
# Connectivity_783.parquet carries no rule, only its result; cross-tabulating
# its per-neuron signs against top_nt in FlyWire 783's neuron_annotations.tsv
# (done once, 2026-09-21) gives: GABA and glutamate negative (39,594 of 43,883
# neurons), acetylcholine, dopamine, serotonin and octopamine positive (92,378
# of 94,110). The residue is top_nt being a later prediction than the one Shiu
# et al. signed with. FlyWire predicts no other transmitter, so the rule has
# no answer for anything else -- histamine included -- and anything else is
# UNKNOWN, which the format drops (open_animal_stage/signs.py).
FLYWIRE_RULE = {
    "gaba": -1, "glutamate": -1,
    "acetylcholine": 1, "dopamine": 1, "serotonin": 1, "octopamine": 1,
}


def make_groups(units, seed):
    """Deal units into one balanced group per action. Deterministic in `seed`.

    Verbatim from Open Fly, open_fly/decode.py.
    """
    rng = np.random.default_rng(seed)
    n_groups = sum(MENU_SIZES.values())
    order = list(rng.permutation(len(units)))
    order.sort(key=lambda u: -len(units[u]))          # stable: seed breaks size ties
    bins = [[] for _ in range(n_groups)]
    totals = [0] * n_groups
    for u in order:
        low = min(totals)
        candidates = [b for b in range(n_groups) if totals[b] == low]
        b = candidates[int(rng.integers(len(candidates)))]
        bins[b].extend(units[u])
        totals[b] += len(units[u])
    slots = list(rng.permutation(n_groups))
    groups, k = {}, 0
    for m in MODULES:
        groups[m] = [np.array(sorted(bins[slots[k + a]]), dtype=np.int64) for a in range(MENU_SIZES[m])]
        k += MENU_SIZES[m]
    return groups


def sha256(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def csr(n, pre, post, count):
    """Sort edges by (pre, post) and return indptr, post, count."""
    pre = np.asarray(pre, np.int64)
    post = np.asarray(post, np.int64)
    count = np.asarray(count, np.int64)
    if len(pre) and (pre.min() < 0 or pre.max() >= n or post.min() < 0 or post.max() >= n):
        raise SystemExit("an edge index is out of range 0..%d" % (n - 1))
    if len(count) and np.abs(count).max() > 32767:
        raise SystemExit("a synapse count of %d does not fit int16" % np.abs(count).max())
    if (count == 0).any():
        raise SystemExit("%d edges carry a zero count" % int((count == 0).sum()))
    order = np.lexsort((post, pre))
    pre, post, count = pre[order], post[order], count[order]
    if len(pre) > 1:
        dup = (pre[1:] == pre[:-1]) & (post[1:] == post[:-1])
        if dup.any():
            raise SystemExit("%d duplicate (pre, post) edges" % int(dup.sum()))
    indptr = np.zeros(n + 1, np.uint64)
    np.add.at(indptr, pre + 1, 1)
    indptr = np.cumsum(indptr, dtype=np.uint64)
    if indptr[-1] >= 2 ** 32:
        raise SystemExit("too many synapses for a u32 index")
    return indptr.astype(np.uint32), post, count


def write_connectome(path, n, indptr, post, count, gap=None):
    """OAS1, little-endian, exactly as docs/species-format.md lays it out."""
    gap_a, gap_b, gap_w = gap if gap is not None else ([], [], [])
    nsyn, ngap = len(post), len(gap_a)
    assert len(indptr) == n + 1 and int(indptr[-1]) == nsyn and len(count) == nsyn
    with open(path, "wb") as f:
        f.write(b"OAS1" + struct.pack("<III", n, nsyn, ngap))
        f.write(np.asarray(indptr).astype("<u4").tobytes())
        f.write(np.asarray(post).astype("<u4").tobytes())
        f.write(np.asarray(count).astype("<i2").tobytes())
        f.write(b"\0" * ((-(nsyn * 2)) % 4))
        f.write(np.asarray(gap_a, np.int64).astype("<u4").tobytes())
        f.write(np.asarray(gap_b, np.int64).astype("<u4").tobytes())
        f.write(np.asarray(gap_w, np.float64).astype("<f4").tobytes())
    return os.path.getsize(path)


def read_connectome(path):
    """(n, indptr, post, count, gap_a, gap_b, gap_w) as memory maps."""
    with open(path, "rb") as f:
        head = f.read(16)
    if head[:4] != b"OAS1":
        raise ValueError("%s: magic %r, not OAS1" % (path, head[:4]))
    n, nsyn, ngap = struct.unpack("<III", head[4:16])
    mm = np.memmap(path, dtype=np.uint8, mode="r")
    off = 16
    indptr = mm[off:off + (n + 1) * 4].view("<u4"); off += (n + 1) * 4
    post = mm[off:off + nsyn * 4].view("<u4"); off += nsyn * 4
    count = mm[off:off + nsyn * 2].view("<i2"); off += nsyn * 2
    off += (-(nsyn * 2)) % 4
    gap_a = mm[off:off + ngap * 4].view("<u4"); off += ngap * 4
    gap_b = mm[off:off + ngap * 4].view("<u4"); off += ngap * 4
    gap_w = mm[off:off + ngap * 4].view("<f4"); off += ngap * 4
    if off != len(mm):
        raise ValueError("%s: header says %d bytes, file has %d" % (path, off, len(mm)))
    return n, indptr, post, count, gap_a, gap_b, gap_w


def validate(n, indptr, post, count, meta):
    """Every invariant the format promises. Raises SystemExit on the first break."""
    def fail(msg):
        raise SystemExit("INVALID: " + msg)
    if meta["n"] != n or len(meta["names"]) != n:
        fail("n disagrees: bin %d, json %d, names %d" % (n, meta["n"], len(meta["names"])))
    if len(set(meta["names"])) != n:
        fail("names are not unique")
    ip = np.asarray(indptr, np.int64)
    if ip[0] != 0 or (np.diff(ip) < 0).any() or ip[-1] != len(post):
        fail("indptr is not a CSR row pointer")
    if len(post) and int(np.asarray(post).max()) >= n:
        fail("a postsynaptic index is out of range")
    if len(count) and (np.asarray(count) == 0).any():
        fail("a zero synapse count")
    # Shiu's constants, except w_syn/w_gap when set by the preregistered rule
    # (tools/calibrate.mjs; the larva is the only fly it applies to).
    cal = meta["params"].get("calibrated")
    tuned = ("w_syn", "w_gap") if isinstance(cal, dict) else ()
    if any(meta["params"].get(k) != PARAMS[k] for k in PARAMS if k not in tuned):
        fail("params are not the Shiu et al. constants")
    if tuned:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from open_animal_stage.package import calibration_problems
        for problem in calibration_problems(meta["params"]):
            fail(problem)
    if set(meta["sensory"]) != set(meta["senses"]):
        fail("sensory channels and senses disagree")
    if sorted(meta["senses"].values()) != sorted(SIGNALS):
        fail("senses must carry each of %s exactly once" % (SIGNALS,))
    seen = {}
    for ch, ids in meta["sensory"].items():
        if not ids:
            fail("sensory channel %s is empty" % ch)
        if min(ids) < 0 or max(ids) >= n or len(set(ids)) != len(ids):
            fail("sensory channel %s has a bad or repeated index" % ch)
        for i in ids:
            if i in seen:
                fail("neuron %d is in sensory channels %s and %s" % (i, seen[i], ch))
            seen[i] = ch
    g = meta["groups"]
    if {m: len(g.get(m, [])) for m in MODULES} != MENU_SIZES:
        fail("groups are not 12 + 12 + 8 + 7")
    union = set()
    for m in MODULES:
        inmod = set()
        for grp in g[m]:
            if not grp:
                fail("an empty group in module %s" % m)
            for i in grp:
                if not 0 <= i < n:
                    fail("group index %d out of range" % i)
                if i in inmod:
                    fail("neuron %d is in two groups of module %s" % (i, m))
                inmod.add(i)
        union |= inmod
    if sorted(union) != sorted(meta["motor"]):
        fail("motor is not exactly the neurons dealt into groups")
    if meta["partition_seed"] != PARTITION_SEED:
        fail("partition seed is not %d" % PARTITION_SEED)
    if not isinstance(meta["provenance"].get("dropped_unknown_sign"), int):
        fail("provenance.dropped_unknown_sign is missing")


def sensory_reach(indptr, count, meta):
    """Signed outgoing synapses per sensory channel: does a channel reach anything?"""
    ip = np.asarray(indptr, np.int64)
    return {ch: int(sum(ip[i + 1] - ip[i] for i in ids)) for ch, ids in meta["sensory"].items()}


def groups_json(groups):
    return {m: [[int(i) for i in grp] for grp in groups[m]] for m in MODULES}


def write_brain_json(path, meta):
    with open(path, "w") as f:
        json.dump(meta, f, separators=(",", ":"))
    return os.path.getsize(path)


def pack_if_large(path, limit_mib=25.0):
    """Open Fly's parts, plain (its --no-gzip, which is what it ships)."""
    if os.path.getsize(path) <= limit_mib * 1024 * 1024:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pack_web", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pack_web.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.pack(path, int(20.0 * 1024 * 1024), compress=False)


def report(meta, indptr, count, size_bin, size_json):
    nsyn = len(count)
    neg = int((np.asarray(count) < 0).sum())
    print("  neurons           %d" % meta["n"])
    print("  synapses (edges)  %d  (%d inhibitory, %d excitatory)" % (nsyn, neg, nsyn - neg))
    print("  synapse count     %d" % int(np.abs(np.asarray(count, np.int64)).sum()))
    print("  dropped (unknown sign) %s" % meta["provenance"]["dropped_unknown_sign"])
    reach = sensory_reach(indptr, count, meta)
    for ch, ids in meta["sensory"].items():
        print("  sense %-8s -> %-8s %4d neurons, %6d signed outgoing edges"
              % (ch, meta["senses"][ch], len(ids), reach[ch]))
    print("  motor             %d neurons in %s groups"
          % (len(meta["motor"]), "+".join(str(len(meta["groups"][m])) for m in MODULES)))
    print("  connectome.bin    %.1f MB   brain.json %.2f MB" % (size_bin / 1e6, size_json / 1e6))
    return reach
