#!/bin/bash
# Cook a reusable Linux runtime using CARLA's own packaging and material registry.
set -eo pipefail
build_root=/workspace/flyhard-build
export UE4_ROOT=$build_root/UnrealEngine_4.26
export FLYHARD_BUILD_JOBS=16
export FLYHARD_MAPS_TO_COOK=${FLYHARD_MAPS_TO_COOK:-/Game/Carla/Maps/Town03+/Carla/PostProcessingMaterials/AnnotationColorLandscape}
case "+$FLYHARD_MAPS_TO_COOK+" in
  *+/Game/Carla/Maps/Town03+*) ;;
  *) echo 'The native runtime starts in Town03; include it in the cooked maps.' >&2; exit 2 ;;
esac
export XDG_RUNTIME_DIR="/tmp/flyhard-xdg-$(id -u)"
export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
export LD_LIBRARY_PATH="$build_root/compat/libffi6/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="$HOME/.local/bin:$PATH"
FLYHARD_SHADER_OPTIONS=$(python3 "$build_root/downloads/shader_options.py")
export FLYHARD_SHADER_OPTIONS
test "$(id -u)" != 0
test -n "${FLYHARD_NATIVE_EXPORT:-}"
test -f "$FLYHARD_NATIVE_EXPORT/unreal-import-receipt.json"
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
source = Path(os.environ['FLYHARD_NATIVE_EXPORT'])
process = json.loads((source / 'import-process-result.json').read_text())
for phase in ['import', 'reload']:
    if process[phase]['exit_code'] != 0:
        raise RuntimeError('Native ' + phase + ' did not exit cleanly')
for name in ['unreal-import-receipt.json', 'unreal-reload-receipt.json']:
    if hashlib.sha256((source / name).read_bytes()).hexdigest() != process[name + '_sha256']:
        raise RuntimeError('Native import receipt changed after process verification')
PY
install -d -m 700 "$XDG_RUNTIME_DIR"
mkdir -p "$build_root/logs" "$build_root/cache/DerivedDataCache"
exec 9>"$build_root/.package.lock"
flock -n 9
rm -f "$build_root/package-result.json"
exec > >(tee -a "$build_root/logs/package.log") 2>&1
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/package-result.json"' EXIT
cd "$build_root/carla"
test "$(git rev-parse HEAD)" = 294096eb1c38eabf246e4f3a9cdab704e33a7f4c
git apply --reverse --check "$build_root/downloads/carla-native.patch"
test -x "$UE4_ROOT/Engine/Binaries/Linux/UE4Editor"

# These are release documentation and examples from the pinned source checkout.
GIT_LFS_SKIP_SMUDGE=1 git sparse-checkout add Docs Co-Simulation
# The native patch changes visual prop creation, not CARLA's RPC protocol.
# Package the same official Python 3.10 client verified by proof_environment.sh.
mkdir -p PythonAPI/carla/dist
cp "$build_root"/wheelhouse/carla-0.9.16-cp310-*.whl PythonAPI/carla/dist/
printf 'cooking\n' > "$build_root/package-stage.txt"
env "UE_LocalDataCachePath=$build_root/cache/DerivedDataCache" \
  bash Util/BuildTools/Package.sh --config Shipping --no-zip --archive-sufix flyhard

python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path('/workspace/flyhard-build')
carla = root / 'carla'
tag = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=carla, text=True).strip() + '-dirty'
runtime = carla / 'Dist' / ('CARLA_Shipping_' + tag + '_flyhard') / 'LinuxNoEditor'
binary = runtime / 'CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping'
if not binary.is_file():
    raise RuntimeError('CARLA package is missing its Shipping executable')
source = Path(os.environ['FLYHARD_NATIVE_EXPORT'])
receipt = json.loads((source / 'unreal-import-receipt.json').read_text())
asset_dir = receipt['native_asset_directory'].removeprefix('/Game/')
cooked = runtime / 'CarlaUE4/Content' / asset_dir
for mesh in receipt['native_meshes']:
    name = mesh['mesh_path'].rsplit('/', 1)[-1].split('.', 1)[0]
    if not (cooked / (name + '.uasset')).is_file():
        raise RuntimeError('Cooked native mesh is missing: ' + name)
shutil.copyfile(source / 'unreal-import-receipt.json', runtime / 'flyhard-native-import.json')
def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
output = {'status': 'cooked; packaged-runtime simulator verification pending',
          'runtime': str(runtime), 'maps': os.environ['FLYHARD_MAPS_TO_COOK'].split('+'),
          'carla_source': '294096eb1c38eabf246e4f3a9cdab704e33a7f4c',
          'engine_source': 'e9d9e60c85f643e10eeb03f42f61554d18dcb30f',
          'patch_sha256': sha(root / 'downloads/carla-native.patch'),
          'engine_lifecycle_patch_sha256': sha(root / 'downloads/engine-lifecycle.patch'),
          'revision': receipt['revision'], 'layout': receipt['layout'],
          'source_model_sha256': receipt['source_model_sha256'],
          'source_model_glb_sha256': receipt['source_model_glb_sha256'],
          'carla_server_version': tag, 'carla_client_version': '0.9.16',
          'import_receipt_sha256': sha(source / 'unreal-import-receipt.json'),
          'import_process_result': json.loads((source / 'import-process-result.json').read_text()),
          'shipping_executable_sha256': sha(binary),
          'native_files': {str(p.relative_to(runtime)): sha(p)
                           for p in sorted(cooked.rglob('*')) if p.is_file()}}
(root / 'package-receipt.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output, indent=2))
PY
printf 'cooked-verification-pending\n' > "$build_root/package-stage.txt"
