"""Populate the pinned private Unreal checkout using parallel Git blob fetches.

Read an existing GitHub credential from JSON on SSH stdin. It is never written
to disk or placed in command arguments. Git still verifies every object hash.
This works around the builder's very slow single-stream Git transfer.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path('/workspace/flyhard-build')
DEST = ROOT / 'UnrealEngine-parallel'
PIN = 'e9d9e60c85f643e10eeb03f42f61554d18dcb30f'
credential = json.load(sys.stdin)['token']
environment = dict(os.environ, FLYHARD_GIT_TOKEN=credential, GIT_TERMINAL_PROMPT='0')
del credential
logs = ROOT / 'logs' / 'source-fetch'
logs.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='flyhard-git-auth-') as auth:
    askpass = Path(auth) / 'askpass'
    askpass.write_text('#!/usr/bin/python3\nimport os,sys\n'
                       'print("x-access-token" if "Username" in sys.argv[1] '
                       'else os.environ["FLYHARD_GIT_TOKEN"])\n')
    askpass.chmod(0o700)
    environment['GIT_ASKPASS'] = str(askpass)

    def git(*args, input=None, output=None, cwd=DEST):
        return subprocess.run(['git', '-c', 'http.version=HTTP/1.1',
                               '-c', 'credential.helper=', '-c', 'gc.auto=0',
                               '-c', 'fetch.negotiationAlgorithm=noop',
                               '-c', 'checkout.workers=16',
                               '-c', 'maintenance.auto=false', *args],
                              cwd=cwd, env=environment, input=input, text=True,
                              stdout=output, stderr=subprocess.STDOUT, check=True)

    if not DEST.exists():
        git('clone', '--depth', '1', '--filter=blob:none', '--no-checkout',
            '--single-branch', '--branch', 'carla',
            'https://github.com/CarlaUnreal/UnrealEngine.git', str(DEST), cwd=ROOT)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=DEST, text=True).strip()
    if head != PIN:
        raise RuntimeError('Unexpected Unreal revision')
    git('config', 'fetch.writeCommitGraph', 'false')
    tree = subprocess.check_output(['git', 'ls-tree', '-r', 'HEAD'], cwd=DEST, text=True)
    blobs = sorted({line.split()[2] for line in tree.splitlines() if line.split()[1] == 'blob'})
    batches = [blobs[i::64] for i in range(64)]

    def fetch(item):
        number, objects = item
        receipt = logs / ('batch-{:02d}.done'.format(number))
        if receipt.exists():
            return
        with (logs / ('batch-{:02d}.log'.format(number))).open('w') as log:
            for attempt in range(3):
                try:
                    git('fetch', '--no-tags', '--no-write-fetch-head', '--no-auto-maintenance',
                        '--recurse-submodules=no', '--filter=blob:none',
                        '--stdin', 'origin', input='\n'.join(objects) + '\n', output=log)
                    break
                except subprocess.CalledProcessError:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
        receipt.write_text(str(len(objects)) + '\n')
        print('Verified blob batch', number, flush=True)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(fetch, enumerate(batches)))
    git('checkout', '--force', 'carla')
    git('fsck', '--connectivity-only')
    result = {'revision': head, 'blobs': len(blobs), 'status': 'checkout verified'}
    (ROOT / 'unreal-source-result.json').write_text(json.dumps(result) + '\n')
    print('UNREAL_SOURCE_VERIFIED', head, flush=True)
    environment.pop('FLYHARD_GIT_TOKEN', None)
