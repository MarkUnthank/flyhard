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
  runtime=$(python3 -c 'import json; print(json.load(open("/workspace/flyhard-build/package-receipt.json"))["runtime"])')
  test -f "$runtime/flyhard-native-import.json"
  cd "$runtime"
  exec ./CarlaUE4.sh "${args[@]}" -stdout -FullStdOutLogOutput
else
  echo 'Usage: server.sh editor|runtime' >&2
  exit 2
fi
