#!/bin/bash
# Require clean commandlet exits as well as checked, persisted native assets.
set -euo pipefail
root=/workspace/flyhard-build
test "$(id -u)" != 0
test -n "${FLYHARD_NATIVE_EXPORT:-}"
test -n "${FLYHARD_NATIVE_IMPORT_ATTEMPT:-}"
exec 9>"$root/.native-import.lock"
flock -n 9
if pgrep -u "$(id -u)" -x UE4Editor >/dev/null; then
  echo 'Stop the editor preview before importing and checking assets.' >&2
  exit 1
fi
python3 - <<'PY'
import os
from pathlib import Path
import shutil
import time
source = Path(os.environ['FLYHARD_NATIVE_EXPORT'])
files = [source / x for x in ['unreal-import-receipt.json', 'unreal-reload-receipt.json',
                              'import-process-result.json'] if (source / x).exists()]
if files:
    history = source / 'import-history' / str(time.time_ns())
    history.mkdir(parents=True)
    for file in files:
        shutil.move(str(file), str(history / file.name))
PY
for phase in import reload; do
  if [ "$phase" = import ]; then script=import_livery.py; else script=verify_saved_livery.py; fi
  set +e
  bash "$root/downloads/editor.sh" -run=pythonscript \
    -script="$root/downloads/$script" -unattended -NullRHI -nosound -nop4
  code=$?
  set -e
  python3 - "$phase" "$code" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys
import time
source = Path(os.environ['FLYHARD_NATIVE_EXPORT'])
file = source / 'import-process-result.json'
result = json.loads(file.read_text()) if file.exists() else {}
result[sys.argv[1]] = {'exit_code': int(sys.argv[2]), 'finished_epoch': time.time()}
for name in ['unreal-import-receipt.json', 'unreal-reload-receipt.json']:
    if (source / name).exists():
        result[name + '_sha256'] = hashlib.sha256((source / name).read_bytes()).hexdigest()
file.write_text(json.dumps(result, indent=2) + '\n')
PY
  if [ "$code" != 0 ]; then exit "$code"; fi
done
