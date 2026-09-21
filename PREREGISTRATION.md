# Preregistration

Open Fly wrote down how a game event reaches the brain and how spikes become an
order **before the fly played**, because a mapping tuned after seeing a result is
not a finding about the animal, it is a finding about the tuning. The same rule
holds here, once per species, and one more rule on top of it that Open Fly did
not need.

## The rule Open Fly did not need

**A stage with two animals on it compares two mappings, not two animals.**

If a fly outscores a worm, the honest reading is that the encode and decode we
wrote for the fly convert Open Doctrines into spikes and back more usefully than
the pair we wrote for the worm. It is not evidence that flies are better at
strategy than worms. It is barely evidence about the brains at all.

So every pairing result is reported with both mappings named, and no pairing
result is described as one species beating another.

The one comparison that is fair is a species against **itself** under two
mappings, or a mapping against a **shuffled control** — the same brain with its
connections permuted, which is the only opponent that holds the mapping fixed
and varies the wiring.

## Per species, before it plays

Each species gets a section below, committed before its first run, stating:

1. **The senses.** Which neurons, named from the source's own annotations, and
   what game quantity drives each. Open Fly's version: land gained and a surplus
   are sugar, land lost and a deficit and new wars are bitter, treasury is water,
   war count drives Johnston's organ.
2. **The clock.** How much simulated time runs per turn, and why that number.
3. **The actions.** Which neurons are read, how they are grouped, and how a
   group becomes one of the game's orders.
4. **What would count as the mapping being bad**, written before the run.

## Rules for every seat, written 2026-09-21 before any calibration ran

**The game reaches every animal the same way.** Four numbers, computed exactly
as Open Fly computes sugar, bitter, water and Johnston's organ
(`web/decide.js`): *reward* (land gained + surplus), *harm* (land lost +
deficit + new wars), *reserve* (treasury against income), *threat* (wars).
Each becomes 0–200 Hz of Poisson input with a 10 Hz floor. A species states
which of its own sensory channels carries which number, named from its source's
annotations (`provenance.sensory` in its brain.json), and nothing else about the
encoding differs between animals.

**Orders come out the same way.** The source's own motor set (descending
neurons for flies, motor neurons for the worm and the sea squirt) is dealt into
the game's 39 action groups with Open Fly's seed, 783, and read by Open Fly's
`choose()`, unchanged: the most active legal action per module up to the budget,
silent actions not taken.

**Every seat is an AI country with its policy switched off** (see
`patches/opendoctrines-stage.patch`). The game's reflexes that are not the policy
-- districts, disclosure, answering incoming diplomacy -- run for every seat
alike. The viewer is the spectator; no seat is the player.

**Seats move in rotating order**, all reading the same world before any moves.

## The neuron, and how its one free constant is set

Every species runs Open Fly's neuron (Shiu et al. 2024): the same equations and
the same constants. For the **female fly** that is the published model. The
**male fly** keeps those constants unchanged too, because the same model on both
sexes is the point of that pairing.

The **worm, the sea squirt and the fly larva** have no published model. Most
worm neurons are graded rather than spiking, so a spiking neuron is a stated
simplification for them. Their synapse counts come from different
reconstructions at different scales, so a synaptic weight that suits FlyWire's
counts need not suit theirs. For these three species only, `w_syn` is set by this
rule, and by nothing else:

1. **The measure.** Drive every sensory channel at 100 Hz (mid-scale) for one
   200 ms window, seeds 1 to 5. Record the fraction of the 39 action groups in
   which at least one neuron spiked, averaged over the seeds.
2. **The target.** The same measure for the female fly under the same drive:
   the one brain on the stage with a validated model.
3. **The ladder.** `w_syn = 0.275 × 2^k` for k = 0, 1, …, 10. The species gets
   the smallest k whose measure reaches the target. If none does, it gets k = 10
   and says so.
4. **Electrical synapses** (worm, sea squirt): `w_gap = 1`, so a one-contact
   junction conducts as much as the membrane leaks. That is fixed, not searched.

No game is played during calibration, and no game result may change these
numbers. `tools/calibrate.mjs` implements the rule and writes what it measured
into each brain.json's `params.calibrated`.

## Conventions adopted where a source has no annotation, 2026-09-21

A convention is our claim about an animal, written down before that animal
plays, and shown to the viewer beside it. The rule for adopting one: take the
**narrowest** convention that lets the mapping reach the motor set at all,
judged by the calibration measure above, which is activity and not game results.

**Fly larva, transmitters.** Only 243 of 2,952 neurons have a published
transmitter, so on published signs alone three of the four senses reach no
neuron and the larva holds every turn. Insect sensory neurons are
overwhelmingly cholinergic, so the larva's *annotated sensory neurons* are
assumed cholinergic (excitatory) and nothing else is:
`tools/export_larva.py --unsigned sensory-cholinergic`. It then reaches the
calibration target at k = 5. The broader `--unsigned all-cholinergic` keeps the
whole connectome and reaches it at k = 1, and is not used, because assuming a
transmitter for 2,606 unannotated cells claims more about the animal than
leaving unmeasured connections out. 88% of the larva's connections are dropped
as unsigned, and that is a fact about this seat, not a detail.

**Zebrafish, senses: four brain nuclei (`brain-nuclei-v1`), adopted
2026-09-21, before any game.** It **replaces** the peripheral-ganglia
convention `mece-ganglia-v1` below; it does not extend it. Fish1's peripheral
sensory cells have almost no traced synapses (the 346 olfactory, 35
trigeminal, 48 lateral-line and 5 vagal ganglion cells send 88 synapses
between them at v704), so no peripheral sense reaches a motor neuron. The
rule: **the four first-order sensory nuclei the atlas names that have a path
to the motor set at v704, one per game signal.** The olfactory bulb and the
area postrema were tested and reach none; the atlas names no trigeminal
sensory nucleus. `Pretectum` = reward, `Tectum/Stratum Periventriculare` =
threat, `Medial Vestibular Nucleus` (r5 and r6 parts) = harm, `Tangential
Vestibular Nucleus` (r5 and r6 parts) = reserve. **Which nucleus carries which
signal is our pairing, not biology.** These are second-order neurons, and the
fish now sees, which it could not before. It was chosen on reachability — the
directed path from each channel to the motor set in the proofread v704 wiring
— and not on any game result; the motor set, the wiring and the sign rule are
unchanged. The page shows it as a warning beside the fish. The automated
agglomeration `seg_241003_agg241003` was also tried as a wiring source and
gave no path from any peripheral sense either (docs/fish1-mapping.md), so the
wiring stays the proofread one.

## What would count as a mapping being bad, written before the first game

- **A seat that never acts.** Holding every module on 90% or more of its turns
  means the mapping does not reach the motor set, whatever the wiring does.
- **A seat indistinguishable from its shuffled control** over 20 or more games
  on fresh seeds. That is not a bad mapping, it is a null result about the
  wiring, and it is reported as one.
- **A pairing result described as one species beating another.** Never, in
  any form.

## Per species

Each species' channels, their annotations and its motor set are in its
brain.json `provenance`, written by its exporter in `tools/`. The female fly's
are Open Fly's, restated unchanged: sugar, bitter and water gustatory receptor
neurons and Johnston's organ, and 1,299 descending neurons.

### Zebrafish larva, 7 dpf (Fish1) — written 2026-09-21, before its first turn

Fish1 is the first species on this stage whose sensory and motor sets needed a
**stated convention on top of the annotation**, so it gets its own document:
**[docs/fish1-mapping.md](docs/fish1-mapping.md)**, which is normative and is
summarised in the package's `brain.json` for the page to show the viewer.

1. **The senses.** Named from Fish1's own published MECE region masks
   (`gs://fish1-public/mece{0,1,2}_231218` — the Z-Brain atlas warped onto this
   specimen): `chemosensory` (olfactory epithelium and the facial and
   glossopharyngeal taste ganglia) = reward, `trigeminal` = harm,
   `octavolateralis` (statoacoustic ganglion and lateral line) = threat,
   `viscerosensory` (vagal ganglia) = reserve. **Three things are ours and are
   conventions**: the join (no released table says which region a soma is in,
   so the mask is sampled at the soma's published centroid), the grouping of
   the ganglia into four channels by modality, and which channel carries which
   signal. All three are in the document above, and in
   `provenance.sensory`/`provenance.motor` marked "CONVENTION (not a source
   annotation)".
2. **The clock.** 200 ms per turn, as every other species on this stage.
3. **The actions.** Every soma whose level-2 MECE label contains "motor" — the
   eight published cranial motor nuclei (nIII, nIV, the two nV trigeminal
   motorneuron clusters, the three VII facial motor clusters, the X vagus
   cluster) — dealt into the 39 groups with seed 783 and read by Open Fly's
   `choose()`, unchanged. The spinal cord and the reticulospinal/Mauthner set
   were available and are **not** used; the document says why, so that a later
   run that swaps them is visibly a different mapping and not a tuning.
4. **What would count as the mapping being bad.** The general bar above, plus
   one specific to the fish: its four channels are 346 / 35 / 48 / 5 neurons,
   an artefact of which peripheral ganglia happen to be soma-segmented. If
   reward drowns the other three, that is this mapping's fault and is reported
   as such. **The channel sizes are not to be evened out after a result is
   seen**, which is the whole point of writing them here first. The fish also
   has **no visual channel at all**: the retina is annotated and contains no
   somata.

**Superseded 2026-09-21 for the senses**: see `brain-nuclei-v1` under
"Conventions adopted". Item 1 above is the original, peripheral-ganglia
convention, kept as written; the reachability finding below is why it was
replaced.

**And it did not get a seat under it, for a reason that is not the mapping.** At
materialization 704 Fish1's axons are largely unproofread, so only about 0.8%
of its 29,474,316 synapses have both endpoints on an identified soma, and no
directed path runs from any sensory channel to any motor neuron. A seat that
cannot be moved by any sense fails the first condition above before a turn is
played. The exporter measures this every run and writes it to
`provenance.usable_as_a_seat`; `data/roster.json` takes `seat` from it, so the
fish seats itself automatically once the data supports it. The mapping above is
committed now, unchanged, precisely so that the re-test cannot be a re-tuning.

Its sign is not a convention: `synapses_axde_label` calls every one of the
29,474,316 synapses inhibitory or excitatory, a cell takes the majority of its
own, and the result is checked against the confocal vglut2a/gad1b call that was
held back from the export.

## The benchmark, written 2026-09-21 before it ran

`tools/stage_bench.mjs` with `bench/plan-v1.json`. Every player takes the same
seat on the same world seed, alone against the game's AI, for 120 turns: seats
1914:FRA, 1914:GER, 1914:SWE and 1939:USA, seeds 7001 to 7005 (fresh: nothing
on this stage was calibrated or looked at on them). Players: each of the seven
animals that plays, each of them with its wiring shuffled (seed 783), *hold*
(does nothing) and *random* (random legal moves up to the budget).

**Score:** land share at the end minus at the start, in percentage points; a
country wiped out ends on zero. **Comparisons are paired** on the same seat and
seed, with 95% bootstrap intervals. A difference whose interval contains zero is
reported as **no difference**, not as a ranking.

**What each comparison is allowed to mean, decided now:**
- *animal vs hold*: whether the mapping does anything useful at all.
- *animal vs random*: whether it does better than chance.
- *animal vs its shuffled wiring*: the one comparison about the brain. Better
  means the real wiring matters for play; no difference is a null result about
  the wiring, and is reported as one.
- *animal vs animal*: a comparison of two mappings we wrote. It is shown, and
  never described as one species being better at strategy than another.

With 20 games per player the intervals will be wide; a result that does not
survive them is not claimed.

## After elimination, written 2026-09-21

Once a seat has lost all its land it is asked for nothing more. From then
until the game ends, each turn drives the sensory channel that carries its
*harm* signal at 200 Hz, the most the encoding allows, with every other channel
silent, and the page shows the response. This is input to a model of a wiring
diagram, not pain: nothing on this stage can feel anything, and the page says
so beside the animal. It happens only after elimination, so it changes no game
result and no benchmark (`tools/stage_bench.mjs` ends a game at the wipe-out).
