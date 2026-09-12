#!/usr/bin/env python3
"""Render one recorded take into the flyhard layout: car, neural activity, fly.

The same three panels every flyhard film uses. What is new is that this builds them
from a clip-library take rather than from a bespoke capture run, so any take already
on disk can be exported without touching CARLA again.

Nothing is re-simulated. The car footage is the take's own recording; the fly is the
MuJoCo rig replayed from the control demands the trial recorded; and the neural
activity is the policy replayed over the observations the trial recorded. The policy
settles from rest on every control step rather than carrying state between them, so
replaying the whole trace in one pass reproduces the run exactly, which is asserted
against the demands the trial wrote down rather than assumed.

No text is drawn over the picture. The title and the readout sit in the surround, so
the car image is clean and captions can be added in an editor afterwards.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1920, 1080
CAR_X, CAR_Y, CAR_W, CAR_H = 24, 64, 1248, 960
RIGHT_X, RIGHT_W = 1296, 600
CNS_Y, CNS_H = 64, 440
FLY_Y, FLY_H = 584, 440
FONT = str(Path(__file__).resolve().parents[1]/'assets'/'fonts'/'Geist.ttf')
SITE = 'thedrivingfly.com'
def surround(title, row, font):
    """The black surround: title, site, and the readout under the panels."""
    plate = Image.new('RGB', (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(plate)
    draw.text((24, 26), f'flyhard | {title}', font=font[28], fill=(235, 235, 235))
    site = draw.textlength(SITE, font=font[28])
    draw.text((WIDTH-24-site, 26), SITE, font=font[28], fill=(235, 235, 235))
    draw.text((RIGHT_X, CNS_Y+CNS_H+14), 'Neural activity', font=font[18], fill=(150, 150, 150))
    draw.text((RIGHT_X, FLY_Y-28), 'Fly', font=font[18], fill=(150, 150, 150))
    speed = f"{row['speed_m_s']:.1f} m/s"
    pedals = f"Throttle {row['measured_throttle']:.2f} · Brake {row['measured_brake']:.2f}"
    wheel = f"Wheel {row['measured_steer']*45:+.1f}°   CARLA steer {row['measured_steer']:+.3f}"
    draw.text((24, HEIGHT-38), speed, font=font[24], fill=(235, 235, 235))
    middle = draw.textlength(pedals, font=font[24])
    draw.text(((WIDTH-middle)/2, HEIGHT-38), pedals, font=font[24], fill=(235, 190, 120))
    right = draw.textlength(wheel, font=font[24])
    draw.text((WIDTH-24-right, HEIGHT-38), wheel, font=font[24], fill=(235, 235, 235))
    return plate


def fit(image, width, height):
    """Cover the panel and crop, so a panel is never letterboxed into black."""
    picture = Image.fromarray(np.asarray(image))
    scale = max(width/picture.width, height/picture.height)
    picture = picture.resize((max(width, round(picture.width*scale)),
                              max(height, round(picture.height*scale))), Image.LANCZOS)
    left, top = (picture.width-width)//2, (picture.height-height)//2
    return picture.crop((left, top, left+width, top+height))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--take', required=True, help='A clip-library take directory')
    parser.add_argument('--activity', required=True,
                        help='Replayed neuron states from scripts/replay_activity.py')
    parser.add_argument('--cns', help='A rendered anatomy layer; built here if absent')
    parser.add_argument('--geometry', default='data/cns-geometry-v1/geometry.npz')
    parser.add_argument('--camera', default='chase')
    parser.add_argument('--sponsors', action='store_true',
                        help='Use the sponsored render where the take has one')
    parser.add_argument('--title', help='Defaults to the take\'s scenario')
    parser.add_argument('--out', required=True)
    parser.add_argument('--preview', type=int, help='Write this many frames as PNGs instead')
    args = parser.parse_args()

    take = Path(args.take)
    manifest = json.loads((take/'take.json').read_text())
    cameras = json.loads((take/'cameras.json').read_text())
    rows = json.loads((take/'trace.json').read_text())
    activity = np.load(args.activity)['activity']
    if len(activity) != len(rows):
        raise SystemExit(f'{len(activity)} replayed steps against {len(rows)} recorded ones')

    # The anatomy is rendered by a separate process and read back as video, because
    # VTK and MuJoCo cannot share one EGL display; see scripts/render_cns_layer.py.
    fps = cameras.get('fps', 20)
    layer = Path(args.cns) if args.cns else Path(args.out).with_name(take.name+'-cns.mp4')
    if not layer.exists():
        subprocess.run([sys.executable, str(Path(__file__).with_name('render_cns_layer.py')),
                        '--activity', args.activity, '--geometry', args.geometry,
                        '--out', str(layer), '--fps', str(fps),
                        '--width', str(RIGHT_W), '--height', str(CNS_H)], check=True)
    cns = imageio.get_reader(layer)
    from flyhard.fly_view import FlyView
    fly = FlyView(RIGHT_W, FLY_H)
    font = {size: ImageFont.truetype(FONT, size) for size in (18, 24, 28)}
    footage = Path(manifest['cameras'][args.camera])
    if not args.sponsors:
        plain = footage.with_name(footage.name.replace('-sponsored', ''))
        footage = plain if (take/plain).exists() else footage
    source = imageio.get_reader(take/footage)
    writer = None
    if not args.preview:
        writer = imageio.get_writer(args.out, fps=fps, codec='libx264',
                                    quality=None, macro_block_size=1,
                                    ffmpeg_params=['-crf', '17', '-preset', 'slow',
                                                   '-movflags', '+faststart'])
    title = args.title or manifest['scenario']
    written = 0
    try:
        for index, row in enumerate(rows):
            fly.replay(row['demand_steer'] if row['demand_steer'] is not None
                       else row['measured_steer'], row['demand_throttle'], row['demand_brake'])
            try:
                car = source.get_data(index)
            except IndexError:
                break
            if args.preview and index % max(1, len(rows)//args.preview):
                continue
            plate = surround(title, row, font)
            plate.paste(fit(car, CAR_W, CAR_H), (CAR_X, CAR_Y))
            plate.paste(Image.fromarray(cns.get_data(index)), (RIGHT_X, CNS_Y))
            plate.paste(Image.fromarray(fly.panel()), (RIGHT_X, FLY_Y))
            if writer is None:
                plate.save(Path(args.out).with_suffix('')/f'frame-{index:04d}.png')
            else:
                writer.append_data(np.asarray(plate))
            written += 1
    finally:
        if writer is not None:
            writer.close()
        source.close()
        cns.close()
        fly.close()
    print(json.dumps({'take': take.name, 'output': args.out, 'frames': written,
                      'camera': args.camera, 'footage': str(footage),
                      'anatomy': str(layer)}), flush=True)


if __name__ == '__main__':
    main()
