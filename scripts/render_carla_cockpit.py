#!/usr/bin/env python3
"""Remote-GPU 1920x1080 composite from one captured body/neural/CARLA run."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from flyhard.cockpit import WheelRig


WIDTH, HEIGHT = 1920, 1080
CAR_X, CAR_Y = 24, 126
CNS_X, CNS_Y, CNS_W, CNS_H = 1248, 126, 648, 414
FLY_X, FLY_Y, FLY_W, FLY_H = 1248, 570, 648, 424
DARK = (14, 21, 21)
MUTED = (157, 177, 171)
PALE = (239, 243, 229)
GREEN = (177, 220, 122)


def paint_neural_rates(base, pixels, normalized):
    """Keep the strongest state at each projected pixel, preserving its sign."""
    active = np.abs(normalized) > 0.025
    values = normalized[active]
    selected = pixels[active]
    destinations = np.where(values[:, None] >= 0, [250, 177, 75], [105, 181, 250])
    colors = (np.array([52, 70, 66]) + np.abs(values[:, None]) *
              (destinations - [52, 70, 66])).astype(np.uint8)
    # A channel-wise maximum mixes overlapping orange and blue neurons into
    # a false pink/white state. Choose one actual neuron's complete RGB color.
    flat_pixels = np.concatenate([
        (selected[:, 1] + dy) * base.shape[1] + selected[:, 0] + dx
        for dx, dy in [(0, 0), (1, 0), (0, 1)]
    ])
    colors = np.tile(colors, (3, 1))
    strongest_first = np.argsort(-np.tile(np.abs(values), 3), kind='stable')
    _, first = np.unique(flat_pixels[strongest_first], return_index=True)
    winners = strongest_first[first]
    panel = base.copy()
    panel.reshape(-1, 3)[flat_pixels[winners]] = colors[winners]
    return panel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='runs/carla-cockpit-v1')
    args = parser.parse_args()
    root = Path(args.run)
    config = json.loads((root / 'config.json').read_text())
    metrics = json.loads((root / 'metrics.json').read_text())
    assert metrics['status'] == 'capture_complete'
    frames = json.loads((root / 'frames.json').read_text())
    body = np.load(root / 'body-trace.npz')
    neural = np.load(root / 'neural-trace.npz')
    somata = np.load(root / 'somata.npz')
    activity = neural['activity']
    qpos = body['qpos']
    font_root = Path('/usr/share/fonts/truetype/dejavu')
    if not (font_root / 'DejaVuSans.ttf').exists():
        import matplotlib
        font_root = Path(matplotlib.get_data_path()) / 'fonts/ttf'
    font_path = str(font_root / 'DejaVuSans.ttf')
    bold_path = str(font_root / 'DejaVuSans-Bold.ttf')
    font = {size: ImageFont.truetype(font_path, size) for size in [14, 15, 16, 18, 20, 22, 26, 30, 36]}
    bold = {size: ImageFont.truetype(bold_path, size) for size in [18, 20, 22, 26, 30, 36]}
    # Rotate the orthographic soma view so the brain is left and the VNC right.
    positions = somata['coordinates'][:, [2, 0]].astype(float)
    positions -= positions.min(axis=0)
    positions *= min((CNS_W - 48) / np.ptp(positions[:, 0]), (CNS_H - 106) / np.ptp(positions[:, 1]))
    positions += [(CNS_W - np.ptp(positions[:, 0])) / 2, 55 + (CNS_H - 106 - np.ptp(positions[:, 1])) / 2]
    pixels = positions.astype(int)
    base = np.full((CNS_H, CNS_W, 3), DARK, dtype=np.uint8)
    for dx, dy in [(0, 0), (1, 0), (0, 1)]:
        base[pixels[:, 1]+dy, pixels[:, 0]+dx] = (52, 70, 66)
    sample = activity[::4, somata['indices'][::4]]
    nonzero = np.abs(sample[np.abs(sample) > 1e-8])
    scale = float(np.quantile(nonzero, 0.95)) if len(nonzero) else 1.0
    rig = WheelRig()
    replay = mj.MjData(rig.model)
    renderer = mj.Renderer(rig.model, height=FLY_H, width=FLY_W)
    camera = mj.MjvCamera()
    camera.lookat[:] = [0, 0, 1.1]
    camera.distance = 5.2
    camera.azimuth = 135
    camera.elevation = -23
    render_start = time.perf_counter()
    previous_neural = -1
    cns_panel = None
    replay_error = 0.0
    clock_error = 0.0
    camera_frames = imageio.get_reader(root / 'carla-camera.mp4')
    written = 0
    with imageio.get_writer(root / 'flyhard-cockpit-16x9.mp4', fps=25, codec='libx264',
            quality=None, macro_block_size=1, ffmpeg_params=['-crf', '17', '-preset', 'slow', '-movflags', '+faststart']) as video:
        for index, car_image in enumerate(camera_frames):
            record = frames[index]
            body_index, neural_index = record['body_index'], record['neural_index']
            assert int(body['decision_index'][body_index]) == neural_index
            assert neural['time'][neural_index] <= body['time'][body_index] + 1e-10
            clock_error = max(clock_error, abs(record['camera_time'] - body['time'][body_index]))
            if neural_index != previous_neural:
                rates = activity[neural_index, somata['indices']]
                normalized = (np.arcsinh(rates / max(scale * 0.05, 1e-8)) / np.arcsinh(20)).clip(-1, 1)
                panel = paint_neural_rates(base, pixels, normalized)
                cns_panel = Image.fromarray(panel)
                previous_neural = neural_index
            replay.qpos[:] = qpos[body_index]
            replay.qvel[:] = body['qvel'][body_index]
            replay.ctrl[:] = body['ctrl'][body_index]
            replay.time = body['time'][body_index]
            replay.eq_active[rig.grip_id] = not config['disable_grip']
            mj.mj_forward(rig.model, replay)
            replay_error = max(replay_error, float(np.max(np.abs(replay.qpos - qpos[body_index]))))
            renderer.update_scene(replay, camera=camera)
            fly_image = renderer.render()
            canvas = Image.new('RGB', (WIDTH, HEIGHT), DARK)
            canvas.paste(Image.fromarray(car_image), (CAR_X, CAR_Y))
            canvas.paste(cns_panel, (CNS_X, CNS_Y))
            canvas.paste(Image.fromarray(fly_image), (FLY_X, FLY_Y))
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 20), 'FLYHARD', font=bold[36], fill=GREEN)
            draw.text((260, 29), 'CONNECTOME  >  FLY  >  WHEEL  >  CARLA', font=font[26], fill=PALE)
            draw.text((24, 76), '165,122 neurons  |  25.56 million measured connections  |  saved model running on an A6000', font=font[18], fill=MUTED)
            draw.text((1650, 29), f't = {record["body_time"]:05.2f} s', font=font[30], fill=GREEN)
            for x, y, w, label in [(CAR_X, CAR_Y, 1200, 'CARLA  /  PHYSICAL WHEEL INPUT'),
                                   (CNS_X, CNS_Y, CNS_W, 'CNS  /  RECORDED MODEL ACTIVITY'),
                                   (FLY_X, FLY_Y, FLY_W, 'FLY  /  RECORDED BODY MOVEMENT')]:
                draw.rectangle((x, y, x+w, y+38), fill=(23, 34, 32))
                draw.text((x+14, y+9), label, font=bold[18], fill=PALE)
            draw.text((CNS_X+16, CNS_Y+CNS_H-42), 'Brain', font=font[15], fill=MUTED)
            draw.text((CNS_X+433, CNS_Y+CNS_H-42), 'Ventral nerve cord', font=font[15], fill=MUTED)
            draw.text((CNS_X+16, CNS_Y+CNS_H-21), f'{len(somata["indices"]):,} annotated somata', font=font[14], fill=MUTED)
            draw.text((CNS_X+266, CNS_Y+CNS_H-21), '+ rate', font=font[14], fill=(250, 177, 75))
            draw.text((CNS_X+337, CNS_Y+CNS_H-21), '- rate', font=font[14], fill=(105, 181, 250))
            draw.text((CNS_X+404, CNS_Y+CNS_H-21), '(model states)', font=font[14], fill=MUTED)
            draw.rectangle((FLY_X, FLY_Y+FLY_H-57, FLY_X+FLY_W, FLY_Y+FLY_H), fill=(23, 34, 32))
            draw.text((FLY_X+16, FLY_Y+FLY_H-49), f'Wheel {np.degrees(record["wheel_angle"]):+05.1f} deg', font=bold[20], fill=GREEN)
            draw.text((FLY_X+293, FLY_Y+FLY_H-46), 'Passive wheel; assisted grip', font=font[15], fill=MUTED)
            draw.text((FLY_X+16, FLY_Y+FLY_H-23), f'Neural update {neural["time"][neural_index]:05.2f}s  ->  body {record["body_time"]:05.2f}s', font=font[14], fill=MUTED)
            draw.rectangle((CAR_X, CAR_Y+868-78, CAR_X+1200, CAR_Y+868), fill=(23, 34, 32))
            target = record['requested_angle']
            direction = 'RIGHT' if target > 0.04 else 'LEFT' if target < -0.04 else 'CENTRE'
            draw.text((CAR_X+18, CAR_Y+868-67), f'REQUEST  {direction}', font=bold[22], fill=PALE)
            draw.text((CAR_X+337, CAR_Y+868-67), f'CAR STEER  {record["applied_steer"]:+.3f}', font=font[22], fill=GREEN)
            draw.text((CAR_X+815, CAR_Y+868-67), f'{record["speed_m_s"]*3.6:04.1f} km/h', font=font[22], fill=PALE)
            draw.text((CAR_X+18, CAR_Y+868-30), 'Steering comes only from measured wheel position. Speed controller is scripted.', font=font[16], fill=MUTED)
            draw.text((24, 1023), 'Learned foreleg steering  |  Turn requests + speed scripted  |  Supported cockpit  |  1x playback', font=font[20], fill=PALE)
            draw.text((24, 1053), 'MaleCNS v1.0 (CC BY 4.0)  /  NeuroMechFly + MuJoCo  /  CARLA proxy vehicle  /  Every panel comes from this episode', font=font[15], fill=MUTED)
            video.append_data(np.asarray(canvas))
            written += 1
            if index in [0, 100, 200, 400]:
                canvas.save(root / f'preview-{index:04}.png')
            if index % 100 == 0:
                print(json.dumps({'rendered_frames': written, 'seconds': time.perf_counter()-render_start}), flush=True)
    camera_frames.close()
    renderer.close()
    assert written == len(frames)
    assert replay_error == 0 and clock_error < 1e-4
    with (root / 'flyhard-cockpit-16x9.mp4').open('rb') as stream:
        video_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'status': 'rendered', 'width': WIDTH, 'height': HEIGHT, 'fps': 25,
        'frames': written, 'duration_s': written/25, 'playback_speed': 1.0,
        'same_episode': True, 'max_camera_body_clock_error_s': clock_error,
        'replay_max_qpos_error': replay_error, 'model_rate_color_scale': scale,
        'neural_display': 'All annotated retained soma locations; x/z orthographic view rotated to put brain left, VNC right; signed asinh color, not spikes. Each overlapping pixel shows the strongest absolute state and preserves its sign.',
        'renderer_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'render_wall_seconds': time.perf_counter()-render_start, 'video_sha256': video_hash}
    (root / 'render-metrics.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
