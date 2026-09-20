#!/usr/bin/env python3
"""Export the Fish1 larval zebrafish connectome into something a browser can run.

    python3 tools/fish1_export.py --out data/export/fish1
    python3 tools/fish1_export.py --out data/export/fish1 --limit 5000   # a slice

WHAT THIS PRODUCES

    fish1.meta.json      provenance: datastack, dataset, materialization
                         version, counts, and the day it was pulled
    fish1.neurons.npz    one row per cell: lore id, root id, sign
    fish1.synapses.npz   pre, post, weight -- as indices into the neuron table

WHY IT IS A SEPARATE STEP, RUN BY A HUMAN

Fish1 is not a download. It is a CAVE datastack behind a personal token that a
person obtains by hand through a Google account, and the token lands in
~/.cloudvolume/secrets/cave-secret.json and must never be committed. There is no
way to make this run in CI without shipping somebody's credentials, so it does
not try: a human runs it, and what they get is committed as a derived export
somewhere that is not this repository.

WHY THE VERSION IS NOT OPTIONAL

The dataset is under active community proofreading. A root id is a 64-bit
segmentation id that CHANGES when anybody merges or splits a segment; a lore id
is a small stable integer for a soma that does not. So an export is only
reproducible against a stated materialization version, and this writes the
version it used into the metadata rather than leaving the reader to guess.
It also refuses to run without one being pinned or explicitly overridden.

THE SIGN PROBLEM, AND WHY FISH1 CAN BE MODELLED AT ALL

A leaky integrate-and-fire model needs to know whether a synapse excites or
inhibits. A bare connectome does not say -- it says two cells touch, and how
often. The fly model gets its signs from FlyWire's neurotransmitter
predictions. Fish1 has something better: the same specimen was imaged with
confocal light microscopy, and the release reports 26,915 vglut2a-positive and
14,510 gad1b-positive cells. vglut2a marks glutamatergic (excitatory) neurons
and gad1b marks GABAergic (inhibitory) ones.

That is 41,425 of 187,053 cells with a measured sign, which is 22%. The rest
are unlabelled, and what to do with them is a MODELLING DECISION, not a fact:

    --unlabelled excitatory   treat them all as excitatory
    --unlabelled drop         use only labelled cells (the honest small model)
    --unlabelled infer        assign by a rule, which must be preregistered

There is no default. Pick one deliberately, write down why in
PREREGISTRATION.md, and it goes in the metadata so a later reader knows which
model they are looking at.
"""
import argparse
import datetime
import json
import os
import sys

# Pinned. See the module docstring: an export without a version is not
# reproducible, and this dataset moves under the community's proofreading.
DEFAULT_MATERIALIZATION = 574
DATASTACK = "fish1_full"
DATASET = "fish1_v250915"
GLOBAL_URL = "https://global.brain-wire-test.org/"


def need(mod):
    try:
        return __import__(mod)
    except ImportError:
        sys.exit(
            "%s is not installed.\n"
            "    pip install caveclient cloud-volume\n"
            "and obtain a token first -- see ROSTER.md, the zebrafish entry." % mod)


def connect(materialization):
    caveclient = need("caveclient")
    from caveclient import CAVEclient

    # The token is read from ~/.cloudvolume/secrets/cave-secret.json by the
    # client itself. This never reads it, never prints it and never writes it.
    try:
        client = CAVEclient(datastack_name=DATASTACK, server_address=GLOBAL_URL)
    except Exception as e:
        sys.exit("could not reach CAVE (%s).\n"
                 "    A token is obtained by hand: see the Programmatic Access\n"
                 "    page of the Fish1 release, then caveclient.auth." % e)

    latest = client.materialize.most_recent_version()
    if materialization is None:
        materialization = latest
        print("  no version pinned; using the most recent (%s)" % latest)
    elif materialization != latest:
        # NOT an error. Pinning an older version on purpose is the whole point
        # of pinning, and being told the tree has moved is the useful part.
        print("  pinned to materialization %s; the most recent is %s"
              % (materialization, latest))
    client.materialize.version = materialization
    return client, materialization


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="directory for the export")
    ap.add_argument("--materialization", type=int, default=DEFAULT_MATERIALIZATION,
                    help="pin the version; 0 means 'whatever is newest', which "
                         "makes the export unreproducible and says so")
    ap.add_argument("--unlabelled", choices=["excitatory", "drop", "infer"],
                    required=True,
                    help="what to do with the 78%% of cells that carry neither "
                         "a vglut2a nor a gad1b label. There is no default: it "
                         "is a modelling decision and belongs in the "
                         "preregistration, not in an argparse line.")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many neurons, for a smoke test")
    args = ap.parse_args()

    version = None if args.materialization == 0 else args.materialization
    client, version = connect(version)

    os.makedirs(args.out, exist_ok=True)
    meta = {
        "dataset": DATASET,
        "datastack": DATASTACK,
        "server": GLOBAL_URL,
        "materialization": version,
        "pulled": datetime.date.today().isoformat(),
        "unlabelled_policy": args.unlabelled,
        "limit": args.limit or None,
        "_note": "root ids in this export are only valid at this "
                 "materialization; lore ids are stable across all of them",
    }

    print("  tables: %s" % ", ".join(sorted(client.materialize.get_tables())[:12]))
    # The rest -- pulling somas, labels and synapses -- is written against the
    # table names that listing prints. They are NOT guessed here: the Fish1
    # notebook is the source, and the first person with a token fills this in
    # from what the listing above actually says, rather than from a name that
    # looked right in a docstring.
    with open(os.path.join(args.out, "fish1.meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("  wrote %s/fish1.meta.json" % args.out)
    print()
    print("  NOT YET COMPLETE: the soma, label and synapse queries are the next")
    print("  step and need the table names the line above prints. Run this with")
    print("  a token, paste the table list into ROSTER.md, and fill them in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
