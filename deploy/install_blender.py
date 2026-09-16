#!/usr/bin/env python3
"""Install the pinned Linux renderer used by the sponsored video pipeline."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


VERSION = "5.2.1"
ARCHIVE = f"blender-{VERSION}-linux-x64.tar.xz"
SHA256 = "a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9"
URL = "https://download.blender.org/release/Blender5.2/" + ARCHIVE


def verify_archive(path, label):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != SHA256:
        raise RuntimeError(f"{label} SHA-256 mismatch: expected {SHA256}, got {actual}")


def verify_binary(binary):
    if not binary.is_file():
        raise RuntimeError("Blender extraction is incomplete; missing binary: " + str(binary))
    try:
        version = subprocess.check_output(
            [str(binary), "--version"], text=True, stderr=subprocess.STDOUT).splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError) as exc:
        raise RuntimeError("Unable to execute the extracted Blender binary") from exc
    expected = "Blender " + VERSION
    if not version.startswith(expected):
        raise RuntimeError(f"Unexpected Blender version: expected {expected}, got {version}")
    return version


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
        verify_archive(partial, "Downloaded Blender archive")
        partial.replace(archive)
    verify_archive(archive, "Blender archive")
    install_dir = args.root / f"blender-{VERSION}-linux-x64"
    binary = install_dir / "blender"
    complete_marker = install_dir / ".flyhard-install-complete"
    complete = complete_marker.is_file() and complete_marker.read_text().strip() == SHA256
    if not binary.is_file() or not complete:
        staging_parent = Path(tempfile.mkdtemp(prefix=".blender-staging-", dir=args.root))
        backup_parent = None
        backup_dir = None
        try:
            with tarfile.open(archive) as source:
                source.extractall(staging_parent, filter="data")
            staged_dir = staging_parent / install_dir.name
            staged_binary = staged_dir / "blender"
            verify_binary(staged_binary)
            (staged_dir / ".flyhard-install-complete").write_text(SHA256 + "\n")
            if install_dir.exists() or install_dir.is_symlink():
                backup_parent = Path(tempfile.mkdtemp(prefix=".blender-backup-", dir=args.root))
                backup_dir = backup_parent / install_dir.name
                install_dir.rename(backup_dir)
            try:
                staged_dir.rename(install_dir)
            except BaseException:
                if backup_dir is not None and (backup_dir.exists() or backup_dir.is_symlink()):
                    backup_dir.rename(install_dir)
                raise
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
            if backup_parent is not None:
                shutil.rmtree(backup_parent, ignore_errors=True)
    version = verify_binary(binary)
    receipt = {"binary": str(binary.resolve()), "version": version, "archive_sha256": SHA256, "source": URL}
    (args.root / "renderer-receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
