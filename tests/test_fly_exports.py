"""Are the three fly packages what docs/species-format.md says they are?

    python3 tests/test_fly_exports.py

Reads web/species/<id>/ for drosophila_female, drosophila_larva and
drosophila_male, as the tools/export_*.py scripts left them. The packages are
large and gitignored, so a missing one is SKIPPED and counted -- a skip is not a
pass, and the count is printed so nobody reads "ok" as "checked".

What is checked is the file, read back from disk, not the exporter's arrays:
header and byte size, CSR shape, indices in range, one sign per presynaptic
neuron, the Shiu constants, four senses carrying the four signals, 12+12+8+7
groups with no neuron twice in a module, motor = the dealt neurons, the
packed parts reassembling to the same bytes, and, for the female, groups and
sensory lists identical to Open Fly's own brain.json.

The validator is also shown a package broken on purpose, and must refuse it.
"""
import copy
import hashlib
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fly_oas1 as oas  # noqa: E402

OPEN_FLY = os.path.join(os.path.expanduser("~"), "CLionProjects", "Open-Fly", "web", "data", "brain.json")
EXPECT = {
    "drosophila_female": {"calibrated": True, "dropped": 0,
                          "senses": {"sugar": "reward", "bitter": "harm", "water": "reserve",
                                     "jon": "threat"}},
    "drosophila_larva": {"calibrated": False, "dropped": None, "senses": None},
    "drosophila_male": {"calibrated": False, "dropped": None,
                        "senses": {"sugar": "reward", "bitter": "harm", "water": "reserve",
                                   "jon": "threat"}},
}

checks = fails = skips = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    if not cond:
        fails += 1
    print("  %s  %s" % ("ok  " if cond else "FAIL", what))


def refuses(meta, n, ip, post, cnt, what):
    try:
        oas.validate(n, ip, post, cnt, meta)
    except SystemExit:
        ok(True, "validator refuses %s" % what)
        return
    ok(False, "validator refuses %s" % what)


def one_sign_per_presynaptic(ip, cnt):
    ip = np.asarray(ip, np.int64)
    s = np.sign(np.asarray(cnt, np.int64))
    rows = np.nonzero(np.diff(ip) > 0)[0]
    if not len(rows):
        return True
    starts = ip[rows]
    return bool((np.minimum.reduceat(s, starts) == np.maximum.reduceat(s, starts)).all()) \
        if ip[-1] == ip[rows[-1] + 1] else False


def check(sid):
    global skips
    d = os.path.join(ROOT, "web", "species", sid)
    b, j = os.path.join(d, "connectome.bin"), os.path.join(d, "brain.json")
    print("\n%s" % sid)
    if not (os.path.exists(b) and os.path.exists(j)):
        skips += 1
        print("  SKIP  no package at %s (run tools/export_*.py)" % os.path.relpath(d, ROOT))
        return
    meta = json.load(open(j))
    try:
        n, ip, post, cnt, ga, gb, gw = oas.read_connectome(b)
        ok(True, "OAS1 header, and byte size = 16 + (n+1)*4 + nsyn*6 + pad + ngap*12")
    except ValueError as e:
        ok(False, str(e))
        return
    ok(len(ga) == 0 and meta["params"]["w_gap"] == 0.0, "no gap junctions, so no gap gain (a fly)")
    try:
        oas.validate(n, ip, post, cnt, meta)
        ok(True, "format invariants: CSR, ranges, params, senses, 39 groups, motor")
    except SystemExit as e:
        ok(False, str(e))
    ok(meta["species"] == sid, "species id is %s" % sid)
    ok(meta["calibrated"] is EXPECT[sid]["calibrated"], "calibrated is %s" % EXPECT[sid]["calibrated"])
    if EXPECT[sid]["senses"]:
        ok(meta["senses"] == EXPECT[sid]["senses"], "senses are the female's mapping")
    if EXPECT[sid]["dropped"] is not None:
        ok(meta["provenance"]["dropped_unknown_sign"] == EXPECT[sid]["dropped"],
           "dropped_unknown_sign = %d" % EXPECT[sid]["dropped"])
    ok(one_sign_per_presynaptic(ip, cnt), "every presynaptic neuron has one sign on all its synapses")
    src = meta["provenance"].get("source", {})
    ok(bool(src) and all("sha256" in v for v in src.values() if isinstance(v, dict)),
       "provenance records sources with sha256")
    ok(bool(meta["provenance"].get("licence")), "provenance records a licence")

    pj = os.path.join(d, "connectome.pack.json")
    big = os.path.getsize(b) > 25 * 1024 * 1024
    if big:
        ok(os.path.exists(pj), "over 25 MiB, so packed parts exist")
    if os.path.exists(pj):
        man = json.load(open(pj))
        h = hashlib.sha256()
        for p in man["parts"]:
            h.update(open(os.path.join(d, p), "rb").read())
        ok(not man["gzip"] and man["size"] == os.path.getsize(b)
           and h.hexdigest() == man["sha256"] == oas.sha256(b),
           "%d parts reassemble to connectome.bin byte for byte" % len(man["parts"]))

    if sid == "drosophila_female":
        if os.path.exists(OPEN_FLY):
            of = json.load(open(OPEN_FLY))
            ok(meta["groups"] == of["groups"], "groups are Open Fly's, neuron for neuron")
            ok(meta["sensory"] == of["sensory"], "sensory channels are Open Fly's")
            ok(meta["motor"] == sorted(of["dn"]), "motor is Open Fly's descending list")
            ok(n == of["n"], "n is Open Fly's")
        else:
            global_skip("Open Fly's brain.json is not on this machine")

    # Break it on purpose: the validator must notice.
    bad = copy.deepcopy(meta)
    g0 = bad["groups"]["e"][0]
    bad["groups"]["e"][1] = sorted(set(bad["groups"]["e"][1]) | {g0[0]})
    refuses(bad, n, ip, post, cnt, "a neuron in two groups of one module")
    bad = copy.deepcopy(meta)
    bad["sensory"][next(iter(bad["sensory"]))] = []
    refuses(bad, n, ip, post, cnt, "an empty sensory channel")
    bad = copy.deepcopy(meta)
    bad["params"]["w_syn"] = 0.3
    refuses(bad, n, ip, post, cnt, "a tuned parameter")


def global_skip(why):
    global skips
    skips += 1
    print("  SKIP  %s" % why)


for sid in EXPECT:
    check(sid)

print("\n%d checks, %d failed, %d skipped" % (checks, fails, skips))
sys.exit(1 if fails else 0)
