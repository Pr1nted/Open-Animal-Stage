#!/usr/bin/env bash
# Build the Open Doctrines module the stage plays through.
#
#   tools/build_web_agent.sh [path/to/Open-Doctrines] [git ref]
#
# Open Fly's build, plus patches/opendoctrines-stage.patch: the multi-seat agent
# session (od_agent_stage_begin / seat_position / seat_play). The patch is
# applied in a detached worktree, never in the Open Doctrines checkout, which
# other sessions edit and commit from. When the stage calls land in Open
# Doctrines itself, the patch goes and this is Open Fly's script again.
# Needs Emscripten (emcmake) on PATH. Then: node tools/stage_check.mjs
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
OD="${1:-$(cd "$HERE/.." && pwd)/OpenDoctrines}"
REF="${2:-HEAD}"
WORK="$(mktemp -d)"
trap 'git -C "$OD" worktree remove --force "$WORK/od" >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT

git -C "$OD" worktree add --detach "$WORK/od" "$REF" >/dev/null
if grep -q "od_agent_stage_begin" "$WORK/od/src/web/AgentWeb.cpp"; then
  echo "Open Doctrines $REF already has the stage calls; not patching"
else
  git -C "$WORK/od" apply "$HERE/patches/opendoctrines-stage.patch"
fi

emcmake cmake -S "$WORK/od" -B "$WORK/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$WORK/build" --target OpenDoctrinesAgent -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)"

mkdir -p "$HERE/web/agent"
cp "$WORK/build/OpenDoctrinesAgent.mjs" "$WORK/build/OpenDoctrinesAgent.wasm" "$WORK/build/OpenDoctrinesAgent.data" "$HERE/web/agent/"
echo "$(git -C "$WORK/od" describe --tags --always)+stage" > "$HERE/web/agent/VERSION"
echo "web/agent: OpenDoctrinesAgent from $(cat "$HERE/web/agent/VERSION")"
