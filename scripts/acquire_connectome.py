#!/usr/bin/env python3
"""Acquire public MaleCNS v1.0 tables and record source hashes, without an API key."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
FILES = {
    "annotations": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "transmitters": "body-neurotransmitters-male-cns-v1.0.feather",
    "weights": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
}
EXPECTED_SHA256 = {
    'annotations': '2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2',
    'transmitters': '95c9289220663abeb3409f3ad9e5a7f8a53f8093f5139d15502cd08da8879621',
    'weights': 'e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1',
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/malecns-v1")
    p.add_argument("--only", choices=FILES)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "sources.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "dataset": "male-cns:v1.0", "license": "CC-BY-4.0",
        "source_page": "https://male-cns.janelia.org/download/", "files": {}}
    for role, name in FILES.items():
        if args.only and role != args.only:
            continue
        path = out / name
        url = BASE + name
        start = time.monotonic()
        if not path.exists():
            temp = path.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=90) as response, temp.open("wb") as f:
                length = int(response.headers.get("Content-Length", "0"))
                while chunk := response.read(8 * 1024 * 1024):
                    f.write(chunk)
                if length and f.tell() != length:
                    raise RuntimeError(f"Incomplete download: {name}")
            temp.replace(path)
        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(8 * 1024 * 1024):
                h.update(chunk)
        if h.hexdigest() != EXPECTED_SHA256[role]:
            raise RuntimeError(f"Source hash differs from the verified v1.0 pilot: {name}")
        manifest["files"][role] = {"filename": name, "url": url, "bytes": path.stat().st_size,
                                    "sha256": h.hexdigest()}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"role": role, "seconds": time.monotonic()-start, **manifest["files"][role]}), flush=True)


if __name__ == "__main__":
    main()
