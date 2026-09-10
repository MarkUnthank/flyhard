#!/usr/bin/env python3
"""Cut synchronized native cameras, with the physical fly in the cabin view."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from OpenGL import GL

from flyhard.cockpit import WheelRig
from flyhard.live_livery import verify_live_livery, verify_layer_livery
from flyhard.interior_view import InteriorFlyView
from flyhard.steering_hud import draw_steering_readout
from flyhard.video_branding import draw_site_brand
from train_roundabout import sha


def depth_image(path):
    encoded = np.asarray(Image.open(path), dtype=np.float32)
    return (encoded[:, :, 0] + 256 * encoded[:, :, 1] + 65536 * encoded[:, :, 2]) * (1000 / 16777215)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--run', required=True)
    p.add_argument('--previews', action='store_true')
    p.add_argument('--asset', required=True, help='Fresh live sponsor export')
    p.add_argument('--cabin-only', action='store_true', help='Check cabin placement before sponsor rendering')
    args = p.parse_args(); root = Path(args.run)
    manifest = verify_live_livery(args.asset, root)
    if not args.cabin_only: verify_layer_livery(args.asset, root / 'sponsor-shots')
    frames = json.loads((root / 'frames.json').read_text())
    config = json.loads((root / 'config.json').read_text())
    plan = json.loads((root / 'edit-plan.json').read_text())
    fps = config['fps']; started = time.perf_counter()
    assert len(plan['frames']) == len(frames)
    if not args.previews and not (root / 'cns-render-metrics.json').exists():
        subprocess.run([sys.executable, 'scripts/render_cns.py', '--run', str(root),
                        '--geometry', 'data/cns-geometry-v1/geometry.npz'], check=True)
    with np.load(root / 'body-trace.npz') as archive:
        body = {k: archive[k] for k in archive.files}
    rig = WheelRig(indicator_stalk=True); replay = mj.MjData(rig.model)
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body('wheel').id, :3] = [.30, .30, .30]
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body('indicator_stalk').id, :3] = [.95, .48, .08]
    cabin = InteriorFlyView(rig, 1248, 960, frames[0]['cameras']['cabin']['relative_matrix'],
                            [.27, -.41, 1.03], metres_per_rig_unit=.16, horizontal_fov=90)
    renderer = mj.Renderer(rig.model, height=440, width=600)
    gpu = GL.glGetString(GL.GL_RENDERER).decode(); assert 'NVIDIA' in gpu
    camera = mj.MjvCamera(); camera.lookat[:] = [.2, 0, 1.1]
    camera.distance = 5.; camera.azimuth = 125; camera.elevation = -24
    fonts = {s: ImageFont.truetype('assets/fonts/Geist.ttf', s) for s in [20, 24, 28, 32]}
    paths = {'front': root / 'carla-camera.mp4', **{n: root / 'cameras' / n / 'rgb.mp4' for n in ['orbit', 'indicator', 'cabin']}}
    readers = {k: imageio.get_reader(v) for k, v in paths.items()}
    neural = None if args.previews else imageio.get_reader(root / 'cns-layer.mp4')
    output = root / 'flyhard-directed-16x9.mp4'
    writer = None if args.previews else imageio.get_writer(output, fps=fps, codec='libx264', macro_block_size=1,
        ffmpeg_params=['-crf', '17', '-preset', 'fast', '-movflags', '+faststart', '-threads', '4',
        '-metadata', f"comment=Sponsor livery r{manifest['revision']} layout{manifest['layoutVersion']}. CARLA 0.9.16, CVC, Universitat Autonoma de Barcelona. Camera-matched MuJoCo fly composite."])
    on, off = plan['signal_on_frame'], plan['signal_off_frame']
    wanted = {0, 25, max(0, on - 15), on + 3, on + 24, on + 45,
              min(len(frames)-1, on+80), off, min(len(frames)-1, off+22)}
    samples, changes, last_camera, fly_pixels = [], [], None, []
    layers = {}
    try:
        for i, record in enumerate(frames):
            images = {name: reader.get_next_data() for name, reader in readers.items()}
            neural_image = neural.get_next_data() if neural else np.zeros((440, 600, 3), np.uint8)
            if args.previews and i not in wanted:
                continue
            shot = plan['frames'][i]; name = shot['camera']
            if args.cabin_only and name != 'cabin':
                continue
            assert record['body_index'] == record['neural_index'] == body['decision_index'][i] == i
            assert abs(body['time'][i] - record['camera_time']) < 1e-4
            for key in ['qpos', 'qvel', 'ctrl']:
                getattr(replay, key)[:] = body[key][i]
            replay.time = body['time'][i]; mj.mj_forward(rig.model, replay)
            raw = images[name]
            dp = root / 'depth' / f'{i:05}.png' if name == 'front' else root / 'cameras' / name / 'depth' / f'{i:05}.png'
            native_depth = depth_image(dp)
            if name == 'cabin':
                cabin.camera_matrix = np.asarray(record['cameras']['cabin']['relative_matrix'])
                raw, mask, _ = cabin.render(replay, raw, native_depth)
                fly_pixels.append({'frame': i, 'pixels': int(mask.sum())})
                # Compose in the calibrated native frame first, then tighten
                # the shot on the forelegs instead of the empty cabin roof.
                raw = np.asarray(Image.fromarray(raw).crop((110, 190, 1085, 940)).resize((1248, 960), Image.Resampling.LANCZOS))
                if i in wanted:
                    Image.fromarray(raw).save(root / f'cabin-composite-{i:04}.png')
            else:
                key = shot['sponsor_key']; directory = root / 'sponsor-shots' / key
                if key not in layers:
                    rgba = np.asarray(Image.open(directory / 'sponsor-layer.png').convert('RGBA'), dtype=np.float32) / 255
                    layer_depth = np.load(directory / 'sponsor-depth.npy')
                    if name != 'orbit':
                        layers[key] = rgba, layer_depth
                else:
                    rgba, layer_depth = layers[key]
                alpha = rgba[:, :, 3] * (native_depth + .03 >= layer_depth)
                raw = (raw * (1 - alpha[:, :, None]) + rgba[:, :, :3] * 255 * alpha[:, :, None]).clip(0, 255).astype(np.uint8)
            if shot['body_closeup']:
                camera.lookat[:] = rig.stalk.center + [-.15, -.1, .22]
                camera.distance = 2.7; camera.azimuth = -105; camera.elevation = -17
            else:
                camera.lookat[:] = [.2, 0, 1.1]
                camera.distance = 5.; camera.azimuth = 125; camera.elevation = -24
            renderer.update_scene(replay, camera=camera, scene_option=cabin.option)
            renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
            canvas = Image.new('RGB', (1920, 1080), 'black')
            canvas.paste(Image.fromarray(raw), (24, 64))
            canvas.paste(Image.fromarray(neural_image), (1296, 64))
            canvas.paste(Image.fromarray(renderer.render()), (1296, 584))
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 23), shot['title'], font=fonts[24], fill='#eee')
            draw.text((1272, 23), f"{record['speed_m_s'] * 3.6:.0f} km/h", anchor='ra', font=fonts[28], fill='white')
            draw.text((1296, 23), 'Neural activity', font=fonts[24], fill='#eee')
            draw.text((1296, 540), 'Foreleg + stalk' if shot['body_closeup'] else 'Fly', font=fonts[24], fill='#eee')
            signal = record['applied_signal'].upper()
            draw.text((1896, 540), 'SIGNAL ' + signal, anchor='ra', font=fonts[24], fill='#ffbd59' if signal != 'OFF' else '#999')
            draw_steering_readout(canvas, requested_angle=record['requested_angle'], wheel_angle=record['wheel_angle'],
                                  applied_steer=record['applied_steer'])
            draw.text((970, 1052), f"Stalk {np.degrees(record['stalk_angle']):+.1f}°", anchor='mm', font=fonts[24], fill='#ddd')
            draw_site_brand(canvas)
            if i in wanted:
                canvas.save(root / f'directed-preview-{i:04}.png')
            if writer:
                writer.append_data(np.asarray(canvas))
            if name != last_camera:
                changes.append({'frame': i, 'time': i / fps, 'camera': name, 'title': shot['title']})
                last_camera = name
            samples.append({'frame': i, 'camera': name, 'carla_frame': record['carla_frame'], 'body_time': replay.time})
            if i % 40 == 0:
                print(json.dumps({'frame': i, 'camera': name, 'wall_seconds': time.perf_counter() - started}), flush=True)
        if writer:
            credit = Image.new('RGB', (1920, 1080), 'black'); draw = ImageDraw.Draw(credit)
            lines = ['Vehicle: CARLA 0.9.16 · CVC, Universitat Autònoma de Barcelona',
                     'Connectome: MaleCNS / Janelia · Fly: NeuroMechFly / FlyGym, EPFL',
                     f"Sponsor livery: revision {manifest['revision']} · layout {manifest['layoutVersion']}",
                     'Cabin fly and sponsor surfaces composited using native camera depth']
            for j, line in enumerate(lines):
                draw.text((960, 440 + j * 50), line, anchor='mm', font=fonts[24], fill='#ddd')
            draw_site_brand(credit)
            for _ in range(2 * fps):
                writer.append_data(np.asarray(credit))
    finally:
        for reader in readers.values(): reader.close()
        if neural: neural.close()
        if writer: writer.close()
        renderer.close(); cabin.close()
    metrics = {'status': 'previewed' if args.previews else 'rendered', 'source_frames': len(frames),
               'fps': fps, 'width': 1920, 'height': 1080, 'duration_seconds': len(frames) / fps + 2,
               'gpu': gpu, 'same_episode': True, 'playback_speed': 1, 'cuts': changes, 'frame_map': samples,
               'cabin_fly_pixels': fly_pixels, 'native_fly': False, 'sponsor_revision': manifest['revision'], 'sponsor_layout': manifest['layoutVersion'],
               'body_sha256': sha(root / 'body-trace.npz'), 'neural_sha256': sha(root / 'neural-trace.npz'),
               'frames_sha256': sha(root / 'frames.json'), 'edit_plan_sha256': sha(root / 'edit-plan.json'),
               'renderer_sha256': sha(__file__), 'wall_seconds': time.perf_counter() - started}
    if writer: metrics['video_sha256'] = sha(output)
    (root / ('directed-preview-metrics.json' if args.previews else 'directed-render-metrics.json')).write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: v for k, v in metrics.items() if k not in ['frame_map', 'cabin_fly_pixels']}, indent=2))


if __name__ == '__main__':
    main()
