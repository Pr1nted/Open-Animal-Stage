#!/usr/bin/env bash
# Serve the stage locally: http://localhost:8102
#
# The page cannot be opened as a file (file://): browsers refuse to start its
# workers and WebAssembly from one. This is all it needs instead.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8102}"
[ -f "$HERE/web/agent/OpenDoctrinesAgent.wasm" ] || { echo "web/agent is empty: run tools/build_web_agent.sh first"; exit 1; }
ls "$HERE"/web/species/*/brain.json >/dev/null 2>&1 || { echo "web/species is empty: run the exporters in tools/ first (see README)"; exit 1; }
echo "Open Animal Stage: http://localhost:$PORT   (Ctrl+C to stop)"
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$HERE/web"
