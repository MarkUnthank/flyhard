#!/bin/bash
# CARLA 0.9.16 editor build; the engine and project remain on the network volume.
set -eo pipefail
build_root=/workspace/flyhard-build
export UE4_ROOT=$build_root/UnrealEngine_4.26
export FLYHARD_BUILD_JOBS=16
export PIP_CACHE_DIR=$build_root/cache/pip
cd "$build_root/carla"
mkdir -p "$build_root/logs"
rm -f "$build_root/carla-result.json"
exec > >(tee -a "$build_root/logs/carla-build.log") 2>&1
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/carla-result.json"' EXIT
test "$(id -u)" != 0
test "$(git rev-parse HEAD)" = 294096eb1c38eabf246e4f3a9cdab704e33a7f4c
test -x "$UE4_ROOT/Engine/Binaries/Linux/UE4Editor"
bash "$build_root/downloads/build_carla_dependencies.sh"
printf 'building-carla-editor\n' > "$build_root/carla-stage.txt"
bash Util/BuildTools/BuildCarlaUE4.sh --build --no-simready
printf 'compiled\n' > "$build_root/carla-stage.txt"
date -u
