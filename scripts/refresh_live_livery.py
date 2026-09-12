#!/usr/bin/env python3
"""Download current paid artwork and freeze a complete livery before each run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default=shutil.which('blender') or '/Applications/Blender.app/Contents/MacOS/Blender')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    asset = ROOT / 'work/live-livery' / stamp
    subprocess.run(['node', str(ROOT / 'apps/website/scripts/export-livery.mjs'), str(asset)], check=True)
    with (asset / 'model-build.log').open('w') as log:
        subprocess.run([args.blender, '--background', '--python-exit-code', '1', '--python', str(asset / 'apply-livery.py'), '--', str(asset)], check=True, stdout=log, stderr=subprocess.STDOUT)
    original = json.loads((asset / 'livery.json').read_text())
    sponsors = [{'slotId': x['slotId'], 'brand': x['brand'], 'url': x['url'],
                 'mesh': x['slot']['panel'], 'texture': x['texture'],
                 'widthMetres': x['slot']['width_m'], 'heightMetres': x['slot']['height_m']} for x in original['placements']]
    manifest = {'revision': original['revision'], 'layoutVersion': original['layoutVersion'],
                'source': original['source'], 'exportedAt': original['fetchedAt'], 'sponsors': sponsors}
    (asset / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    hashes = json.loads((asset / 'sha256.json').read_text())
    for name in ['manifest.json', 'sponsored-mini.blend', 'sponsored-mini.glb']:
        hashes[name] = hashlib.sha256((asset / name).read_bytes()).hexdigest()
    (asset / 'sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    with (asset / 'mesh-export.log').open('w') as log:
        subprocess.run([args.blender, '--background', '--python-exit-code', '1', '--python', str(ROOT / 'scripts/export_sponsor_meshes.py'), '--', str(asset)], check=True, stdout=log, stderr=subprocess.STDOUT)
    archive = asset.with_suffix('.tar.gz')
    files = ['manifest.json', 'sha256.json', 'render-panels.npz', *[x['texture'] for x in sponsors]]
    with tarfile.open(archive, 'w:gz') as bundle:
        for name in files:
            bundle.add(asset / name, arcname=str((asset / name).relative_to(ROOT)))
    receipt = {'asset': str(asset), 'relative_asset': str(asset.relative_to(ROOT)), 'archive': str(archive),
               'revision': manifest['revision'], 'layout': manifest['layoutVersion'], 'sponsors': len(sponsors),
               'source': manifest['source'], 'fetched_at': manifest['exportedAt']}
    (ROOT / 'work/latest-livery.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__': main()
