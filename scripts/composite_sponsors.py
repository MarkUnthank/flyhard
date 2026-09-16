#!/usr/bin/env python3
"""Composite the live sponsor livery onto already recorded scenario footage.

The sponsor panels are rasterised from the real curved meshes and depth-tested
against CARLA's own depth buffer, so the car and other traffic occlude them
correctly. This is a presentation composite on top of unsponsored CARLA frames;
nothing about the simulation or the recorded metrics changes.

Runs from the saved take alone. The per-frame camera pose in the vehicle frame was
written at capture time, so sponsoring footage never means re-running CARLA.
"""
import argparse
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image

from flyhard.clips import ClipLibrary
from flyhard.live_livery import verify_live_livery

DEFAULT_VIEWS = ('wide', 'chase')


def depth_metres(path):
    """CARLA packs depth into 24 bits across the colour channels, scaled to 1 km."""
    raw = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32)
    packed = raw[:, :, 0]+raw[:, :, 1]*256.+raw[:, :, 2]*65536.
    return 1000.*packed/(256.**3-1)


def composite_take(take_dir, sponsor_for, views, fps, quality):
    cameras = json.loads((take_dir/'cameras.json').read_text())
    frames = cameras['frames']
    written = {}
    for name in views:
        view = cameras['views'].get(name)
        if view is None:
            continue
        source = take_dir/view['rgb']
        target = source.with_name('rgb-sponsored.mp4')
        covered = 0
        with imageio.get_reader(source) as reader, imageio.get_writer(
                target, fps=fps, codec='libx264', macro_block_size=1,
                ffmpeg_params=['-crf', str(quality), '-preset', 'veryfast', '-threads', '3']) as writer:
            for index, rgb in enumerate(reader):
                if index >= len(frames):
                    break
                entry = frames[index]['views'][name]
                depth = depth_metres(take_dir/view['depth']/f'{index:05}.png')
                out, pixels = sponsor_for(name).render(
                    entry['relative_matrix'], entry['fov'], rgb.astype(np.float32), depth)
                covered += pixels
                writer.append_data(out)
        written[name] = {'file': str(target.relative_to(take_dir)),
                         'sponsor_pixels': int(covered),
                         'mean_sponsor_pixels_per_frame': round(covered/max(len(frames), 1), 1)}
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True)
    parser.add_argument('--asset', required=True, help='Fresh live sponsor export')
    parser.add_argument('--out', required=True, help='Directory for the livery verification receipt')
    parser.add_argument('--scenario')
    parser.add_argument('--views', default=','.join(DEFAULT_VIEWS))
    parser.add_argument('--quality', type=int, default=16)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = verify_live_livery(args.asset, out)
    library = ClipLibrary(args.library)
    views = [v for v in args.views.split(',') if v]

    from flyhard.sponsor_view import SponsorView
    renderers, receipts = {}, []
    try:
        for record in library.takes():
            if args.scenario and record['scenario'] != args.scenario:
                continue
            take_dir = Path(record['directory'])
            if not (take_dir/'cameras.json').exists():
                receipts.append({'take': record['id'], 'skipped': 'no camera metadata'})
                continue
            trial = json.loads((take_dir/'trial.json').read_text()) if (take_dir/'trial.json').exists() else None
            centre = (trial or {}).get('vehicle_bounds', {}).get('location', [0., 0., 0.])
            key = tuple(round(v, 4) for v in centre)
            if key not in renderers:
                renderers[key] = SponsorView(args.asset, manifest, centre)
            written = composite_take(take_dir, lambda _name: renderers[key], views,
                                     record['fps'], args.quality)
            receipts.append({'take': record['id'], 'scenario': record['scenario'],
                             'outcome': record['outcome'], 'views': written})
            print(json.dumps(receipts[-1]), flush=True)
    finally:
        for renderer in renderers.values():
            renderer.close()

    (out/'sponsor-composite-receipt.json').write_text(json.dumps(
        {'library': str(library.root), 'asset': str(args.asset),
         'revision': manifest['revision'], 'layout': manifest['layoutVersion'],
         'sponsors': [s['brand'] for s in manifest['sponsors']], 'views': views,
         'takes': receipts,
         'claim': 'Sponsor panels rasterised from the delivered meshes and depth-composited '
                  'onto unsponsored CARLA frames. Presentation only; no recorded metric, '
                  'trajectory or control value is affected.'}, indent=2)+'\n')


if __name__ == '__main__':
    main()
