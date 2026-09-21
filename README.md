# Open Animal Stage

**Mapped brains play a strategy game against each other, live in your browser.**

A sister project to [Open Fly](https://github.com/Pr1nted/Open-Fly), which put one
simulated fruit-fly brain in front of [Open Doctrines](https://github.com/Pr1nted/Open-Doctrines)
and let it play. Open Fly has one animal and one seat. This has a roster and a
table: pick who sits down, pick how many, and watch them play the same game
against each other.

Same shape as Open Fly, deliberately. It compiles to a static page, the brains
run in workers, the game is Open Doctrines' own engine as WebAssembly driven
through its agent session, and nothing about any of it learned to play.

## What it is meant to do

- **Spectate one animal.** A fish in a tank with a screen. A fly at a keyboard.
  A worm in a dish. One station per species, in the style of Open Fly's room.
- **Put any two against each other.** Any pair from the roster, each on its own
  seat in the same world.
- **Put several in at once.** The game already runs many countries; a stage with
  four animals in it is four seats driven by four brains.
- **Show the mouse looking.** The mouse is not a player — see below — and the
  honest thing to do with it is show what its visual cortex does when it is shown
  the map.

## The roster, and what is actually available

Every entry here is a real, released dataset. What differs is how complete it is,
whether a published *model* exists or we have to build one, and how the data is
obtained. [ROSTER.md](ROSTER.md) is the working document; this is the summary.

| Animal | Dataset | Scale | On the stage |
|---|---|---|---|
| Fruit fly, adult female | FlyWire 783 | 138,639 neurons | **Plays.** Open Fly's brain, spike for spike |
| Fruit fly, adult male | MaleCNS v1.0 | 166,700 neurons | **Plays**, with the female's mapping and constants |
| Roundworm, hermaphrodite | Cook et al. 2019 | 302 neurons + gap junctions | **Plays** (calibrated, k = 3) |
| Roundworm, male | Cook et al. 2019 | 385 neurons + gap junctions | **Plays** (calibrated, k = 4) |
| Sea squirt larva | Ryan et al. 2016 | 207 neurons + gap junctions | **Plays**, but never reached the calibration target |
| Fruit fly, larva | Winding et al. 2023 | 2,952 neurons | **Plays** (calibrated, k = 5), its sensory neurons assumed cholinergic by a stated convention |
| Zebrafish larva, 7dpf | Fish1 | 187,052 somas | **Plays** (calibrated, k = 4), sensing through four brain nuclei by a stated convention |
| Mouse | MICrONS digital twin | 8,221 recorded neurons | **Watches** the world; cannot play |

### The three honest problems

**The mouse cannot play.** MICrONS is 1.4 × 0.87 × 0.84 mm of primary visual
cortex and three higher visual areas in a P87 mouse — 200,000 cells, 120,000
neurons, 523 million synapses, and 75,000 neurons with recorded responses to
visual stimuli. It is the most beautiful dataset on this list and it has no
motor output, because it is not a whole brain. A patch of visual cortex given a
seat in a strategy game would be a puppet with our hand inside it.

So the mouse gets the role it can actually have: it is **shown** the map and we
display what its cortex does. That is a real thing the data supports — the
functional half of MICrONS is exactly "these neurons, shown these images,
responded like this" — and it is not the same activity as playing.

**The zebrafish's sense organs are not in the traced data.** Fish1 releases
187,052 somata and 29.5 million synapses, and the synapses carry a per-synapse
excitatory/inhibitory call, which is everything a LIF model needs. What it does
not yet have is *axons attached to their cell bodies*: a presynaptic endpoint
lands on a segment carrying an identified soma about 2% of the time, so only
~0.8% of synapses have both ends on a cell, and no path runs from any sensory
peripheral sensory ganglion to any motor neuron (the public automated
agglomeration was tried too, and is no better). The brain itself is wired: so
the fish senses through four brain nuclei instead — pretectum, tectum and two
vestibular nuclei — the first-order sensory nuclei the atlas names that reach
the motor set. That is **our convention, not the animal's**, adopted on
reachability before any game (`PREREGISTRATION.md`), and the page shows it as
a warning beside the fish. `docs/fish1-mapping.md` has the numbers.

**"Both sexes of fly" may not be two brains.** The female (FlyWire/FAFB) is a
whole adult brain. The best-known male *Drosophila* volume is MANC, the male
adult *ventral nerve cord* — not a brain. Whether a male whole-brain or whole-CNS
reconstruction is released, and at what completeness, is the first thing to check
before promising a male fly a seat. Recorded as an open question rather than a
feature.

## How it is built

Mirrors Open Fly where it can, so somebody who has read that repository can
read this one.

```
web/                   the page: one stage, one worker per brain
  index.html           the room: a station per seat, the world on the wall
  brain.js             every species' neuron: Open Fly's, plus gap junctions
                       and the shuffled control
  decide.js            game -> four signals -> each species' senses; spikes -> orders
  game-worker.js       Open Doctrines as WebAssembly, several seats in one world
  mouse-worker.js      the MICrONS digital twin (ONNX), for the mouse's station
  species/<id>/        packages the exporters write (gitignored; docs/species-format.md)
patches/               the multi-seat agent session for Open Doctrines
tools/                 exporters, calibration, and the checks below
open_animal_stage/     the Python reference: signs, the LIF core, the shuffle, the stage
```

## Run it locally

```bash
tools/build_web_agent.sh ../OpenDoctrines     # web/agent: the game, patched for several seats
.venv/bin/python tools/export_female_fly.py   # needs ../Open-Fly's web/data
.venv/bin/python tools/export_male_fly.py     # MaleCNS v1.0, public bucket, ~150 MB
.venv/bin/python tools/export_celegans.py     # WormWiring + Wang et al. 2024
.venv/bin/python tools/export_ciona.py        # eLife 16962 source data
~/fish1-venv/bin/python tools/fish1_regions.py   # Fish1: soma -> published MECE brain region
~/fish1-venv/bin/python tools/fish1_export.py --sensory-convention brain-nuclei-v1
                                              # Fish1; needs a personal CAVE token, ~40 min
node tools/calibrate.mjs --write              # the preregistered rule; no game is played
tools/serve.sh                                # http://localhost:8102
```

The checks:

```bash
bash tests/run_all.sh                 # exports, signs, LIF, shuffle, stage, roster
node tools/stage_check.mjs            # several seats, one world; no seat is secretly the AI's
node tools/check_fly_identity.mjs     # the stage's fly is Open Fly's, spike for spike
```

## What is not claimed

None of these animals learned to play. None of them knows it is playing. How a
game event becomes a sensory input, and how spikes become an order, is our design
and not biology — the same disclosure Open Fly makes, and for the same reason.
Each species' mapping will be written down in `PREREGISTRATION.md` before that
species plays, so the wiring cannot be tuned after seeing a result and presented
as a finding.

Pairing two species is a comparison between two mappings we wrote, not between
two animals. A fly beating a worm would say something about our encode and
decode, and almost nothing about flies and worms.

## Related

- [Open Fly](https://github.com/Pr1nted/Open-Fly) — one fly, one seat, the page
  this one is modelled on.
- [Open Doctrines](https://github.com/Pr1nted/Open-Doctrines) — the game all of
  them play, and its Gearbox mod ABI.
