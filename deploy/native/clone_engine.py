"""Populate the pinned private Unreal checkout with verified Git blobs.

Read an existing GitHub credential from JSON on SSH stdin. It is never written
to disk or placed in command arguments. Every source run has an explicit ID so
the continuation wrapper cannot consume an old success receipt.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


ROOT = Path('/workspace/flyhard-build')
DEST = ROOT / 'UnrealEngine-parallel'
PIN = 'e9d9e60c85f643e10eeb03f42f61554d18dcb30f'
ORIGIN = 'https://github.com/CarlaUnreal/UnrealEngine.git'


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + str(os.getpid()) + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def validate_origin():
    if DEST.is_symlink():
        raise RuntimeError('Unreal checkout path must not be a symlink')
    if not DEST.exists():
        return
    if not (DEST / '.git').is_dir():
        raise RuntimeError('Existing Unreal destination is not a Git checkout')
    try:
        actual = subprocess.check_output(
            ['git', 'config', '--get', 'remote.origin.url'], cwd=DEST, text=True).strip()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('Existing Unreal checkout has no readable origin') from exc
    if actual != ORIGIN:
        raise RuntimeError('Existing Unreal checkout has an unexpected origin')


def run_source(run_id, result_path, started_epoch):
    atomic_json(result_path, {'run_id': run_id, 'status': 'running',
                              'started_epoch': started_epoch})
    credential = None
    try:
        validate_origin()
        payload = json.load(sys.stdin)
        credential = payload['token']
        if not isinstance(credential, str) or not credential:
            raise RuntimeError('Source credential payload has no token')
        environment = dict(os.environ, FLYHARD_GIT_TOKEN=credential, GIT_TERMINAL_PROMPT='0')
        credential = None

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
                    '--single-branch', '--branch', 'carla', ORIGIN, str(DEST), cwd=ROOT)
            validate_origin()
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=DEST, text=True).strip()
            if head != PIN:
                raise RuntimeError('Unexpected Unreal revision before blob verification')
            git('config', 'fetch.writeCommitGraph', 'false')
            tree = subprocess.check_output(['git', 'ls-tree', '-r', PIN], cwd=DEST, text=True)
            blobs = sorted({line.split()[2] for line in tree.splitlines() if line.split()[1] == 'blob'})
            batches = [batch for batch in (blobs[i::64] for i in range(64)) if batch]

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

            # Git's object database is shared by all batches. Serializing the
            # fetches avoids concurrent pack/index corruption on the volume.
            for item in enumerate(batches):
                fetch(item)
            git('checkout', '--force', PIN)
            checked_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=DEST, text=True).strip()
            if checked_head != PIN:
                raise RuntimeError('Unreal checkout did not land on the pinned revision')
            git('fsck', '--connectivity-only')
            result = {'run_id': run_id, 'revision': checked_head, 'blobs': len(blobs),
                      'status': 'checkout verified', 'started_epoch': started_epoch,
                      'finished_epoch': time.time()}
            atomic_json(result_path, result)
            print('UNREAL_SOURCE_VERIFIED', checked_head, flush=True)
    except BaseException as exc:
        atomic_json(result_path, {'run_id': run_id, 'status': 'failed',
                                  'started_epoch': started_epoch, 'finished_epoch': time.time(),
                                  'error': f'{type(exc).__name__}: {exc}'})
        raise
    finally:
        if credential is not None:
            del credential


def main():
    run_id = os.environ.get('FLYHARD_SOURCE_RUN_ID', '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', run_id):
        raise RuntimeError('FLYHARD_SOURCE_RUN_ID must be a unique safe run identifier')
    result_path = Path(os.environ.get(
        'FLYHARD_SOURCE_RESULT', str(ROOT / ('unreal-source-result-' + run_id + '.json'))))
    started_epoch = time.time()
    run_source(run_id, result_path, started_epoch)


if __name__ == '__main__':
    main()
