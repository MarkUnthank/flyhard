#!/usr/bin/env python3
"""Composite the fly and its controls into the cabin view of every recorded take.

A post-pass rather than part of the capture: the rig is deterministic and the trial
recorded every control demand it was given, so replaying it offline reproduces exactly
the limb positions the run produced. That means the cabin footage already on disk can
gain the fly without another CARLA pass.

The clean cabin render is kept beside the composited one, so the edit can use either.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import imageio.v2 as imageio

from flyhard.clips import ClipLibrary, sha

OUTPUT = 'rgb-fly.mp4'


def compose(directory):
    """Render one take's cabin view with the fly in it. Returns a short report."""
    from flyhard.fly_view import FlyView
    directory = Path(directory)
    cameras = json.loads((directory/'cameras.json').read_text())
    cabin = cameras['views'].get('cabin')
    if cabin is None:
        return {'take': directory.name, 'skipped': 'no cabin view'}
    rows = json.loads((directory/'trace.json').read_text())
    frames = [f for f in cameras['frames'] if 'cabin' in f['views']]
    reader = imageio.get_reader(directory/cabin['rgb'])
    target = directory/Path(cabin['rgb']).parent/OUTPUT
    writer = imageio.get_writer(target, fps=cameras.get('fps', 20), codec='libx264',
                                ffmpeg_params=['-crf', '17', '-preset', 'veryfast'])
    view = drawn = None
    written = 0
    try:
        for index, row in enumerate(rows):
            # Where the fly steers, the wheel follows the learned demand; where it does
            # not, it follows the lane-keeping request. Either way this is the number
            # the trial actually sent to the rig.
            steer = row['demand_steer'] if row['demand_steer'] is not None else row['measured_steer']
            if view is None:
                first = reader.get_data(0)
                view = FlyView(first.shape[1], first.shape[0])
            view.replay(steer, row['demand_throttle'], row['demand_brake'])
            if index >= len(frames):
                break
            try:
                rgb = reader.get_data(index)
            except IndexError:
                break
            meta = frames[index]['views']['cabin']
            composed, drawn = view.render(meta['relative_matrix'], meta['fov'], rgb)
            writer.append_data(composed)
            written += 1
    finally:
        writer.close()
        reader.close()
        if view is not None:
            view.close()
    return {'take': directory.name, 'frames': written, 'fly_pixels_last': drawn,
            'output': str(target.relative_to(directory))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True)
    parser.add_argument('--scenario', help='Only this scenario; default is every take')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--keep-clean', action='store_true',
                        help='Leave the take pointing at the clean cabin render')
    args = parser.parse_args()

    library = ClipLibrary(args.library)
    takes = [t for t in library.takes()
             if (not args.scenario or t['scenario'] == args.scenario) and 'cabin' in t['cameras']]
    if not takes:
        raise SystemExit(f'No takes with a cabin view in {args.library}')
    print(json.dumps({'takes': len(takes), 'workers': args.workers}), flush=True)

    done = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(compose, t['directory']): t for t in takes}
        for future in as_completed(futures):
            report = future.result()
            done.append((futures[future], report))
            print(json.dumps(report), flush=True)

    if args.keep_clean:
        return
    for record, report in done:
        if 'frames' not in report:
            continue
        directory = Path(record['directory'])
        manifest = json.loads((directory/'take.json').read_text())
        relative = str(Path(manifest['cameras']['cabin']).parent/OUTPUT)
        manifest['cameras']['cabin'] = relative
        manifest.setdefault('camera_sha256', {})['cabin'] = sha(directory/relative)
        manifest['notes'] = (manifest.get('notes', '')+' Cabin view carries the fly rig, '
                             'replayed from this take\'s own recorded control demands and '
                             'composited over the clean render, which is kept beside it.').strip()
        (directory/'take.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(library.index()['by_scenario'], indent=2))


if __name__ == '__main__':
    main()
