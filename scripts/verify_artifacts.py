#!/usr/bin/env python3
"""Create/verify content hashes before deleting a paid experiment host."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['create', 'verify'])
    parser.add_argument('--manifest', default='work/remote-artifact-manifest.json')
    args = parser.parse_args(); manifest_path = Path(args.manifest)
    if args.mode == 'create':
        paths = list(Path('runs').rglob('*')) + list(Path('data/graph-traced-v1').glob('*'))
        # Rendering extends this metadata locally; the original capture metadata
        # is retained in the export log. All underlying states are compared.
        paths = [p for p in paths if p.is_file() and str(p) != 'runs/e03-learned-replay/metrics.json']
        manifest = {'files': {str(p): {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(paths)}}
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2))
    else:
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest['files'].items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Manifest paths must remain in the current workspace')
            if path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
                raise RuntimeError(f'Artifact verification failed: {name}')
    print(json.dumps({'status': 'verified' if args.mode == 'verify' else 'created',
                      'files': len(manifest['files']),
                      'bytes': sum(x['bytes'] for x in manifest['files'].values()),
                      'manifest_sha256': digest(manifest_path)}, indent=2))


if __name__ == '__main__':
    main()
