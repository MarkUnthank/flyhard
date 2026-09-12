#!/bin/bash
# Cache the Python client wheels alongside the native simulator build.
set -euo pipefail
build_root=/workspace/flyhard-build
mkdir -p "$build_root/wheelhouse" "$build_root/logs"
test -x "$build_root/venv/bin/python" || python3 -m venv "$build_root/venv"
python=$build_root/venv/bin/python
requirements=${FLYHARD_PROOF_REQUIREMENTS:-$build_root/downloads/proof-requirements.txt}
test -s "$requirements"
test -s "$build_root/wheelhouse/proof-wheels.sha256" \
  || { echo 'A preverified proof wheelhouse is required; refusing an unpinned download.' >&2; exit 1; }
(cd "$build_root/wheelhouse" && sha256sum -c proof-wheels.sha256)
"$python" -m pip install --no-index --find-links "$build_root/wheelhouse" \
  --no-deps --require-hashes -r "$requirements"
"$python" -c 'import carla,numpy,PIL; print("CARLA proof imports verified", numpy.__version__, PIL.__version__)'
"$python" -m pip freeze > "$build_root/proof-environment.lock.txt"
