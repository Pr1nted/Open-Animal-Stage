#!/usr/bin/env bash
# Publish the stage to itch.io as an HTML5 game.
#
#   tools/publish_itch.sh --check           stage it and check it against itch's limits, nothing else
#   tools/publish_itch.sh --zip             ... and write out/open-animal-stage-web.zip for a manual upload
#   tools/publish_itch.sh --push            ... and push it with butler to pr1nted/open-animal-stage:web
#
# It publishes from THIS machine, not from CI: the brains cannot be rebuilt on a
# CI runner (the zebrafish needs a personal CAVE token, the mouse an ONNX export
# environment), so what ships is exactly the build that was tested here. Only
# the species data/roster.json clears for redistribution is staged
# (tools/stage_web.py); that tool also refuses any file over 25 MiB.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/out/itch-dist"
TARGET="${ITCH_TARGET:-pr1nted/open-animal-stage:web}"
MODE="${1:---check}"

python3 "$HERE/tools/stage_web.py" --out "$OUT"

# itch.io's limits for an HTML5 upload (itch.io/docs/creators/html5): the page
# must be index.html at the root, at most 1,000 files, 500 MB extracted, and no
# single file over 200 MB.
python3 - "$OUT" <<'PY'
import os, sys
root = sys.argv[1]
files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]
total = sum(os.path.getsize(f) for f in files)
big = max(files, key=os.path.getsize)
problems = []
if not os.path.exists(os.path.join(root, "index.html")): problems.append("no index.html at the root")
if len(files) > 1000: problems.append(f"{len(files)} files, itch allows 1,000")
if total > 500e6: problems.append(f"{total/1e6:.0f} MB, itch allows 500 MB")
if os.path.getsize(big) > 200e6: problems.append(f"{os.path.relpath(big, root)} is over 200 MB")
print(f"itch limits: {len(files)} files, {total/1e6:.0f} MB, largest {os.path.relpath(big, root)} {os.path.getsize(big)/1e6:.1f} MB")
if problems: sys.exit("NOT UPLOADABLE: " + "; ".join(problems))
print("within itch.io's HTML5 limits")
PY

VERSION="$(git -C "$HERE" describe --tags --always --dirty)"
case "$MODE" in
  --check) ;;
  --zip)
    rm -f "$HERE/out/open-animal-stage-web.zip"
    (cd "$OUT" && zip -qr -X "$HERE/out/open-animal-stage-web.zip" .)
    echo "out/open-animal-stage-web.zip ($(du -h "$HERE/out/open-animal-stage-web.zip" | cut -f1)), version $VERSION: upload it on the project's Edit page, tick 'This file will be played in the browser'"
    ;;
  --push)
    command -v butler >/dev/null || { echo "butler is not installed: https://itch.io/docs/butler/installing.html, then 'butler login'"; exit 1; }
    butler push "$OUT" "$TARGET" --userversion "$VERSION"
    butler status "$TARGET"
    ;;
  *) echo "usage: $0 --check | --zip | --push"; exit 2 ;;
esac
