#!/usr/bin/env python3
"""Seed immutable simulator/renderer assets once onto an attached network volume.

Run explicitly on a CPU Pod before the first GPU launch. Normal runtime startup
never downloads or extracts packages. A verified directory is atomically promoted
only after the official archive passes SHA-256 verification.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

ASSETS = {
    'carla-0.9.16': {
        'url': 'https://downloads.carlasim.com/Linux/CARLA_0.9.16.tar.gz',
        'sha256': '09e3ebb28df17962f0c997e66f4b914ad5ea6f1d6a6dbbf13c9f87eb38346d57',
        'suffix': '.tar.gz', 'binary': 'CarlaUE4.sh',
    },
    'blender-5.2.1': {
        'url': 'https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz',
        'sha256': 'a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9',
        'suffix': '.tar.xz', 'binary': 'blender-5.2.1-linux-x64/blender',
    },
}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def seed(root, name, spec, downloads):
    destination = root/name
    marker = destination/'asset-receipt.json'
    if marker.exists():
        receipt = json.loads(marker.read_text())
        if receipt['archive_sha256'] != spec['sha256']:
            raise RuntimeError(f'Unexpected existing asset: {destination}')
        binary = destination/spec['binary']
        if not binary.is_file() or sha256(binary) != receipt['binary_sha256']:
            raise RuntimeError(f'Damaged cached asset: {binary}')
        return {**receipt, 'cached': True}
    if destination.exists():
        raise RuntimeError(f'Unverified asset directory already exists: {destination}')
    archive = downloads/(name+spec['suffix'])
    if not archive.exists() or sha256(archive) != spec['sha256']:
        if shutil.which('aria2c'):
            subprocess.run(['aria2c', '--max-connection-per-server=16', '--split=16',
                            '--min-split-size=1M', '--file-allocation=none',
                            '--continue=true',
                            '--allow-overwrite=true', '--auto-file-renaming=false',
                            '--summary-interval=30', '--console-log-level=warn',
                            '--user-agent=Mozilla/5.0 Flyhard runtime',
                            '--dir='+str(downloads), '--out='+archive.name,
                            '--checksum=sha-256='+spec['sha256'], spec['url']], check=True)
        else:
            subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                            '--user-agent', 'Mozilla/5.0 Flyhard runtime',
                            '--output', str(archive), spec['url']], check=True)
    if sha256(archive) != spec['sha256']:
        raise RuntimeError(f'Archive checksum mismatch: {name}')
    staging = Path(tempfile.mkdtemp(prefix=name+'.partial-', dir=root))
    # mkdtemp defaults to 0700, but CARLA runs as ubuntu rather than root.
    staging.chmod(0o755)
    try:
        subprocess.run(['tar', '--no-same-owner', '-xf', str(archive),
                        '-C', str(staging)], check=True)
        binary = staging/spec['binary']
        if not binary.is_file():
            raise RuntimeError(f'Expected executable missing: {binary}')
        receipt = {'name': name, 'source': spec['url'], 'archive_sha256': spec['sha256'],
                   'binary': spec['binary'], 'binary_sha256': sha256(binary),
                   'seeded_epoch': time.time(), 'cached': False}
        (staging/'asset-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise
    # Keep the verified source archive on the durable volume as well. A future
    # rebuild can restore extracted assets without another multi-GB download.
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/workspace/flyhard-runtime'))
    parser.add_argument('--downloads', type=Path, help='Defaults to ROOT/downloads; partial transfers survive Pod deletion')
    args = parser.parse_args()
    args.downloads = args.downloads or args.root/'downloads'
    args.root.mkdir(parents=True, exist_ok=True)
    args.downloads.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with (args.root/'.seed.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {name: executor.submit(seed, args.root, name, spec, args.downloads)
                       for name, spec in ASSETS.items()}
            receipts = {name: future.result() for name, future in futures.items()}
        result = {'status': 'seeded', 'assets': receipts,
                  'wall_seconds': time.time()-started, 'completed_epoch': time.time()}
        (args.root/'seed-receipt.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
