#!/usr/bin/env python3
"""Export the Fish1 larval zebrafish connectome as a species package.

    ~/fish1-venv/bin/python tools/fish1_export.py --sensory-convention mece-ganglia-v1
    ~/fish1-venv/bin/python tools/fish1_export.py --sensory-convention mece-ganglia-v1 --no-fetch

Raw pages cached (and gitignored) under data/raw/fish1/; package out in
web/species/zebrafish_larva/; the `export` block of zebrafish_larva in
data/roster.json rewritten.

WHY THIS IS A SEPARATE STEP, RUN BY A HUMAN

Fish1 is not a download. It is a CAVE datastack behind a personal token that a
person obtains by hand through a Google account, and the token lands in
~/.cloudvolume/secrets/cave-secret.json and must never be committed. There is no
way to make this run in CI without shipping somebody's credentials, so it does
not try: a human runs it, and what they get is a derived export that is not
committed to this repository.

WHY THE VERSION IS NOT OPTIONAL

The dataset is under active community proofreading. A root id is a 64-bit
segmentation id that CHANGES when anybody merges or splits a segment; a lore id
is a small stable integer for a soma that does not. So an export is only
reproducible against a stated materialization version. Nodes are keyed by lore
id; root ids appear nowhere in the package except as the stated basis of the
join, and the version is recorded beside them.

WHERE THE BULK DATA IS NOT

gs://fish1-public is world-readable without a token and does hold the synapses
in bulk, as neuroglancer sharded annotations under
syn_241003_agg241003_reorient_axde_ei.precomputed/ (1.8 GB by_id, 1.65 GB in
the two relationship indexes, with the excitatory/inhibitory call as the
annotation's uint32 `type` property). It is NOT used, for one decisive reason:
the cell ids in those files are flat segment ids of the seg_241003_agg241003
aggregation (ten digits, e.g. 4961161286), and the somas table's pt_root_id at
this materialization is a ChunkedGraph root id (864691128...). They are
different id spaces, a year apart, with no published crosswalk. Joining them
would mean re-looking-up every soma position in a 2024 segmentation and
silently mis-assigning every cell that has been proofread since. The CAVE
tables are what the pinned version actually means, so the export walks them in
disjoint id ranges -- about 20 minutes for 29.5M synapses -- and caches each
range. It does NOT page by limit/offset: this server does not order rows
stably at depth, and an earlier draft that did returned 2.7M of 18.4M rows
twice and as many not at all, silently. See fetch().

THE SIGN PROBLEM, AND WHY FISH1 CAN BE MODELLED AT ALL

A leaky integrate-and-fire model needs to know whether a synapse excites or
inhibits. A bare connectome does not say. Fish1 has TWO independent sources:

  synapses_axde_label   a per-synapse call, tag "1" inhibitory, "2" excitatory,
                        for all 29,474,316 axon-to-dendrite synapses. This is
                        what the export uses.
  somas.cell_type       a per-cell call from the companion confocal light
                        microscopy of the same specimen -- 26,915 "exc"
                        (vglut2a-positive) and 14,510 "inh" (gad1b-positive)
                        cells, 145,627 "na". NOT used to assign signs: it is
                        held back and used to CHECK them, which is the only
                        validation in this export that does not come from us.

A LIF neuron has one sign, so a cell whose own synapses disagree needs a rule.
The rule is the majority of that cell's labelled synapses, fixed here and
recorded; a cell with an exact tie is UNKNOWN and its synapses are dropped, as
docs/species-format.md requires of an unknown sign.

SENSORY AND MOTOR: WHOSE ANNOTATION, AND WHICH PART IS OURS

Fish1 annotates no CELL TYPES -- classification_system is "na" for all 187,052
somas and cell_type is only exc/inh/na. It does annotate BRAIN REGIONS, and
publicly: gs://fish1-public/mece{0,1,2,3}_231218 are a four-level,
mutually-exclusive segmentation on the EM grid with names in
segment_properties, being the Z-Brain atlas (Randlett et al. 2015) warped onto
this specimen by ANTs. They name `Ganglia/Trigeminal Ganglion`,
`Ganglia/Statoacoustic Ganglion`, `Retina`, `.../X Vagus motorneuron cluster`
and the rest. So the sets ARE named from the source's own annotation, which is
what ROSTER.md's seat test asks for.

Three things are ours, and the export says so wherever it names them:

  the join         no released table says which region a soma is in, so
                   tools/fish1_regions.py samples the mask at the soma's own
                   published centroid. It must be run first.
  the grouping     the annotated ganglia are grouped into four channels by
                   modality, because the game gives every animal exactly four.
  the assignment   which channel carries reward, harm, reserve or threat, by
                   analogy to Open Fly's sugar, bitter, water and Johnston's
                   organ.

--sensory-convention is required and has no default, so the run names the
convention it used; it is written out in full in docs/fish1-mapping.md, and
brain.json's provenance.sensory and provenance.motor carry the same statement,
marked "CONVENTION (not a source annotation)" around exactly the parts that
are ours, for the page to show the viewer.
"""
import argparse
import datetime
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from open_animal_stage import package as pk                        # noqa: E402

RAW = os.path.join(ROOT, "data", "raw", "fish1")
DATASTACK = "fish1_full"
DATASET = "fish1_v250915"
GLOBAL_URL = "https://global.brain-wire-test.org"

# Pinned. See the module docstring. 574, which an earlier draft of this file
# named, has been expired off the server; the versions it offers are
# 686, 698, 700, 702, 703, 704.
DEFAULT_MATERIALIZATION = 704

# The server returns intermittent 503s under load; every call goes through
# retry(). Observed: a table recovering after four tries of 20s or more.
SYN_COLS = ["target_id", "tag", "pre_pt_root_id", "post_pt_root_id"]
# Rows per id-range query. The server truncates at this and says so in a
# warning; the fetch treats a full result as "this range is not complete" and
# splits it, so the number is a batch size and never a cap on what is kept.
SLAB_LIMIT = 250000
INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1

# somas / somas_distance_to_landmark are annotated at 8 x 8 x 30 nm
# (client.materialize.get_table_metadata("somas")["voxel_resolution"]).
SOMA_VOXEL_NM = (8.0, 8.0, 30.0)

# The released row count for synapses_axde at this materialization. The build
# checks the ranges it assembled against it and refuses to write a package if
# they disagree. The id ranges cannot overlap or leave a gap by construction,
# but the check is kept anyway: a brain quietly missing a seventh of its
# synapses is exactly the failure this export already had once.
SYNAPSES_RELEASED = 29474316
SOMAS_RELEASED = 187052

I16_MAX = 32767

LICENCE = (
    "Fish1 (fish1_v250915), Lichtman and Engert labs (Harvard) with Google "
    "Connectomics, via the CAVE datastack fish1_full at "
    "https://global.brain-wire-test.org, materialization 704. Access is by a "
    "personal token obtained by hand; the token is never read, printed or "
    "written by this exporter. The redistribution terms for Fish1 have not "
    "been established by this project -- data/roster.json records "
    "redistribute: null and redistribute_why, and this derived package is "
    "gitignored and not published until those terms are read."
)

# --------------------------------------------------------------- the convention
#
# Fully written up, with its evidence, in docs/fish1-mapping.md. The SETS below
# are the source's own annotation: the published MECE region masks in
# gs://fish1-public (the Z-Brain atlas, Randlett et al. 2015, warped onto this
# specimen by ANTs -- Fish1 preprint Methods; FishExplorer companion paper),
# sampled at each soma's published centroid by tools/fish1_regions.py.
#
# Three things are OURS and are conventions, each stated in brain.json:
#   1. the join -- no released table says which region a soma is in;
#   2. grouping the annotated ganglia into four channels by modality;
#   3. which channel carries which of the game's four signals.
# None of them has a tunable number in it. See "Outcome-blindness" in the doc.

CONVENTIONS = {
    "mece-ganglia-v1": {
        "sensory": "MECE level-1 Ganglia classes + level-0 Retina, by modality",
        "motor": "MECE level-2 labels containing 'motor'",
    },
}

# Verbatim mece1_231218 / mece0_231218 labels. Every peripheral sensory
# structure Fish1 annotates is used, and each is used exactly once: the four
# channels are the four modalities the annotation distinguishes, not a
# selection from them.
SENSORY = [
    ("chemosensory", "reward", 1, [
        "Ganglia/Olfactory Epithelium", "Ganglia/Facial Sensory Ganglion",
        "Ganglia/Facial glossopharyngeal ganglion", "Ganglia/Vagal Ganglia"],
     "Open Fly's reward channel is its sugar gustatory receptor neurons: "
     "appetitive chemosensation. In a fish that is olfaction plus the facial "
     "and glossopharyngeal taste ganglia. Grouping smell with taste is OURS. "
     "In this specimen only the olfactory epithelium actually carries somata "
     "-- both taste ganglia sample empty -- so the channel is olfactory in "
     "practice, and it is much the largest of the four, which "
     "docs/fish1-mapping.md records as the mapping's main risk."),
    ("trigeminal", "harm", 1, ["Ganglia/Trigeminal Ganglion"],
     "Open Fly's harm channel is its bitter GRNs, the aversive one. The "
     "trigeminal ganglion is the larval zebrafish's nociceptive and "
     "somatosensory ganglion."),
    ("octavolateralis", "threat", 1, [
        "Ganglia/Statoacoustic Ganglion", "Ganglia/Anterior Lateral Line Ganglion",
        "Ganglia/Posterior Lateral Line Ganglia",
        "Ganglia/Lateral Line Neuromast O1", "Ganglia/Lateral Line Neuromast OC1",
        "Ganglia/Lateral Line Neuromast SO1", "Ganglia/Lateral Line Neuromast SO2",
        "Ganglia/Lateral Line Neuromast SO3", "Ganglia/Lateral Line Neuromast D1",
        "Ganglia/Lateral Line Neuromast D2", "Ganglia/Lateral Line Neuromast N"],
     "Open Fly's threat channel is Johnston's organ, the fly's mechanosensory "
     "and auditory organ. The statoacoustic ganglion and the lateral line are "
     "one hair-cell system with the same job, and they are the input that "
     "drives the larva's escape. The statoacoustic ganglion samples empty in "
     "this specimen, so the channel is carried by the lateral line alone."),
    ("viscerosensory", "reserve", 1, ["Ganglia/Vagal Ganglia"],
     "Open Fly carries reserve -- treasury against income, a slow homeostatic "
     "scalar -- on its water-sensing neurons. The vagal ganglia are the "
     "larva's viscerosensory afferents: internal bodily state, which is the "
     "closest thing the annotation offers to a homeostatic sense."),
]

# Annotated and EMPTY, which is a fact about the data and is reported rather
# than worked around. `Retina` (mece0) and `Ganglia/Statoacoustic Ganglion`,
# `Ganglia/Facial Sensory Ganglion`, `Ganglia/Facial glossopharyngeal
# ganglion` and four of the twelve neuromast regions (mece1) contain NO soma:
# the soma segmentation covers the CNS and some peripheral ganglia, not the
# eye or the ear. So the fish has no visual channel at all -- a gap in the
# DATA, not a choice -- and the octavolateralis channel is carried by the
# lateral line alone.
EXPECT_EMPTY = ["Retina", "Ganglia/Statoacoustic Ganglion",
                "Ganglia/Facial Sensory Ganglion",
                "Ganglia/Facial glossopharyngeal ganglion"]

# The motor rule is a substring, not a list: every level-2 MECE label
# containing "motor" (case-insensitively). Over the 70 published level-2
# labels that picks out the eight cranial motor nuclei -- nIII, nIV, the two
# nV trigeminal motorneuron clusters, the three VII facial motor clusters and
# the X vagus motorneuron cluster -- and nothing else. The source calls them
# motor neurons in those words.
MOTOR_SUBSTRING = "motor"

# The Fish1 preprint's own reliability rule for the confocal exc/inh call:
# "cells located as third neighbors or further (10 um or more from the
# landmark center) are predominantly non-matches". Used ONLY to restrict the
# sign cross-check, never as an anatomical coordinate.
LANDMARK_TRUST_UM = 10.0


def retry(fn, what="call", tries=14, base=10, cap=120):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)[:180].replace("\n", " ")
            if i == tries - 1:
                raise
            wait = min(cap, base * (1.5 ** i))
            print("    %s failed (%d/%d): %s; sleeping %.0fs"
                  % (what, i + 1, tries, msg, wait), flush=True)
            time.sleep(wait)


# ---------------------------------------------------------------------- fetch

def connect(version):
    from caveclient import CAVEclient
    # The token is read from ~/.cloudvolume/secrets/cave-secret.json by the
    # client itself. This never reads it, never prints it and never writes it.
    c = retry(lambda: CAVEclient(datastack_name=DATASTACK, server_address=GLOBAL_URL),
              "connect")
    versions = retry(lambda: c.materialize.get_versions(), "get_versions")
    if version not in versions:
        raise SystemExit(
            "materialization %d is not available (the server offers %s).\n"
            "    An export is only reproducible against a version that still\n"
            "    exists; re-pin deliberately rather than falling back."
            % (version, sorted(versions)))
    c.materialize.version = version
    return c


def fetch(version):
    """Cache every page under data/raw/fish1. Resumable: a page already on
    disk is never refetched, so a 503 storm costs only the page it hit."""
    import pandas as pd
    os.makedirs(RAW, exist_ok=True)
    need_syn = not os.path.exists(os.path.join(RAW, "syn_v%d" % version, "DONE"))
    need_tbl = [t for t in ("somas", "somas_distance_to_landmark",
                            "relaxin_177172_output_080426")
                if not os.path.exists(os.path.join(RAW, "%s.v%d.parquet" % (t, version)))]
    if not need_syn and not need_tbl:
        print("  cache is complete; nothing to fetch")
        return
    c = connect(version)
    for tbl in need_tbl:
        out = os.path.join(RAW, "%s.v%d.parquet" % (tbl, version))
        df = retry(lambda: c.materialize.query_table(tbl, materialization_version=version), tbl)
        df.to_parquet(out)
        print("  %s: %d rows" % (tbl, len(df)), flush=True)
    if not need_syn:
        return
    d = os.path.join(RAW, "syn_v%d" % version)
    os.makedirs(d, exist_ok=True)
    total, nrange, t0 = 0, 0, time.time()

    def slab(lo, hi, depth=0):
        """Fetch the half-open id range [lo, hi), splitting it if it saturates.

        NOT offset paging. An earlier draft of this file paged with
        limit/offset and it was WRONG: at depth the server's row order is not
        stable between queries, so pages overlapped (8 of 91 adjacent pairs,
        up to 37,492 rows) and 2.7M of 18.4M rows came back twice -- which
        means as many were never returned at all. The loss was silent and
        would have shipped a brain quietly missing a seventh of its synapses.

        Ranges over `target_id` have neither failure: they are disjoint and
        contiguous by construction, and re-running one returns exactly the
        same rows (checked). filter_greater/less are STRICT, so [lo, hi) is
        expressed as (lo-1, hi) and the ends of the int64 domain simply omit
        the filter on that side."""
        nonlocal total, nrange
        tag = "%d_%d" % (lo, hi)
        p = os.path.join(d, "r%s.parquet" % tag)
        if os.path.exists(p):
            total += len(pd.read_parquet(p, columns=["tag"]))
            nrange += 1
            return
        kw = {}
        if lo > INT64_MIN:
            kw["filter_greater_dict"] = {"target_id": lo - 1}
        if hi < INT64_MAX + 1:
            kw["filter_less_dict"] = {"target_id": hi}
        df = retry(lambda: c.materialize.query_table(
            "synapses_axde_label", limit=SLAB_LIMIT, select_columns=list(SYN_COLS),
            materialization_version=version, **kw), "range %s" % tag)
        if len(df) >= SLAB_LIMIT:
            # Saturated: the server truncated, so this range is not complete.
            mid = lo + (hi - lo) // 2
            if mid <= lo or mid >= hi:
                raise SystemExit("cannot split id range [%d,%d)" % (lo, hi))
            slab(lo, mid, depth + 1)
            slab(mid, hi, depth + 1)
            return
        df[SYN_COLS].astype({"target_id": "int64", "tag": "int8",
                             "pre_pt_root_id": "uint64", "post_pt_root_id": "uint64"}
                            ).to_parquet(p + ".part", index=False)
        os.replace(p + ".part", p)
        total += len(df)
        nrange += 1
        if nrange % 10 == 0:
            print("  %d ranges, %d rows, %.0fs" % (nrange, total, time.time() - t0),
                  flush=True)

    sys.setrecursionlimit(10000)
    slab(INT64_MIN, INT64_MAX + 1)
    print("  synapses: %d rows in %d id ranges, %.0fs"
          % (total, nrange, time.time() - t0))
    open(os.path.join(d, "DONE"), "w").write("%d\n" % total)


# ---------------------------------------------------------------------- build

def load_somas(version):
    import numpy as np
    import pandas as pd
    s = pd.read_parquet(os.path.join(RAW, "somas.v%d.parquet" % version))
    if len(s) != SOMAS_RELEASED:
        print("  NOTE: somas has %d rows, the release says %d" % (len(s), SOMAS_RELEASED))
    root = s.pt_root_id.to_numpy("uint64")
    u, cnt = np.unique(root[root != 0], return_counts=True)
    shared = u[cnt > 1]
    keep = (root != 0) & ~np.isin(root, shared)
    drop_noseg = int((root == 0).sum())
    drop_shared = int(((root != 0) & np.isin(root, shared)).sum())
    s = s[keep].reset_index(drop=True)

    rp = os.path.join(RAW, "soma_regions.v%d.parquet" % version)
    if not os.path.exists(rp):
        raise SystemExit("missing %s -- run tools/fish1_regions.py first: the "
                         "sensory and motor sets are the published MECE region "
                         "masks and there is no fallback." % rp)
    reg = pd.read_parquet(rp).set_index("id").reindex(s.id.to_numpy("int64")
                                                      ).reset_index(drop=True)
    for c in ("l0", "l1", "l2"):
        reg[c] = reg[c].fillna("")

    # Distance to the nearest EM-to-LM registration landmark, used ONLY to say
    # where the confocal exc/inh label can be trusted (Fish1 Methods).
    d = pd.read_parquet(os.path.join(RAW, "somas_distance_to_landmark.v%d.parquet" % version))
    dist = (d.set_index("id_ref").tag.astype(float)
            .reindex(s.id.to_numpy("int64")).to_numpy("float64"))

    pos = np.stack(s.pt_position.values).astype("float64") * np.array(SOMA_VOXEL_NM) / 1000.0
    unlabelled = {c: int((reg[c] == "").sum()) for c in ("l0", "l1", "l2")}
    return s, pos, reg, dist, {
        "somas_in_table": SOMAS_RELEASED,
        "dropped_no_segment": drop_noseg,
        "dropped_root_shared_by_several_somas": drop_shared,
        "shared_roots": int(len(shared)),
        "nodes": int(len(s)),
        "outside_every_mece_mask": unlabelled,
        "mece_level0": {k: int(v) for k, v in reg.l0.value_counts().items()},
    }


def load_synapses(version, root_sorted, order, n):
    """Page files -> (pre_idx, post_idx, tag) as node indices, plus a tally of
    what was dropped. An endpoint whose root id is not one of the kept somas'
    is unmatched: that synapse touches a fragment with no soma in the volume,
    or a soma we could not identify, and it is dropped."""
    import numpy as np
    import pandas as pd
    files = sorted(glob.glob(os.path.join(RAW, "syn_v%d" % version, "r*.parquet")))
    if not files:
        raise SystemExit("no cached synapse pages; run without --no-fetch")
    pres, posts, tags = [], [], []
    rows = 0
    seen_ids = []
    for f in files:
        df = pd.read_parquet(f)
        rows += len(df)
        seen_ids.append(df.target_id.to_numpy("int64"))
        a = map_roots(df.pre_pt_root_id.to_numpy("uint64"), root_sorted, order, n)
        b = map_roots(df.post_pt_root_id.to_numpy("uint64"), root_sorted, order, n)
        m = (a >= 0) & (b >= 0)
        pres.append(a[m].astype("int32"))
        posts.append(b[m].astype("int32"))
        tags.append(df.tag.to_numpy("int8")[m])
    ids = np.concatenate(seen_ids)
    distinct = int(len(np.unique(ids)))
    del seen_ids, ids
    pre = np.concatenate(pres); post = np.concatenate(posts); tag = np.concatenate(tags)
    return pre, post, tag, {"rows_fetched": rows, "distinct_synapse_ids": distinct,
                            "released": SYNAPSES_RELEASED,
                            "both_endpoints_on_a_soma": int(len(pre))}


def map_roots(x, root_sorted, order, n):
    """root id -> node index, -1 if it is not one of the kept somas."""
    import numpy as np
    i = np.searchsorted(root_sorted, x)
    i[i >= len(root_sorted)] = 0
    hit = root_sorted[i] == x
    out = np.where(hit, order[i], -1)
    return out.astype("int64")


def cell_signs(pre, tag, n):
    """One sign per presynaptic cell: the majority of that cell's own labelled
    synapses. An exact tie is UNKNOWN, and a synapse from a neuron of unknown
    sign is dropped at export, never assumed excitatory."""
    import numpy as np
    exc = np.bincount(pre, weights=(tag == 2), minlength=n).astype("int64")
    inh = np.bincount(pre, weights=(tag == 1), minlength=n).astype("int64")
    sign = np.zeros(n, dtype="int8")
    sign[exc > inh] = 1
    sign[inh > exc] = -1
    has = (exc + inh) > 0
    tie = has & (exc == inh)
    mixed = has & (exc > 0) & (inh > 0)
    return sign, exc, inh, {
        "presynaptic_cells": int(has.sum()),
        "excitatory": int((sign > 0).sum()),
        "inhibitory": int((sign < 0).sum()),
        "tie_unknown": int(tie.sum()),
        "cells_whose_synapses_disagree": int(mixed.sum()),
        "disagreement_rate_over_presynaptic_cells":
            round(float(mixed.sum()) / max(1, int(has.sum())), 6),
    }


def check_against_clem(s, sign, exc, inh, dist):
    """The only check in this export that is not us checking ourselves: the
    per-synapse sign against the companion confocal vglut2a / gad1b call,
    which is a different measurement of the same specimen, made with a
    different instrument, and was NOT used to derive the sign.

    Reported three ways, because the label's own reliability varies: over every
    labelled cell, over cells with enough synapses for a majority to mean
    anything, and over the cells the Fish1 preprint says the label can be
    trusted for at all (within 10 um of an EM-to-LM registration landmark)."""
    import numpy as np
    lab = s.cell_type.to_numpy()
    want = np.where(lab == "exc", 1, np.where(lab == "inh", -1, 0)).astype("int8")
    tot = exc + inh
    near = dist < LANDMARK_TRUST_UM
    out = {}
    for name, m in (
            ("all_labelled_cells", (want != 0) & (tot >= 1)),
            ("with_10_or_more_synapses", (want != 0) & (tot >= 10)),
            ("with_10_or_more_synapses_and_within_10um_of_a_landmark",
             (want != 0) & (tot >= 10) & near)):
        if not m.any():
            continue
        agree = int((sign[m] == want[m]).sum())
        out[name] = {"cells": int(m.sum()), "agree": agree,
                     "agreement": round(agree / int(m.sum()), 4)}
    out["_note"] = (
        "somas.cell_type is the confocal vglut2a (exc) / gad1b (inh) call. It "
        "is held back from the export and used only here. The landmark cut is "
        "the Fish1 preprint's own: cells 10 um or more from an EM-to-LM "
        "correspondence point are predominantly non-matches, so the label "
        "itself is unreliable there and a disagreement is not evidence "
        "against the synapse tags.")
    return out


def edges(pre, post, tag, sign, n):
    """Ordered pairs -> one signed i16 count each."""
    import numpy as np
    keep = sign[pre] != 0
    drop_unknown = int((~keep).sum())
    pre, post = pre[keep], post[keep]
    self_syn = int((pre == post).sum())
    m = pre != post
    pre, post = pre[m], post[m]
    key = pre.astype("int64") * n + post
    del pre, post
    key, cnt = np.unique(key, return_counts=True)
    a = (key // n).astype("int32")
    b = (key % n).astype("int32")
    del key
    clamped = int((cnt > I16_MAX).sum())
    biggest = int(cnt.max()) if len(cnt) else 0
    cnt = np.minimum(cnt, I16_MAX).astype("int32") * sign[a].astype("int32")
    return (a, b, cnt.astype("int16")), {
        "dropped_unknown_sign": drop_unknown,
        "self_synapses_dropped": self_syn,
        "pairs": int(len(a)),
        "pairs_clamped_to_int16": clamped,
        "largest_pair_count": biggest,
    }


def reachability(synapses, n, sensory, motor):
    """Can a sense reach an order at all?

    Not a quality measure and not tuneable -- a yes/no about the wiring. Open
    Fly's `choose()` reads the motor groups after 200 ms of drive on the
    sensory channels, so if no directed path runs from a channel to any motor
    neuron, that channel cannot move that seat no matter what the neuron model
    does. PREREGISTRATION.md's first failure condition ("a seat that never
    acts") is then guaranteed before a single turn is played, and the package
    says so instead of letting the fish sit down and lose."""
    import numpy as np
    if not synapses:
        return {"edges": 0, "note": "no edges at all"}
    a = np.fromiter((p for p, _, _ in synapses), "int64", len(synapses))
    b = np.fromiter((q for _, q, _ in synapses), "int64", len(synapses))
    mset = np.zeros(n, bool)
    mset[list(motor)] = True
    outdeg = np.bincount(a, minlength=n)
    indeg = np.bincount(b, minlength=n)
    out = {
        "edges": len(synapses),
        "neurons_with_an_outgoing_edge": int((outdeg > 0).sum()),
        "neurons_with_an_incoming_edge": int((indeg > 0).sum()),
        "isolated_neurons": int(((outdeg == 0) & (indeg == 0)).sum()),
        "motor_neurons_with_an_incoming_edge": int((indeg[mset] > 0).sum()),
        "motor_neurons": int(mset.sum()),
        "channels": {},
    }
    for ch, idx in sensory.items():
        src = np.array(idx, dtype="int64")
        seen = np.zeros(n, bool)
        seen[src] = True
        frontier, hops = src, 0
        # One pass over the edge list per hop, not one slice per frontier
        # neuron: the frontier can be tens of thousands of cells wide.
        while len(frontier):
            infront = np.zeros(n, bool)
            infront[frontier] = True
            nxt = np.unique(b[infront[a]])
            nxt = nxt[~seen[nxt]]
            if not len(nxt):
                break
            seen[nxt] = True
            frontier = nxt
            hops += 1
        out["channels"][ch] = {
            "neurons": len(src),
            "with_an_outgoing_edge": int((outdeg[src] > 0).sum()),
            "reaches": int(seen.sum()), "hops": hops,
            "motor_neurons_reached": int((seen & mset).sum()),
        }
    out["any_channel_reaches_the_motor_set"] = any(
        v["motor_neurons_reached"] > 0 for v in out["channels"].values())
    return out


def sets_by_convention(reg):
    """Sensory channels and the motor set, from the published MECE labels.

    `reg` is the per-node region frame from tools/fish1_regions.py, already
    aligned to the node order. Raises rather than shipping an empty channel:
    an empty sensory channel means the join is wrong, and docs/fish1-mapping.md
    says that is withdrawn, not patched."""
    import numpy as np
    sensory, prov = {}, {}
    for ch, signal, level, wanted, why in SENSORY:
        col = reg["l%d" % level].to_numpy()
        idx = np.nonzero(np.isin(col, wanted))[0]
        if len(idx) == 0:
            raise SystemExit(
                "sensory channel %r is empty: no soma sampled onto %s in "
                "mece%d_231218. The join is wrong -- fix it, do not loosen it."
                % (ch, wanted, level))
        sensory[ch] = idx.astype(int).tolist()
        prov[ch] = {"signal": signal, "mece_level": level, "regions": wanted,
                    "neurons": len(idx),
                    "per_region": {w: int((col == w).sum()) for w in wanted},
                    "why": why}
    l2 = reg["l2"].to_numpy()
    leaf = np.array([s.rsplit("/", 1)[-1] for s in l2])
    hit = np.char.find(np.char.lower(leaf.astype(str)), MOTOR_SUBSTRING) >= 0
    motor_idx = np.nonzero(hit)[0].astype(int).tolist()
    nuclei = sorted({s for s in l2[hit]})
    if not motor_idx:
        raise SystemExit("no soma sampled onto a level-2 region whose label "
                         "contains %r; the join is wrong" % MOTOR_SUBSTRING)
    empty = {}
    for w in EXPECT_EMPTY:
        lv = 0 if "/" not in w else 1
        empty[w] = int((reg["l%d" % lv].to_numpy() == w).sum())
    prov["_annotated_but_empty"] = {
        "counts": empty,
        "note": ("Regions Fish1 annotates that contain NO soma in this "
                 "specimen. The soma segmentation covers the CNS and some "
                 "peripheral ganglia, not the eye or the ear, so THE FISH HAS "
                 "NO VISUAL CHANNEL AT ALL -- a gap in the data, not a choice "
                 "-- and the octavolateralis channel is carried by the lateral "
                 "line without the statoacoustic ganglion. Reported rather "
                 "than worked around: a channel is never refilled from "
                 "somewhere else to make the numbers look better."),
        "motor_nuclei_with_no_soma": [
            s for s in ("Midbrain/Tegmentum/Oculomotor Nucleus nIII",
                        "Hindbrain/Rhombomere 1/Oculomotor Nucleus nIV",
                        "Hindbrain/Rhombomere 2/Anterior Cluster of nV Trigeminal Motorneurons",
                        "Hindbrain/Rhombomere 3/Posterior Cluster of nV Trigeminal Motorneurons",
                        "Hindbrain/Rhombomere 5/VII Facial Motor and octavolateralis efferent neurons",
                        "Hindbrain/Rhombomere 6/VII Facial Motor and octavolateralis efferent neurons1",
                        "Hindbrain/Rhombomere 7/VII Facial Motor and octavolateralis efferent neurons2",
                        "Hindbrain/Caudal Hindbrain/X Vagus motorneuron cluster")
            if s not in nuclei],
    }
    return motor_idx, nuclei, sensory, prov


def build(version, convention, out_dir):
    import numpy as np
    t0 = time.time()
    s, pos, reg, dist, node_report = load_somas(version)
    n = len(s)
    lore = s.id.to_numpy("int64")
    names = ["lore%d" % i for i in lore]
    root = s.pt_root_id.to_numpy("uint64")
    order = np.argsort(root)
    root_sorted = root[order]

    pre, post, tag, syn_report = load_synapses(version, root_sorted, order, n)
    print("  synapses: %d fetched, %d with both endpoints on a soma"
          % (syn_report["rows_fetched"], syn_report["both_endpoints_on_a_soma"]), flush=True)
    if syn_report["distinct_synapse_ids"] != SYNAPSES_RELEASED:
        raise SystemExit(
            "the cached pages hold %d distinct synapse ids; the release says %d.\n"
            "    Offset paging skipped or duplicated something -- delete\n"
            "    data/raw/fish1/syn_v%d and refetch rather than exporting a\n"
            "    brain that is quietly missing synapses."
            % (syn_report["distinct_synapse_ids"], SYNAPSES_RELEASED, version))

    sign, exc, inh, sign_report = cell_signs(pre, tag, n)
    clem = check_against_clem(s, sign, exc, inh, dist)
    print("  signs: +%d -%d, %d ties, %.2f%% of presynaptic cells disagree with "
          "themselves; CLEM agreement %.3f (>=10 synapses, near a landmark)"
          % (sign_report["excitatory"], sign_report["inhibitory"],
             sign_report["tie_unknown"],
             100 * sign_report["disagreement_rate_over_presynaptic_cells"],
             clem.get("with_10_or_more_synapses_and_within_10um_of_a_landmark",
                      {}).get("agreement", float("nan"))), flush=True)

    (a, b, c), edge_report = edges(pre, post, tag, sign, n)
    del pre, post, tag
    synapses = list(zip(a.tolist(), b.tolist(), c.tolist()))
    del a, b, c

    motor_idx, nuclei, sensory, sprov = sets_by_convention(reg)
    senses = {ch: signal for ch, signal, _, _, _ in SENSORY}
    groups, rule = pk.deal_groups([[i] for i in motor_idx])
    motor = sorted({i for m in pk.MODULES for g in groups[m] for i in g})
    overlap = set(motor) & {i for v in sensory.values() for i in v}
    if overlap:
        raise SystemExit("motor and sensory overlap by %d neurons" % len(overlap))

    reach = reachability(synapses, n, sensory, motor)
    seatable = bool(reach.get("any_channel_reaches_the_motor_set"))
    seat_why = (
        "" if seatable else
        "NOT USABLE AS A SEAT at materialization %d, and the reason is the "
        "DATA, not this mapping. Fish1's axons are largely unproofread: a "
        "presynaptic endpoint lands on a segment that carries a soma only "
        "about 2%% of the time (a postsynaptic one, being near its dendrite, "
        "about 32%%), so only %d of %d synapses -- %.2f%% -- have BOTH ends "
        "on an identified cell. Confirmed independently of this join: asked "
        "how many supervoxels they contain, segments carrying a soma hold "
        "152-5,600 and the unmatched presynaptic segments hold 1-4, which is "
        "a few voxels of neurite; is_latest_roots() says all of them are "
        "current at this version, so they are not stale ids. %d of %d "
        "neurons are left with no edge at "
        "all. Worse, no directed path runs from any sensory channel to any of "
        "the %d motor neurons (%s), so no sense can move this seat however "
        "long it is driven, and PREREGISTRATION.md's first failure condition "
        "-- a seat that never acts -- is guaranteed before a turn is played. "
        "The package is still written, because it is a faithful export of "
        "what this version contains and will become usable as the community "
        "proofreads the axons; data/roster.json records seat: false with this "
        "reason. Re-run against a later materialization to re-test."
        % (version, syn_report["both_endpoints_on_a_soma"], syn_report["rows_fetched"],
           100.0 * syn_report["both_endpoints_on_a_soma"] / max(1, syn_report["rows_fetched"]),
           reach["isolated_neurons"], n, len(motor),
           "; ".join("%s reaches %d neurons in %d hops, 0 motor"
                     % (c, v["reaches"], v["hops"])
                     for c, v in reach["channels"].items())))
    if not seatable:
        print("  *** " + seat_why.split(". ")[0] + " ***", flush=True)

    mece_cite = (
        "The region masks are the source's own, published and world-readable "
        "at gs://fish1-public/mece{0,1,2}_231218 with their names in "
        "segment_properties: the Z-Brain reference atlas (Randlett et al. "
        "2015, Nat Methods 12:1039, doi:10.1038/nmeth.3581) warped onto this "
        "specimen by ANTs, as the Fish1 preprint's Methods describe "
        "(doi:10.1101/2025.06.10.658982) and the FishExplorer companion paper "
        "documents (doi:10.1101/2025.07.14.664689).")
    conv_join = (
        "CONVENTION (not a source annotation), and the only one with any "
        "mechanism in it: NO released table says which region a soma is in, "
        "so tools/fish1_regions.py samples the mask at each soma's own "
        "published centroid -- pt_position at 8x8x30 nm, the masks at "
        "512x512x30 nm, so x and y are divided by 64 and z is used unchanged. "
        "A soma landing on region 0 is outside every mask, is recorded as "
        "unlabelled and is in no channel and no group (%s outside at levels "
        "0/1/2). There is no threshold in this join to move. It was checked "
        "two ways. 96%% of somata land inside a level-0 region, which a wrong "
        "scale would not do. And the atlas agrees with the shape of the soma "
        "cloud about the same axis: read geometrically, with no mask, the "
        "cloud narrows along +x to a tube about 50 um wide about a constant "
        "midline; read from the mask, the level-0 labels come out in "
        "anatomical order along that axis (Forebrain 133-425 um, Midbrain "
        "339-509, Hindbrain 462-750, Spinal Cord 766-981, 2nd-98th "
        "percentiles), and 77%% of the somata in that caudal tube are "
        "labelled Spinal Cord while the rest are labelled nothing."
        % "/".join(str(node_report["outside_every_mece_mask"][c])
                   for c in ("l0", "l1", "l2")))
    conv_sensory = (
        "SOURCE ANNOTATION plus a stated CONVENTION (not a source annotation) "
        "for the grouping and the signal assignment. The SETS are Fish1's own "
        "MECE regions and nothing was picked: every peripheral sensory "
        "structure the annotation distinguishes is used, and each is used "
        "exactly once, so the four channels are the four annotated modalities. "
        "A MECE mask is an atlas REGION and not a per-cell call, so each "
        "channel is SOMATA INSIDE the annotated ganglion rather than "
        "identified sensory neurons, and is over-inclusive; it is reported "
        "that way rather than trimmed. The channels are also very unequal "
        "(%s), an artefact of which peripheral ganglia got soma-segmented, "
        "which docs/fish1-mapping.md records as this mapping's main risk and "
        "which is deliberately NOT evened out. Fish1 annotates a Retina and "
        "it contains NO somata, so the fish has no visual channel at all: a "
        "gap in the data, and no region was promoted to stand in for it. "
        "%s || %s || CONVENTION (not a source annotation), ours: (a) the four "
        "channels group the annotated ganglia BY MODALITY -- smell with the "
        "taste ganglia, the statoacoustic ganglion with the lateral line -- "
        "and (b) which channel carries reward, harm, reserve or threat is "
        "ours, by analogy to Open Fly's sugar, bitter, water and Johnston's "
        "organ. Channels: %s. Both were written into docs/fish1-mapping.md "
        "before the fish played a turn; see that file for the reasoning "
        "channel by channel and for what would count as this mapping being "
        "bad. Convention id: %s."
        % (" / ".join(str(sprov[ch]["neurons"]) for ch, _, _, _, _ in SENSORY),
           mece_cite, conv_join,
           "; ".join("%s = %s (%d cells, %s)"
                     % (ch, sprov[ch]["signal"], sprov[ch]["neurons"],
                        ", ".join(sprov[ch]["regions"])) for ch, _, _, _, _ in SENSORY),
           convention))
    conv_motor = (
        "SOURCE ANNOTATION plus the same stated CONVENTION (not a source "
        "annotation) for the join. %d SOMATA INSIDE THE ANNOTATED CRANIAL "
        "MOTOR NUCLEI -- deliberately not called 'motor neurons', because a "
        "MECE mask is an atlas REGION and not a per-cell call: it is the "
        "Z-Brain atlas warped onto this specimen and sampled at 512 nm "
        "voxels, so a nucleus's mask covers its territory and every soma "
        "lying in it, motor neurons and neighbours alike. A 7 dpf larva has "
        "cranial motor neurons in the hundreds, not thousands, so THIS SET IS "
        "OVER-INCLUSIVE and is reported that way rather than trimmed: any "
        "trimming rule (nearest the centroid, smallest N, densest core) would "
        "be a free parameter we invented with nothing to fix it against. The "
        "same caveat applies to every sensory channel. Selected by a "
        "SUBSTRING RULE and not a hand-written list: every soma whose level-2 "
        "MECE label contains 'motor', case-insensitively. Over the 70 "
        "published level-2 labels that picks out the eight cranial motor "
        "nuclei and nothing else -- %s. The source calls them motor neurons "
        "in those words, which is what PREREGISTRATION.md asks for. %s || %s "
        "|| NOT USED, and "
        "recorded so a later run that swaps them is visibly a different "
        "mapping and not a tuning: the Spinal Cord (a level-0 region with no "
        "level-2 subdivision, so motor neurons and interneurons together, and "
        "calling all of it motor would call interneurons motor neurons), and "
        "the Mauthner cell with the reticulospinal nuclei (RoL2, RoM1-3, "
        "MiV1-2, MiD2-3, CaD, CaV and the rest of the Kimmel set) -- the "
        "fish's descending neurons, which is what Open Fly's own motor set "
        "is, but which the source does not call motor neurons. Dealt into the "
        "39 groups with Open Fly's seed 783 (%s). Convention id: %s."
        % (len(motor_idx), "; ".join(nuclei), mece_cite, conv_join, rule,
           convention))

    meta = {
        "species": "zebrafish_larva",
        "dataset": "Fish1 (%s)" % DATASET,
        "version": "CAVE datastack %s, materialization %d" % (DATASTACK, version),
        "n": n,
        "names": names,
        "lore_ids": [int(i) for i in lore],
        "params": dict(pk.SHIU_PARAMS),
        "sensory": sensory,
        "senses": senses,
        "groups": groups,
        "motor": motor,
        "partition_seed": pk.PARTITION_SEED,
        "window_ms": 200,
        "provenance": {
            "neurons": (
                "Nodes are somas from the `somas` table at materialization %d, "
                "keyed by LORE ID (the stable small integer), which is what "
                "`names` holds as lore<id>. Root ids are the join key to the "
                "synapse tables and are NOT the identity: they change with "
                "proofreading, so the version is stated everywhere. Of the %d "
                "somas released, %d have no segment at this version "
                "(pt_root_id 0) and %d share a root id with another soma "
                "(%d such roots, up to %d somas on one) -- a merge that makes "
                "the cell ambiguous -- so both groups are dropped, leaving %d "
                "nodes."
                % (version, SOMAS_RELEASED, node_report["dropped_no_segment"],
                   node_report["dropped_root_shared_by_several_somas"],
                   node_report["shared_roots"], 19, n)),
            "signs": (
                "Per synapse from `synapses_axde_label` (tag 1 inhibitory, 2 "
                "excitatory) for all %d axon-to-dendrite synapses. A LIF "
                "neuron has ONE sign, so each presynaptic cell takes the "
                "MAJORITY of its own labelled synapses; an exact tie is "
                "UNKNOWN and its synapses are dropped, never assumed "
                "excitatory. %d cells are excitatory, %d inhibitory, %d tied. "
                "%d of %d presynaptic cells (%.1f%%) have synapses that "
                "disagree with each other, which the majority rule resolves. "
                "Checked against the companion confocal vglut2a/gad1b call in "
                "somas.cell_type, which was NOT used to assign the sign: %s."
                % (SYNAPSES_RELEASED, sign_report["excitatory"],
                   sign_report["inhibitory"], sign_report["tie_unknown"],
                   sign_report["cells_whose_synapses_disagree"],
                   sign_report["presynaptic_cells"],
                   100 * sign_report["disagreement_rate_over_presynaptic_cells"],
                   ", ".join("%s %d/%d = %.1f%%"
                             % (k.replace("_", " "), v["agree"], v["cells"],
                                100 * v["agreement"])
                             for k, v in clem.items() if not k.startswith("_")))),
            "sign_validation": clem,
            "sign_report": sign_report,
            "synapses": (
                "%d synapses fetched from `synapses_axde_label` (a reference "
                "table on `synapses_axde`, so one query returns the tag and "
                "both root ids), fetched in disjoint, contiguous ranges of "
                "`target_id` of at most %d rows each -- NOT by limit/offset, "
                "which this server does not order stably at depth and which "
                "silently returned 2.7M of 18.4M rows twice, and as many not "
                "at all. %d "
                "distinct synapse ids, matching the released %d. %d have both "
                "endpoints on a kept soma; the other %d touch a fragment with "
                "no soma in the volume, or a soma dropped above, and are "
                "dropped. %d more are dropped for an unknown (tied) "
                "presynaptic sign and %d are self-synapses. What remains is "
                "%d ordered pairs, each a signed count; %d exceeded int16 and "
                "were clamped to %d (largest pair: %d synapses)."
                % (syn_report["rows_fetched"], SLAB_LIMIT,
                   syn_report["distinct_synapse_ids"], SYNAPSES_RELEASED,
                   syn_report["both_endpoints_on_a_soma"],
                   syn_report["rows_fetched"] - syn_report["both_endpoints_on_a_soma"],
                   edge_report["dropped_unknown_sign"],
                   edge_report["self_synapses_dropped"], edge_report["pairs"],
                   edge_report["pairs_clamped_to_int16"], I16_MAX,
                   edge_report["largest_pair_count"])),
            "synapse_report": syn_report,
            "edge_report": edge_report,
            "gap_junctions": (
                "None. Fish1 releases no gap junction table (the tables are "
                "somas, somas_distance_to_landmark, relaxin_177172_output_"
                "080426, synapses_axax, synapses_axde, synapses_axde_label, "
                "synapses_axde_pre/post_synapse_id and synapses_axon_to_"
                "dendrite_size), so ngap is 0 and w_gap stays 0. Electrical "
                "coupling is real in larval zebrafish -- the Mauthner network "
                "in particular -- and its absence here is a gap in the DATA, "
                "not a claim that there is none."),
            "not_used": (
                "synapses_axax (9.5M axon-to-axon synapses) is left out: the "
                "model has no axo-axonic mechanism, and treating them as "
                "axo-dendritic would be wrong silently. "
                "somas_distance_to_landmark is NOT used as a spatial or "
                "anatomical coordinate: the Fish1 Methods identify the "
                "landmarks as the 9,421 EM-to-LM correspondence points from "
                "iterative point-cloud matching, so the number is a "
                "registration-quality metric, not anatomy. It is used for the "
                "one thing the paper documents it for -- cells 10 um or more "
                "from a landmark are predominantly non-matches, so the "
                "confocal exc/inh label cannot be trusted there -- which "
                "restricts the sign cross-check and nothing else. "
                "relaxin_177172_output_080426 (60 cells: 20 tagged relaxin, 40 "
                "tagged 177172_output) is left out: nothing published ties it "
                "to Fish1 (the preprint contains no occurrence of 'relaxin', "
                "and the lab's CAVE scripts repository has none either), so it "
                "reads as an in-progress user table and is treated as "
                "unannotated. mece3_231218 (21 level-3 regions, including the "
                "retinal arborization fields AF1-AF9) is sampled by neither "
                "the sensory nor the motor rule: AFs are retinal AXON "
                "terminals in the brain, not somata, so they would double-"
                "count the retina."),
            "sensory": conv_sensory,
            "sensory_channels": sprov,
            "mece_regions": "gs://fish1-public/mece{0,1,2}_231218, joined by tools/fish1_regions.py",
            "motor": conv_motor,
            "motor_rule": rule,
            "convention": convention,
            "convention_doc": "docs/fish1-mapping.md",
            "params": (
                "Open Fly's constants from Shiu et al. 2024 (fly LIF), "
                "unchanged; w_gap 0.0 (no gap junctions in the dataset) and "
                "calibrated false -- w_syn is set later by the preregistered "
                "rule in tools/calibrate.mjs, not tuned here. A fly LIF neuron "
                "on zebrafish cells is a stated simplification: no published "
                "model of Fish1 exists."),
            "licence": LICENCE,
            "dropped_unknown_sign": edge_report["dropped_unknown_sign"],
            "validation": {"nodes": node_report, "synapses": syn_report,
                           "signs": sign_report, "edges": edge_report,
                           "sign_against_clem": clem, "reachability": reach},
            "usable_as_a_seat": seatable,
            "why_no_seat": seat_why or None,
            "exported": datetime.date.today().isoformat(),
            "exporter": "tools/fish1_export.py",
            "source_bucket_not_used": (
                "gs://fish1-public holds the same synapses in bulk as "
                "neuroglancer sharded annotations "
                "(syn_241003_agg241003_reorient_axde_ei.precomputed, 1.8 GB), "
                "readable without a token. Not used: its cell ids are flat "
                "seg_241003_agg241003 segment ids, a different id space from "
                "this version's ChunkedGraph root ids, with no published "
                "crosswalk."),
        },
    }
    pk.write_package(out_dir, n, synapses, [], meta)
    bad = pk.check_package(out_dir)
    if bad:
        raise SystemExit("zebrafish_larva: package check failed:\n  " + "\n  ".join(bad))
    size = os.path.getsize(os.path.join(out_dir, "connectome.bin"))
    print("zebrafish_larva: %d nodes, %d ordered pairs (%.1f MB), 0 gap junctions; "
          "signs +%d -%d ?%d; motor %d (%s); %.0fs"
          % (n, len(synapses), size / 1e6, sign_report["excitatory"],
             sign_report["inhibitory"], sign_report["tie_unknown"], len(motor),
             rule, time.time() - t0))
    return {
        "dataset_version": meta["version"],
        "datastack": DATASTACK,
        "dataset": DATASET,
        "server": GLOBAL_URL,
        "materialization": version,
        "exported": meta["provenance"]["exported"],
        "exporter": "tools/fish1_export.py",
        "package": os.path.relpath(out_dir, ROOT),
        "package_bytes": size,
        "sign_source": ("synapses_axde_label, per synapse; one sign per cell by "
                        "majority. Checked against somas.cell_type (confocal "
                        "vglut2a/gad1b), which was not used to assign it."),
        "sensory_motor": ("CONVENTION, not an annotation: see docs/fish1-mapping.md "
                          "and provenance.sensory / provenance.motor. Convention "
                          "id: %s" % convention),
        "licence": LICENCE,
        "counts": {"somas_released": SOMAS_RELEASED, "neurons": n,
                   "synapses_released": SYNAPSES_RELEASED,
                   "synapses_both_ends_on_a_soma": syn_report["both_endpoints_on_a_soma"],
                   "ordered_pairs": edge_report["pairs"],
                   "dropped_unknown_sign": edge_report["dropped_unknown_sign"],
                   "gap_junctions": 0, "motor_neurons": len(motor)},
        "validation": meta["provenance"]["validation"],
        "usable_as_a_seat": seatable,
        "why_no_seat": seat_why or None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materialization", type=int, default=DEFAULT_MATERIALIZATION)
    ap.add_argument("--sensory-convention", choices=sorted(CONVENTIONS), required=True,
                    help="Fish1's sensory and motor SETS come from its own "
                         "published MECE region masks, but joining them to "
                         "somata, grouping them into four channels and "
                         "assigning the game's signals are all ours. There is "
                         "no default, so a run always names the convention it "
                         "used; it is written out in docs/fish1-mapping.md and "
                         "the fish shows it to the viewer as a warning.")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--no-roster", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "species", "zebrafish_larva"))
    args = ap.parse_args()

    if not args.no_fetch:
        fetch(args.materialization)
    block = build(args.materialization, args.sensory_convention, args.out)
    if not args.no_roster:
        path = os.path.join(ROOT, "data", "roster.json")
        d = json.load(open(path))
        for s in d["species"]:
            if s["id"] == "zebrafish_larva":
                s["export"] = block
                s["access"]["materialization"] = args.materialization
                # The roster's `neurons` is the dataset's scale, not the
                # node count: 187,052 somas released, 178,976 of them usable
                # as nodes. The export block carries both.
                s["neurons"] = SOMAS_RELEASED
                # seat: true only if a sense can actually reach an order.
                # `status` is deliberately left alone: its vocabulary
                # (working / candidate / station-only) is read by the page,
                # and seat + why_no_seat already carry the verdict.
                s["seat"] = bool(block["usable_as_a_seat"])
                if not s["seat"]:
                    s["why_no_seat"] = block["why_no_seat"]
                    s["blocker"] = ("Fish1 v%d: axons are unproofread, so only "
                                    "%.2f%% of synapses have both ends on an "
                                    "identified cell and no sensory channel "
                                    "reaches the motor set. Re-test on a later "
                                    "materialization."
                                    % (args.materialization,
                                       100.0 * block["counts"]["synapses_both_ends_on_a_soma"]
                                       / max(1, block["counts"]["synapses_released"])))
                else:
                    s.pop("why_no_seat", None)
        with open(path + ".tmp", "w") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(path + ".tmp", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
