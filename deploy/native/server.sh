#!/bin/bash
# Run an owned native CARLA server for the RGB/depth and attachment checks.
set -euo pipefail
build_root=/workspace/flyhard-build
mode=${1:-editor}
test "$(id -u)" != 0
exec 9>"$build_root/.native-server.lock"
flock -w 30 9 || { echo 'Another native server still holds the server lock.' >&2; exit 1; }
export XDG_RUNTIME_DIR="/tmp/flyhard-xdg-$(id -u)"
export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
install -d -m 700 "$XDG_RUNTIME_DIR"
args=(/Game/Carla/Maps/Town03 -game -RenderOffScreen -unattended -nosound
      -nop4 -carla-rpc-port=2000 -quality-level=Epic)
if [ "$mode" = editor ]; then
  exec bash "$build_root/downloads/editor.sh" "${args[@]}"
elif [ "$mode" = runtime ]; then
  : "${FLYHARD_RUNTIME_MANIFEST:?Runtime mode requires a pinned manifest path}"
  : "${FLYHARD_RUNTIME_MANIFEST_SHA256:?Runtime mode requires a pinned manifest digest}"
  resolver=${FLYHARD_RUNTIME_RESOLVER:-/workspace/flyhard/scripts/runtime_manifest.py}
  if [ ! -f "$resolver" ]; then
    resolver="$build_root/downloads/runtime_manifest.py"
  fi
  test -f "$resolver"
  resolve_args=(resolve --manifest "$FLYHARD_RUNTIME_MANIFEST" --sha256 "$FLYHARD_RUNTIME_MANIFEST_SHA256")
  case "${FLYHARD_RUNTIME_CANDIDATE:-0}" in
    0) ;;
    1) resolve_args+=(--allow-candidate) ;;
    *) echo 'FLYHARD_RUNTIME_CANDIDATE must be 0 or 1' >&2; exit 2 ;;
  esac
  selection=$(python3 "$resolver" "${resolve_args[@]}")
  runtime=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["root"])' <<< "$selection")
  cd "$runtime"
  exec ./CarlaUE4.sh "${args[@]}" -stdout -FullStdOutLogOutput
else
  echo 'Usage: server.sh editor|runtime' >&2
  exit 2
fi
