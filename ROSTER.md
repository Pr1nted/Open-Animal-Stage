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
  FlyWire's release data is CC BY-NC 4.0 (https://flywire.ai/guidelines), as
  Open Fly's web/data/LICENSE.txt records: non-commercial.
- **Exported (verified 2026-09-21)** `tools/export_female_fly.py` re-encodes
  Open Fly's `web/data/connectome.bin` (SFC1) and `brain.json`, read in place,
  into `web/species/drosophila_female/` (OAS1, ngap 0). 138,639 neurons and
  15,091,983 signed connections (54,492,922 synapses), the same bytes behind a
  new header; 0 dropped for sign. Names are FlyWire root ids from
  `Completeness_783.csv`. Groups, sensory lists and the 1,299 descending
  neurons are Open Fly's; re-dealing them from FlyWire's annotations with the
  copied `make_groups` reproduces them exactly, and the test compares them to
  Open Fly's brain.json neuron for neuron. Senses: sugar (20 LB3) reward,
  bitter (20 LB1a-d) harm, water (17 LB3 + 1 LB2d) reserve, Johnston's organ
  (145) threat. connectome.bin 91.1 MB, packed as Open Fly packs it (5 plain
  parts); brain.json 2.9 MB.

## Fruit fly, adult male — MaleCNS v1.0

**Answered 2026-09-21, and the answer is better than expected.** The open
question was whether a male *brain* existed or only MANC, the male ventral nerve
cord. It does.

- **Scale** 166,691 neurons, annotated into 11,691 cell types.
- **Coverage** The complete male central nervous system: brain, optic lobes,
  neck connective and ventral nerve cord. Every neuron reconstructed and
  proofread, every synapse detected.
- **Neurotransmitters predicted**, which means the sign problem is already
  solved here — the same reason the female fly is runnable.
- **Released** 8 June 2026, by FlyEM (HHMI Janelia) with the University of
  Cambridge, the MRC Laboratory of Molecular Biology and Google Research.
- **Licence** CC-BY 4.0. The most permissive on this list by a distance: a
  derived export can be redistributed with attribution, which is not true of
  every other entry.
- **Access** neuPrint, and the `malecns` natverse R package
  (https://natverse.org/malecns/). https://male-cns.janelia.org/
- **Status** **Strong candidate, and probably the second seat.** Complete, signed,
  permissively licensed, and comparable in scale to the female (138,639 vs
  166,691) — which makes male-against-female the one cross-species pairing on
  this stage where the two brains are close enough in size and kind that the
  comparison is not absurd on its face.
- **No token needed (verified 2026-09-21).** The flat connectome is a public
  bucket, `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/`, readable
  over plain HTTPS at storage.googleapis.com. `tools/export_male_fly.py` fetches
  the body annotations (14 MB), body neurotransmitters (43 MB) and
  connectome weights (1.05 GB, minconf 0.5) into `data/raw/malecns_v1.0/`;
  sha256 of each in `data/roster.json`.
- **Exported** `web/species/drosophila_male/`, the female's mapping restated in
  MaleCNS names. Neurons = every body with a superclass: **166,700**, nine more
  than the announced 166,691, not explained. 25,582,938 neuron→neuron edges
  (124 M synapses); signs by the FlyWire rule on `consensus_nt`; 677,985 edges
  (2.7%) dropped as unknown — histamine (7,891 neurons; FlyWire never predicts
  it, so the rule has no answer), `unclear` (2,999) and no call (178).
- **Senses** Left side, as the female's. Labellar GRN receptor identities are
  from Tastekin et al. (bioRxiv 10.1101/2025.08.25.671814), which names the
  MaleCNS types: sugar LB3b+LB3c (Gr64f), 17 neurons (female 20); water LB3a
  (ppk28), 9 (female 18); bitter LB1a-d (Gr33a), 19 (female 20). Johnston's
  organ by `flywireType` in the female's type list: 264 (female 145, a subset
  Shiu et al. chose). **Not matched:** FlyWire does not split LB3 and MaleCNS
  does, so the male's sugar/water split rests on the GAL4 matches, not on the
  female's lists; the female's one LB2d water neuron has no published receptor
  identity and has no male counterpart here; `JO-unclear` has no flywireType
  in MaleCNS (7 left JO bodies unmatched).
- **Motor** superclass `descending_neuron`, 1,314 neurons in 484 cell types
  (female 1,299), dealt by the female's rule and seed. Left out:
  `descending_neuron_tbc` (2), `sensory_descending` (12).
- **Size** connectome.bin 150.1 MB in 8 plain 20 MiB parts; brain.json 1.5 MB.
  `calibrated: false` — Shiu et al.'s constants are the female's, untuned.

### Prior art worth reading before building this

`zhengxuyu/nfly` treats MaleCNS v1.0 as a recurrent network that plays
Gymnasium environments, and `IONOFIELD/FLYCNS` is a benchmarked spiking
simulation of the same dataset. Neither is this project — a Gymnasium
environment is not Open Doctrines and an RNN is not a LIF model — but somebody
has already taken this connectome and made it act, and reading how they mapped
inputs and outputs is worth an afternoon before we write ours.

## Fruit fly, larva — Winding et al. (2023)

- **Scale** 3,016 neurons, whole brain, synapse-resolution.
- **Status** Complete and small, which makes it the cheapest second player.
- **Model** None published that we know of. A LIF model over the published
  connectivity is the obvious approach and is ours to write and preregister.
- **Release (verified 2026-09-21)** Data S1 of the paper, mirrored at
  github.com/brain-networks/larval-drosophila-connectome: a 2,952 × 2,952
  summed matrix (rows presynaptic; equals aa+ad+da+dd), 352,611 synapses on
  110,677 edges — the paper's 3,016 neurons and 548,000 synapses include
  neurons and sites outside the analysed matrix. Licence: supplementary
  material of a Science paper, no open licence stated; cite it and treat the
  export as not cleared for redistribution until asked.
- **Signs are the problem.** Data S1 has no neurotransmitters. The only
  released per-neuron labels found are the first author's 'mw neurotransmitter'
  annotations in the paper's public CATMAID (Virtual Fly Brain L1 CNS): 243 of
  2,952 neurons (151 cholinergic, 42 GABA, 26 glutamate, 4 GABA+glutamate,
  14 dopamine, 6 octopamine). Under the drop rule **89% of edges (98,385 of
  110,677) and 82% of synapses are dropped.** The author's 2023 CNN predictions
  (mwinding/brain_models) are not among the public CATMAID's annotations.
- **Exported, but not playable as it stands** `tools/export_larva.py` →
  `web/species/drosophila_larva/`. Senses from annotations.csv, both sides:
  olfactory 42 (reward), noci 6 (harm), gut 85 (reserve), mechano-Ch 12
  (threat). Only olfactory has any signed outgoing synapse — **harm, reserve
  and threat reach no neuron.** Motor: DN-VNC 182 + DN-SEZ 164 = 346, pairs
  dealt together; 159 of them get any signed input.

## Roundworm, *C. elegans* — Cook et al. (2019)

- **Scale** 302 neurons (hermaphrodite), 385 (male). Both sexes, whole animal.
- **Status** The only entry that is complete in every sense and has been for
  years. Small enough to run at full detail with no export pipeline at all.
- **Why it matters here** It gives the stage a species where the wiring is not
  in question, so a disagreement between two runs is about our encode and decode
  rather than about missing data.
- **Release (verified 2026-09-21)** WormWiring.org, SI 5 "Connectome adjacency
  matrices, corrected July 2020" and SI 4 "Cell lists" (Cook et al. 2019). The
  chemical weight is Cook's number of EM serial sections of connectivity
  (number and size of synapses, with extrapolated connections), not a synapse
  count. `tools/export_celegans.py` → `web/species/c_elegans_{herm,male}/`;
  URLs and sha256 of every raw file are in `data/roster.json` `export`.
- **Counts** Hermaphrodite 302 neurons (paper 302); all-cell edges 4,879
  chemical and 1,450 gap (paper 4,887 and 1,447). Male 385 (paper 385); 5,306
  and 1,758 (paper 5,315 and 1,755). Neuron→neuron: 3,709 / 4,048 chemical
  edges, 1,091 / 1,281 gap pairs.
- **Signs** Wang et al. 2024 (eLife 13:RP95402, CC-BY 4.0), both sexes, through
  `signs.transmitter_sign`: glutamate excitatory by rule (GluCl exceptions
  admitted, not modelled), co-transmitting and monoamine-only cells unknown.
  548 (hermaphrodite) / 658 (male) chemical edges dropped for unknown sign.
- **Gap junctions** Kept as their own array (SI 5 symmetric sheet, pairs once),
  never folded into chemical synapses; `w_gap` is 0 until the JS brain's
  calibration rule sets it.
- **Licence** No open licence on the SI files or WormWiring (© Emmons lab 2020;
  Springer Nature paper). **The derived export is not cleared for
  redistribution** until the authors are asked.
- **Senses** attractive chemosensory ASE/AWA/AWC = reward, nociceptive ASH/ADL
  = harm, O2/CO2 URX/BAG = reserve, gentle touch ALM/AVM/PLM/PVM = threat —
  all from SI 4's own modality notes. Motor: SI 4 "motorneuron", 126 / 118.

## Sea squirt larva, *Ciona intestinalis* — Ryan et al. (2016)

- **Scale** 177 CNS neurons, 6,618 synapses — of which 1,772 are neuromuscular
  junctions — plus **1,206 gap junctions**.
- **Published** eLife 2016, 10.7554/eLife.16962. The first connectome obtained
  from a single individual, which is a property none of the large datasets have.
- **Status** Complete. A chordate, which makes it the fish's nearest relative on
  this stage and the cheapest one to run.
- **The gap junctions are not a footnote.** 1,206 electrical synapses against
  6,618 chemical ones is a fifth of the wiring, and a LIF core that treats an
  electrical synapse as a chemical one is wrong in a way nothing will report.
  Same caveat as *C. elegans*, and worse in proportion.
- **Release (verified 2026-09-21)** eLife Figure 16 source data 1 (chemical)
  and 2 (gap, partners > 0.12 µm) as Excel matrices of cumulative contact
  depth in µm per cell pair — not per-synapse lists — with cell types from
  Figure 1 and Figure 3 source data. **Licence CC-BY 4.0**, so a derived export
  can be redistributed with attribution.
- **Counts** 180 CNS neurons found against the paper's 177 (the released tables
  disagree with each other by a few cells; held to ±5), plus 27 peripheral
  sensory neurons that appear in the matrices: 207 nodes. 2,976 neuron→neuron
  chemical pairs and 410 gap pairs. The paper's 6,618 synapses and 1,206 gap
  junctions are counts of contacts and cannot be recomputed from the matrices.
- **Signs** By cell class from Kourakis et al. 2019 (eLife 8:e44753, CC-BY
  4.0). Three classes (PR-I, pr-AMG RN, AntRN) are assigned from majority
  statements; most brain-vesicle interneurons have no published transmitter,
  so 110 of 207 neurons are unknown and 1,313 chemical pairs are dropped.
- **Senses** PR-I = reward, PR-II (dimming/escape) = harm, coronet = reserve
  (modality not established — the weakest mapping), rostral trunk epidermal
  mechanosensory neurons = threat. Motor: MN1–5 L/R + 4 midtail motor neurons =
  14, dealt round-robin. `tools/export_ciona.py` → `web/species/ciona_larva/`.

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
- **Paper** Petkova, Januszewski, Blakely, Herrera, Schuhknecht et al., "A
  connectomic resource for neural cataloguing and circuit dissection of the
  larval zebrafish brain", bioRxiv 2025, doi:10.1101/2025.06.10.658982,
  CC-BY-NC 4.0. Companion: FishExplorer, doi:10.1101/2025.07.14.664689.
- **Two-level ids** A *lore id* is a small stable integer for a soma. A *root
  id* is a 64-bit segmentation id that **changes when anybody proofreads**.
  Always check `is_latest_roots()`.
- **Pin the materialization version.** The dataset is under active community
  proofreading, so an export is only reproducible against a stated version.
  **574 is expired**; the server offers 686, 698, 700, 702, 703, 704, and the
  export is pinned to **704**. Record it in `data/roster.json` every time.
- **Tables** (v704) `somas` 187,052 · `somas_distance_to_landmark` ·
  `synapses_axde` 29,474,316 · `synapses_axde_label` (the same rows with
  `tag` 1 = inhibitory, 2 = excitatory) · `synapses_axax` ·
  `synapses_axde_pre/post_synapse_id` · `synapses_axon_to_dendrite_size` ·
  `relaxin_177172_output_080426` (60 cells, nothing published about it).
  `synapses_axde_label` is a *reference table* on `synapses_axde`, so one query
  returns the tag and both root ids.
- **Do not page this server with limit/offset.** It does not order rows stably
  at depth. Paging 29.5M rows 200k at a time returned **2.7M of 18.4M rows
  twice** — 8 of 91 adjacent page pairs overlapped, by up to 37,492 rows — and
  therefore never returned as many others. Nothing in the response says so.
  Page by disjoint, contiguous ranges of `target_id` instead (a flat
  `filter_greater_dict`/`filter_less_dict`; the *keyed* form and any filter on
  a joined table's column both 500), split a range whenever it comes back full,
  and check the total against the released row count at the end.
  `tools/fish1_export.py` does all four.
- **Signs are solved, per synapse.** `synapses_axde_label` calls every one of
  the 29.5M axon-to-dendrite synapses excitatory or inhibitory. A LIF neuron
  needs one sign per cell, so a cell takes the majority of its own (40.2% of
  presynaptic cells disagree with themselves; an exact tie is dropped). The
  confocal vglut2a/gad1b call in `somas.cell_type` is **held back from the
  export and used to check it**, which is the only validation in the package
  that does not come from us: the two instruments **agree on 87.9%** of the
  1,012 cells where both are trustworthy (≥ 10 labelled synapses and within
  10 um of a registration landmark).
- **Region annotation exists and is public.** `gs://fish1-public/mece{0,1,2,3}_231218`
  are a four-level MECE brain-region segmentation with names in
  `segment_properties` — the Z-Brain atlas (Randlett et al. 2015) warped onto
  this specimen. They name the trigeminal, statoacoustic, lateral line, vagal
  and olfactory ganglia, the Mauthner cell, the reticulospinal nuclei and the
  cranial motor nuclei. **No released table joins them to somata**; that join
  is ours and is written down in [docs/fish1-mapping.md](docs/fish1-mapping.md).
  `somas.classification_system` is "na" for every row — there is no cell-type
  annotation, only regions.
- **No gap junctions** are released. `ngap` is 0 and `w_gap` stays 0. Electrical
  coupling is real in this animal; its absence here is a gap in the data.
- **The bulk bucket does not rescue it either (measured 2026-09-21).**
  `gs://fish1-public` holds the same 29,474,316 synapses as neuroglancer
  sharded annotations (1.8 GB, same e/i call), keyed by the automated
  agglomeration `seg_241003_agg241003`. `tools/fish1_agglomeration.py` joins it
  to the somata by sampling the agglomeration at each centroid, and
  `tools/fish1_export.py --wiring agglomeration-241003` builds from it: 1.60% of
  presynaptic endpoints on a soma (v704 1.83%), 0.72% both ends (v704 0.80%),
  no sense reaches a motor neuron. It is the segmentation the ChunkedGraph was
  seeded from; the axons are fragmented in both. The package stays on
  `--wiring proofread-v704`. Numbers in docs/fish1-mapping.md.
- **Model** Open Fly's LIF (Shiu et al. 2024) over Fish1, uncalibrated at
  export; `tools/calibrate.mjs` sets `w_syn` by the preregistered rule. There
  is no published Fish1 model, so the neuron is a stated simplification.
- **The axons are not proofread, and that is the blocker.** Joining the
  synapses to the somata at v704: a **post**synaptic endpoint lands on a
  soma-bearing segment ~32% of the time, a **pre**synaptic one ~2%, and **both
  0.80%** (235,703 of 29,474,316) — the presynaptic side is spread over
  millions of one-synapse axon fragments. Confirmed without the join: asked how many supervoxels they hold,
  soma-bearing segments hold 152–5,600 and unmatched presynaptic segments hold
  1–4, and `is_latest_roots()` says every one of them is current, so they are
  fragments and not stale ids. The soma-to-soma graph that remains is mostly
  disconnected, and
  **no directed path runs from any sensory channel to any motor neuron**, so no
  sense can move the seat. This is a fact about how much of the volume has been
  proofread, not about the mapping or the animal.
- **Senses moved into the brain (2026-09-21).** Since no peripheral sense
  reaches a motor neuron, the fish senses through four brain nuclei:
  `brain-nuclei-v1` — pretectum = reward, tectum (periventricular layer) =
  threat, medial vestibular nucleus = harm, tangential vestibular nucleus =
  reserve. The rule is "the four first-order sensory nuclei the atlas names
  that have a path to the motor set at v704, one per signal"; the pairing of
  nucleus to signal is ours. It replaces the ganglia convention, is recorded in
  PREREGISTRATION.md, and is shown to the viewer as a warning. On the proofread
  v704 wiring every channel reaches the motor set: 1,600 / 1,582 / 1,572 /
  1,576 of 4,254 motor-nucleus somata.
- **Status** **Plays** (calibrated k = 4, w_syn = 4.4; ladder 0% 0% 2% 23%
  83% against the fly's 74.4%). `tools/fish1_regions.py` then
  `tools/fish1_export.py --sensory-convention brain-nuclei-v1` →
  `web/species/zebrafish_larva/`. What follows is the history of the original
  peripheral-ganglia convention, kept because it is why the senses moved. The mapping is preregistered in
  `docs/fish1-mapping.md` and is committed unchanged so that a later re-test
  cannot be a re-tuning; the exporter runs the sensory→motor reachability test
  every time and `data/roster.json` takes `seat` straight from it, so the fish
  seats itself when a later materialization supports it. Secondary weaknesses,
  recorded before any result: the four channels are unequal (346 / 35 / 48 / 5)
  and there is **no visual channel** — the retina is annotated and contains no
  somata.

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

**Platynereis dumerilii larva.** What is complete is the *visual* connectome
(eLife 4:e08069), not the animal. A visual circuit has the same problem the
mouse has — it is a part, and giving a part a seat means supplying the rest of
the animal ourselves. Revisit if a whole-larva reconstruction is released.

**Mouse, as a player.** Kept on the roster as a station; see its entry. Recorded
here too so nobody re-proposes it as a seat.

**Zebrafish spinal cord (10%) and pre-differentiation whole brain.** Superseded
for our purposes by Fish1, which is the same animal at a usable completeness.

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
