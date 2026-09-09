#!/usr/bin/env python3
"""Launch the validated GPU image and wait for CUDA and CARLA readiness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import runpod_control as control

SSH_CONFIG = ROOT / 'work/ssh-config'


def archive_session():
    if not control.STATE.exists():
        return
    state = json.loads(control.STATE.read_text())
    if not state.get('closed'):
        raise RuntimeError('A Pod session is already open. Use --wait or reconcile its status first.')
    destination = ROOT / 'work/sessions' / state['name']
    destination.mkdir(parents=True, exist_ok=True)
    for name in ['runpod-session.json', 'ssh-config', 'runpod-guard.log', 'runtime-launch.json']:
        source = ROOT / 'work' / name
        if source.exists():
            shutil.copy2(source, destination / name)


def ensure_key():
    key = ROOT / 'secrets/runpod_ed25519'
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '',
                        '-C', 'flyhard-runpod', '-f', str(key)], check=True)
    if not key.with_suffix('.pub').exists():
        raise RuntimeError('The project SSH public key is missing.')


def write_ssh(endpoint):
    host, user, port = endpoint['host'], endpoint['username'], int(endpoint['port'])
    if not re.fullmatch(r'[A-Za-z0-9.:-]+', host) or not re.fullmatch(r'[A-Za-z0-9_-]+', user):
        raise ValueError('Unexpected SSH endpoint from Runpod')
    if not 1 <= port <= 65535:
        raise ValueError('Invalid SSH port from Runpod')
    SSH_CONFIG.write_text(
        f'Host flyhard\n  HostName {host}\n  Port {port}\n  User {user}\n'
        f'  IdentityFile "{ROOT}/secrets/runpod_ed25519"\n'
        f'  UserKnownHostsFile "{ROOT}/work/runpod-known-hosts"\n'
        '  StrictHostKeyChecking accept-new\n  BatchMode yes\n  ConnectTimeout 5\n')
    SSH_CONFIG.chmod(0o600)


def wait_ready(timeout_seconds=1200):
    state = json.loads(control.STATE.read_text())
    if state.get('closed') or not state.get('pod_id'):
        raise RuntimeError('No active Pod session to wait for.')
    requested_epoch = state.get('boot_requested_epoch', state['requested_epoch'])
    end = time.monotonic() + timeout_seconds
    last_status = None
    last_update = 0.0
    remote = shlex.join(['/opt/flyhard-env/bin/python', '-c',
        "import json; from pathlib import Path; p=Path('/workspace/flyhard/work/runtime'); "
        "print(json.dumps({n:json.loads((p/(n+'.json')).read_text()) for n in ['ready','build-receipt']}))"])
    while time.monotonic() < end:
        pod = control.resolve_pod(state)
        if pod is None or pod['status'] in {'EXITED', 'TERMINATED'}:
            raise RuntimeError('Pod stopped before it became ready.')
        endpoint = pod.get('ssh', {}).get('direct')
        status = (pod['status'], bool(endpoint))
        if status != last_status or time.monotonic()-last_update >= 60:
            print(json.dumps({'status': status[0], 'ssh_assigned': status[1],
                              'elapsed_seconds': round(time.time()-requested_epoch, 1)}), flush=True)
            last_status = status
            last_update = time.monotonic()
        if endpoint:
            write_ssh(endpoint)
            try:
                result = subprocess.run(['ssh', '-F', str(SSH_CONFIG), 'flyhard', remote],
                                        capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired:
                result = None
            if result is not None and result.returncode == 0:
                received = json.loads(result.stdout)
                ready, build = received['ready'], received['build-receipt']
                if ready['container_started_epoch'] < requested_epoch:
                    time.sleep(1)
                    continue
                if ready['status'] != 'ready' or ready['cuda_kernel_check'] != 'passed':
                    raise RuntimeError('Runtime did not pass its GPU readiness check.')
                if build['source_revision'] != state['expected_source_revision']:
                    raise RuntimeError('Running image source revision differs from the selected release.')
                if pod['image'] != state['expected_image']:
                    raise RuntimeError('Provider image differs from the selected release.')
                receipt = {'pod_id': pod['id'], 'image': pod['image'],
                    'source_revision': build['source_revision'], 'data_center': pod['dataCenterId'],
                    'requested_epoch': requested_epoch,
                    'request_to_ready_seconds': ready['ready_epoch']-requested_epoch,
                    'provider_and_image_seconds': ready['container_started_epoch']-requested_epoch,
                    'observed_ready_epoch': time.time(), 'ready': ready}
                (ROOT / 'work/runtime-launch.json').write_text(json.dumps(receipt, indent=2)+'\n')
                print(json.dumps(receipt, indent=2), flush=True)
                print('Connect: '+shlex.join(['ssh', '-F', str(SSH_CONFIG), 'flyhard']), flush=True)
                return receipt
        time.sleep(10)
    raise TimeoutError('Runtime readiness timed out. Inspect the Pod logs before retrying.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', action='store_true', help='Wait for the current session without creating a Pod')
    parser.add_argument('--timeout', type=int, default=1200, help='Readiness timeout in seconds')
    args = parser.parse_args()
    if not 30 <= args.timeout <= 1800:
        parser.error('Readiness timeout must be between 30 and 1800 seconds')
    if not args.wait:
        release = json.loads((ROOT / 'deploy/runtime.json').read_text())
        if not release['validated'] or not re.fullmatch(
                r'ghcr\.io/markunthank/flyhard@sha256:[0-9a-f]{64}', release['image']):
            raise RuntimeError('The release must identify a GPU-validated immutable image.')
        archive_session()
        ensure_key()
        name = 'flyhard-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        config = {'name': name, 'cloud': 'SECURE',
            'gpu': {'id': release['default_gpu'], 'count': 1},
            'image': release['image'], 'disk': release['container_disk_gb'],
            'mounts': {'persistent': {'size': release['workspace_gb'], 'path': '/workspace'}},
            'ports': ['22/tcp'],
            'env': {'FLYHARD_MAX_RUNTIME_SECONDS': str(release['runtime_seconds'])}}
        config_path = ROOT / 'work/runtime-pod-config.json'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2))
        control.launch(config_path)
        state = json.loads(control.STATE.read_text())
        state.update(expected_image=release['image'], expected_source_revision=release['source_revision'])
        state['deadline_epoch'] = min(state['deadline_epoch'], time.time()+release['runtime_seconds'])
        control.save_state(state)
    try:
        wait_ready(args.timeout)
    except (Exception, KeyboardInterrupt):
        state = json.loads(control.STATE.read_text())
        pod = control.resolve_pod(state)
        if pod and pod['status'] not in {'EXITED', 'TERMINATED'}:
            control.request('POST', '/v2/pods/'+pod['id']+'/action', {'action': 'stop'})
            print('Readiness failed; Pod stop requested. Workspace is retained for inspection.', file=sys.stderr)
        raise


if __name__ == '__main__':
    main()
