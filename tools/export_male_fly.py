"""The adult male fly, MaleCNS v1.0 (FlyEM, Janelia; CC-BY 4.0), into OAS1.

    .venv/bin/python tools/export_male_fly.py [--out web/species/drosophila_male]

No token. The flat connectome is in a public bucket, read over plain HTTPS
(gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/, listed at
https://male-cns.janelia.org/download/). Downloads land in
data/raw/malecns_v1.0/, gitignored:

  body-annotations-male-cns-v1.0-minconf-0.5.feather     14 MB
  body-neurotransmitters-male-cns-v1.0.feather           43 MB
  connectome-weights-male-cns-v1.0-minconf-0.5.feather   1.05 GB

THE POINT OF THIS EXPORT is that it is the female's mapping on the male brain,
so every choice below is the female's choice, restated in MaleCNS's names:

  neurons   every body the release gives a superclass (its neuron annotation).
  signs     the FlyWire rule (tools/fly_oas1.py) on `consensus_nt`, the
            release's per-neuron call. 'unclear', no call, and histamine --
            which FlyWire never predicts, so the rule has no answer for it --
            are UNKNOWN and their synapses dropped and counted.
  sugar     left labellar LB3b + LB3c, the Gr64f (sweet) types
  water     left labellar LB3a, the ppk28 (water) type
  bitter    left labellar LB1a-d, the Gr33a (bitter) types
            -- receptor identities from Tastekin et al., "The Comprehensive
            Drosophila Taste-Feeding Connectome" (bioRxiv 10.1101/2025.08.25.
            671814; Cell 2026), which names the MaleCNS GRN types. The female's
            FlyWire lists are LB3 (sugar), LB3 + one LB2d (water), LB1a-d
            (bitter), left side; FlyWire does not split LB3, MaleCNS does.
  jon       left Johnston's organ bodies whose `flywireType` is one of the
            FlyWire types in the female's list.
  motor     superclass 'descending_neuron', whole cell types (`type`, else
            `hemibrainType`, else the body) dealt into 39 groups by Open Fly's
            make_groups with seed 783 -- the female's rule, line for line.

calibrated is false and nothing is tuned: these are Shiu et al.'s constants,
fitted to the female.
"""
import argparse
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as pf
import pyarrow.ipc as ipc

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fly_oas1 as oas  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw", "malecns_v1.0")
BUCKET = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
GS = "gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/"
FILES = {
    "annotations": ("body-annotations-male-cns-v1.0-minconf-0.5.feather",
                    "2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2"),
    "neurotransmitters": ("body-neurotransmitters-male-cns-v1.0.feather",
                          "95c9289220663abeb3409f3ad9e5a7f8a53f8093f5139d15502cd08da8879621"),
    "weights": ("connectome-weights-male-cns-v1.0-minconf-0.5.feather",
                "e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1"),
}
NT_COLUMN = "consensus_nt"

GRN_TYPES = {
    "sugar": ["LB3b", "LB3c"],
    "bitter": ["LB1a", "LB1b", "LB1c", "LB1d"],
    "water": ["LB3a"],
}
# The FlyWire cell types of the female's 145 Johnston's organ neurons
# (Open Fly's sensory_ids.json 'jon', looked up in FlyWire 783's annotations).
FEMALE_JO_TYPES = ["JO-CA1", "JO-CA2", "JO-CL", "JO-CM", "JO-DA", "JO-DP", "JO-ED1",
                   "JO-ED2_a", "JO-ED2_b", "JO-ED2_c", "JO-EV1", "JO-EV2", "JO-EV3",
                   "JO-EV4", "JO-EV5", "JO-EV6", "JO-FD1", "JO-FD2", "JO-FV", "JO-mz",
                   "JO-unclear"]
SIDE = "L"          # the female's lists are all left-side neurons
SENSES = {"sugar": "reward", "bitter": "harm", "water": "reserve", "jon": "threat"}
FEMALE_COUNTS = {"sugar": 20, "bitter": 20, "water": 18, "jon": 145, "descending": 1299}
PAPER = {"neurons": 166691, "cell_types": 11691}


def get(name, sha):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        print("downloading", BUCKET + name)
        tmp = p + ".part"
        with urllib.request.urlopen(BUCKET + name, timeout=600) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 24)
                if not b:
                    break
                f.write(b)
        os.replace(tmp, p)
    got = oas.sha256(p)
    if got != sha:
        raise SystemExit("%s sha256 %s, expected %s" % (name, got, sha))
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "species", "drosophila_male"))
    args = ap.parse_args()
    paths = {k: get(*v) for k, v in FILES.items()}

    ann = pd.read_feather(paths["annotations"])
    if ann["bodyId"].duplicated().any():
        raise SystemExit("duplicate bodyIds in the annotations")
    neu = ann[ann["superclass"].notna()].sort_values("bodyId").reset_index(drop=True)
    body = neu["bodyId"].to_numpy(np.int64)
    n = len(body)

    nt = pd.read_feather(paths["neurotransmitters"], columns=["body", NT_COLUMN, "predicted_nt"])
    nt = nt.drop_duplicates("body").set_index("body").reindex(body)
    call = nt[NT_COLUMN].fillna("<none>").to_numpy().astype(str)
    sign = np.array([oas.FLYWIRE_RULE.get(c, 0) for c in call], np.int64)
    nt_counts = pd.Series(call).value_counts().to_dict()
    alt = np.array([oas.FLYWIRE_RULE.get(c, 0) for c in nt["predicted_nt"].fillna("<none>").astype(str)])

    # Edges between neurons, streamed out of the 1 GB table.
    bodies = pa.array(body)
    pre_l, post_l, w_l = [], [], []
    total_rows = total_w = 0
    with pa.memory_map(paths["weights"]) as src:
        reader = ipc.open_file(src)
        for k in range(reader.num_record_batches):
            b = reader.get_batch(k)
            total_rows += b.num_rows
            total_w += pc.sum(b.column("weight")).as_py() or 0
            m = pc.and_(pc.is_in(b.column("body_pre"), bodies), pc.is_in(b.column("body_post"), bodies))
            f = b.filter(m)
            pre_l.append(f.column("body_pre").to_numpy())
            post_l.append(f.column("body_post").to_numpy())
            w_l.append(f.column("weight").to_numpy())
    pre = np.searchsorted(body, np.concatenate(pre_l))
    post = np.searchsorted(body, np.concatenate(post_l))
    w = np.concatenate(w_l).astype(np.int64)
    del pre_l, post_l, w_l
    if (w <= 0).any():
        raise SystemExit("non-positive weights in the table")
    self_loops = int((pre == post).sum())
    keep = sign[pre] != 0
    dropped_edges = int((~keep).sum())
    dropped_syn = int(w[~keep].sum())
    alt_dropped = int((alt[pre] == 0).sum())
    edges_all, syn_all = len(w), int(w.sum())
    indptr, post_s, count_s = oas.csr(n, pre[keep], post[keep], w[keep] * sign[pre[keep]])
    del pre, post, w, keep

    # Senses.
    left = neu["rootSide"].eq(SIDE).to_numpy()
    typ = neu["type"].fillna("").to_numpy().astype(str)
    fwt = neu["flywireType"].fillna("").to_numpy().astype(str)
    sensory = {}
    for ch, types in GRN_TYPES.items():
        sensory[ch] = [int(i) for i in np.nonzero(left & np.isin(typ, types))[0]]
    sensory["jon"] = [int(i) for i in np.nonzero(left & np.isin(fwt, FEMALE_JO_TYPES))[0]]
    jo_matched = sorted(set(fwt[sensory["jon"]]))
    jo_unmatched = [t for t in FEMALE_JO_TYPES if t not in jo_matched]
    jo_left_no_fw = int((left & pd.Series(typ).str.startswith("JO-").to_numpy() & (fwt == "")).sum())

    # Motor.
    dn = neu[neu["superclass"] == "descending_neuron"]
    units = {}
    for i, r in dn.iterrows():
        key = r["type"] if isinstance(r["type"], str) and r["type"] else \
            (r["hemibrainType"] if isinstance(r["hemibrainType"], str) and r["hemibrainType"]
             else "body:%d" % r["bodyId"])
        units.setdefault(key, []).append(int(i))
    groups = oas.make_groups([sorted(units[k]) for k in sorted(units)], oas.PARTITION_SEED)
    motor = sorted(i for u in units.values() for i in u)
    n_dn_tbc = int((neu["superclass"] == "descending_neuron_tbc").sum())
    n_sens_desc = int((neu["superclass"] == "sensory_descending").sum())

    os.makedirs(args.out, exist_ok=True)
    out_bin = os.path.join(args.out, "connectome.bin")
    size_bin = oas.write_connectome(out_bin, n, indptr, post_s, count_s)
    meta = {
        "species": "drosophila_male",
        "dataset": "MaleCNS v1.0", "version": "v1.0 flat connectome, minconf 0.5",
        "n": n, "names": [str(b) for b in body],
        "params": dict(oas.PARAMS), "calibrated": False,
        "sensory": sensory, "senses": SENSES,
        "groups": oas.groups_json(groups), "motor": motor,
        "partition_seed": oas.PARTITION_SEED, "window_ms": oas.WINDOW_MS,
        "provenance": {
            "neurons": "every body with a superclass in body-annotations (the release's "
                       "neuron annotation), sorted by bodyId; names are bodyIds. %d, "
                       "against 166,691 announced" % n,
            "synapses": "connectome-weights minconf 0.5, both ends neurons: %d edges, %d "
                        "synapses (%d self-loops kept, as FlyWire's table keeps them); whole "
                        "table %d rows, %d synapses" % (edges_all, syn_all, self_loops,
                                                         total_rows, total_w),
            "signs": "FlyWire rule on body-neurotransmitters `%s`: gaba, glutamate -1; "
                     "acetylcholine, dopamine, serotonin, octopamine +1; histamine, "
                     "unclear, none UNKNOWN and dropped" % NT_COLUMN,
            "nt_calls": {k: int(v) for k, v in nt_counts.items()},
            "sensory": "left (rootSide L) labellar GRNs by MaleCNS type with receptor "
                       "identity from Tastekin et al. (bioRxiv 10.1101/2025.08.25.671814): "
                       "sugar LB3b+LB3c (Gr64f), water LB3a (ppk28), bitter LB1a-d (Gr33a); "
                       "jon: left bodies whose flywireType is one of the female list's "
                       "FlyWire JO types",
            "sensory_unmatched": {
                "jon_flywire_types_absent_on_left": jo_unmatched,
                "left_JO_bodies_with_no_flywireType": jo_left_no_fw,
                "water_LB2d": "the female's water list has one LB2d; no receptor identity "
                              "for LB2d is published, so the male's water is LB3a alone",
                "female_counts": FEMALE_COUNTS,
            },
            "motor": "superclass descending_neuron, %d neurons in %d cell types, dealt into "
                     "39 groups by Open Fly's make_groups, seed 783. Left out: "
                     "descending_neuron_tbc (%d), sensory_descending (%d)"
                     % (len(motor), len(units), n_dn_tbc, n_sens_desc),
            "params": "Shiu et al. (2024) constants, fitted to the female; not tuned here",
            "licence": "MaleCNS v1.0, FlyEM / HHMI Janelia, CC-BY 4.0 "
                       "(https://creativecommons.org/licenses/by/4.0/); cite the MaleCNS "
                       "release (https://male-cns.janelia.org/)",
            "source": {k: {"url": BUCKET + v[0], "gs": GS + v[0], "sha256": v[1]}
                       for k, v in FILES.items()},
            "paper": PAPER,
            "dropped_unknown_sign": dropped_edges,
            "dropped_unknown_sign_synapses": dropped_syn,
            "dropped_if_predicted_nt": alt_dropped,
        },
    }
    oas.validate(n, indptr, post_s, count_s, meta)
    out_json = os.path.join(args.out, "brain.json")
    size_json = oas.write_brain_json(out_json, meta)
    n2, ip2, post2, cnt2, *_ = oas.read_connectome(out_bin)
    oas.validate(n2, ip2, post2, cnt2, json.load(open(out_json)))

    print("drosophila_male -> %s" % args.out)
    oas.report(meta, ip2, cnt2, size_bin, size_json)
    print("  vs release        neurons %d/%d, types among neurons %d/%d"
          % (n, PAPER["neurons"], neu["type"].nunique(), PAPER["cell_types"]))
    print("  edges             %d between neurons (%d synapses); table %d rows (%d synapses)"
          % (edges_all, syn_all, total_rows, total_w))
    print("  dropped           %d of %d edges (%.1f%%), %d synapses (%.1f%%); with predicted_nt: %d edges"
          % (dropped_edges, edges_all, 100.0 * dropped_edges / edges_all, dropped_syn,
             100.0 * dropped_syn / syn_all, alt_dropped))
    print("  nt calls          %s" % nt_counts)
    print("  vs female         sugar %d/20 bitter %d/20 water %d/18 jon %d/145 dn %d/1299"
          % (len(sensory["sugar"]), len(sensory["bitter"]), len(sensory["water"]),
             len(sensory["jon"]), len(motor)))
    print("  JO types unmatched on the left: %s; left JO bodies with no flywireType: %d"
          % (jo_unmatched, jo_left_no_fw))
    print("  DN units %d; left out: descending_neuron_tbc %d, sensory_descending %d"
          % (len(units), n_dn_tbc, n_sens_desc))
    oas.pack_if_large(out_bin)


if __name__ == "__main__":
    main()
