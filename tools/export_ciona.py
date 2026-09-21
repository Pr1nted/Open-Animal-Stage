#!/usr/bin/env python3
"""Export the Ciona intestinalis larval connectome (Ryan, Lu & Meinertzhagen
2016) as a species package.

    .venv/bin/python tools/export_ciona.py             # fetch if missing
    .venv/bin/python tools/export_ciona.py --no-fetch

Raw files in data/raw/ryan2016/ (gitignored); package out in
web/species/ciona_larva/; the `export` block of ciona_larva in data/roster.json
rewritten with the URL and sha256 of every raw file read.

WHAT COMES FROM WHERE (all eLife 5:e16962, CC-BY 4.0, unless said otherwise)

  nodes       every cell named in Figure 16 source data 1 (chemical matrix) or
              2 (gap junction matrix) that Figure 1 source data 1 or Figure 3
              source data 1 types as a neuron -- the CNS neurons, plus the
              peripheral (epidermal) sensory neurons whose axons enter the CNS
              and appear in the matrices. Muscle, basal lamina, ependymal
              cells, lens and other accessory cells, the two "ambiguous" cells
              and matrix labels no table types are not nodes; their edges are
              counted and left out.
  chemical    Figure 16 source data 1, rows presynaptic, value = cumulative
              depth of presynaptic contact in um (sections x section
              thickness). Stored as the i16 count in nominal 60 nm section
              equivalents, round(depth / 0.06), at least 1.
  gap         Figure 16 source data 2, cumulative membrane contact depth in um
              (only partners > 0.12 um are in the matrix). Stored as float um,
              once per pair; a pair listed in both orientations is summed.
  signs       Kourakis et al. 2019 (eLife 8:e44753, CC-BY 4.0), by cell class,
              through signs.transmitter_sign -- see CLASS_TRANSMITTERS.
  sensory     Figure 1 source data 1 classes annotated "Sensory".
  motor       Figure 1 source data 1 classes annotated "Motor neuron": MN1-5
              L/R and the midtail motor neurons (MTN).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from open_animal_stage.signs import Sign, transmitter_sign          # noqa: E402
from open_animal_stage import package as pk                        # noqa: E402

RAW = os.path.join(ROOT, "data", "raw", "ryan2016")
CDN = "https://cdn.elifesciences.org/articles/16962/"
FILES = {
    "cell_types": "elife-16962-fig1-data1-v1.xlsx",
    "neurons": "elife-16962-fig3-data1-v1.xlsx",
    "chemical": "elife-16962-fig16-data1-v1.xlsx",
    "gap": "elife-16962-fig16-data2-v1.xlsx",
}

# Ryan et al. 2016 abstract: "we document the synaptic connectome of the
# larva's 177 CNS neurons. These formed 6618 synapses including 1772
# neuromuscular junctions, augmented by 1206 gap junctions."
PAPER = {"cns_neurons": 177, "synapses": 6618, "nmj": 1772, "gap_junctions": 1206}
# The released tables do not agree with each other to the cell (Figure 3's
# list, Figure 1's key and the matrices name slightly different sets), so the
# CNS neuron count is held to +/- NEURON_TOLERANCE, stated, not to equality.
NEURON_TOLERANCE = 5
SECTION_UM = 0.06

LICENCE = ("Ryan, Lu & Meinertzhagen (2016) eLife 5:e16962, doi:10.7554/eLife.16962, "
           "CC-BY 4.0 (source data files included). Transmitter assignments: Kourakis "
           "et al. (2019) eLife 8:e44753, doi:10.7554/eLife.44753, CC-BY 4.0. A derived "
           "export may be redistributed with attribution to both.")

NON_NEURON = {"mul", "mulm", "mur", "murm", "bm", "bm-noto", "Ep", "Total",
              "Grand Total"}

# Cell class -> (transmitters, basis). Kourakis et al. 2019 unless stated.
# "majority" marks a class whose transmitter the paper gives for most, not all,
# members and does not identify the exceptions; the class value is used for
# all of them, and the provenance lists these classes by name.
CLASS_TRANSMITTERS = {
    "PR-I": ({"Glu"}, "majority: 'the majority of the PR-Is are exclusively glutamatergic "
                      "with the exception of two ventral cells' (VGAT), not identified"),
    "PR-II": ({"GABA"}, "all VGAT-positive, a subset co-expressing VGLUT; the paper's "
                        "circuit model treats PR-II output as inhibitory"),
    "Antenna": ({"Glu"}, "'glutamate is used ... exclusively in sensory neurons "
                         "(photoreceptors, antenna cells, and epidermal sensory neurons)'"),
    "epidermal sensory": ({"Glu"}, "VGLUT-expressing epidermal sensory neurons "
                                   "(Kourakis 2019 Fig 2b; Horie et al. 2008b)"),
    "prRN": ({"ACh"}, "VACHT/AMPAR-positive relay neurons of the PR-I circuit "
                      "(Fig 5, Fig 9 model); registration alone was evenly mixed"),
    "pr-AMG RN": ({"GABA"}, "majority: registration predicts 5 of 8 VGAT, 2 VACHT, 1 "
                            "unresolved; the paper's model treats them as GABAergic"),
    "AntRN": ({"GABA"}, "majority: registration predicts 8 of 10 AntRNs VGAT-positive"),
    "Eminens": ({"GABA"}, "VGAT reporter expression, agreeing with GAD (Takamura 2010)"),
    "AMG": ({"GABA"}, "'the AMGs, with the exception of one cell [AMG5], are GABAergic'"),
    "AMG5": ({"ACh"}, "the central VACHT-positive AMG"),
    "MGIN": ({"ACh"}, "ventral MG VACHT block (MNs, ddNs, MGINs)"),
    "ddN": ({"ACh"}, "ventral MG VACHT block"),
    "MN": ({"ACh"}, "motor neurons are cholinergic (Takamura et al. 2002, 2010)"),
    "ACIN": ({"Gly"}, "'the ACINs ... are glycinergic' (Nishino et al. 2010)"),
}

# Figure 1 source data 1 classes annotated "Sensory", and the signal each
# drives. Coronet, PR-III, the tail epidermal neurons and BTNs ("Sensory/
# Interneuron") are not used.
SENSORY = {
    "photoreceptor_I": {
        "signal": "reward", "class": "PR-I",
        "why": ("Type I photoreceptors (23), annotated Sensory. They drive the larva's "
                "directed swimming (phototaxis) through the excitatory PR-I -> prRN -> "
                "MGIN pathway (Kourakis 2019): the sense it steers toward a place by. "
                "Mapping land gained to it is our design; Ciona has no appetitive "
                "chemosense in the connectome to stand in for the fly's sugar."),
    },
    "photoreceptor_II": {
        "signal": "harm", "class": "PR-II",
        "why": ("Type II photoreceptors (7), annotated Sensory. They mediate the dimming "
                "(shadow) response, an escape behaviour (Salas et al. 2018; Kourakis "
                "2019): the larva's aversive visual channel, standing in for bitter."),
    },
    "coronet": {
        "signal": "reserve", "class": "Coronet",
        "why": ("Coronet cells (16), annotated Sensory: ciliated cells with bulbous "
                "protrusions into the canal and dense-core vesicle synapses, proposed as "
                "pressure/ambient-state sensors. Their modality is NOT established; they "
                "are used for the slow homeostatic 'reserve' signal because they are the "
                "remaining annotated-sensory CNS class that is neither visual nor "
                "mechanosensory. The weakest mapping of the four."),
    },
    "rten_mechanosensory": {
        "signal": "threat", "class": "RTEN",
        "why": ("Rostral trunk epidermal neurons, Figure 1 classes pna and pnb (pns1-7, "
                "9-13 in the matrix), annotated Sensory and described as 'anterior "
                "mechanosensory peripheral neuron'. Body-wall mechanosensation, as the "
                "fly's Johnston's organ channel is."),
    },
}
MOTOR_CLASSES = ("MN", "MTN")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def raw_files(allow_fetch):
    out = {}
    for key, name in FILES.items():
        url, p = CDN + name, os.path.join(RAW, name)
        if not os.path.exists(p):
            if not allow_fetch:
                raise SystemExit("missing %s (download %s)" % (p, url))
            os.makedirs(RAW, exist_ok=True)
            print("  fetch", url)
            with urllib.request.urlopen(url, timeout=120) as r, open(p + ".part", "wb") as f:
                f.write(r.read())
            os.replace(p + ".part", p)
        out[key] = {"path": os.path.relpath(p, ROOT), "url": url, "sha256": sha256(p)}
    return out


def sheet_rows(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [tuple(r) for r in wb.worksheets[0].iter_rows(values_only=True)]


def clean(x):
    if x is None:
        return ""
    if isinstance(x, float) and x == int(x):
        x = int(x)
    return str(x).strip()


# Matrix labels that name the same cell differently in the two matrices or
# the two tables. Each is justified in the comment beside it.
ALIASES = {
    **{"Cor%d" % i: "coronet%d" % i for i in range(1, 17)},   # gap matrix spelling
    "NeckNL": "165", "NeckNR": "166",   # Fig 3: 165 is VL, 166 is VR, "Neck"
    # The gap matrix calls the two bipolar interneurons BPN1/BPN2, the chemical
    # matrix 90 and 92. Neither table says which is which; numeric order is
    # ASSUMED (BPN1 = 90, BPN2 = 92). Both are BPIN of unknown sign, so the
    # assumption touches wiring only, never a sign, sensory or motor set.
    "BPN1": "90", "BPN2": "92",
}


def cell_classes(fig1_path, fig3_path):
    """{canonical label: class} for every cell the two tables type as a neuron."""
    cls = {}
    for r in sheet_rows(fig3_path)[2:]:
        cid, typ = clean(r[0]), clean(r[1])
        if not cid or not typ or cid in ("MODE:",):
            continue
        cid = clean(r[0]).replace(" ", "").rstrip("*")
        cid = re.sub(r"\(.*\)$", "", cid)            # "107(Ep)" -> "107"
        cls[cid] = typ
    # Normalise the Figure 3 spellings to the matrix spellings.
    ren = {}
    for k, v in cls.items():
        k2 = k
        k2 = re.sub(r"^Antenna(\d)$", r"Ant\1", k2)
        k2 = re.sub(r"^mt(\d+)$", r"midtail\1", k2)
        k2 = re.sub(r"^pr-([a-g])$", r"pr\1", k2)
        # PR-III cells are named by number in the matrices, except the two
        # Figure 1 calls lens6 and lens7 (not the PNIN "6" or any cell "7").
        k2 = {"prIII-6": "lens6", "prIII-7": "lens7"}.get(k2, k2)
        k2 = re.sub(r"^prIII-(\d+)$", r"\1", k2)
        ren[k2] = v
    cls = ren
    # Figure 1 fills what Figure 3's sheet leaves out (25, 138, the PNS, aaIN).
    extra = {"25": "PNIN", "138": "prIN", "aaIN1": "aaIN", "aaIN2": "aaIN",
             "aaIN3": "aaIN", "Em1": "Eminens1", "Em2": "Eminens2",
             "BTN1": "BTN", "BTN2": "BTN", "BTN3": "BTN", "BTN4": "BTN"}
    for p in ("pns1", "pns2", "pns5", "pns6", "pns9", "pns13",
              "pns3", "pns4", "pns7", "pns10", "pns11", "pns12"):
        extra[p] = "RTEN"
    for p in ("ATEN1", "ATEN2", "ATEN3", "ATEN4", "pna", "pnb", "pnc", "pnf",
              "pnh", "pnu", "pnx", "pnz"):
        extra[p] = "epidermal sensory"
    for k, v in extra.items():
        cls.setdefault(k, v)
    return cls


def classify(typ, name):
    """Figure 3 cell type -> the class keys used by the sign/sensory/motor tables."""
    t = typ.strip()
    if t == "PR (I)":
        return "PR-I"
    if t == "PR (II)":
        return "PR-II"
    if t == "PR (III)":
        return "PR-III"
    if t == "Coronet":
        return "Coronet"
    if t == "Antenna":
        return "Antenna"
    if t.startswith("Eminens"):
        return "Eminens"
    if t == "AMG":
        return "AMG5" if name == "AMG5" else "AMG"
    if t == "Midtail neuron":
        return "MTN"
    if t in ("lens cell", "Ambiguous") or t.startswith("vacIN") and "no axon" in t:
        return None
    return t


def matrix(path):
    rows = sheet_rows(path)
    cols = {j: clean(c) for j, c in enumerate(rows[0]) if j > 0 and c is not None}
    out = {}
    for r in rows[1:]:
        a = clean(r[0])
        if not a:
            continue
        for j, b in cols.items():
            v = r[j] if j < len(r) else None
            if v is None or clean(v) == "":
                continue
            out[(a, b)] = float(v)
    return out


def canon(label):
    return ALIASES.get(label, label)


def export(raw, out_dir):
    typed = cell_classes(os.path.join(ROOT, raw["cell_types"]["path"]),
                         os.path.join(ROOT, raw["neurons"]["path"]))
    chem = matrix(os.path.join(ROOT, raw["chemical"]["path"]))
    gap = matrix(os.path.join(ROOT, raw["gap"]["path"]))

    labels = sorted({canon(x) for k in list(chem) + list(gap) for x in k} - NON_NEURON,
                    key=lambda s: (not s[0].isalpha(), s.lower()))
    cls, untyped, excluded = {}, [], []
    for lab in labels:
        t = typed.get(lab)
        if t is None:
            untyped.append(lab)
            continue
        c = classify(t, lab)
        if c is None:
            excluded.append(lab)
            continue
        cls[lab] = c
    names = [x for x in labels if x in cls]
    index = {nm: i for i, nm in enumerate(names)}
    n = len(names)
    pns = [nm for nm in names if cls[nm] in ("RTEN", "epidermal sensory", "BTN")]
    cns = n - len(pns)

    signs, basis = [], {}
    for nm in names:
        c = cls[nm]
        tx, why = CLASS_TRANSMITTERS.get(c, (set(), "no transmitter published for class"))
        signs.append(transmitter_sign(tx))
        basis.setdefault(c, {"transmitters": sorted(tx), "basis": why, "neurons": 0})
        basis[c]["neurons"] += 1
    n_exc = sum(s is Sign.EXCITATORY for s in signs)
    n_inh = sum(s is Sign.INHIBITORY for s in signs)
    n_unk = n - n_exc - n_inh

    # Chemical.
    synapses, drop_sign, drop_nonneuron, off_grid = [], 0, 0, 0
    worst = 0.0
    nmj_depth = sum(v for (a, b), v in chem.items() if b in ("mul", "mulm", "mur", "murm"))
    for (a, b), v in chem.items():
        a, b = canon(a), canon(b)
        if a in NON_NEURON or b in NON_NEURON or a not in index or b not in index:
            drop_nonneuron += 1
            continue
        sec = v / SECTION_UM
        k = max(1, int(round(sec)))
        err = abs(sec - round(sec))
        if err > 1e-6:
            off_grid += 1
            worst = max(worst, err)
        s = signs[index[a]]
        if s is Sign.UNKNOWN:
            drop_sign += 1
            continue
        synapses.append((index[a], index[b], k * s.value))
    merged = {}
    for i, j, c in synapses:            # two labels aliased onto one cell
        merged[(i, j)] = merged.get((i, j), 0) + c
    synapses = [(i, j, c) for (i, j), c in merged.items()]

    # Gap junctions.
    pairs, g_self, g_non = {}, 0, 0
    for (a, b), v in gap.items():
        a, b = canon(a), canon(b)
        if a in NON_NEURON or b in NON_NEURON or a not in index or b not in index:
            g_non += 1
            continue
        if a == b:
            g_self += 1
            continue
        key = tuple(sorted((index[a], index[b])))
        pairs[key] = pairs.get(key, 0.0) + v
    gaps = [(i, j, w) for (i, j), w in pairs.items()]

    # Sensory and motor.
    sensory, senses, sprov = {}, {}, {}
    for ch, spec in SENSORY.items():
        idx = [index[nm] for nm in names if cls[nm] == spec["class"]]
        sensory[ch] = idx
        senses[ch] = spec["signal"]
        sprov[ch] = {"signal": spec["signal"], "class": spec["class"],
                     "neurons": [names[i] for i in idx], "why": spec["why"]}
    motor_names = [nm for nm in names if cls[nm] in MOTOR_CLASSES]
    groups, rule = pk.deal_groups([[index[x]] for x in motor_names])
    motor = sorted({i for m in pk.MODULES for g in groups[m] for i in g})

    fails = []
    if abs(cns - PAPER["cns_neurons"]) > NEURON_TOLERANCE:
        fails.append("CNS neurons %d vs paper %d" % (cns, PAPER["cns_neurons"]))
    for ch, idx in sensory.items():
        if not idx:
            fails.append("sensory channel %s is empty" % ch)
    report = {
        "cns_neurons": {"got": cns, "paper": PAPER["cns_neurons"],
                        "tolerance": NEURON_TOLERANCE},
        "cns_neurons_note": (
            "Held to +/- %d, not equality: the released tables disagree with each "
            "other (Figure 1 lists seven PR-III ids for a class it counts as six, and "
            "gives several classes as 'n [m]'), and the CNS set here is every "
            "matrix label that Figure 3 or Figure 1 types as a CNS neuron."
            % NEURON_TOLERANCE),
        "pns_neurons_in_matrix": len(pns),
        "chemical_pairs_neuron_to_neuron": len(synapses) + drop_sign,
        "gap_pairs_neuron_neuron": len(gaps),
        "paper_counts_not_comparable": (
            "The paper counts synapses (%d, of which %d neuromuscular) and gap junctions "
            "(%d). The released matrices give one cumulative depth per cell pair, so the "
            "export has pairs, not synapses; no released table lets the synapse totals be "
            "recomputed (Figure 3's per-neuron sums give 5,809 presynaptic sites and 968 "
            "gap junctions over the CNS neurons alone). Neuromuscular depth in the matrix: "
            "%.1f um (Figure 4 source data: 435.4 um for synapses > 1 section)."
            % (PAPER["synapses"], PAPER["nmj"], PAPER["gap_junctions"], nmj_depth)),
    }
    majority = [c for c, (_, why) in CLASS_TRANSMITTERS.items() if why.startswith("majority")]

    meta = {
        "species": "ciona_larva",
        "dataset": "Ryan et al. (2016)",
        "version": "eLife 5:e16962 VOR, Figure 16 source data 1 and 2 (v1)",
        "n": n,
        "names": names,
        "classes": [cls[nm] for nm in names],
        "params": dict(pk.SHIU_PARAMS),
        "sensory": sensory,
        "senses": senses,
        "groups": groups,
        "motor": motor,
        "partition_seed": pk.PARTITION_SEED,
        "window_ms": 200,
        "provenance": {
            "neurons": ("%d nodes: %d CNS neurons (paper: 177) and %d peripheral sensory "
                        "neurons that appear in the matrices (%s). Typed from Figure 3 "
                        "source data 1, with Figure 1 source data 1 for cells Figure 3's "
                        "sheet omits. Left out: %d matrix labels no table types as a "
                        "neuron (%s) and %d typed but not neurons (%s)." % (
                            n, cns, len(pns), ", ".join(pns), len(untyped),
                            ", ".join(untyped), len(excluded), ", ".join(excluded))),
            "aliases": ("Cor1-16 = coronet1-16; NeckNL/NeckNR = 165/166 (Figure 3 sides); "
                        "BPN1/BPN2 = 90/92 by numeric order, ASSUMED -- no table says."),
            "chemical": ("Figure 16 source data 1, rows presynaptic; value = cumulative depth "
                         "of presynaptic contact (um). Count = round(depth / 0.06 um), >= 1: "
                         "nominal 60 nm section equivalents. %d pairs were not on the 0.06 "
                         "grid (section thickness varied); worst rounding %.2f sections. %d "
                         "kept; %d cells of the matrix with muscle, basal lamina or a "
                         "non-neuron left out." % (off_grid, worst, len(synapses), drop_nonneuron)),
            "gap": ("Figure 16 source data 2 (partners > 0.12 um only), cumulative membrane "
                    "contact depth in um as gap_w, one entry per pair (both orientations "
                    "summed). %d kept; %d self-contacts and %d cells with non-neurons left "
                    "out." % (len(gaps), g_self, g_non)),
            "signs": ("By cell class from Kourakis et al. 2019 (eLife 8:e44753) through "
                      "open_animal_stage.signs.transmitter_sign (ACh/Glu excitatory, GABA/"
                      "Gly inhibitory, both or neither UNKNOWN). Glutamate is excitatory by "
                      "rule. Classes assigned from a MAJORITY statement, exceptions "
                      "unidentified: %s. Every other class (BV intrinsic interneurons, "
                      "PR-III, coronet, BTN, midtail, PMGN, neck, secondary/PN/pr-cor/"
                      "pr-BTN relay neurons) has no published transmitter and is UNKNOWN. "
                      "Result: %d excitatory, %d inhibitory, %d unknown." % (
                          ", ".join(majority), n_exc, n_inh, n_unk)),
            "sign_classes": basis,
            "sensory": sprov,
            "motor": ("Figure 1 source data 1 classes annotated 'Motor neuron': MN1-5 left "
                      "and right and the midtail motor neurons (midtail1, 2, 4, 7): %d "
                      "neurons, fewer than 39, so dealt round-robin (numpy default_rng(783); a "
                      "fresh permutation per module, drawn e, p, w, n; neuron i of it goes "
                      "to group i mod groups): each neuron in exactly one group "
                      "per module, groups of 1-2, shared across modules." % len(motor_names)),
            "motor_rule": rule,
            "params": ("Open Fly's constants from Shiu et al. 2024 (fly LIF), unchanged; "
                       "w_gap 0.0 and calibrated false -- w_syn and w_gap are set later by "
                       "one fixed rule in the JS brain, not tuned here. Ciona larval neurons "
                       "have not been shown to spike like the fly's; a LIF neuron is a "
                       "stated simplification."),
            "licence": LICENCE,
            "dropped_unknown_sign": drop_sign,
            "validation": report,
            "raw": raw,
            "exported": datetime.date.today().isoformat(),
            "exporter": "tools/export_ciona.py",
        },
    }
    if fails:
        raise SystemExit("ciona_larva: validation failed:\n  " + "\n  ".join(fails))
    pk.write_package(out_dir, n, synapses, gaps, meta)
    bad = pk.check_package(out_dir)
    if bad:
        raise SystemExit("ciona_larva: package check failed:\n  " + "\n  ".join(bad))
    print("ciona_larva: %d nodes (%d CNS vs paper 177, %d PNS), %d chemical kept of %d "
          "(%d dropped for unknown sign), %d gap pairs; signs +%d -%d ?%d; motor %d "
          "(%s); untyped labels left out: %s"
          % (n, cns, len(pns), len(synapses), len(synapses) + drop_sign, drop_sign,
             len(gaps), n_exc, n_inh, n_unk, len(motor), rule, untyped))
    return {
        "dataset_version": meta["version"],
        "exported": meta["provenance"]["exported"],
        "exporter": "tools/export_ciona.py",
        "package": os.path.relpath(out_dir, ROOT),
        "sources": raw,
        "sign_source": "Kourakis et al. 2019, eLife 8:e44753 (CC-BY 4.0), by cell class",
        "licence": LICENCE,
        "counts": {"neurons": n, "cns_neurons": cns, "pns_neurons": len(pns),
                   "chemical_pairs": len(synapses), "gap_pairs": len(gaps),
                   "dropped_unknown_sign": drop_sign, "motor_neurons": len(motor)},
        "validation": report,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--no-roster", action="store_true")
    args = ap.parse_args()
    block = export(raw_files(not args.no_fetch),
                   os.path.join(ROOT, "web", "species", "ciona_larva"))
    if not args.no_roster:
        path = os.path.join(ROOT, "data", "roster.json")
        d = json.load(open(path))
        for s in d["species"]:
            if s["id"] == "ciona_larva":
                s["export"] = block
        with open(path + ".tmp", "w") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(path + ".tmp", path)


if __name__ == "__main__":
    main()
