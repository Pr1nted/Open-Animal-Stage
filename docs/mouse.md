# The mouse station

The mouse does not play. MICrONS is a cubic millimetre of visual cortex with no
motor output (see ROSTER.md). What it can honestly do is **look**: the station
shows the mouse the game's world map each turn and displays what a model of its
visual cortex predicts its neurons would do.

That model exists, is public, and runs in a browser. This document records what
it is, what was checked, and what is left.

## The model: the MICrONS digital twin

Wang et al., "Foundation model of neural activity predicts response to new
stimulus types", *Nature* 640:470 (2025), doi:10.1038/s41586-025-08829-y.

- **What it is.** A recurrent network (CvT-LSTM core) trained on two-photon
  recordings from **mouse 17797**, the same animal whose cortex was then
  reconstructed by electron microscopy for MICrONS. A shared "foundation" core
  is frozen. Each of the 13 imaging scans has its own readout (one output per
  recorded unit), its own eye-to-monitor geometry ("perspective") and its own
  behaviour network ("modulation"). **One scan is one model.** They share the
  core's weights but not its computation, because the per-scan perspective
  and modulation networks feed the core.
- **Code.** <https://github.com/cajal/fnn>, MIT licence (the LICENSE file was
  read). `fnn.microns.scan(session, scan_idx)` loads a scan.
- **Weights.** Public S3 with no login:
  `s3://bossdb-open-data/iarpa_microns/minnie/functional_data/foundation_model/foundational_model_weights_and_metadata_v1.zip`,
  222 MB, md5 `58fcac4b31ad2902c81e339432cec787` (checked on download).
  Contains `params_core.pt` (18 MB), 13 × `params_<session>_<scan>.pt`
  (11–21 MB each), `units.csv` and `scans.csv`. A second zip,
  `…_with_ori_training.zip`, has the same core with readouts trained further
  on oriented stimuli (used for the orientation figures of Ding et al. 2025).
  Not used here.

### What it takes as input (verified in the fnn code and demo notebooks)

| input | shape | what it is | what the station feeds |
|---|---|---|---|
| stimulus | 144 × 256, one channel | grayscale frame on the monitor, pixel/255 | the map, rendered at exactly 144 × 256 and converted to luminance |
| frame rate | 30 Hz | "must be sampled at 30Hz to match the training regime" | 30 frames per second of clip |
| perspective | 2 | pupil x, pupil y, each z-scored over the scan's training set | 0, 0 — the average eye position |
| modulation | 2 | pupil radius, treadmill velocity, each z-scored | 0, 0 — average pupil, average running |

Zero for both behavioural inputs is fnn's own default
(`Visual.default_perspective/default_modulation`), and it is the honest value:
there is no mouse on the stage, so there is no pupil and no running to report.
Feeding "excited" values to make the display livelier would be a hand in the
puppet and is not done.

The release's `performance/metadata.csv` gives a **burn-in of 10 frames** — the first
third of a second is the model settling, not a response.

### What it outputs

One number per recorded unit per frame: `exp` of the readout (fnn's Poisson
unit). The training targets were each unit's recorded activity scaled by its
training-set mean (fnn demo 4), so ~1 reads as "this neuron's typical level".
*That reading is inferred from the training spec; the release does not state
the unit for the released weights.*

### Which neurons, and are they this mouse's neurons?

- **All units are real recorded neurons of mouse 17797.** Each has a
  `(session, scan_idx, unit_id)`, a visual area (V1, LM, AL, RL), a 2P soma
  position in µm and an imaging field (`digital_twin_properties/v2/anatomy`),
  a receptive-field centre (`…/readout`), and a held-out prediction score
  `cc_norm` (`…/performance`). 104,171 units across the 13 scans.
- **A subset is matched to the connectome.** Ding, Fahey, Papadopoulos et al.
  2025 (doi:10.1038/s41586-025-08840-3) released `node_data_v1.pkl` (295 MB,
  public S3) coregistering **12,894** functional units to EM nuclei, one unit
  per nucleus, with the EM nucleus id, nucleus position in nm, layer
  (L2/3, L4, L5) and proofreading status. For those cells the twin's output
  *is* a prediction for a specific cell in the reconstruction.
- **Root ids are deliberately not stored.** A nucleus id is stable; a segment
  root id changes with proofreading and is only meaningful at a stated
  materialization. Resolving nucleus → root id at a pinned version is a CAVE
  query, and CAVE needs a personal token (see "Needs a human" below).
- Scan **6-4** is the default export: 8,221 units, **1,316 EM-matched** (the
  most of any scan; 622 L2/3, 277 L4, 320 L5, 97 with no layer given), areas
  V1 5,999 / LM 1,027 / RL 878 / AL 317, median `cc_norm` 0.61.
  `--scan 8-5` is the demo's scan (9,941 units, 1,042 matched).

## What was built

`tools/export_microns_twin.py` (run with the venv in `data/raw/micro_venv`)
writes, to `web/species/mouse_v1/` (gitignored, like every species export):

- **`model.onnx`, 34.9 MiB.** One 1/30 s step of the scan-6-4 twin, opset 17.
  The network's recurrent state — two frames of history for each of six
  temporal convolutions, h and c for the core's CvT-LSTM and the modulation
  LSTM, 16 tensors, 25.9 MiB — is lifted out of fnn's Python-side caches into
  explicit graph inputs and outputs. Initial state is all zeros (every
  temporal conv zero-pads in time, every LSTM starts at zero; the tool refuses
  to export if that stops being true). fnn's grouped `conv3d` calls are
  rewritten as the equivalent grouped `conv2d` at export time, because
  onnxruntime-web's WebGPU backend refuses grouped Conv3D.
- **`mouse.json`, 0.7 MB.** Units in readout order (unit id, area, field, 2P
  soma µm, RF centre, cc_norm, and for matched cells nucleus id, layer, EM
  soma nm, proofread status), the input spec above, the state tensor names
  and shapes, provenance with the ONNX sha256, and citations.

### Checks (verified, 2026-09-21, Apple-silicon Mac)

The exported step, run 30 times with its own state fed back, was compared
against `fnn`'s own `model.predict` on the same 30 frames of a map-like test
image, with zero behaviour inputs:

| runtime | max relative error | time per frame | 1 s clip (30 frames) |
|---|---|---|---|
| PyTorch (fnn), all cores | reference | 80 ms | 2.4 s |
| onnxruntime CPU, 1 thread | 1.9e-6 | 190–218 ms | ~6 s |
| onnxruntime-web 1.30 WASM in Node, 1 thread | 1.2e-6 | 332 ms | ~10 s |
| onnxruntime-web WASM in Node, 4 threads | 1.2e-6 | 120 ms | ~3.6 s |
| onnxruntime-web WASM in Chromium 152, page not cross-origin isolated (1 thread) | 1.2e-6 | 322 ms | ~10 s |
| onnxruntime-web WebGPU in Chromium 152, state copied back each frame | 2.4e-6 | 191 ms | ~5.7 s |
| onnxruntime-web WebGPU, state kept on GPU (`preferredOutputLocation: 'gpu-buffer'`) | 2.4e-6 | 94 ms | **~2.8 s** |

Not checked: nonzero perspective/modulation inputs (the station never feeds
them), other scans than 6-4, other browsers or slower machines. Session
creation took 0.4 s (Node) to 2.7 s (browser, incl. compile).

Multithreaded WASM needs the page to be cross-origin isolated (COOP/COEP
headers), which a static host such as GitHub Pages cannot set without a
service-worker shim. WebGPU with GPU-resident state is the fastest path and
needs no isolation; WASM single-thread is the fallback.

## What the station would show

Per turn, in a worker, so the game never waits on the mouse:

1. The mouse has been looking at the previous map (state carried over — it is
   one continuous viewing session, not a fresh mouse each turn).
2. The new map is rendered at 144 × 256, converted to luminance, and held
   for 1 s (30 frames). ~3 s on WebGPU, ~10 s on single-thread WASM.
3. Display: each of the 8,221 neurons at its real 2P soma position (top-down,
   areas outlined), coloured by predicted activity relative to the previous
   map's, with the 1,316 EM-matched cells marked and clickable (nucleus id,
   layer, area, cc_norm). Optionally the stimulus with each neuron's RF
   centre drawn on it, so a viewer can see which part of the map a firing
   neuron is looking at.

### What it claims

- These are real neurons of the MICrONS mouse, at their real positions, and
  1,316 of them are cells in the reconstruction.
- The activity shown is a published, validated model's prediction of how
  those neurons would respond if this mouse were shown this image on its
  training monitor, with average eye position, pupil and running.
- Each neuron's prediction comes with how good the model is for that neuron
  (`cc_norm`), and the page should show it.

### What it does not claim

- It is **not recorded activity**. The mouse was never shown the map.
- It is **not a simulation of the connectome**. The twin is a deep network
  fitted to functional recordings; the EM wiring is not in it. The EM match
  gives identity and position, not mechanism.
- The mouse does not understand, evaluate or play the map. Nothing flows from
  the station back into the game.
- A strategy map is far outside the naturalistic movies the twin was trained
  on. The paper's point is that it generalises to new stimulus types, but
  "predicts well for natural video" is the evidence, not "predicts well for
  maps".
- Colour is discarded: the model was trained on grayscale stimuli.

## Licences

| thing | licence | status |
|---|---|---|
| fnn code | MIT | verified (LICENSE in the repo) |
| MICrONS data | CC BY 4.0 | verified on MICrONS Explorer's terms page, which covers "all the material on this website" |
| twin weights, properties, node_data | presumably CC BY 4.0 as MICrONS data | **not verified**: the S3 READMEs state no licence, and the BossDB AWS registry lists CC BY 4.0, CC0 and CC BY-NC-SA 4.0 for the bucket without mapping them to datasets. Confirm before publishing the ONNX. |

Citation requested by the release README: Wang et al. 2025 and Ding et al.
2025 for the twin and its properties; MICrONS Consortium 2025
(doi:10.1038/s41586-025-08790-w) for the anatomy.

## Reproducing

```sh
uv venv -p python3.13 data/raw/micro_venv
VIRTUAL_ENV=data/raw/micro_venv uv pip install torch onnx onnxruntime onnxscript \
    pandas scipy tqdm requests git+https://github.com/cajal/fnn.git@8f34c6753bd818c8fcd1daa91499a057252bea7e
B=https://bossdb-open-data.s3.amazonaws.com/iarpa_microns/minnie
mkdir -p data/raw/microns/{properties/{anatomy,performance,readout},coreg}
cd data/raw/microns
curl -O $B/functional_data/foundation_model/foundational_model_weights_and_metadata_v1.zip
unzip foundational_model_weights_and_metadata_v1.zip
P=$B/functional_data/digital_twin_properties/v2
for f in anatomy/units.csv performance/units.csv readout/units.csv readout/readout_locations.npy; do
  curl -o properties/$f $P/$f; done
curl -o coreg/node_data_v1.pkl \
  $B/functional_data/functional_connectomics/node_and_edge_properties/v1/node_data_v1.pkl
cd ../../..
data/raw/micro_venv/bin/python tools/export_microns_twin.py   # --scan 8-5 for another scan
```

Total download ≈ 520 MB. Not needed and not fetched: the precomputed
responses (`digital_twin_properties/v2/responses/`, 31 GB + 2.8 GB) and the
readout weights array (213 MB, duplicated in the zip).

`node_data_v1.pkl` is a Python pickle; loading one executes code from the file.
It comes from the MICrONS team's own release bucket, which is the trust being
extended.

## Remaining steps

1. **Station page and worker** (not written; `web/*.js` and `index.html` are
   other agents' files): load `model.onnx` with onnxruntime-web (WebGPU with
   `preferredOutputLocation: 'gpu-buffer'`, WASM fallback), render the map to
   144 × 256 luminance, step 30 frames per turn after a 10-frame burn-in on
   first load, draw the neuron map from `mouse.json`.
2. **Publish the model file.** `web/species/` is gitignored; the site build
   has to stage the 35 MB ONNX (under GitHub Pages' 100 MB file limit), and
   only after the weights licence is confirmed.
3. **Optional size cuts**, each needing the same ONNX-vs-fnn check: fp16
   weights (~17 MB), or a readout restricted to the 1,316 EM-matched units
   (the readout is ~5 M of the 8.8 M parameters).
4. **Root ids at a pinned materialization**, if the page should link cells to
   Neuroglancer — needs a human with a CAVE token (below).
5. **Roster.** `data/roster.json` and ROSTER.md can record the mouse's
   `model` as the twin and `export` as scan 6-4 of `…weights_and_metadata_v1`
   (not edited here).

### Needs a human

- **CAVE token** (per the CAVEclient docs; not attempted here: Google login at
  `https://global.daf-apis.com/auth/api/v1/create_token`, saved to
  `~/.cloudvolume/secrets/cave-secret.json`, never committed) — only to map
  nucleus ids to current root ids in `minnie65_public`. Nothing built here
  needs it.
- **Licence confirmation** for the twin weights, from the paper's data
  availability statement or the MICrONS team.

## If the twin could not run in a browser

It can, so this is only for the record. The next honest option would be a
precomputed set: run the twin offline on a fixed set of map renders and ship
the responses, labelled on the page as precomputed and not live. It would cost
~33 KB per render per scan (8,221 float32) and would freeze the station to maps
somebody rendered in advance. The release's own 75,000-frame response set is
responses to *its* stimuli, not to maps, and cannot stand in for either.
