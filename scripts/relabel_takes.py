#!/usr/bin/env python3
"""Recompute every take's caption from the metrics it already recorded.

Labels are derived from the trial's own numbers, so a wording fix does not need CARLA
run again. This was written because takes the scorer had passed were being captioned
"failed to give way": giving way by slowing rather than stopping dead is correct
driving and the scorer counts it as a pass, but the caption said otherwise, which would
have put a SUCCESS badge beside a sentence calling it a failure.
"""
import argparse
import json
from pathlib import Path

from flyhard.clips import ClipLibrary

from evaluate_scenario import describe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    library = ClipLibrary(args.library)
    changed = []
    for record in library.takes():
        manifest_path = Path(record['directory'])/'take.json'
        manifest = json.loads(manifest_path.read_text())
        wanted = describe(manifest['scenario'], manifest['metrics'])
        if wanted == manifest.get('label'):
            continue
        changed.append({'take': manifest['id'] if 'id' in manifest else record['id'],
                        'outcome': manifest['outcome'],
                        'was': manifest.get('label'), 'now': wanted})
        if not args.dry_run:
            manifest['label'] = wanted
            manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    for row in changed:
        print(json.dumps(row), flush=True)
    if not args.dry_run:
        library.index()
    print(json.dumps({'takes': len(library.takes()), 'relabelled': len(changed),
                      'dry_run': args.dry_run}))


if __name__ == '__main__':
    main()
