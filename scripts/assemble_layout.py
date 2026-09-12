#!/usr/bin/env python3
"""Build the flyhard layout from an exported elements folder, and tail it with credits.

The layout renderer works from a clip-library take and re-renders the fly and the
anatomy as it goes, which needs the policy checkpoint and a GPU. Once a take has been
exported as elements, all three panels already exist as films, so the layout is a
composite of things on disk and nothing has to be simulated, replayed or re-rendered.
That is what this does, which is also why it still works when the machine that made
the elements is gone.

Nothing is written over the picture. The title and the control readout sit in the
black surround, so the car image stays clean and any commentary can be added in an
editor afterwards. The clip ends on a credits card rather than a hard cut.
"""
import argparse
import json
from pathlib import Path
import sys

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_take_layout import (CAR_H, CAR_W, CAR_X, CAR_Y, CNS_H, CNS_Y, FLY_H, FLY_Y,
                                FONT, HEIGHT, RIGHT_W, RIGHT_X, SCALE, WIDTH, fit,
                                surround)

CREDITS = ['Vehicle: CARLA 0.9.16 · CVC, Universitat Autònoma de Barcelona',
           'Connectome: MaleCNS / Janelia · CC BY 4.0',
           'Fly: NeuroMechFly / FlyGym · NeLy, EPFL',
           'The fly in the cabin is the recorded run replayed, blended over the frame',
           'Neuron colour is model state, not measured biological activity']
CREDIT_SECONDS = 3.


def contain(image, width, height):
    """Fit the whole frame inside the panel on black, losing none of it.

    The car pane is filled by cropping, because a driving camera has nothing important
    at its edges. The anatomy and the fly are already rendered against black with the
    subject framed to the edges of their own picture, so cropping them cuts the fly's
    wheel off. These are fitted instead.
    """
    picture = Image.fromarray(np.asarray(image))
    scale = min(width/picture.width, height/picture.height)
    picture = picture.resize((max(1, round(picture.width*scale)),
                              max(1, round(picture.height*scale))), Image.LANCZOS)
    panel = Image.new('RGB', (width, height), (0, 0, 0))
    panel.paste(picture, ((width-picture.width)//2, (height-picture.height)//2))
    return panel


def credits_card(font, extra=()):
    plate = Image.new('RGB', (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(plate)
    draw.text((WIDTH/2, HEIGHT*.36), 'flyhard', anchor='mm', font=font[28],
              fill=(235, 235, 235))
    for index, line in enumerate([*CREDITS, *extra]):
        draw.text((WIDTH/2, HEIGHT*.44+index*46*SCALE), line, anchor='mm', font=font[18],
                  fill=(190, 190, 190))
    draw.text((WIDTH/2, HEIGHT*.80), 'thedrivingfly.com', anchor='mm', font=font[24],
              fill=(150, 150, 150))
    return plate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--elements', required=True, help='An exported elements folder')
    parser.add_argument('--camera', default='chase', choices=['chase', 'wide', 'cabin-fly'])
    parser.add_argument('--title')
    parser.add_argument('--out', required=True)
    parser.add_argument('--credit-seconds', type=float, default=CREDIT_SECONDS)
    args = parser.parse_args()

    folder = Path(args.elements)
    manifest = json.loads((folder/'take.json').read_text())
    rows = json.loads((folder/'trace.json').read_text())
    fps = json.loads((folder/'cameras.json').read_text()).get('fps', manifest.get('fps', 20))
    car = imageio.get_reader(folder/f'{args.camera}.mp4')
    panels = {name: imageio.get_reader(folder/f'{name}.mp4')
              for name in ('cns', 'fly') if (folder/f'{name}.mp4').exists()}
    missing = [name for name in ('cns', 'fly') if name not in panels]
    font = {size: ImageFont.truetype(FONT, size*SCALE) for size in (18, 24, 28)}
    title = args.title or f"{manifest['scenario']} — {manifest.get('label', '')}".strip(' —')

    writer = imageio.get_writer(args.out, fps=fps, codec='libx264', quality=None,
                               macro_block_size=1,
                               ffmpeg_params=['-crf', '16', '-preset', 'slow',
                                              '-pix_fmt', 'yuv420p', '-movflags',
                                              '+faststart'])
    written = 0
    try:
        for index, row in enumerate(rows):
            try:
                frame = car.get_data(index)
            except IndexError:
                break
            plate = surround(title, row, font)
            plate.paste(fit(frame, CAR_W, CAR_H), (CAR_X, CAR_Y))
            for name, box in (('cns', (CNS_Y, CNS_H)), ('fly', (FLY_Y, FLY_H))):
                reader = panels.get(name)
                if reader is None:
                    continue
                try:
                    panel = reader.get_data(index)
                except IndexError:
                    continue
                plate.paste(contain(panel, RIGHT_W, box[1]), (RIGHT_X, box[0]))
            writer.append_data(np.asarray(plate))
            written += 1
        card = np.asarray(credits_card(font))
        for _ in range(round(args.credit_seconds*fps)):
            writer.append_data(card)
    finally:
        writer.close()
        car.close()
        for reader in panels.values():
            reader.close()
    print(json.dumps({'take': manifest['id'], 'out': args.out, 'camera': args.camera,
                      'frames': written, 'credit_frames': round(args.credit_seconds*fps),
                      'fps': fps, 'width': WIDTH, 'height': HEIGHT,
                      'panels_missing': missing}), flush=True)


if __name__ == '__main__':
    main()
