# Fish1: where the zebrafish's senses and orders come from

Written 2026-09-21, before the fish played a single turn. Everything in here is
fixed by `tools/fish1_export.py` and restated in the package's `brain.json`
under `provenance.sensory` and `provenance.motor`, so the page can show it to
the viewer.

The short version: **the sets are the source's own annotation. The join, the
grouping into four channels, and which channel carries which game signal are
ours, and are conventions.** This document separates those three things line by
line, because the seat test in `ROSTER.md` turns on exactly that distinction.

> ## The fish does not get a seat, and the mapping is not why
>
> At materialization 704 **no directed path runs from any sensory channel to
> any motor neuron**, so no sense can move this seat however long it is driven.
> The cause is the state of the data, not this document: Fish1's *axons are
> largely unproofread*, so a presynaptic endpoint lands on a segment carrying
> an identified soma only about 2% of the time. See
> [The wiring is not there yet](#the-wiring-is-not-there-yet) for the numbers.
>
> The mapping below is written out in full anyway, unchanged and before any
> result was seen, because it is the mapping that will be used when the axons
> are proofread — and because a mapping written *after* a re-test would be
> worth nothing.

## What Fish1 annotates, and what it does not

**It does not annotate cell types.** The `somas` table has
`classification_system = "na"` for all 187,052 rows, and `cell_type` is only
`"exc"` (26,915, vglut2a-positive), `"inh"` (14,510, gad1b-positive) and `"na"`
(145,627). That is a neurotransmitter class from the companion confocal light
microscopy, not an anatomical type. There is no released per-cell table naming
retinal ganglion cells, tectal types, hair cells, or motor neurons.

**It does annotate brain regions, publicly and well.** `gs://fish1-public`
holds a four-level, mutually-exclusive-and-collectively-exhaustive region
segmentation on the EM grid, world-readable without a token:

| layer | regions | examples |
|---|---|---|
| `mece0_231218` | 6 | Retina, Forebrain, Ganglia, Midbrain, Hindbrain, Spinal Cord |
| `mece1_231218` | 31 | `Ganglia/Trigeminal Ganglion`, `Hindbrain/Rhombomere 4` |
| `mece2_231218` | 70 | `Hindbrain/Rhombomere 4/Mauthner`, `.../X Vagus motorneuron cluster` |
| `mece3_231218` | 21 | `.../Retinal Arborization Field 5 (AF5)` |

Names are in each layer's `segment_properties/info`. They are the **Z-Brain**
reference atlas (Randlett et al. 2015, Nat Methods 12:1039, doi:10.1038/nmeth.3581)
warped onto this specimen with ANTs, as the Fish1 preprint's Methods describe,
and documented in the FishExplorer companion paper (doi:10.1101/2025.07.14.664689).
Fish1 itself: Petkova, Januszewski, Blakely, Herrera, Schuhknecht et al., "A
connectomic resource for neural cataloguing and circuit dissection of the larval
zebrafish brain", bioRxiv 2025, doi:10.1101/2025.06.10.658982, CC-BY-NC 4.0.

## Convention 1: the join (ours)

**No released table says which region a soma is in.** `tools/fish1_regions.py`
samples the mask at each soma's own published centroid:

- `somas.pt_position` is in 8 x 8 x 30 nm voxels
  (`get_table_metadata("somas")["voxel_resolution"]`).
- the `mece*_231218` layers are 512 x 512 x 30 nm.
- so x and y are divided by 64, z is used unchanged, and the uint64 at that
  voxel is the region id.

A soma whose centroid lands on region 0 is **outside every mask** and is
recorded as unlabelled. It is never guessed at, and an unlabelled soma is in no
sensory channel and in no motor group.

This is a point sample of a warped atlas, so it inherits the registration's
error. It is a convention in the sense that we chose to do it at all; it is not
a free parameter, because there is nothing in it to tune.

Verification that the scaling is right, not assumed. Two things check it.

**96% of somata land inside a level-0 region** (179,772 of 187,052). A wrong
scale would put them nowhere or at random.

**The atlas and the shape of the soma cloud agree about the same axis.** Read
geometrically, with no mask involved, the cloud narrows monotonically along +x
to a tube about 50 um wide and 55 um tall around a constant midline
(y = 263 um), which is a spinal cord and nothing else in a 7 dpf larva has that
shape. Read from the mask, the level-0 labels come out in anatomical order
along the same axis — Forebrain 133–425 um, Midbrain 339–509, Hindbrain
462–750, Spinal Cord 766–981 (2nd–98th percentiles; Hindbrain and Spinal Cord
abut, overlapping over about 11 um, with 318 hindbrain somata caudal of the
most rostral spinal one). 77% of the somata in the narrow caudal tube
(x ≥ 850 um) carry the label `Spinal Cord` and the rest carry none.

## The sensory channels: source annotation, our grouping

Every peripheral sensory structure Fish1 annotates is used, and each is used
exactly once. Nothing was picked; the four channels are the four modalities the
annotation distinguishes.

| channel | MECE regions (verbatim labels) | somas | in the package | game signal |
|---|---|---|---|---|
| `chemosensory` | `Ganglia/Olfactory Epithelium`, `Ganglia/Facial Sensory Ganglion`, `Ganglia/Facial glossopharyngeal ganglion` | 2,844 | 346 | **reward** |
| `trigeminal` | `Ganglia/Trigeminal Ganglion` | 35 | 35 | **harm** |
| `octavolateralis` | `Ganglia/Statoacoustic Ganglion`, `Ganglia/Anterior Lateral Line Ganglion`, `Ganglia/Posterior Lateral Line Ganglia`, and the eight `Ganglia/Lateral Line Neuromast *` | 182 | 48 | **threat** |
| `viscerosensory` | `Ganglia/Vagal Ganglia` | 29 | 5 | **reserve** |

"somas" counts every soma in the region. "in the package" counts those that
survive into the node set, which is somata with exactly one non-zero
`pt_root_id` at this version — 178,976 of 187,052. The peripheral ganglia lose
far more than the brain does (the olfactory epithelium keeps 346 of 2,844),
because they are the least-segmented part of the volume. That is the first
sign of the problem in the next section but one.

### Annotated, and empty

Some regions Fish1 names contain **no soma at all** in this specimen, because
the soma segmentation covers the CNS and some peripheral ganglia but not the
eye or the ear:

`Retina` · `Ganglia/Statoacoustic Ganglion` · `Ganglia/Facial Sensory Ganglion`
· `Ganglia/Facial glossopharyngeal ganglion` · four of the twelve neuromasts

Two consequences, both reported rather than worked around:

- **The fish has no visual channel.** The retina is annotated and has no
  somata, so vision is absent from the mapping. That is a gap in the data, not
  a choice, and no other region was promoted to stand in for it.
- The `octavolateralis` channel is carried by the **lateral line alone**, and
  `chemosensory` by the **olfactory epithelium alone**.

A channel is never refilled from somewhere else to make the numbers look
better.

### Convention 2: which channel carries which signal (ours)

The reasoning, by analogy to Open Fly, which is the only mapping on this stage
that came from a published model:

- **reward = chemosensory.** Open Fly's reward channel is its sugar gustatory
  receptor neurons: appetitive chemosensation. In a fish that is olfaction plus
  the facial and glossopharyngeal taste ganglia. Grouping smell with taste is
  ours; the alternative, splitting them, would have left a modality without a
  signal. (Both taste ganglia sample empty here, so in practice the channel is
  the olfactory epithelium.)
- **harm = trigeminal.** Open Fly's harm channel is its bitter GRNs: the
  aversive one. The trigeminal ganglion is the larval zebrafish's nociceptive
  and somatosensory ganglion.
- **threat = octavolateralis.** Open Fly's threat channel is Johnston's organ,
  the fly's mechanosensory and auditory organ. The statoacoustic ganglion and
  the lateral line are one hair-cell system with the same job, and they are the
  input that drives the larva's escape. (The statoacoustic ganglion samples
  empty, so the lateral line carries it alone.)
- **reserve = viscerosensory.** Open Fly carries reserve — treasury against
  income, a slow homeostatic scalar — on its water-sensing neurons. The vagal
  ganglia are the larva's viscerosensory afferents: internal bodily state,
  which is the closest thing the annotation offers to a homeostatic sense.

### The channels are unequal, and are left that way

346 / 35 / 48 / 5. Every channel becomes 0–200 Hz of Poisson drive per neuron,
so reward reaches the brain with roughly ten times the current of harm and
seventy times that of reserve. Open Fly's channels are 20 / 20 / 18 / 145, and
the sea squirt's 23 / 7 / 14 / 12.

This is an artefact of which peripheral ganglia got soma-segmented, not of
anything about zebrafish. **It is left alone.** Subsampling the olfactory
epithelium down to the size of the others would be exactly the kind of
after-the-fact adjustment `PREREGISTRATION.md` exists to forbid, and it would
be indistinguishable from tuning once a result is in.

It is, in the end, not what stops the fish. That is the next section.

## The motor set: source annotation, mechanical rule

**Motor neurons are every soma whose level-2 MECE label contains the substring
"motor", case-insensitively.** That rule, and not a hand-written list, picks
out exactly these eight published nuclei and nothing else in the 70 level-2
labels:

- `Midbrain/Tegmentum/Oculomotor Nucleus nIII`
- `Hindbrain/Rhombomere 1/Oculomotor Nucleus nIV`
- `Hindbrain/Rhombomere 2/Anterior Cluster of nV Trigeminal Motorneurons`
- `Hindbrain/Rhombomere 3/Posterior Cluster of nV Trigeminal Motorneurons`
- `Hindbrain/Rhombomere 5/VII Facial Motor and octavolateralis efferent neurons`
- `Hindbrain/Rhombomere 6/VII Facial Motor and octavolateralis efferent neurons1`
- `Hindbrain/Rhombomere 7/VII Facial Motor and octavolateralis efferent neurons2`
- `Hindbrain/Caudal Hindbrain/X Vagus motorneuron cluster`

These are the cranial motor nuclei: the source calls them motor neurons, in
those words, and `PREREGISTRATION.md` asks for "the source's own motor set
(… motor neurons for the worm and the sea squirt)". They are dealt into the 39
action groups by `open_animal_stage.package.deal_groups` with Open Fly's seed,
783, unchanged.

### A region is not a cell type, and this set is too big

The join returns **4,287 somata** inside those eight nuclei (**4,254** of them
survive into the node set). A 7 dpf larva does not have four thousand cranial
motor neurons — the real number is in the hundreds.

The reason is structural and is not fixable from this data: **the MECE masks
are atlas regions, not per-cell calls.** They are the Z-Brain atlas warped onto
this specimen, sampled at 512 nm voxels, so a mask named "X Vagus motorneuron
cluster" covers the territory of that nucleus and every soma that happens to
lie in it — motor neurons, neighbouring interneurons, and whatever the
registration error drags in. The honest description of this set is therefore
**"somata inside the annotated cranial motor nuclei"**, not "motor neurons",
and that is how `brain.json` words it.

No threshold is applied to trim it, because any trimming rule — nearest to the
centroid, smallest N, densest core — would be a free parameter invented by us
with nothing to fix it against, and `PREREGISTRATION.md` exists to stop exactly
that. The over-inclusion is recorded instead, here and in the package, as a
known weakness of the mapping. The same caveat applies to every sensory channel
above.

### What was available and is not used, and why

- **The spinal cord.** `Spinal Cord` is a level-0 region with no level-2
  subdivision, so it is spinal motor neurons and spinal interneurons together.
  Calling all of it motor would be calling interneurons motor neurons.
- **The Mauthner cell and the reticulospinal nuclei** (`Rhombomere 4/Mauthner`,
  `RoL2`, `RoM1-3`, `MiV1-2`, `MiD2-3`, `CaD`, `CaV`, and the rest of the
  Kimmel set). These are the fish's descending neurons, and Open Fly's motor
  set is descending neurons, so this is a real alternative. It is not used
  because the cranial nuclei are annotated as *motor neurons* in the source's
  own words and the descending set is not. Recorded here so that a later run
  that swaps them is visibly a different mapping and not a tuning.
- **`somas_distance_to_landmark`.** Now identified: the Fish1 Methods describe
  9,421 EM-to-LM correspondence points established by iterative point-cloud
  matching, and this table is each soma's distance to the nearest one. It is a
  **registration-quality number, not anatomy** — the paper's own rule is that
  cells 10 um or more from a landmark are predominantly non-matches, so the
  `exc`/`inh` label cannot be trusted there. It is used for exactly that, to
  restrict the sign cross-check below, and for nothing spatial.
- **`relaxin_177172_output_080426`** (60 cells: 20 tagged `relaxin`, 40 tagged
  `177172_output`). Nothing published ties it to Fish1 — the preprint contains
  no occurrence of "relaxin", and the lab's CAVE scripts repository has none
  either. It reads as an in-progress user table. Not used.
- **`synapses_axax`** (9.5M axon-to-axon synapses). The LIF model has no
  axo-axonic mechanism and treating them as axo-dendritic would be wrong
  silently.

## Outcome-blindness

None of the numbers or sets above was chosen after seeing a game result,
because none of them can be: they are the published region masks, a substring
rule on the published labels, and a coordinate division fixed by two published
voxel resolutions. There is no threshold in this mapping that can be moved.

The two genuinely free choices are the grouping of the ganglia into four
channels and the assignment of signals to channels. Both are written above,
before the first turn, and `PREREGISTRATION.md` records that a mapping changed
after a result is not a finding about the animal.

## The sign, and the one check that is not us

Signs come from `synapses_axde_label`, a per-synapse call for all 29,474,316
axon-to-dendrite synapses (tag `1` inhibitory, `2` excitatory). A LIF neuron
has one sign, so each presynaptic cell takes the **majority of its own labelled
synapses**; an exact tie is UNKNOWN and its synapses are dropped, as
`docs/species-format.md` requires. The disagreement rate is recorded in
`brain.json`.

`somas.cell_type` — the confocal vglut2a/gad1b call — is **held back from the
export and used only to check it**. It is a different measurement of the same
specimen, made with a different instrument, and it played no part in assigning
the sign. The agreement rate is in `brain.json` under
`provenance.sign_validation`. Measured at version 704:

| cells compared | agreement |
|---|---|
| every cell with a confocal label (7,890) | 55.8% |
| those with ≥ 10 labelled synapses (1,098) | 88.3% |
| those with ≥ 10 and within 10 um of a registration landmark (1,012) | **87.9%** |

The first row is a coin flip because a cell with one or two synapses has no
meaningful majority; the third is the honest one, being the cells where both
measurements are worth trusting — the synapse count is enough for a majority
and the Fish1 paper says the confocal label can be relied on. **Two
independent instruments agree on the sign of about seven cells in eight.**
That is the strongest evidence in this export that the model is built on
something real, and it is the only evidence in it that did not come from us.

For the record: 12,114 cells come out excitatory, 16,165 inhibitory and 2,793
tied (dropped). **40.2%** of presynaptic cells have synapses that disagree with
each other, which the majority rule resolves; 10,880 synapses are dropped for a
tied sign and 94 are self-synapses.

## The wiring is not there yet

This is the finding that decides the seat, and it is about Fish1's
**proofreading state**, not about the mapping above.

Fish1 releases 29,474,316 axon-to-dendrite synapses and 187,052 somata. Joining
one to the other through `pt_root_id` at version 704 gives:

| | share of synapses |
|---|---|
| **post**synaptic endpoint on a segment that carries a soma | ~32% |
| **pre**synaptic endpoint on a segment that carries a soma | ~2% |
| **both** endpoints on an identified cell | **0.80%** (235,703 of 29,474,316) |

The asymmetry is the whole story. A postsynaptic site sits on a dendrite, a few
microns from its own soma, so the automatic segmentation usually has them in
one piece. A presynaptic site sits on an axon, which is thin, long, and breaks
— in a sample of 4M synapses the presynaptic side was spread over **2.18
million distinct segments**, most carrying one or two synapses each. Those are
axon fragments, not cells.

Confirmed a second way, without going through the join at all. Asking the
ChunkedGraph how many supervoxels each segment contains:

| | supervoxels per segment |
|---|---|
| segments that carry a soma | 152, 179, 185, 208, 3,593, 5,600 |
| presynaptic segments that do not | 1, 1, 1, 2, 2, 4 |

A one-supervoxel segment is a few voxels of neurite. `is_latest_roots()` says
all of them are current at this version, so these are not stale ids — they are
what the segmentation currently contains.

So the soma-to-soma graph this export can build is tiny and mostly
disconnected: 148,724 ordered pairs over 178,976 neurons, of which **111,089
(62%) have no edge at all**. The peripheral ganglia, which are the sensory
channels, are the worst-served part of the volume — of the four channels'
346 / 35 / 48 / 5 neurons, only **16 / 2 / 3 / 0** have a single outgoing
synapse. Breadth-first search from each channel therefore dies after one hop,
reaching 347 / 37 / 51 / 5 neurons and **zero** motor neurons, out of 4,254.
(2,067 of those motor neurons do have incoming edges — just never from a
sense.)

**What this is not.** It is not a flaw in the region masks, the sign rule, the
channel grouping or the signal assignment — every one of those is fine and
checks out. It is not something a threshold can fix. And it is not a statement
about zebrafish: it is a statement about how much of one EM volume has been
proofread so far, which will change.

**Why the project's convention rule does not rescue it.**
`PREREGISTRATION.md` ("Conventions adopted where a source has no annotation")
allows taking the narrowest convention that lets a mapping reach the motor set,
and that is how the fly larva's unsigned synapses were handled: its edges
existed and only their *signs* were missing, so a stated assumption about
transmitters put them back. Here the missing thing is the **edges themselves**.
There is no assumption about an unproofread axon fragment that attaches it to a
soma — doing so would be inventing connectivity, which is the one thing no
convention in this project is allowed to do.

**What to do about it.** Nothing, except re-run. The exporter computes the
reachability test every time and writes `provenance.usable_as_a_seat` into
`brain.json`; `data/roster.json` takes `seat` straight from it. When the
community's proofreading attaches enough axons to their somata, the same
command produces a seatable fish with no edits to this document. Re-testing on
a later materialization is the entire remedy.

## What would count as this mapping being bad

`PREREGISTRATION.md` sets the general bar. For the fish specifically:

- The motor set is a few hundred cranial motor neurons out of ~179,000. If the
  fish holds every module on 90% or more of its turns, the mapping does not
  reach the motor set and that is a failure of this document, not a fact about
  zebrafish.
- If the sensory channels turn out to be mostly unlabelled or empty after the
  join, the join is wrong and the mapping must be withdrawn rather than patched
  with a looser threshold.
- The channel sizes are 2,844 / 35 / 182 / 29 (see "The main risk" above). If
  the fish's behaviour is dominated by the reward channel to the point that the
  other three never matter, that is this document's fault and is reported as
  such -- not fixed by resizing a channel after the fact.
- If the fish is indistinguishable from its shuffled control over 20 or more
  games on fresh seeds, that is a null result about the wiring and is reported
  as one.
