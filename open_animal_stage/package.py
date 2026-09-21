"""The species package (docs/species-format.md): write it, read it, check it.

One writer and one reader, so the exporters and the test agree on the layout
by construction rather than by two people reading the same table. The reader
and the checks are plain Python (struct, json) so the test runs anywhere; only
the group dealer needs numpy, because it must be Open Fly's generator with
Open Fly's seed to mean what Open Fly's groups mean.
"""
import json
import os
import struct

MAGIC = b"OAS1"
MENU_SIZES = {"e": 12, "p": 12, "w": 8, "n": 7}      # as open_fly/decode.py
MODULES = "epwn"
N_GROUPS = sum(MENU_SIZES.values())                   # 39
PARTITION_SEED = 783
SIGNALS = ("reward", "harm", "reserve", "threat")

# Open Fly's constants (Shiu et al. 2024), unchanged, plus the gap gain. The
# gap gain is 0 and "calibrated" is false: w_syn and w_gap get calibrated later
# by one fixed rule in the JS brain, not by hand in an exporter.
SHIU_PARAMS = {"dt": 0.1, "t_mbr": 20, "tau": 5, "v_0": -52, "v_th": -45,
               "v_rst": -52, "t_rfc": 2.2, "t_dly": 1.8, "w_syn": 0.275,
               "f_poi": 250, "w_gap": 0.0, "calibrated": False}



def calibration_problems(p):
    """A params block is either Open Fly's constants untouched, or those
    constants with w_syn and w_gap set by the rule in PREREGISTRATION.md
    ("The neuron, and how its one free constant is set"), which
    tools/calibrate.mjs applies and records. Anything else was set by hand."""
    cal = p.get("calibrated")
    if not isinstance(cal, dict):
        return []
    bad = []
    k = cal.get("k")
    if not isinstance(k, int) or not 0 <= k <= 10:
        bad.append("params.calibrated.k is %r, not a ladder step 0..10" % (k,))
    elif abs(p.get("w_syn", 0) - 0.275 * 2 ** k) > 1e-9:
        bad.append("params.w_syn is %r, but ladder step %d is %r" % (p.get("w_syn"), k, 0.275 * 2 ** k))
    if p.get("w_gap") not in (0, 1):
        bad.append("params.w_gap is %r; the rule fixes it at 1 (0 with no junctions)" % (p.get("w_gap"),))
    if "rule" not in cal or "ladder" not in cal:
        bad.append("params.calibrated does not record its rule and ladder")
    return bad

# --------------------------------------------------------------------- groups

def bilateral_units(names):
    """Motor neurons as units: a left/right homologue pair moves together.

    Open Fly deals whole cell types so that left and right homologues land in
    the same group. The worm has no cell-type table at that grain, but its
    names carry the side: XXXL and XXXR are one unit when both are in the set.
    Anything else (RMED, VA01, M4) is a unit of one.
    """
    s = set(names)
    units, used = [], set()
    for x in sorted(names):
        if x in used:
            continue
        if x.endswith("L") and x[:-1] + "R" in s:
            u = [x, x[:-1] + "R"]
        elif x.endswith("R") and x[:-1] + "L" in s:
            u = [x[:-1] + "L", x]
        else:
            u = [x]
        used.update(u)
        units.append(u)
    return units


def deal_groups(units, seed=PARTITION_SEED):
    """Units (lists of neuron indices) into 12 + 12 + 8 + 7 groups.

    39 or more neurons: Open Fly's make_groups, line for line -- balanced bins,
    largest units first, seeded ties, then a seeded permutation of bins onto
    actions. Fewer than 39: round-robin, as docs/species-format.md says. For
    each module the neurons are put in a seeded order and dealt across its
    groups in turn, so every neuron is in exactly one group per module (modules
    share neurons; groups within a module never do). Returns (groups, rule).
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    neurons = sorted(i for u in units for i in u)
    if len(neurons) >= N_GROUPS:
        order = list(rng.permutation(len(units)))
        order.sort(key=lambda u: -len(units[u]))
        bins = [[] for _ in range(N_GROUPS)]
        totals = [0] * N_GROUPS
        for u in order:
            low = min(totals)
            cand = [b for b in range(N_GROUPS) if totals[b] == low]
            b = cand[int(rng.integers(len(cand)))]
            bins[b].extend(units[u])
            totals[b] += len(units[u])
        slots = list(rng.permutation(N_GROUPS))
        groups, k = {}, 0
        for m in MODULES:
            groups[m] = [sorted(int(i) for i in bins[slots[k + a]])
                         for a in range(MENU_SIZES[m])]
            k += MENU_SIZES[m]
        return groups, "balanced"
    groups = {}
    for m in MODULES:
        # A fresh seeded order per module (drawn in e, p, w, n order from the
        # one generator). With one shared order, e and p -- both 12 groups --
        # would be the same partition, and two menus would always agree.
        order = [neurons[int(j)] for j in rng.permutation(len(neurons))]
        k = MENU_SIZES[m]
        groups[m] = [sorted(int(order[i]) for i in range(len(order)) if i % k == a)
                     for a in range(k)]
    return groups, "round-robin"


# ---------------------------------------------------------------- write / read

def write_package(out_dir, n, synapses, gaps, meta):
    """synapses: (pre, post, signed_count); gaps: (a, b, weight), a < b.

    Writes connectome.bin and brain.json into out_dir. The CSR is sorted by
    (pre, post), as Open Fly's is.
    """
    os.makedirs(out_dir, exist_ok=True)
    syn = sorted(synapses)
    for pre, post, c in syn:
        if c == 0 or not -32768 <= c <= 32767:
            raise ValueError("synapse %d->%d has count %r, which is zero or "
                             "does not fit int16" % (pre, post, c))
    indptr = [0] * (n + 1)
    for pre, _, _ in syn:
        indptr[pre + 1] += 1
    for i in range(n):
        indptr[i + 1] += indptr[i]
    gaps = sorted(gaps)
    blob = bytearray(MAGIC + struct.pack("<III", n, len(syn), len(gaps)))
    blob += struct.pack("<%dI" % (n + 1), *indptr)
    blob += struct.pack("<%dI" % len(syn), *[p for _, p, _ in syn])
    blob += struct.pack("<%dh" % len(syn), *[c for _, _, c in syn])
    blob += b"\0" * ((-len(blob)) % 4)
    blob += struct.pack("<%dI" % len(gaps), *[a for a, _, _ in gaps])
    blob += struct.pack("<%dI" % len(gaps), *[b for _, b, _ in gaps])
    blob += struct.pack("<%df" % len(gaps), *[w for _, _, w in gaps])
    with open(os.path.join(out_dir, "connectome.bin"), "wb") as f:
        f.write(bytes(blob))
    with open(os.path.join(out_dir, "brain.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
        f.write("\n")


def read_package(pkg_dir):
    """Returns (header, arrays, meta). Raises ValueError on a malformed file."""
    raw = open(os.path.join(pkg_dir, "connectome.bin"), "rb").read()
    meta = json.load(open(os.path.join(pkg_dir, "brain.json")))
    if raw[:4] != MAGIC:
        raise ValueError("magic is %r, not %r" % (raw[:4], MAGIC))
    n, nsyn, ngap = struct.unpack_from("<III", raw, 4)
    off = 16
    indptr = struct.unpack_from("<%dI" % (n + 1), raw, off); off += (n + 1) * 4
    post = struct.unpack_from("<%dI" % nsyn, raw, off); off += nsyn * 4
    count = struct.unpack_from("<%dh" % nsyn, raw, off); off += nsyn * 2
    pad = (-off) % 4
    if raw[off:off + pad] != b"\0" * pad:
        raise ValueError("padding after count is not zero")
    off += pad
    ga = struct.unpack_from("<%dI" % ngap, raw, off); off += ngap * 4
    gb = struct.unpack_from("<%dI" % ngap, raw, off); off += ngap * 4
    gw = struct.unpack_from("<%df" % ngap, raw, off); off += ngap * 4
    if off != len(raw):
        raise ValueError("file is %d bytes, layout says %d" % (len(raw), off))
    return ({"n": n, "nsyn": nsyn, "ngap": ngap, "bytes": len(raw)},
            {"indptr": indptr, "post": post, "count": count,
             "gap_a": ga, "gap_b": gb, "gap_w": gw}, meta)


# ---------------------------------------------------------------------- check

def check_package(pkg_dir):
    """Every invariant the format promises. Returns a list of failures."""
    bad = []
    try:
        h, a, meta = read_package(pkg_dir)
    except (ValueError, struct.error, OSError) as e:
        return ["unreadable: %s" % e]
    n = h["n"]
    if meta.get("n") != n:
        bad.append("brain.json n=%r, connectome.bin n=%d" % (meta.get("n"), n))
    if len(meta.get("names", [])) != n or len(set(meta.get("names", []))) != n:
        bad.append("names: %d entries (%d distinct) for %d neurons"
                   % (len(meta.get("names", [])), len(set(meta.get("names", []))), n))
    ip = a["indptr"]
    if ip[0] != 0 or ip[n] != h["nsyn"] or any(ip[i] > ip[i + 1] for i in range(n)):
        bad.append("indptr is not a CSR over %d synapses" % h["nsyn"])
    if any(not 0 <= p < n for p in a["post"]):
        bad.append("a postsynaptic index is out of range")
    if any(c == 0 for c in a["count"]):
        bad.append("a synapse has count 0")
    if any(not (0 <= x < n and 0 <= y < n and x < y)
           for x, y in zip(a["gap_a"], a["gap_b"])):
        bad.append("a gap junction is out of range or not stored once as a < b")
    if len(set(zip(a["gap_a"], a["gap_b"]))) != h["ngap"]:
        bad.append("a gap junction pair is stored twice")
    if any(not (w > 0) for w in a["gap_w"]):
        bad.append("a gap junction has weight <= 0")

    sens, senses = meta.get("sensory", {}), meta.get("senses", {})
    if set(sens) != set(senses):
        bad.append("sensory channels %s and senses %s differ" % (sorted(sens), sorted(senses)))
    if sorted(senses.values()) != sorted(SIGNALS):
        bad.append("senses must map one channel to each of %s, got %s"
                   % (SIGNALS, senses))
    for ch, idx in sens.items():
        if not idx:
            bad.append("sensory channel %r is empty" % ch)
        if any(not 0 <= i < n for i in idx):
            bad.append("sensory channel %r has an index out of range" % ch)

    groups = meta.get("groups", {})
    if {m: len(groups.get(m, [])) for m in MODULES} != MENU_SIZES:
        bad.append("groups are not 12+12+8+7: %s"
                   % {m: len(groups.get(m, [])) for m in MODULES})
    dealt = set()
    for m in MODULES:
        seen = set()
        for g in groups.get(m, []):
            if not g:
                bad.append("module %s has an empty group" % m)
            for i in g:
                if not 0 <= i < n:
                    bad.append("module %s: index %d out of range" % (m, i))
                if i in seen:
                    bad.append("module %s: neuron %d is in two groups" % (m, i))
                seen.add(i)
        dealt |= seen
    if sorted(dealt) != sorted(meta.get("motor", [])):
        bad.append("motor list is not exactly the neurons dealt into groups")
    if meta.get("partition_seed") != PARTITION_SEED:
        bad.append("partition_seed is %r" % meta.get("partition_seed"))
    prov = meta.get("provenance", {})
    for k in ("neurons", "signs", "sensory", "motor", "params", "licence"):
        if not prov.get(k):
            bad.append("provenance.%s is missing" % k)
    if not isinstance(prov.get("dropped_unknown_sign"), int):
        bad.append("provenance.dropped_unknown_sign is not an integer")
    p = meta.get("params", {})
    tuned = ("w_syn", "w_gap", "calibrated") if isinstance(p.get("calibrated"), dict) else ()
    for k, v in SHIU_PARAMS.items():
        if k not in tuned and p.get(k) != v:
            bad.append("params.%s is %r, Open Fly's is %r" % (k, p.get(k), v))
    bad += calibration_problems(p)
    return bad
