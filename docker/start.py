"""Start a preinstalled Flyhard runtime and publish measured readiness.

No package installation, simulator download or extraction happens here.
Workspace code is mutable; the Python environment and CARLA are image assets.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from sync_workspace import sync_workspace


def main():
    started = time.time()
    bundled = Path('/opt/flyhard')
    project = Path('/workspace/flyhard')
    project.mkdir(parents=True,exist_ok=True)
    if os.environ.get('FLYHARD_RUNTIME_LAYOUT') == 'network-volume':
        import hashlib
        asset = Path(os.environ['FLYHARD_CARLA_ROOT'])
        cached = json.loads((asset/'asset-receipt.json').read_text())
        if cached['archive_sha256'] != '09e3ebb28df17962f0c997e66f4b914ad5ea6f1d6a6dbbf13c9f87eb38346d57':
            raise RuntimeError('Seed the pinned CARLA asset before launching this image')
        binary = asset/cached['binary']
        if hashlib.sha256(binary.read_bytes()).hexdigest() != cached['binary_sha256']:
            raise RuntimeError('Cached CARLA launcher has changed; revalidate the volume')
        if not os.environ.get('FLYHARD_NETWORK_VOLUME_ID'):
            raise RuntimeError('Network runtime requires the durable volume ID from the launcher')
    source = sync_workspace(bundled, project, os.environ['FLYHARD_SOURCE_REVISION'])
    environment = project/'.venv'
    if not environment.exists():environment.symlink_to('/opt/flyhard-env',target_is_directory=True)
    if environment.resolve() != Path('/opt/flyhard-env'):
        raise RuntimeError('Workspace .venv differs from the packaged environment; use a fresh workspace.')
    node_modules = project/'node_modules'
    if not node_modules.exists():
        node_modules.symlink_to('/opt/flyhard/node_modules', target_is_directory=True)
    if node_modules.resolve() != Path('/opt/flyhard/node_modules'):
        raise RuntimeError('Workspace node_modules differs from the packaged livery environment')
    runtime = project/'work/runtime'; runtime.mkdir(parents=True,exist_ok=True)
    ready = runtime/'ready.json'; ready.unlink(missing_ok=True)
    receipt = {'status':'starting','container_started_epoch':started,
        'source_revision':os.environ['FLYHARD_SOURCE_REVISION'],
        'workspace_source': {'locally_modified':source['locally_modified'], 'backup':source['backup']},
        'installation_at_startup':False,'project':str(project)}
    (runtime/'startup.json').write_text(json.dumps(receipt,indent=2))
    shutil.copy2(bundled/'build-receipt.json',runtime/'build-receipt.json')
    processes,logs = [],[]
    def spawn(command,name):
        log = (runtime/f'{name}.log').open('a');logs.append(log)
        process = subprocess.Popen(command,cwd=project,stdout=log,stderr=subprocess.STDOUT)
        processes.append(process);return process
    def shutdown(*_):
        for process in processes:
            if process.poll() is None:process.terminate()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    try:
        spawn(['/start.sh'],'services')
        limit = int(os.environ['FLYHARD_MAX_RUNTIME_SECONDS'])
        if not 120 <= limit <= 21600:raise ValueError('Runtime limit must be between 120 and 21600 seconds')
        if os.environ.get('RUNPOD_POD_ID'):
            spawn([sys.executable,str(bundled/'scripts/pod_deadline.py'),
                '--deadline',str(started+limit)],'deadline')
        spawn(['bash',str(project/'scripts/start_carla.sh')],'carla')
        health = spawn([sys.executable,str(bundled/'scripts/runtime_health.py'),
            '--output',str(ready),'--started-epoch',str(started)],'health')
        while health.poll() is None:
            if any(p.poll() is not None for p in processes if p is not health):
                raise RuntimeError('A required runtime process exited during startup; inspect work/runtime logs.')
            time.sleep(.5)
        if health.returncode != 0:raise RuntimeError('Runtime readiness check failed')
        processes.remove(health)
        print(ready.read_text(),flush=True)
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('A required runtime process exited; inspect work/runtime logs.')
            time.sleep(1)
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()
        for log in logs:log.close()


if __name__ == '__main__':main()
