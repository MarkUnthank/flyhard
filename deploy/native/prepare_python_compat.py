"""Retain the ABI library required by Unreal 4.26's bundled Python on Ubuntu 22."""
import hashlib
from pathlib import Path
import subprocess
import urllib.request

root = Path('/workspace/flyhard-build')
archive = root / 'downloads/libffi6_3.2.1-8_amd64.deb'
archive_sha = 'fa26945b0aadfc72ec623c68be9cc59235a7fe42e2388f7015fd131f4fb06dc9'
library = root / 'compat/libffi6/usr/lib/x86_64-linux-gnu/libffi.so.6.0.4'
library_sha = '5a675e4f4e40312eebbaf9816e009793a394ae9385115bf10b82b83643f84963'

def check(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Compatibility cache checksum mismatch: ' + str(path))

if not archive.exists():
    url = 'https://archive.ubuntu.com/ubuntu/pool/main/libf/libffi/' + archive.name
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    partial = archive.with_suffix('.partial')
    partial.write_bytes(data)
    check(partial, archive_sha)
    partial.replace(archive)
check(archive, archive_sha)
if not library.exists():
    destination = root / 'compat/libffi6'
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(['dpkg-deb', '-x', str(archive), str(destination)], check=True)
check(library, library_sha)
print('Verified retained libffi6 archive and Unreal Python compatibility library')
