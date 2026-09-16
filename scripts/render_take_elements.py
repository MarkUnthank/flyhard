#!/usr/bin/env python3
"""Export one recorded take as separate, unedited elements rather than a composite.

An edit wants layers, not a finished frame. So each camera angle leaves here as its
own file at the size it was shot, the fly and the anatomy leave as their own films at
the same size, and nothing is captioned, cropped or laid out. What an editor stacks
them into afterwards is not this script's business.

The one element that is not a straight copy is the cabin: the fly is composited into
it, because a cabin shot of an empty driver's seat is not the shot. That composite is
a replay of the control demands the trial recorded, not a fresh simulation, and it is
an alpha blend over the frame, because the cabin depth buffer is not kept.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import imageio.v2 as imageio
import numpy as np

# The elements are delivered at the size the cameras shot, which is 4:3, so an editor
# crops to whatever aspect the cut wants rather than being handed someone else's crop.
# The rendered elements match that height in 16:9, which is the panel shape they are.
ELEMENT_WIDTH, ELEMENT_HEIGHT = 3840, 2160
# x264 defaults to about one and a half threads per core, which on a 96 core box is
# 144 threads per encoder holding 33 megabyte frames. Several exports at once then
# ask for more than the machine will give and ffmpeg dies with an empty stderr and a
# broken pipe, which is what happened. Capped, so exports can run side by side.
ENCODE = ['-crf', '15', '-preset', 'fast', '-threads', '8', '-movflags', '+faststart']


def writer(path, fps):
    return imageio.get_writer(path, fps=fps, codec='libx264', quality=None,
                              macro_block_size=1, ffmpeg_params=ENCODE)


def cabin_with_fly(take, manifest, cameras, rows, out, fps):
    """The cabin angle with the fly working the controls, frame for frame."""
    from flyhard.fly_view import FlyView
    view = cameras['views']['cabin']
    source = imageio.get_reader(take/manifest['cameras']['cabin'])
    probe = source.get_data(0)
    fly = FlyView(probe.shape[1], probe.shape[0])
    stream, drawn, written = writer(out, fps), 0, 0
    try:
        for index, row in enumerate(rows):
            fly.replay(row['demand_steer'] if row['demand_steer'] is not None
                       else row['measured_steer'], row['demand_throttle'],
                       row['demand_brake'])
            try:
                frame = source.get_data(index)
            except IndexError:
                break
            recorded = cameras['frames'][index]['views']['cabin']
            picture, pixels = fly.render(recorded['relative_matrix'], view['fov'], frame)
            stream.append_data(picture)
            drawn += pixels
            written += 1
    finally:
        stream.close()
        source.close()
        fly.close()
    if not drawn:
        raise SystemExit('the fly never landed a pixel in the cabin frame')
    return {'frames': written, 'mean_fly_pixels': round(drawn/max(written, 1))}


def fly_element(rows, out, fps):
    """The fly alone against black, from the angle every flyhard film frames it."""
    from flyhard.fly_view import FlyView
    fly = FlyView(ELEMENT_WIDTH, ELEMENT_HEIGHT)
    stream = writer(out, fps)
    try:
        for row in rows:
            fly.replay(row['demand_steer'] if row['demand_steer'] is not None
                       else row['measured_steer'], row['demand_throttle'],
                       row['demand_brake'])
            stream.append_data(fly.panel())
    finally:
        stream.close()
        fly.close()
    return {'frames': len(rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--take', required=True, help='A clip-library take directory')
    parser.add_argument('--activity', help='Replayed neuron states, for the anatomy element')
    parser.add_argument('--geometry', default='data/cns-geometry-v1/geometry.npz')
    parser.add_argument('--out', required=True)
    parser.add_argument('--skip', nargs='*', default=[],
                        help='Element names to leave out: chase wide cabin fly cns')
    args = parser.parse_args()

    take = Path(args.take)
    manifest = json.loads((take/'take.json').read_text())
    cameras = json.loads((take/'cameras.json').read_text())
    rows = json.loads((take/'trace.json').read_text())
    fps = cameras.get('fps', manifest.get('fps', 20))
    out = Path(args.out)/manifest['id']
    out.mkdir(parents=True, exist_ok=True)
    made, started = {}, time.perf_counter()

    # The take's own record travels with the elements. Without it a folder of five
    # films says nothing about which run it is, what the fly did or whether it passed.
    for name in ('take.json', 'cameras.json', 'trace.json'):
        shutil.copyfile(take/name, out/name)

    # The angles the cameras shot are copied byte for byte. Re-encoding them would be
    # an edit, and a lossy one, for no gain.
    for name in ('chase', 'wide'):
        if name in args.skip or name not in manifest['cameras']:
            continue
        shutil.copyfile(take/manifest['cameras'][name], out/f'{name}.mp4')
        made[name] = {'copied_from': manifest['cameras'][name]}

    if 'cabin' not in args.skip and 'cabin' in manifest['cameras']:
        made['cabin'] = cabin_with_fly(take, manifest, cameras, rows,
                                       str(out/'cabin-fly.mp4'), fps)

    if 'cns' not in args.skip and args.activity:
        # The anatomy is rendered by a process of its own: VTK and MuJoCo cannot share
        # one EGL display. See scripts/render_cns_layer.py.
        subprocess.run([sys.executable, str(Path(__file__).with_name('render_cns_layer.py')),
                        '--activity', args.activity, '--geometry', args.geometry,
                        '--out', str(out/'cns.mp4'), '--fps', str(fps),
                        '--width', str(ELEMENT_WIDTH), '--height', str(ELEMENT_HEIGHT)],
                       check=True)
        made['cns'] = {'width': ELEMENT_WIDTH, 'height': ELEMENT_HEIGHT}

    if 'fly' not in args.skip:
        made['fly'] = fly_element(rows, str(out/'fly.mp4'), fps)

    report = {'take': manifest['id'], 'scenario': manifest['scenario'],
              'outcome': manifest['outcome'], 'label': manifest.get('label', ''),
              'out': str(out), 'fps': fps, 'elements': made,
              'seconds': round(time.perf_counter()-started, 1)}
    (out/'elements.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
