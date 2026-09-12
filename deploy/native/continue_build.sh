#!/bin/bash
# Run as builder under the existing Pod budget/deadline guard.
set -euo pipefail
build_root=/workspace/flyhard-build
source_run_id=${FLYHARD_SOURCE_RUN_ID:?Set the same unique source run ID for clone_engine.py and continue_build.sh}
if ! [[ "$source_run_id" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo 'FLYHARD_SOURCE_RUN_ID is not a safe run identifier' >&2
  exit 2
fi
source_result=${FLYHARD_SOURCE_RESULT:-$build_root/unreal-source-result-$source_run_id.json}
source_wait=${FLYHARD_SOURCE_WAIT_SECONDS:-1800}
[[ "$source_wait" =~ ^[1-9][0-9]*$ ]]
rm -f "$build_root/pipeline-result.json"
exec > >(tee -a "$build_root/logs/native-pipeline.log") 2>&1
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/pipeline-result.json"' EXIT
printf 'waiting-for-source\n' > "$build_root/pipeline-stage.txt"
source_deadline=$((SECONDS + source_wait))
while :; do
  if [ -f "$source_result" ]; then
    source_status=$(python3 - "$source_result" "$source_run_id" <<'PY'
import json
import sys
result = json.loads(open(sys.argv[1]).read())
if result.get('run_id') != sys.argv[2]:
    raise RuntimeError('Source result belongs to another run')
print(result.get('status', ''))
PY
    )
    case "$source_status" in
      'checkout verified') break ;;
      failed)
        python3 - "$source_result" <<'PY' >&2
import json
import sys
result = json.loads(open(sys.argv[1]).read())
print('Source fetch failed: ' + str(result.get('error', 'unknown source error')))
PY
        exit 1
        ;;
      running) ;;
      *) echo "Unexpected source handoff status: $source_status" >&2; exit 1 ;;
    esac
  fi
  if (( SECONDS >= source_deadline )); then
    echo "Timed out waiting for source handoff: $source_result" >&2
    exit 1
  fi
  sleep 10
done
python3 - "$source_result" "$source_run_id" <<'PY'
import json
import sys
result = json.loads(open(sys.argv[1]).read())
if result.get('run_id') != sys.argv[2] or result.get('status') != 'checkout verified':
    raise RuntimeError('Source handoff is not a verified checkout')
if result.get('revision') != 'e9d9e60c85f643e10eeb03f42f61554d18dcb30f':
    raise RuntimeError('Source handoff revision is not pinned')
PY
if [ ! -d "$build_root/UnrealEngine_4.26" ]; then
  mv "$build_root/UnrealEngine-parallel" "$build_root/UnrealEngine_4.26"
fi
test -d "$build_root/UnrealEngine_4.26/.git"
test "$(git -C "$build_root/UnrealEngine_4.26" rev-parse HEAD)" = e9d9e60c85f643e10eeb03f42f61554d18dcb30f
if [ "${1:-setup}" != carla ]; then
  printf 'building-engine\n' > "$build_root/pipeline-stage.txt"
  bash "$build_root/downloads/build_engine.sh" "${1:-setup}"
fi
printf 'building-carla\n' > "$build_root/pipeline-stage.txt"
bash "$build_root/downloads/build_carla.sh"
printf 'editor-built-import-pending\n' > "$build_root/pipeline-stage.txt"
