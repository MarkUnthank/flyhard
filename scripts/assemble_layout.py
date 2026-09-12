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
# What counts as arriving, stopping and pulling away. These describe the cut, not any
# recorded quantity, and changing them changes only where the edit lands.
BRAKING = .15
HALTED = .3            # Metres per second. Below this the car is standing still.
MOVING = .5
LEAD_IN = 1.5          # Seconds of wide shot before the brakes come on.


def cut_plan(rows, cameras, fps):
    """Where to cut, taken from what the car did rather than from a stopwatch.

    The sequence is the one the edit asks for: behind the car on the approach, wide as
    it arrives at the crossing, inside the cabin for the wait, wide again as it leaves.
    Each of those boundaries is an event in the trace, so the cut lands on the action
    in any take rather than at a time that happened to suit one of them.
    """
    start = rows[0]['time']

    def when(predicate, after=None, default=None):
        for row in rows:
            if after is not None and row['time'] <= after:
                continue
            if predicate(row):
                return row['time']-start+1/fps
        return default

    total = rows[-1]['time']-start+1/fps
    braking = when(lambda row: row['measured_brake'] > BRAKING, default=total*.5)
    halt = when(lambda row: row['speed_m_s'] < HALTED, after=start+braking, default=None)
    away = (when(lambda row: row['speed_m_s'] > MOVING, after=start+halt)
            if halt is not None else None)
    plan = [(0., 'chase'), (max(0., braking-LEAD_IN), 'wide')]
    if halt is not None and away is not None:
        plan += [(halt, 'cabin-fly'), (away, 'wide')]
    else:
        # A take that never stops has no wait to sit inside the cabin for, and the
        # moment worth seeing is the car running through the crossing, which is a
        # thing you watch from outside: from the cabin the pedestrian is behind the
        # A-pillar and there is nothing on screen. So the wide shot takes the crossing
        # itself, hung on the front bumper passing the line, with the cabin either
        # side of it.
        line = when(lambda row: row.get('front_to_line', -1.) is not None
                    and row.get('front_to_line', -1.) > 0.)
        if line is not None:
            plan += [(line-LEAD_IN, 'wide'), (line+LEAD_IN, 'cabin-fly')]
            plan[1] = (plan[1][0], 'cabin-fly')
    # Only keep cuts that move forwards, to a camera that was actually exported.
    kept = []
    for at, camera in plan:
        if camera not in cameras:
            continue
        if kept and at <= kept[-1][0]:
            kept[-1] = (kept[-1][0], camera)
        else:
            kept.append((at, camera))
    return kept


def content_box(reader, samples=12, floor=12, margin=.04):
    """The rectangle the panel's subject actually occupies, over the whole clip.

    The anatomy is a small object rendered in the middle of a 16:9 frame of black, and
    dropping that frame whole into the layout's panel leaves the brain a fifth of the
    size it could be. So the black is measured rather than assumed: the union of the
    lit pixels across the clip, padded, is what gets scaled into the panel. Sampling
    the whole clip rather than one frame matters because a neuron that only fires late
    still has to be inside the frame from the start, or the panel drifts.
    """
    frames = reader.count_frames() if hasattr(reader, 'count_frames') else 0
    picks = range(0, max(frames, 1), max(1, (frames or samples)//samples))
    left = top = 10**9
    right = bottom = -1
    height = width = 0
    for index in picks:
        try:
            frame = np.asarray(reader.get_data(index))
        except (IndexError, RuntimeError):
            break
        height, width = frame.shape[:2]
        lit = np.argwhere(frame.max(axis=2) > floor)
        if not len(lit):
            continue
        left, top = min(left, lit[:, 1].min()), min(top, lit[:, 0].min())
        right, bottom = max(right, lit[:, 1].max()), max(bottom, lit[:, 0].max())
    if right < 0 or not width:
        return None
    pad_x, pad_y = round((right-left)*margin), round((bottom-top)*margin)
    return (max(0, left-pad_x), max(0, top-pad_y),
            min(width, right+pad_x+1), min(height, bottom+pad_y+1))


def to_aspect(box, aspect, width, height):
    """Grow a content box to the panel's shape, so filling the panel cuts nothing.

    Cropping to the subject and then filling the panel crops twice: the second crop
    takes the fly's wheel and the outer edges of the brain off. Widening or heightening
    the box first means the resize is a straight scale, with whatever black the frame
    has around the subject making up the difference.
    """
    left, top, right, bottom = box
    wide, tall = right-left, bottom-top
    if wide/tall < aspect:
        wide = tall*aspect
    else:
        tall = wide/aspect
    x, y = (left+right)/2, (top+bottom)/2
    left, right = x-wide/2, x+wide/2
    top, bottom = y-tall/2, y+tall/2
    # Clamp into the frame without changing the shape, by sliding rather than cutting.
    left, right = (left+max(0, -left), right+max(0, -left))
    top, bottom = (top+max(0, -top), bottom+max(0, -top))
    left, right = (left-max(0, right-width), right-max(0, right-width))
    top, bottom = (top-max(0, bottom-height), bottom-max(0, bottom-height))
    return (round(max(0, left)), round(max(0, top)),
            round(min(width, right)), round(min(height, bottom)))


def panel_frame(image, box, width, height):
    """Crop a panel to its subject and scale it into the layout's box, losing nothing."""
    picture = Image.fromarray(np.asarray(image))
    if box is not None:
        picture = picture.crop(to_aspect(box, width/height, picture.width, picture.height))
    return picture.resize((width, height), Image.LANCZOS)


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
    parser.add_argument('--camera', help='Hold one angle for the whole clip instead '
                        'of cutting between them')
    parser.add_argument('--title')
    parser.add_argument('--out', required=True)
    parser.add_argument('--credit-seconds', type=float, default=CREDIT_SECONDS)
    args = parser.parse_args()

    folder = Path(args.elements)
    manifest = json.loads((folder/'take.json').read_text())
    rows = json.loads((folder/'trace.json').read_text())
    fps = json.loads((folder/'cameras.json').read_text()).get('fps', manifest.get('fps', 20))
    angles = {name: folder/f'{name}.mp4' for name in ('chase', 'wide', 'cabin-fly')
              if (folder/f'{name}.mp4').exists()}
    if args.camera:
        angles = {args.camera: angles[args.camera]}
    cars = {name: imageio.get_reader(path) for name, path in angles.items()}
    plan = ([(0., args.camera)] if args.camera
            else cut_plan(rows, set(cars), fps))
    if not plan:
        raise SystemExit(f'no camera angles in {folder}')
    panels = {name: imageio.get_reader(folder/f'{name}.mp4')
              for name in ('cns', 'fly') if (folder/f'{name}.mp4').exists()}
    missing = [name for name in ('cns', 'fly') if name not in panels]
    boxes = {name: content_box(reader) for name, reader in panels.items()}
    font = {size: ImageFont.truetype(FONT, size*SCALE) for size in (18, 24, 28)}
    title = args.title or f"{manifest['scenario']} — {manifest.get('label', '')}".strip(' —')

    writer = imageio.get_writer(args.out, fps=fps, codec='libx264', quality=None,
                               macro_block_size=1,
                               ffmpeg_params=['-crf', '16', '-preset', 'slow',
                                              '-pix_fmt', 'yuv420p', '-movflags',
                                              '+faststart'])
    written = 0
    try:
        shots = []
        for index, row in enumerate(rows):
            second = index/fps
            camera = [name for at, name in plan if at <= second][-1]
            if not shots or shots[-1]['camera'] != camera:
                shots.append({'camera': camera, 'from': round(second, 2)})
            try:
                frame = cars[camera].get_data(index)
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
                plate.paste(panel_frame(panel, boxes[name], RIGHT_W, box[1]),
                            (RIGHT_X, box[0]))
            writer.append_data(np.asarray(plate))
            written += 1
        card = np.asarray(credits_card(font))
        for _ in range(round(args.credit_seconds*fps)):
            writer.append_data(card)
    finally:
        writer.close()
        for reader in cars.values():
            reader.close()
        for reader in panels.values():
            reader.close()
    print(json.dumps({'take': manifest['id'], 'out': args.out, 'shots': shots,
                      'frames': written, 'credit_frames': round(args.credit_seconds*fps),
                      'fps': fps, 'width': WIDTH, 'height': HEIGHT,
                      'panels_missing': missing,
                      'panel_content_boxes': {name: [int(v) for v in box] if box else None
                                              for name, box in boxes.items()}}), flush=True)


if __name__ == '__main__':
    main()
