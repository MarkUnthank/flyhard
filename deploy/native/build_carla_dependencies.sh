#!/bin/bash
# Independent of UE4Editor: can run at lower priority during the engine build.
set -eo pipefail
build_root=/workspace/flyhard-build
export UE4_ROOT=$build_root/UnrealEngine_4.26
export FLYHARD_BUILD_JOBS=${FLYHARD_BUILD_JOBS:-4}
export PIP_CACHE_DIR=$build_root/cache/pip
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$build_root/logs"
exec 9>"$build_root/.carla-dependencies.lock"
flock 9
rm -f "$build_root/carla-dependencies-result.json"
exec > >(tee -a "$build_root/logs/carla-dependencies.log") 2>&1
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/carla-dependencies-result.json"' EXIT
test "$(id -u)" != 0
cd "$build_root/carla"
test "$(git rev-parse HEAD)" = 294096eb1c38eabf246e4f3a9cdab704e33a7f4c
test -f "$UE4_ROOT/Engine/Build/OneTimeSetupPerformed"
test -f Makefile
test -f CMakeLists.txt
if ! git apply --reverse --check "$build_root/downloads/carla-native.patch" >/dev/null 2>&1; then
  git apply --check "$build_root/downloads/carla-native.patch"
  git apply "$build_root/downloads/carla-native.patch"
fi
printf 'building\n' > "$build_root/carla-dependencies-stage.txt"
python3 -m pip install --user -r PythonAPI/carla/requirements.txt
make LibCarla.server.release osm2odr downloadplugins
printf 'compiled\n' > "$build_root/carla-dependencies-stage.txt"
