#!/bin/bash
# Cache the Python client wheels alongside the native simulator build.
set -euo pipefail
build_root=/workspace/flyhard-build
mkdir -p "$build_root/wheelhouse" "$build_root/logs"
test -x "$build_root/venv/bin/python" || python3 -m venv "$build_root/venv"
python=$build_root/venv/bin/python
packages=(numpy==2.2.6 pillow==12.3.0 carla==0.9.16)
if [ -f "$build_root/wheelhouse/proof-wheels.sha256" ]; then
  (cd "$build_root/wheelhouse" && sha256sum -c proof-wheels.sha256)
fi
if ! "$python" -m pip download --no-index --find-links "$build_root/wheelhouse" \
  --dest "$build_root/wheelhouse" "${packages[@]}"; then
  "$python" -m pip download --dest "$build_root/wheelhouse" --timeout 120 --retries 5 "${packages[@]}"
fi
(cd "$build_root/wheelhouse" && sha256sum ./*.whl > proof-wheels.sha256.partial \
  && mv proof-wheels.sha256.partial proof-wheels.sha256)
"$python" -m pip install --no-index --find-links "$build_root/wheelhouse" "${packages[@]}"
"$python" -c 'import carla,numpy,PIL; print("CARLA proof imports verified", numpy.__version__, PIL.__version__)'
"$python" -m pip freeze > "$build_root/proof-environment.lock.txt"
