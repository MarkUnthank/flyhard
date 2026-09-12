#!/bin/bash
# Rebuild the editor lifecycle fix after the owned preview has stopped.
set -euo pipefail
build_root=/workspace/flyhard-build
test "$(id -u)" != 0
exec 9>"$build_root/.editor-rebuild.lock"
flock -n 9 || { echo 'An editor preview or rebuild already holds the editor lock.' >&2; exit 1; }
if pgrep -u "$(id -u)" -x UE4Editor >/dev/null; then
  echo 'Stop the active editor preview before replacing its libraries.' >&2
  exit 1
fi
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/editor-fix-result.json"' EXIT
cd "$build_root/UnrealEngine_4.26"
test "$(git rev-parse HEAD)" = e9d9e60c85f643e10eeb03f42f61554d18dcb30f
git apply --reverse --check "$build_root/downloads/engine-lifecycle.patch"
bash Engine/Build/BatchFiles/Linux/Build.sh UE4Editor Linux Development \
  -WaitMutex -MaxParallelActions=16 -NoHotReload
sha256sum Engine/Binaries/Linux/libUE4Editor-UnrealEd.so > "$build_root/editor-fix-binary.sha256"
printf 'compiled; clean import validation pending\n' > "$build_root/editor-fix-stage.txt"
