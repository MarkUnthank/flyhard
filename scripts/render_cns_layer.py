#!/usr/bin/env python3
"""Render replayed neuron states to a video, in a process of its own.

VTK and MuJoCo both want the EGL display and do not agree about whose it is: put the
anatomy and the fly rig in one process and whichever starts second falls back to X11,
which is not there. So the anatomy is rendered here, on its own, and the layout script
reads the result back as a video. That separation is why the cockpit films have always
shelled out for this layer rather than importing it.
"""
import argparse
import json
from pathlib import Path
import time

import imageio.v2 as imageio
import numpy as np

from flyhard.cns_view import CNSView


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--activity', required=True, help='Replayed neuron states (npz)')
    parser.add_argument('--geometry', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--fps', type=float, default=20.)
    parser.add_argument('--width', type=int, default=600)
    parser.add_argument('--height', type=int, default=440)
    args = parser.parse_args()

    # Materialise once: indexing an NpzFile rereads the whole state matrix per frame.
    with np.load(args.activity) as archive:
        activity = archive['activity']
    started = time.perf_counter()
    view = CNSView(args.geometry, activity, width=args.width, height=args.height)
    writer = imageio.get_writer(args.out, fps=args.fps, codec='libx264', quality=None,
                                macro_block_size=1,
                                ffmpeg_params=['-crf', '14', '-preset', 'fast'])
    try:
        for state in activity:
            writer.append_data(view.render(state))
    finally:
        writer.close()
        view.close()
    print(json.dumps({'out': args.out, 'frames': len(activity),
                      'seconds': round(time.perf_counter()-started, 1),
                      'renderer': view.gpu_capabilities.replace('\n', ' | '),
                      'scale': view.scale}))


if __name__ == '__main__':
    main()
