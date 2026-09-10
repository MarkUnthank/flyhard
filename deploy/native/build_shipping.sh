#!/bin/bash
# Compile the reusable server while independent native visual checks run.
set -euo pipefail
build_root=/workspace/flyhard-build
test "$(id -u)" != 0
exec 9>"$build_root/.shipping-build.lock"
flock -n 9
jobs=${FLYHARD_BUILD_JOBS:-8}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]]
cd "$build_root/carla"
test "$(git rev-parse HEAD)" = 294096eb1c38eabf246e4f3a9cdab704e33a7f4c
git apply --reverse --check "$build_root/downloads/carla-native.patch"
printf 'compiling\n' > "$build_root/shipping-stage.txt"
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/shipping-result.json"' EXIT
bash "$build_root/UnrealEngine_4.26/Engine/Build/BatchFiles/Linux/Build.sh" \
  CarlaUE4 Linux Shipping \
  -project="$build_root/carla/Unreal/CarlaUE4/CarlaUE4.uproject" \
  -MaxParallelActions="$jobs" -NoHotReload
sha256sum Unreal/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping > "$build_root/shipping-binary.sha256"
printf 'compiled\n' > "$build_root/shipping-stage.txt"
