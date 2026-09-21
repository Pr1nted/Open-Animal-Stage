"""The first-instar Drosophila larva brain, Winding et al. (2023), into OAS1.

    .venv/bin/python tools/export_larva.py [--out web/species/drosophila_larva]

Downloads (once) into data/raw/winding2023/, which is gitignored:

  Supplementary-Data-S1.zip   the paper's Data S1: the 2,952 x 2,952 summed
                              connectivity matrix (all-all, rows presynaptic),
                              its aa/ad/da/dd parts, and annotations.csv
                              (cell type, sensory modality, left/right pairs).
                              Mirrored by the Betzel lab on GitHub, because the
                              Science supplement is behind a publisher page.
  catmaid/nt_*.json           neurotransmitter identities. Data S1 carries none,
                              so they are read from the paper's own public
                              CATMAID project (Virtual Fly Brain, "L1 CNS"): the
                              annotations meta-annotated 'mw neurotransmitter'
                              by the first author. Anonymous, read-only API.

THE SIGN RULE is the FlyWire rule (tools/fly_oas1.py): GABA and glutamate
inhibit, acetylcholine, dopamine and octopamine excite. 'mw GABAergic and
glutamatergic' is inhibitory either way. 'mw cholinergic and glutamatergic'
contradicts itself and is UNKNOWN. Every other neuron is UNKNOWN, and every
synapse it makes is dropped and counted -- which, for this dataset, is most of
them. That is reported, not repaired.

Nothing here is tuned. calibrated is false: no published simulation of this
connectome exists to match.
"""
import argparse
import http.cookiejar
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fly_oas1 as oas  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw", "winding2023")
S1_URL = ("https://github.com/brain-networks/larval-drosophila-connectome/raw/main/"
          "Supplementary-Data-S1.zip")
S1_SHA256 = "8c1f43809ed5d527ba61b154e377cc21da26383a75eda8aab85ce05607a72a4c"
CATMAID = "https://l1em.catmaid.virtualflybrain.org/"
PROJECT = 1

# CATMAID annotation id -> (name, sign). Ids are stable in a CATMAID project;
# the name is checked against the server's so a renumbering cannot slip past.
NT_ANNOTATIONS = {
    22265070: ("mw cholinergic", 1),
    22265077: ("mw GABAergic", -1),
    22265088: ("mw glutamatergic", -1),
    22265128: ("mw GABAergic and glutamatergic", -1),
    22265488: ("mw cholinergic and glutamatergic", 0),   # contradicts itself: UNKNOWN
    22274404: ("mw dopaminergic", 1),
    22274419: ("mw octopaminergic", 1),
}

# Winding et al.'s own sensory modality annotations (annotations.csv,
# additional_annotations), one per game signal. Why each:
#   olfactory  -> reward   ORNs. Larvae approach most odorants their Or
#                          repertoire detects; the gustatory classes in the data
#                          mix sweet and bitter receptors under one label, so
#                          they cannot carry one valence.
#   noci       -> harm     the nociceptive modality (ascending in this dataset:
#                          the brain receives it from A1).
#   gut        -> reserve  enteric/gut sensory neurons: the dataset's
#                          interoceptive, homeostatic sense.
#   mechano-Ch -> threat   chordotonal mechanosensation (vibration), the
#                          larval homologue of Johnston's organ, which is itself
#                          a chordotonal organ.
SENSES = {"olfactory": "reward", "noci": "harm", "gut": "reserve", "mechano-Ch": "threat"}

# Brain outputs as the paper classifies them: dVNC and dSEZ. Ring-gland
# neurons (RGN) are also outputs but neuroendocrine, not motor, and are left out.
MOTOR_CLASSES = ("DN-VNC", "DN-SEZ")

PAPER = {"neurons": 3016, "synapses": 548000}


def fetch(url, path, data=None, opener=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with (opener or urllib.request.build_opener()).open(req, timeout=300) as r:
        body = r.read()
    with open(path, "wb") as f:
        f.write(body)
    return body


def get_s1():
    os.makedirs(RAW, exist_ok=True)
    z = os.path.join(RAW, "Supplementary-Data-S1.zip")
    if not os.path.exists(z):
        print("downloading", S1_URL)
        fetch(S1_URL, z)
    got = oas.sha256(z)
    if got != S1_SHA256:
        raise SystemExit("Data S1 sha256 %s, expected %s" % (got, S1_SHA256))
    d = os.path.join(RAW, "Supplementary-Data-S1")
    if not os.path.exists(os.path.join(d, "all-all_connectivity_matrix.csv")):
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():
                if m.startswith("Supplementary-Data-S1/") and m.endswith(".csv"):
                    zf.extract(m, RAW)
    return d, got


def get_nt():
    """{annotation id: [skeleton ids]} from the public CATMAID, cached."""
    d = os.path.join(RAW, "catmaid")
    os.makedirs(d, exist_ok=True)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    out, shas = {}, {}
    # The annotation list: to check each id still carries the name we expect.
    ann_path = os.path.join(d, "annotations.json")
    if not os.path.exists(ann_path):
        fetch(CATMAID + "%d/annotations/" % PROJECT, ann_path, opener=opener)
    names = {a["id"]: a["name"] for a in json.load(open(ann_path))["annotations"]}
    shas["annotations.json"] = oas.sha256(ann_path)
    for aid, (name, _) in NT_ANNOTATIONS.items():
        if names.get(aid) != name:
            raise SystemExit("CATMAID annotation %d is %r, expected %r" % (aid, names.get(aid), name))
        p = os.path.join(d, "nt_%d.json" % aid)
        if not os.path.exists(p):
            if not any(c.name.startswith("csrftoken") for c in jar):
                opener.open(CATMAID, timeout=120).read()
            tok = next(c.value for c in jar if c.name.startswith("csrftoken"))
            body = urllib.parse.urlencode([("annotated_with", aid), ("types", "neuron")]).encode()
            fetch(CATMAID + "%d/annotations/query-targets" % PROJECT, p, data=body, opener=opener,
                  headers={"X-CSRFToken": tok, "Referer": CATMAID})
        ents = json.load(open(p))["entities"]
        out[aid] = [int(s) for e in ents for s in e["skeleton_ids"]]
        shas[os.path.basename(p)] = oas.sha256(p)
    return out, shas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "species", "drosophila_larva"))
    ap.add_argument("--unsigned", choices=["drop", "sensory-cholinergic", "all-cholinergic"],
                    default="drop",
                    help="what to do with a neuron the source gives no transmitter for. "
                         "drop: use only published signs (89%% of the wiring goes). "
                         "sensory-cholinergic / all-cholinergic: assume cholinergic, which is "
                         "OUR convention and is recorded as one. See PREREGISTRATION.md.")
    args = ap.parse_args()

    s1, s1_sha = get_s1()
    nt, nt_sha = get_nt()

    A = pd.read_csv(os.path.join(s1, "all-all_connectivity_matrix.csv"), index_col=0)
    skids = [int(x) for x in A.index]
    if [int(x) for x in A.columns] != skids:
        raise SystemExit("matrix rows and columns are not the same neurons in the same order")
    W = A.to_numpy()
    if (W < 0).any() or (W != np.round(W)).any():
        raise SystemExit("the matrix is not non-negative synapse counts")
    W = W.astype(np.int64)
    parts = np.zeros_like(W)
    for k in ("aa", "ad", "da", "dd"):
        P = pd.read_csv(os.path.join(s1, "%s_connectivity_matrix.csv" % k), index_col=0)
        P.index = P.index.astype(int)
        P.columns = P.columns.astype(int)
        parts += P.reindex(index=skids, columns=skids).fillna(0).to_numpy().astype(np.int64)
    all_is_sum = bool((parts == W).all())
    n = len(skids)
    index = {s: i for i, s in enumerate(skids)}

    # Signs.
    votes = {}
    for aid, sks in nt.items():
        for s in sks:
            votes.setdefault(s, set()).add(NT_ANNOTATIONS[aid][1])
    sign = np.zeros(n, np.int64)
    for s, v in votes.items():
        if s in index and len(v) == 1:
            sign[index[s]] = next(iter(v))
    labelled = {name: len(set(sks) & set(index)) for aid, (name, _) in NT_ANNOTATIONS.items()
                for sks in [nt[aid]]}

    # Annotations: pairs, cell types, modalities.
    ann = pd.read_csv(os.path.join(s1, "annotations.csv"), dtype=str)

    def ids(row):
        return [int(row[c]) for c in ("left_id", "right_id") if row[c] != "no pair" and int(row[c]) in index]

    sensory = {}
    for ch in SENSES:
        rows = ann[ann["additional_annotations"] == ch]
        sensory[ch] = sorted(index[s] for _, r in rows.iterrows() for s in ids(r))
    # ── A CONVENTION, NOT AN ANNOTATION ──
    #
    # Only 243 of 2,952 neurons have a published transmitter, so under the
    # drop-unknown rule 89% of the wiring goes and three of the four senses
    # reach no neuron at all: the larva loads, plays, and holds every turn,
    # which reads as an animal with nothing to say rather than as missing data.
    # Insect sensory neurons are overwhelmingly cholinergic (excitatory), so
    # --unsigned sensory-cholinergic assumes that for the annotated sensory
    # neurons ONLY, and all-cholinergic assumes it for every unannotated
    # neuron. Both are OUR claim, not the source's. Whichever is used is named
    # in provenance.signs, beginning with the word CONVENTION, and the page
    # shows it as a warning beside that animal.
    sens_ids = sorted({i for v in sensory.values() for i in v})
    assumed = 0
    if args.unsigned != "drop":
        target = sens_ids if args.unsigned == "sensory-cholinergic" else range(n)
        for i in target:
            if sign[i] == 0:
                sign[i] = 1
                assumed += 1

    pre, post = np.nonzero(W)
    cnt = W[pre, post]
    keep = sign[pre] != 0
    dropped_edges = int((~keep).sum())
    dropped_syn = int(cnt[~keep].sum())
    indptr, post_s, count_s = oas.csr(n, pre[keep], post[keep], cnt[keep] * sign[pre[keep]])

    units = []
    for _, r in ann[ann["celltype"].isin(MOTOR_CLASSES)].sort_values(["celltype", "left_id", "right_id"]).iterrows():
        u = sorted(index[s] for s in ids(r))
        if u:
            units.append(u)
    flat = [i for u in units for i in u]
    if len(flat) != len(set(flat)):
        raise SystemExit("a descending neuron is in two annotation rows")
    groups = oas.make_groups(units, oas.PARTITION_SEED)
    motor = sorted(flat)
    by_class = {c: int(sum(len(ids(r)) for _, r in ann[ann["celltype"] == c].iterrows())) for c in MOTOR_CLASSES}

    os.makedirs(args.out, exist_ok=True)
    out_bin = os.path.join(args.out, "connectome.bin")
    size_bin = oas.write_connectome(out_bin, n, indptr, post_s, count_s)
    total_syn = int(W.sum())
    meta = {
        "species": "drosophila_larva",
        "dataset": "Winding et al. (2023)", "version": "Science 379:eadd9330, Data S1",
        "n": n, "names": [str(s) for s in skids],
        "params": dict(oas.PARAMS), "calibrated": False,
        "sensory": sensory, "senses": SENSES,
        "groups": oas.groups_json(groups), "motor": motor,
        "partition_seed": oas.PARTITION_SEED, "window_ms": oas.WINDOW_MS,
        "provenance": {
            "neurons": "Data S1 all-all_connectivity_matrix.csv, the paper's 2,952 analysed "
                       "brain neurons (of 3,016 reconstructed); names are CATMAID skeleton ids "
                       "in the public L1 CNS project",
            "synapses": "all-all matrix, rows presynaptic (axon and dendrite inputs and "
                        "outputs summed); %d synapses on %d edges; all-all equals aa+ad+da+dd: %s"
                        % (total_syn, int(len(cnt)), all_is_sum),
            "convention": None if args.unsigned == "drop" else (
                "CONVENTION (not a source annotation): a neuron the source gives no "
                "transmitter for is treated as cholinergic (excitatory), for %s. "
                "Insect sensory neurons are overwhelmingly cholinergic; this is our claim, "
                "not Winding et al.'s. %d neurons were signed this way."
                % ("the annotated sensory neurons only" if args.unsigned == "sensory-cholinergic"
                   else "every unannotated neuron", assumed)),
            "unsigned_rule": args.unsigned,
            "signs": "FlyWire rule on the CATMAID 'mw neurotransmitter' annotations: "
                     "GABAergic, glutamatergic, GABAergic-and-glutamatergic -1; cholinergic, "
                     "dopaminergic, octopaminergic +1; cholinergic-and-glutamatergic and every "
                     "unannotated neuron UNKNOWN, dropped. %d of %d neurons signed"
                     % (int((sign != 0).sum()), n),
            "signed_neurons": {"total": int((sign != 0).sum()), "excitatory": int((sign > 0).sum()),
                               "inhibitory": int((sign < 0).sum()), "by_annotation": labelled},
            "sensory": "annotations.csv additional_annotations, both sides: olfactory (ORNs) "
                       "reward; noci harm; gut reserve; mechano-Ch (chordotonal) threat. "
                       "Reasons in tools/export_larva.py",
            "motor": "annotations.csv celltype DN-VNC (%d) + DN-SEZ (%d) = %d descending "
                     "neurons, left/right pairs dealt together as units into 39 groups, "
                     "seed 783" % (by_class["DN-VNC"], by_class["DN-SEZ"], len(motor)),
            "params": "Shiu et al. (2024) adult-fly constants, unchanged and uncalibrated for "
                      "the larva",
            "licence": "Winding et al. 2023, Science 379:eadd9330, Data S1 (supplementary "
                       "material; no open licence stated: cite the paper, do not "
                       "redistribute the export until cleared). CATMAID annotations from the "
                       "public Virtual Fly Brain L1 CNS project; cite Winding et al. 2023",
            "source": {
                "data_s1": {"url": S1_URL, "sha256": s1_sha},
                "catmaid": {"url": CATMAID, "project": PROJECT,
                            "endpoint": "annotations/query-targets", "sha256": nt_sha},
            },
            "paper": PAPER,
            "dropped_unknown_sign": dropped_edges,
            "dropped_unknown_sign_synapses": dropped_syn,
        },
    }
    oas.validate(n, indptr, post_s, count_s, meta)
    out_json = os.path.join(args.out, "brain.json")
    size_json = oas.write_brain_json(out_json, meta)
    n2, ip2, post2, cnt2, *_ = oas.read_connectome(out_bin)
    oas.validate(n2, ip2, post2, cnt2, json.load(open(out_json)))

    print("drosophila_larva -> %s" % args.out)
    reach = oas.report(meta, ip2, cnt2, size_bin, size_json)
    print("  vs paper          neurons %d/%d, synapses %d/%d (matrix total)"
          % (n, PAPER["neurons"], total_syn, PAPER["synapses"]))
    print("  signed neurons    %d/%d (%.1f%%): %s" % ((sign != 0).sum(), n, 100.0 * (sign != 0).sum() / n, labelled))
    print("  dropped           %d of %d edges (%.1f%%), %d of %d synapses (%.1f%%)"
          % (dropped_edges, len(cnt), 100.0 * dropped_edges / len(cnt),
             dropped_syn, total_syn, 100.0 * dropped_syn / total_syn))
    print("  all-all == aa+ad+da+dd: %s" % all_is_sum)
    silent = [ch for ch, r in reach.items() if r == 0]
    if silent:
        print("  WARNING: sensory channel(s) %s have no signed outgoing synapse: under the "
              "drop rule the signal reaches no neuron" % silent)
    in_signed = int(np.isin(motor, np.unique(np.asarray(post_s))).sum())
    print("  descending neurons with any signed input: %d/%d" % (in_signed, len(motor)))
    oas.pack_if_large(out_bin)


if __name__ == "__main__":
    main()
