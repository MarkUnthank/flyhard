#!/usr/bin/env python3
"""Install the pinned Linux renderer used by the sponsored video pipeline."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request


VERSION = "5.2.1"
ARCHIVE = f"blender-{VERSION}-linux-x64.tar.xz"
SHA256 = "a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9"
URL = "https://download.blender.org/release/Blender5.2/" + ARCHIVE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/workspace/blender"))
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This installer targets the Linux x86-64 GPU runtime")
    args.root.mkdir(parents=True, exist_ok=True)
    archive = args.root / ARCHIVE
    if not archive.exists():
        partial = archive.with_suffix(".download")
        request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 Flyhard renderer"})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        with partial.open("rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == SHA256
        partial.replace(archive)
    with archive.open("rb") as f:
        assert hashlib.file_digest(f, "sha256").hexdigest() == SHA256
    binary = args.root / f"blender-{VERSION}-linux-x64" / "blender"
    if not binary.exists():
        with tarfile.open(archive) as source:
            source.extractall(args.root, filter="data")
    version = subprocess.check_output([str(binary), "--version"], text=True).splitlines()[0]
    assert version.startswith("Blender " + VERSION), version
    receipt = {"binary": str(binary.resolve()), "version": version, "archive_sha256": SHA256, "source": URL}
    (args.root / "renderer-receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
