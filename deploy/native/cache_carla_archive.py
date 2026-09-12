#!/usr/bin/env python3
"""Keep the pinned CARLA dependency archives on the private build volume."""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlparse


ROOT = Path('/workspace/flyhard-build/downloads/carla-dependencies')
MANIFEST = Path(__file__).with_name('archive-manifest.json')


def sha256(path):
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def fetch(spec, url=None):
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / spec['name']
    with archive.with_suffix(archive.suffix + '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if archive.is_file() and archive.stat().st_size == spec['bytes'] and sha256(archive) == spec['sha256']:
            return archive
        partial = archive.with_suffix(archive.suffix + '.partial')
        aria = os.environ.get('FLYHARD_ARIA2') or shutil.which('aria2c')
        if aria:
            subprocess.run([aria, '--continue=true', '--max-connection-per-server=8',
                            '--split=8', '--min-split-size=1M', '--file-allocation=none',
                            '--auto-file-renaming=false', '--allow-overwrite=true',
                            '--max-tries=5', '--retry-wait=5', '--connect-timeout=20',
                            '--timeout=60', '--console-log-level=warn', '--summary-interval=60',
                            '--checksum=sha-256=' + spec['sha256'], '--dir=' + str(ROOT),
                            '--out=' + partial.name, url or spec['url']], check=True)
        else:
            subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                            '--connect-timeout', '20', '--max-time', '600',
                            '--output', str(partial), url or spec['url']], check=True)
        if partial.stat().st_size != spec['bytes'] or sha256(partial) != spec['sha256']:
            raise RuntimeError('Archive checksum or size mismatch: ' + spec['name'])
        partial.replace(archive)
        return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', nargs='?')
    parser.add_argument('--prefetch', action='store_true')
    args = parser.parse_args()
    specs = json.loads(MANIFEST.read_text())
    if args.prefetch:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for archive in pool.map(fetch, specs):
                print('Verified cached archive: ' + archive.name, flush=True)
        return
    if not args.url:
        parser.error('Supply an archive URL or --prefetch')
    name = Path(urlparse(args.url).path).name
    spec = next((s for s in specs if s['name'] == name), None)
    if spec is None:
        raise RuntimeError('Dependency is absent from the pinned archive manifest: ' + name)
    archive = fetch(spec, args.url)
    destination = Path.cwd() / name
    if destination.resolve() != archive.resolve():
        shutil.copyfile(archive, destination)
    print('Using verified cached archive: ' + name, flush=True)


if __name__ == '__main__':
    main()
