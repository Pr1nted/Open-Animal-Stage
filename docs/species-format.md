# The species package

Every animal that takes a seat ships as two files under `web/species/<id>/`,
read by one brain worker (`web/brain.js`). Open Fly's `connectome.bin` +
`brain.json` is this format with no gap junctions and no `senses` block, so the
female fly is exported by the same rule it always was.

## `connectome.bin`, little-endian

| bytes | field |
|---|---|
| 4 | magic `OAS1` |
| 4 | `n` neurons (u32) |
| 4 | `nsyn` chemical synapses (u32) |
| 4 | `ngap` gap junctions (u32), each stored once |
| (n+1)·4 | `indptr` (u32), CSR over presynaptic neuron |
| nsyn·4 | `post` (u32) |
| nsyn·2 | `count` (i16), **signed**: synapse count × sign of the presynaptic neuron |
| pad to 4 | zero bytes |
| ngap·4 | `gap_a` (u32) |
| ngap·4 | `gap_b` (u32) |
| ngap·4 | `gap_w` (f32), junction strength in the source's unit (count, or area) |

A synapse from a neuron of UNKNOWN sign is **dropped at export**, never assumed
excitatory (see `open_animal_stage/signs.py`). The number dropped goes in
`brain.json` under `provenance.dropped_unknown_sign`.

## `brain.json`

```json
{
  "species": "c_elegans_herm",
  "dataset": "Cook et al. (2019)", "version": "SI 5, 2019-07",
  "n": 302,
  "names": ["ADAL", "..."],
  "params": {"dt": 0.1, "t_mbr": 20, "tau": 5, "v_0": -52, "v_th": -45,
             "v_rst": -52, "t_rfc": 2.2, "t_dly": 1.8, "w_syn": 0.275,
             "f_poi": 250, "w_gap": 0.0},
  "sensory": {"<channel>": [0, 5, 9]},
  "senses":  {"<channel>": "reward | harm | reserve | threat"},
  "groups":  {"e": [[...] x12], "p": [[...] x12], "w": [[...] x8], "n": [[...] x7]},
  "motor": [/* every neuron dealt into groups */],
  "partition_seed": 783,
  "window_ms": 200,
  "provenance": {
    "neurons": "...", "signs": "...", "sensory": "...", "motor": "...",
    "params": "...", "licence": "...", "dropped_unknown_sign": 0
  }
}
```

### The four game signals

The game reaches every animal as the same four numbers, computed exactly as
Open Fly computes them (`web/decide.js`, `Encoder.signals`). A species only
chooses **which of its sensory channels carries which signal**:

| signal | Open Fly's channel | computed from |
|---|---|---|
| `reward` | sugar | land gained + budget surplus |
| `harm` | bitter | land lost + deficit + 0.5 × new wars |
| `reserve` | water | treasury / (12 × gross income) |
| `threat` | Johnston's organ | wars / 3 |

Each maps to 0–200 Hz Poisson input, 10 Hz floor, as in Open Fly.

### The 39 action groups

Motor neurons, **named from the source's own annotation** (descending neurons
for flies, motor neurons for the worm and the sea squirt), are dealt into
12 + 12 + 8 + 7 groups by a seeded shuffle (`partition_seed`, 783 as Open Fly).
With fewer than 39 motor neurons, groups are dealt round-robin with each neuron
in exactly one group per module (modules may share neurons, never a group within
one module); the count is stated in `provenance.motor`.

### Gap junctions

`w_gap` > 0 adds `w_gap · gap_w · (v_j − v_i)` to `v_i` each step, both ways.
Electrical synapses are a fifth of the sea squirt's wiring and much of the
worm's; treating them as chemical synapses would be wrong silently.
