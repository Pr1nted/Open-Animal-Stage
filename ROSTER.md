# The roster

One row per candidate, with what is actually known about it. A species does not
get a seat until its row says how the data is obtained, what licence it carries,
and what has to be built before it can act.

Checked 2026-09-21 unless a row says otherwise. Where a row says **verify**, it
means exactly that: nobody has confirmed it and it must not be built on until
somebody has.

---

## Fruit fly, adult female — FlyWire / FAFB

- **Scale** 138,639 neurons, ~15 million synaptic connections.
- **Model** Leaky integrate-and-fire, Shiu et al. (2024), built on FlyWire.
- **Status** **Working.** Open Fly runs it in a browser worker and matches the
  original Brian2 model spike for spike.
- **Reuse** `open_fly/brain.py` and `open_fly/sensory_ids.json`; the brain core
  here should be the same code, not a second copy of it.
- **Licence** Model code MIT (philshiu/Drosophila_brain_model). Connectome per
  FlyWire's own terms — check before redistributing any derived export.

## Fruit fly, adult male — Janelia

- **Scale** verify.
- **Status** **verify, and this is the first question to settle.** The
  well-known male volume is MANC, the male adult *ventral nerve cord*, which is
  not a brain and cannot stand in for one. Whether a male whole-brain or
  whole-CNS reconstruction exists at a usable completeness is unconfirmed.
- **How to check** neuPrint's dataset list (https://neuprint.janelia.org)
  requires a Google login, so a human has to look. Note for whoever does: record
  the dataset name, whether it includes the brain or only the nerve cord, the
  neuron count, and the completeness figure.
- **If it is nerve cord only** then the male fly is not a player. It could still
  be a station — a nerve cord driving legs and wings is a thing worth showing —
  but it is not a seat, and saying otherwise would be the mouse mistake twice.

## Fruit fly, larva — Winding et al. (2023)

- **Scale** 3,016 neurons, whole brain, synapse-resolution.
- **Status** Complete and small, which makes it the cheapest second player.
- **Model** None published that we know of. A LIF model over the published
  connectivity is the obvious approach and is ours to write and preregister.
- **Verify** the exact release form of the connectivity matrix and its licence.

## Roundworm, *C. elegans* — Cook et al. (2019)

- **Scale** 302 neurons (hermaphrodite), 385 (male). Both sexes, whole animal.
- **Status** The only entry that is complete in every sense and has been for
  years. Small enough to run at full detail with no export pipeline at all.
- **Why it matters here** It gives the stage a species where the wiring is not
  in question, so a disagreement between two runs is about our encode and decode
  rather than about missing data.
- **Verify** which release to use, and the gap-junction handling — the worm's
  electrical synapses are not the same thing as chemical ones and a LIF core
  that treats them alike is wrong in a way that will not be obvious.

## Sea squirt larva, *Ciona intestinalis* — Ryan et al. (2016)

- **Scale** ~177 neurons, whole larva.
- **Status** Complete. A chordate, which makes it an interesting neighbour to
  the fish on the same stage.
- **Verify** release form and licence.

## Zebrafish larva, 7dpf — Fish1

- **Scale** 187,053 cell bodies across brain, spinal cord and ganglia.
  26,915 vglut2a-positive and 14,510 gad1b-positive cells.
- **Source** Lichtman and Engert labs (Harvard) with Google Connectomics.
  EM at 4 nm × 4 nm × 30 nm, with companion confocal LM from the same specimen.
- **Access** CAVE Python client (`caveclient`, `cloud-volume`), datastack
  `fish1_full`, dataset `fish1_v250915`, global server
  `https://global.brain-wire-test.org/`. **Requires a personal token** obtained
  by hand through a Google account; it lands in
  `~/.cloudvolume/secrets/cave-secret.json` and must never be committed.
- **Two-level ids** A *lore id* is a small stable integer for a soma. A *root
  id* is a 64-bit segmentation id that **changes when anybody proofreads**.
  Always check `is_latest_roots()`.
- **Pin the materialization version.** The dataset is under active community
  proofreading, so an export is only reproducible against a stated version
  (574 as of 2026-09-21). Record it in `data/roster.json` with every export.
- **Model** None. This is the largest piece of new work on the list: a LIF model
  over Fish1. The neurotransmitter labels are the reason it is feasible at all —
  vglut2a and gad1b give each cell an excitatory or inhibitory sign, which is
  precisely what the Shiu-style core needs and what a bare connectome does not
  have.
- **Status** Plausible, not proven. Nothing should claim the fish plays until a
  model exists and has been validated against something.

## Mouse — MICrONS cubic millimetre

- **Scale** 1.4 × 0.87 × 0.84 mm of a P87 mouse: ~200,000 cells, ~120,000
  neurons, 523 million synapses, spanning all six layers of primary visual
  cortex and three higher visual areas (LM, AL, RL).
- **Functional half** ~75,000 pyramidal neurons with recorded single-cell
  responses to visual stimuli, from two-photon imaging of the same tissue.
- **Status** **Not a player, and not a candidate to become one.** This is visual
  cortex. It has no motor output because it is not a whole brain, and a patch of
  cortex given a seat would be our hand in a puppet.
- **What it can honestly do** Be shown the map and have its response displayed.
  The functional data is literally "these neurons, shown these images, responded
  like this", so showing it something and reporting what happens is the use the
  dataset supports.
- **Access** Dynamic segmentation prompts for a Google login; there are static
  releases too. Verify which to use and the licence on each.

---

## Rejected, and why

Nothing yet. When something is rejected it goes here with the reason, so the
same dataset is not re-investigated every six months.

## The test a species has to pass to get a seat

1. The connectome is released, and we can state its version.
2. Every neuron has a sign, or there is a defensible way to assign one.
3. There is a set of neurons we can honestly call sensory, and a set we can
   honestly call motor — named from the source's own annotations, not chosen by
   us because they gave a good result.
4. The mapping from game to senses and from spikes to orders is written in
   PREREGISTRATION.md **before** the species plays.
5. The model is validated against something that is not us: a published
   simulation, recorded activity, or a documented behaviour.
