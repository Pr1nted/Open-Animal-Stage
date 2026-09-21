#!/usr/bin/env bash
# Render the Open Animal Stage trailer, start to finish, offline:
#   tools/trailer/make.sh            -> out/trailer/oas-trailer.mp4
# Steps: capture the shots (headless Chrome, virtual clock) -> synthesise the
# music -> render captions and end card -> cut with ffmpeg.
# Pass --gl swiftshader if the machine has no usable GPU in headless Chrome.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$HERE"
OUT=out/trailer
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
mkdir -p "$OUT"
node tools/trailer/capture.mjs --out "$OUT" "$@"
"$PY" tools/trailer/music.py "$OUT/timeline.json" "$OUT/music.wav"
node tools/trailer/overlays.mjs --out "$OUT"
node tools/trailer/montage.mjs --out "$OUT"
ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$OUT/oas-trailer.mp4"
