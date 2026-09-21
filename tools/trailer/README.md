# The trailer

One command renders it, offline, from this repository:

    tools/trailer/make.sh

and writes `out/trailer/oas-trailer.mp4` (1920x1080, 30 fps, H.264 + AAC,
about 75 s). `out/` is not committed.

Needs: Node 22 (built-in WebSocket and fetch; no npm packages), Google Chrome
(found at its usual macOS or Linux path, or set `CHROME=`), ffmpeg, and Python 3
with numpy (the project's `.venv` is used when present). The species packages
and `web/agent` must be in place, as for `tools/serve.sh`. The page loads
three.js and its fonts from their CDNs, as it always does.

## What each step does

| Step | File | Output |
|---|---|---|
| Film the shots | `capture.mjs` | `out/trailer/frames/NN-name/*.png`, `timeline.json` |
| Compose the music | `music.py` | `out/trailer/music.wav` |
| Captions, corner hint, end card | `overlays.mjs` | `out/trailer/overlays/` |
| Cut | `montage.mjs` | `out/trailer/oas-trailer.mp4` |

`shots.mjs` is the one list: every shot's camera move, length in bars and
caption, and the stage that is filmed (every species that can play, the worm
twice -- its own wiring and shuffled -- and the mouse watching).

**Frame-exact capture.** `capture.mjs` serves `web/`, opens the page in
headless Chrome with `?capture`, seats the stage through the page's own
controls, waits until every brain is on its pedestal and a few turns have been
played, hides the panels, and then films. Under `?capture` the page's clock is
virtual: each frame is `__oas.step()` (exactly 1/30 s of animation) and a
screenshot, so motion is perfectly even however slow the machine is. Game
turns are held to one every 2.4 s of virtual time so the brains flash at a
steady pace. WebGL runs on the GPU (ANGLE/Metal on a Mac); on a machine
without one, `make.sh --gl swiftshader` renders in software, slowly.

`node tools/trailer/capture.mjs --stills` grabs one frame from the middle of
each shot into `out/trailer/stills/` for checking framing; `--only a,b`
films only the named shots.

**Timing.** The music is 90 BPM in 4/4. Each shot lasts a whole or half number
of bars and is filmed one beat longer, and that beat is the crossfade, so
every cut lands on a bar line. The end card starts on the downbeat where the
music resolves.

**Logos.** Open Fly's from `../Open-Fly/docs/brand`, this project's from
`docs/brand/logo.png`, Open Doctrines' from `../OpenDoctrines/data/Icon`
(`OPEN_FLY_DIR` and `OD_DIR` override the sibling paths). If this project's
logo is missing, the end card falls back to a text wordmark and
`overlays.mjs` warns; re-run it and `montage.mjs` once the logo exists.

**Captions** say only what is measured or built: neuron counts from the
packages, what the page does. Nothing in the trailer says an animal is
clever, good at strategy, or feels anything; see `shots.mjs` before adding a
line.

## The music is original and free to use

`music.py` synthesises the whole track from sine waves and noise with numpy:
detuned additive pads, FM bell "spikes" at Poisson-random times (neurons
firing), a sub bass, a soft kick, a filtered-noise swell, and a synthetic
reverb. No samples, loops or recordings are used and nothing is downloaded,
so the track is an original work made for this project. It is free to use,
with the rest of the trailer, under the project's licence (Apache-2.0, see
`LICENSE`), and re-rendering gives the same file (fixed seed).

## Recording by hand

The page's own recorder is separate from this pipeline: open the stage with
`?record` (e.g. `http://localhost:8102/?record`) and press **T** for the auto
tour or **R** to record while you fly; see `web/record.js`.
`node tools/trailer/record_test.mjs <url> <dir>` checks it end to end in
headless Chrome.
