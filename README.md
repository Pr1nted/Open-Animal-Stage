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

| Animal | Dataset | Scale | Can it play? |
|---|---|---|---|
| Fruit fly, adult female | FlyWire / FAFB | 139k neurons | **Yes** — Open Fly already does it |
| Fruit fly, adult male | Janelia male CNS | to verify | **Unknown**, see below |
| Fruit fly, larva | Winding et al. 2023 | 3,016 neurons | Likely — complete brain, small |
| Roundworm (*C. elegans*) | Cook et al. 2019 | 302 / 385 neurons | Likely — complete, both sexes |
| Sea squirt larva (*Ciona*) | Ryan et al. 2016 | ~177 neurons | Likely — complete |
| Zebrafish larva, 7dpf | **Fish1** | 187,053 somas | Plausible — needs a model built |
| Mouse | **MICrONS** cubic millimetre | 120k neurons | **No.** It is visual cortex |

### The two honest problems

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

**"Both sexes of fly" may not be two brains.** The female (FlyWire/FAFB) is a
whole adult brain. The best-known male *Drosophila* volume is MANC, the male
adult *ventral nerve cord* — not a brain. Whether a male whole-brain or whole-CNS
reconstruction is released, and at what completeness, is the first thing to check
before promising a male fly a seat. Recorded as an open question rather than a
feature.

## How it is built

Mirrors Open Fly file for file where it can, so somebody who has read that
repository can read this one.

```
open_animal_stage/     one module per species: brain, encode, decode
  brain.py             the shared leaky integrate-and-fire core
  species/             per-animal wiring: what a sense is, what an action is
tools/                 export the connectome, pack it, stage the site
web/                   the page: workers, scene, packed data
scene/                 the stations, generated rather than hand-modelled
data/                  roster and provenance, not the connectomes themselves
```

A connectome is not in this repository. The exports are large, several of them
are licensed per-dataset, and one of them (Fish1) needs a personal access token
that must never be committed. `tools/` fetches and derives; `data/roster.json`
records exactly which version of which dataset an export came from.

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
