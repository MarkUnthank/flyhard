"""Fetch APT's authenticated package plan with curl's parallel transfer engine.

APT still chooses versions and performs the installation. Package files are
checked against the size/hash supplied by APT before entering its archive cache.
"""
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

cache = Path('/var/cache/apt/archives')
saved = Path('/workspace/flyhard-build/apt-archives')
saved.mkdir(parents=True, exist_ok=True)
for file in saved.glob('*.deb'):
    if not (cache / file.name).exists():
        shutil.copyfile(file, cache / file.name)
plan = subprocess.check_output(['apt-get', '-y', '--print-uris', '--no-install-recommends',
                                'install', *sys.argv[1:]], text=True)
entries = []
for line in plan.splitlines():
    if not line.startswith("'"):
        continue
    url, name, size, hash_spec = shlex.split(line)
    if Path(name).name != name or not name.endswith('.deb'):
        raise RuntimeError('Unexpected package archive name')
    algorithm, expected = hash_spec.split(':', 1)
    entries.append((url, name, int(size), algorithm.lower().replace('sum', ''), expected))


def verified(path, size, algorithm, expected):
    if not path.exists() or path.stat().st_size != size:
        return False
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest() == expected


pending = []
for entry in entries:
    url, name, size, algorithm, expected = entry
    partial = cache / 'partial' / name
    if verified(partial, size, algorithm, expected):
        partial.replace(cache / name)
    else:
        pending.append(entry)
config = cache / 'flyhard-curl.conf'
config.write_text('\nnext\n'.join(
    'url = {}\noutput = {}\nfail\nlocation\nipv4\nretry = 3\ncontinue-at = "-"'.format(
        '"' + url.replace('"', '\\"') + '"', '"' + str(cache / 'partial' / name) + '"')
    for url, name, *_ in pending))
print('Parallel package downloads:', len(pending), flush=True)
if pending:
    subprocess.run(['curl', '--parallel', '--parallel-immediate', '--parallel-max', '12',
                    '--fail-early', '--config', str(config)], check=True)
for _, name, size, algorithm, expected in entries:
    target = cache / name
    partial = cache / 'partial' / name
    if partial.exists():
        if not verified(partial, size, algorithm, expected):
            raise RuntimeError('Package checksum mismatch: ' + name)
        partial.replace(target)
    if not verified(target, size, algorithm, expected):
        raise RuntimeError('Package checksum mismatch: ' + name)
for file in cache.glob('*.deb'):
    shutil.copyfile(file, saved / file.name)
print('Verified package archives saved for reuse', flush=True)
