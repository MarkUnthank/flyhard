"""Require a freshly checked production sponsor snapshot before a recording."""
import hashlib
import json
from pathlib import Path
import time
import urllib.request


ORIGIN = 'https://thedrivingfly.com'


def verify_live_livery(asset, output):
    asset, output = Path(asset), Path(output)
    manifest = json.loads((asset / 'manifest.json').read_text())
    def get(path):
        request = urllib.request.Request(ORIGIN + path, headers={'Cache-Control': 'no-cache', 'User-Agent': 'Flyhard recording preflight'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    live = get('/api/livery')
    inventory = get('/model/ad-spaces.json')
    if manifest['revision'] != live['revision']:
        raise RuntimeError('Sponsors changed: run scripts/refresh_live_livery.py before recording or rendering')
    if manifest['layoutVersion'] != inventory['layout_version']:
        raise RuntimeError('Panel layout changed: rebuild the latest livery')
    if {s['slotId'] for s in manifest['sponsors']} != set(live['placements']):
        raise RuntimeError('Missing or extra paid sponsor surfaces')
    hashes = json.loads((asset / 'sha256.json').read_text())
    used = ['manifest.json', *[s['texture'] for s in manifest['sponsors']]]
    for name in ['render-panels.npz', 'sponsored-mini.blend', 'sponsored-mini.glb']:
        if (asset / name).exists(): used.append(name)
    for name in used:
        if hashlib.sha256((asset / name).read_bytes()).hexdigest() != hashes[name]:
            raise RuntimeError('Sponsor file checksum mismatch: ' + name)
    receipt = {'source': ORIGIN, 'checked_epoch': time.time(), 'revision': live['revision'],
               'layout': inventory['layout_version'], 'sponsor_count': len(manifest['sponsors']),
               'snapshot_exported_at': manifest.get('exportedAt'),
               'verified_files': {name: hashes[name] for name in used}, 'status': 'current'}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'livery-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'livery-preflight.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return manifest


def verify_layer_livery(asset, layers):
    """Reject pre-rendered projections from a different livery snapshot."""
    asset, layers = Path(asset), Path(layers)
    manifest = json.loads((asset / 'manifest.json').read_text())
    hashes = json.loads((asset / 'sha256.json').read_text())
    metrics = json.loads((layers / 'metrics.json').read_text())
    if (metrics['revision'], metrics['layout']) != (manifest['revision'], manifest['layoutVersion']):
        raise RuntimeError('Sponsor projections are stale: rebuild them from the fresh live export')
    if metrics['source_blend_sha256'] != hashes['sponsored-mini.blend']:
        raise RuntimeError('Sponsor projections do not match the selected packed model')
