#!/bin/bash
# Use the private native editor and retain its shader/derived-data cache.
set -euo pipefail
build_root=/workspace/flyhard-build
test "$(id -u)" != 0
exec 9>"$build_root/.editor-rebuild.lock"
flock -n 9 || { echo 'An editor rebuild is holding the editor lock.' >&2; exit 1; }
export XDG_RUNTIME_DIR="/tmp/flyhard-xdg-$(id -u)"
install -d -m 700 "$XDG_RUNTIME_DIR"
# This builder uses NVIDIA. Fail in its driver if graphics is unavailable,
# rather than silently selecting Mesa's CPU renderer.
export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
test -f "$VK_ICD_FILENAMES"
export LD_LIBRARY_PATH="$build_root/compat/libffi6/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p "$build_root/cache/DerivedDataCache"
python3 "$build_root/downloads/patch_editor_python.py"
shader_options=$(python3 "$build_root/downloads/shader_options.py")
read -r -a shader_args <<< "$shader_options"
exec env "UE_LocalDataCachePath=$build_root/cache/DerivedDataCache" \
  "$build_root/UnrealEngine_4.26/Engine/Binaries/Linux/UE4Editor" \
  "$build_root/carla/Unreal/CarlaUE4/CarlaUE4.uproject" \
  "$@" "${shader_args[@]}"
