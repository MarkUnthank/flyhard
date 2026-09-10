#!/bin/bash
# Run as builder under the existing Pod budget/deadline guard.
set -euo pipefail
build_root=/workspace/flyhard-build
rm -f "$build_root/pipeline-result.json"
exec > >(tee -a "$build_root/logs/native-pipeline.log") 2>&1
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/pipeline-result.json"' EXIT
printf 'waiting-for-source\n' > "$build_root/pipeline-stage.txt"
until [ -f "$build_root/unreal-source-result.json" ]; do sleep 10; done
python3 - <<'PY'
import json
from pathlib import Path
result = json.loads(Path('/workspace/flyhard-build/unreal-source-result.json').read_text())
assert result['revision'] == 'e9d9e60c85f643e10eeb03f42f61554d18dcb30f'
assert result['status'] == 'checkout verified'
PY
if [ ! -d "$build_root/UnrealEngine_4.26" ]; then
  mv "$build_root/UnrealEngine-parallel" "$build_root/UnrealEngine_4.26"
fi
if [ "${1:-setup}" != carla ]; then
  printf 'building-engine\n' > "$build_root/pipeline-stage.txt"
  bash "$build_root/downloads/build_engine.sh" "${1:-setup}"
fi
printf 'building-carla\n' > "$build_root/pipeline-stage.txt"
bash "$build_root/downloads/build_carla.sh"
printf 'editor-built-import-pending\n' > "$build_root/pipeline-stage.txt"
