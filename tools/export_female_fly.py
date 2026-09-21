"""The adult female fly, re-encoded from Open Fly's own web export into OAS1.

    .venv/bin/python tools/export_female_fly.py
        [--open-fly ~/CLionProjects/Open-Fly] [--fly-data ~/.open_fly/fly]
        [--out web/species/drosophila_female]

Reads IN PLACE, never copies into this repository:
  <open-fly>/web/data/connectome.bin   SFC1 (web/brain.js): n, nsyn, indptr,
                                       post, signed int16 count
  <open-fly>/web/data/brain.json       the 39 groups, 4 sensory channels, params
  <fly-data>/Completeness_783.csv      the FlyWire root ids, in brain-index
                                       order -- Open Fly's brain.json carries
                                       indices only, and OAS1 wants names
  <fly-data>/neuron_annotations.tsv    optional: re-deals the groups with the
                                       copied make_groups and requires the
                                       result to equal Open Fly's

Nothing is re-derived that Open Fly already decided: the synapses are the same
bytes behind a new header, and the groups and sensory channels are Open Fly's
lists, not recomputed ones. The only new decision is the `senses` block, which
is Open Fly's own mapping written down (docs/species-format.md).
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fly_oas1 as oas  # noqa: E402

HOME = os.path.expanduser("~")
SENSES = {"sugar": "reward", "bitter": "harm", "water": "reserve", "jon": "threat"}
PAPER = {"neurons": 138639, "connections": 15091983}   # FlyWire 783 as Shiu et al. ship it


def read_sfc1(path):
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    if bytes(raw[:4]) != b"SFC1":
        raise SystemExit("%s is not SFC1" % path)
    n, nsyn = struct.unpack("<II", bytes(raw[4:12]))
    off = 12
    indptr = raw[off:off + (n + 1) * 4].view("<u4"); off += (n + 1) * 4
    post = raw[off:off + nsyn * 4].view("<u4"); off += nsyn * 4
    count = raw[off:off + nsyn * 2].view("<i2"); off += nsyn * 2
    if off != len(raw):
        raise SystemExit("SFC1 layout says %d bytes, file has %d" % (off, len(raw)))
    return n, indptr, post, count


def regroup(tsv, flyids):
    """Open Fly's descending_units, then the copied make_groups."""
    import csv
    index = {f: i for i, f in enumerate(flyids)}
    units = {}
    with open(tsv, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["super_class"] != "descending":
                continue
            i = index.get(row["root_id"])
            if i is None:
                continue
            key = row["cell_type"] or row["hemibrain_type"] or ("root:" + row["root_id"])
            units.setdefault(key, []).append(i)
    return oas.make_groups([sorted(units[k]) for k in sorted(units)], oas.PARTITION_SEED)


def tilde(p):
    return p.replace(HOME, "~", 1) if p.startswith(HOME) else p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-fly", default=os.path.join(HOME, "CLionProjects", "Open-Fly"))
    ap.add_argument("--fly-data", default=os.path.join(HOME, ".open_fly", "fly"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(HERE), "web", "species", "drosophila_female"))
    args = ap.parse_args()

    src_bin = os.path.join(args.open_fly, "web", "data", "connectome.bin")
    src_json = os.path.join(args.open_fly, "web", "data", "brain.json")
    comp_csv = os.path.join(args.fly_data, "Completeness_783.csv")
    tsv = os.path.join(args.fly_data, "neuron_annotations.tsv")
    for p in (src_bin, src_json, comp_csv):
        if not os.path.exists(p):
            raise SystemExit("missing %s" % p)

    n, indptr, post, count = read_sfc1(src_bin)
    ofly = json.load(open(src_json))
    flyids = []
    with open(comp_csv) as f:
        next(f)
        for line in f:
            flyids.append(line.split(",", 1)[0].strip())
    if len(flyids) != n or ofly["n"] != n:
        raise SystemExit("neuron counts disagree: bin %d, brain.json %d, csv %d" % (n, ofly["n"], len(flyids)))

    # The groups are Open Fly's, taken as shipped. Re-dealing them here is a
    # check on the copied make_groups, not a source of them.
    groups = {m: [[int(i) for i in g] for g in ofly["groups"][m]] for m in oas.MODULES}
    regrouped = None
    if os.path.exists(tsv):
        regrouped = oas.groups_json(regroup(tsv, flyids)) == groups
        if not regrouped:
            raise SystemExit("the copied make_groups does not reproduce Open Fly's groups")
    motor = sorted({i for m in oas.MODULES for g in groups[m] for i in g})
    if motor != sorted(ofly["dn"]):
        raise SystemExit("Open Fly's dn list is not the union of its groups")

    sensory = {ch: [int(i) for i in ofly["sensory"][ch]] for ch in SENSES}
    pos = {f: i for i, f in enumerate(flyids)}
    sids = json.load(open(os.path.join(args.open_fly, "open_fly", "sensory_ids.json")))
    for ch in SENSES:
        want = [pos[f] for f in sids[ch] if f in pos]
        if want != sensory[ch]:
            raise SystemExit("sensory channel %s is not sensory_ids.json in v783" % ch)

    params = dict(oas.PARAMS)
    for k, v in ofly["params"].items():
        if params[k] != v:
            raise SystemExit("Open Fly's %s is %r, not the Shiu constant %r" % (k, v, params[k]))

    os.makedirs(args.out, exist_ok=True)
    out_bin = os.path.join(args.out, "connectome.bin")
    size_bin = oas.write_connectome(out_bin, n, indptr, post, count)

    meta = {
        "species": "drosophila_female",
        "dataset": "FlyWire / FAFB", "version": "783 (Shiu et al. 2024 Connectivity_783)",
        "n": n, "names": flyids, "params": params,
        "calibrated": True,
        "sensory": sensory, "senses": SENSES,
        "groups": groups, "motor": motor,
        "partition_seed": oas.PARTITION_SEED, "window_ms": oas.WINDOW_MS,
        "provenance": {
            "neurons": "FlyWire public release 783, in Completeness_783.csv order "
                       "(Shiu et al. 2024); names are FlyWire root ids",
            "signs": "Shiu et al. (2024) Connectivity_783 'Excitatory x Connectivity': "
                     "GABA and glutamate negative; acetylcholine, dopamine, serotonin, "
                     "octopamine positive (FlyWire neurotransmitter predictions)",
            "sensory": "Open Fly open_fly/sensory_ids.json: Shiu et al.'s notebook lists, "
                       "left labellum GRNs (sugar: LB3; bitter: LB1a-d; water: LB3 + LB2d) "
                       "and left Johnston's organ (jon: JO-C/D/E/F types, JO-mz)",
            "motor": "FlyWire super_class 'descending' (neuron_annotations.tsv), whole "
                     "cell types dealt into 39 groups by Open Fly's make_groups, seed 783; "
                     "%d neurons" % len(motor),
            "params": "Shiu et al. (2024), unchanged; calibrated: Open Fly matches the "
                      "published Brian2 model spike for spike",
            "licence": "FlyWire data CC BY-NC 4.0 (https://flywire.ai/guidelines); "
                       "model MIT (philshiu/Drosophila_brain_model)",
            "source": {
                "connectome": {"path": tilde(src_bin), "format": "SFC1", "sha256": oas.sha256(src_bin)},
                "brain_json": {"path": tilde(src_json), "sha256": oas.sha256(src_json)},
                "names": {"path": tilde(comp_csv), "sha256": oas.sha256(comp_csv)},
                "upstream": "https://github.com/philshiu/Drosophila_brain_model (Connectivity_783.parquet, "
                            "Completeness_783.csv)",
            },
            "groups_redealt_and_equal": regrouped,
            "paper": PAPER,
            "dropped_unknown_sign": 0,
        },
    }
    out_json = os.path.join(args.out, "brain.json")
    oas.validate(n, indptr, post, count, meta)
    size_json = oas.write_brain_json(out_json, meta)

    # Read back what was written and validate THAT, not the arrays in memory.
    n2, ip2, post2, cnt2, *_ = oas.read_connectome(out_bin)
    oas.validate(n2, ip2, post2, cnt2, json.load(open(out_json)))
    if not (np.array_equal(ip2, indptr) and np.array_equal(post2, post) and np.array_equal(cnt2, count)):
        raise SystemExit("OAS1 body differs from the SFC1 body it was copied from")

    print("drosophila_female -> %s" % args.out)
    oas.report(meta, ip2, cnt2, size_bin, size_json)
    print("  vs paper          neurons %d/%d, connections %d/%d"
          % (n, PAPER["neurons"], len(post), PAPER["connections"]))
    print("  groups re-dealt from annotations and equal to Open Fly's: %s" % regrouped)
    oas.pack_if_large(out_bin)


if __name__ == "__main__":
    main()
