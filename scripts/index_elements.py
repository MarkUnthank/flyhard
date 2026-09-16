#!/usr/bin/env python3
"""Write an index over a directory of exported take elements.

A folder per take, five films in each, is only navigable with a list that says what
each take was: which scenario, whether the fly passed, and what it did. That is what
this writes, in JSON for a later tool and in Markdown for a person.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from flyhard.synopsis import synopsis

ELEMENTS = ('chase.mp4', 'wide.mp4', 'cabin-fly.mp4', 'cns.mp4', 'fly.mp4')
DESCRIPTION = {'chase.mp4': 'chase, behind the car', 'wide.mp4': 'wide, world fixed',
               'cabin-fly.mp4': 'cabin, fly composited in', 'cns.mp4': 'neuron activity',
               'fly.mp4': 'the fly alone'}


def probe(path):
    """Width, height and frames without decoding, when ffprobe is to hand."""
    import subprocess
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                              '-show_entries', 'stream=width,height,nb_frames',
                              '-of', 'csv=p=0', str(path)],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        width, height, frames = out.split(',')[:3]
        return {'width': int(width), 'height': int(height), 'frames': int(frames)}
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root)
    takes = []
    # Hidden directories are the transfer's staging area, not takes.
    for folder in sorted(p for p in root.iterdir()
                         if p.is_dir() and not p.name.startswith('.')):
        record = folder/'take.json'
        manifest = json.loads(record.read_text()) if record.exists() else {}
        entry = {'id': manifest.get('id', folder.name),
                 'scenario': manifest.get('scenario', folder.name.split('-')[0]),
                 'outcome': manifest.get('outcome', 'unknown'),
                 'label': manifest.get('label', ''),
                 'seconds': manifest.get('duration_seconds'),
                 'fps': manifest.get('fps'), 'elements': {}, 'missing': []}
        trace = folder/'trace.json'
        entry['synopsis'] = (synopsis(json.loads(trace.read_text()),
                                      manifest.get('metrics')) if trace.exists() else [])
        for name in ELEMENTS:
            path = folder/name
            if path.exists() and path.stat().st_size > 1024:
                entry['elements'][name] = {'megabytes': round(path.stat().st_size/1e6, 1),
                                           **probe(path)}
            else:
                entry['missing'].append(name)
        entry['complete'] = not entry['missing']
        takes.append(entry)
    (root/'index.json').write_text(json.dumps({'takes': takes}, indent=2)+'\n')

    lines = ['# flyhard 4K elements', '',
             'One folder per take. Every film is the same length and frame rate, so they',
             'stack on a timeline without any sliding. The two camera angles are the',
             'capture untouched; the cabin has the fly composited onto the controls; the',
             'neuron activity and the fly panel are rendered at 3840x2160.', '',
             'Each take is described by beats read off its own control trace, timed in',
             'seconds from the first frame, so the description cannot drift away from the',
             'footage. A trial stops being scored at the moment of a collision, so beats',
             'after an impact are what the car did afterwards, not behaviour it was',
             'marked on.', '']
    for scenario in sorted({t['scenario'] for t in takes}):
        lines += [f'## {scenario}', '']
        for take in [t for t in takes if t['scenario'] == scenario]:
            state = take['outcome'] + ('' if take['complete']
                                       else f" (still missing {', '.join(take['missing'])})")
            lines.append(f"### `{take['id']}` — {take['label'] or state}")
            lines.append('')
            if not take['complete']:
                lines.append(f"Missing: {', '.join(take['missing'])}.")
                lines.append('')
            lines += [f'- {beat}' for beat in take['synopsis']]
            lines.append('')
    lines += ['## What each file is', '']
    lines += [f'- `{name}` — {DESCRIPTION[name]}' for name in ELEMENTS]
    lines.append('')
    (root/'README.md').write_text('\n'.join(lines))
    print(json.dumps({'root': str(root), 'takes': len(takes),
                      'complete': sum(t['complete'] for t in takes)}))


if __name__ == '__main__':
    main()
