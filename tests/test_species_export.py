"""Do the exported species packages hold to docs/species-format.md?

    python3 tests/test_species_export.py

WHY THIS TEST EXISTS

An exporter that writes a file the brain can load is not the same as one that
writes the brain it claims to. The failures that matter here all load and run:
a synapse index past the end, a sensory channel with nobody in it, a neuron in
two groups of one menu so two orders always fire together, a gap junction
stored twice so it counts double. Every one of those plays badly, and "plays
badly" reads as a fact about the animal.

The packages are derived from raw data that is not in the repository, so a
checkout without them SKIPS each species -- loudly, and counted, because a
skip is not a pass. With them present, every invariant is checked, and the
checker is itself broken on purpose once to prove it can fail.
"""
import json
import os
import shutil
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from open_animal_stage import package as pk      # noqa: E402

# What each package must say about itself, from the papers (see the exporters).
#
# "gaps" says whether the SOURCE releases gap junctions. It is an expectation,
# not a property of the format: the worm and the sea squirt must have them
# because their reconstructions publish them and treating an electrical synapse
# as a chemical one is wrong silently, and Fish1 must NOT, because it releases
# no gap junction table at all and inventing one would be worse. A package that
# disagrees with its source either way is a bug.
EXPECT = {
    "c_elegans_herm": {"n": 302, "gaps": True, "exporter": "celegans"},
    "c_elegans_male": {"n": 385, "gaps": True, "exporter": "celegans"},
    "ciona_larva": {"cns": (177, 5), "gaps": True, "exporter": "ciona"},
    "zebrafish_larva": {"gaps": False, "exporter": "fish1",
                        # Fish1 v704: 187,052 somas, of which 6,001 have no
                        # segment and 2,075 share a root id with another soma.
                        "n": 178976,
                        # brain-nuclei-v1 (PREREGISTRATION.md, Conventions
                        # adopted): four first-order brain nuclei, because the
                        # peripheral ganglia have almost no traced synapses.
                        "channels": {"pretectum", "tectum", "medial_vestibular",
                                     "tangential_vestibular"},
                        # The sets are the source's own MECE regions, but the
                        # join, the grouping and the signal assignment are
                        # ours. docs/fish1-mapping.md is normative and the
                        # package must carry the same statement, marked, or
                        # the page cannot warn the viewer.
                        "convention": "brain-nuclei-v1"},
}

checks = fails = skips = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        fails += 1


print("Species packages\n")
present = []
for sid, exp in EXPECT.items():
    d = os.path.join(ROOT, "web", "species", sid)
    print("== %s ==" % sid)
    if not os.path.exists(os.path.join(d, "connectome.bin")):
        skips += 1
        print("  SKIP  web/species/%s is absent -- run tools/%s_export.py or "
              "tools/export_%s.py with the raw data to check it"
              % (sid, exp["exporter"], exp["exporter"]))
        continue
    present.append(sid)
    raw = open(os.path.join(d, "connectome.bin"), "rb").read()
    ok(raw[:4] == b"OAS1", "magic is OAS1")
    n, nsyn, ngap = struct.unpack_from("<III", raw, 4)
    size = 16 + (n + 1) * 4 + nsyn * 6
    size += (-size) % 4
    size += ngap * 12
    ok(len(raw) == size, "file is exactly the size the header implies (%d bytes: "
       "n=%d, %d synapses, %d gap junctions)" % (len(raw), n, nsyn, ngap))
    bad = pk.check_package(d)
    for b in bad:
        print("        " + b)
    ok(not bad, "every invariant in package.check_package holds")
    meta = json.load(open(os.path.join(d, "brain.json")))
    ok(meta["species"] == sid, "brain.json names itself %s" % sid)
    if "n" in exp:
        ok(n == exp["n"], "%d neurons, as the paper says (%d)" % (n, exp["n"]))
    if "cns" in exp:
        want, tol = exp["cns"]
        got = meta["provenance"]["validation"]["cns_neurons"]["got"]
        ok(abs(got - want) <= tol, "%d CNS neurons, paper %d, tolerance %d" % (got, want, tol))
    ok(nsyn > 0, "has chemical synapses (%d)" % nsyn)
    ok((ngap > 0) == exp["gaps"],
       "gap junctions: %d, and the source %s release them"
       % (ngap, "does" if exp["gaps"] else "does not"))
    if not exp["gaps"]:
        ok(meta["params"]["w_gap"] == 0.0,
           "w_gap is 0 where there are no junctions to conduct")
        ok(bool(meta["provenance"].get("gap_junctions")),
           "provenance says why there are none, rather than leaving it blank")
    if "channels" in exp:
        ok(set(meta["sensory"]) == exp["channels"],
           "sensory channels are exactly %s" % sorted(exp["channels"]))
    if "convention" in exp:
        prov = meta["provenance"]
        ok(prov.get("convention") == exp["convention"],
           "records which convention it was built with (%r)" % prov.get("convention"))
        # The seat test in ROSTER.md turns on the viewer being told which part
        # of the mapping is the source's and which part is ours. If this
        # marker goes missing the page shows a convention as an annotation.
        ok(all("CONVENTION (not a source annotation)" in prov.get(k, "")
               for k in ("sensory", "motor")),
           "provenance.sensory and .motor both mark what is a convention")
        ok(os.path.exists(os.path.join(ROOT, prov.get("convention_doc", ""))),
           "the convention document it names exists (%s)" % prov.get("convention_doc"))
    cal = meta["params"]["calibrated"]
    ok((cal is False and meta["params"]["w_gap"] == 0.0)
       or (isinstance(cal, dict) and not pk.calibration_problems(meta["params"])),
       "params are untouched, or set by the preregistered rule and say so (%s)"
       % ("k=%d" % cal["k"] if isinstance(cal, dict) else "uncalibrated"))
    ok(isinstance(meta["provenance"]["dropped_unknown_sign"], int),
       "dropped_unknown_sign is recorded (%d)" % meta["provenance"]["dropped_unknown_sign"])
    motor = set(meta["motor"])
    sens = {i for v in meta["sensory"].values() for i in v}
    ok(not (motor & sens), "no neuron is both a sense and an order")

print("\n== the checker can fail (broken on purpose) ==")
if not present:
    skips += 1
    print("  SKIP  no package to break")
else:
    # The smallest present package: this copies the whole thing seven times,
    # and the fish is 60 MB of it.
    src = min((os.path.join(ROOT, "web", "species", s) for s in present),
              key=lambda d: os.path.getsize(os.path.join(d, "connectome.bin")))
    print("  (broken copies are made of %s)" % os.path.basename(src))
    with tempfile.TemporaryDirectory() as tmp:
        def broken(mutate_meta=None, mutate_bin=None):
            d = os.path.join(tmp, "x")
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(src, d)
            if mutate_meta:
                p = os.path.join(d, "brain.json")
                m = json.load(open(p))
                mutate_meta(m)
                json.dump(m, open(p, "w"))
            if mutate_bin:
                p = os.path.join(d, "connectome.bin")
                b = bytearray(open(p, "rb").read())
                mutate_bin(b)
                open(p, "wb").write(bytes(b))
            return pk.check_package(d)

        ok(broken() == [], "an unmodified copy passes")
        ok(broken(mutate_bin=lambda b: b.__setitem__(slice(0, 4), b"SFC1")),
           "a wrong magic is caught")

        def two_groups(m):
            g = m["groups"]["e"]
            g[1].append(g[0][0])
        ok(broken(two_groups), "a neuron in two groups of one module is caught")

        def empty_sense(m):
            k = next(iter(m["sensory"]))
            m["sensory"][k] = []
        ok(broken(empty_sense), "an empty sensory channel is caught")

        def out_of_range(b):
            n = struct.unpack_from("<I", b, 4)[0]
            off = 16 + (n + 1) * 4          # first postsynaptic index
            struct.pack_into("<I", b, off, n + 7)
        ok(broken(mutate_bin=out_of_range), "a postsynaptic index past the end is caught")

        def truncate(b):
            del b[-4:]
        ok(broken(mutate_bin=truncate), "a truncated file is caught")

print("\n%d checks, %d failed, %d skipped" % (checks, fails, skips))
if skips:
    print("(a skip is not a pass: %d package(s) were not checked in this run)" % skips)
sys.exit(1 if fails else 0)
