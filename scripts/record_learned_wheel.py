#!/usr/bin/env python3
"""Record learned joint commands and replay body/neurons from the same clock.

No diagnostic IK or desired-action labels are used here. The requested wheel
angle is a disclosed task input; this experiment has no camera observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pyarrow.feather as feather


def capture(args):
    import torch
    from flyhard.cockpit import WheelRig
    from flyhard.motor_policy import WheelPolicy

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    state = checkpoint['model']
    graph = np.load(Path(args.graph) / 'graph.npz')
    policy = WheelPolicy(graph, state['sensory_ids'].numpy(), state['motor_ids'].numpy(),
                         state['neutral'].numpy(), state['action_scale'].numpy(),
                         checkpoint['config']['seed'])
    policy.load_state_dict(state); policy.to(device).eval()
    del checkpoint, state
    rig = WheelRig()
    targets = np.random.default_rng(61733).uniform(0.18, 0.42, 100) * np.tile([1, -1], 50)
    trace = {k: [] for k in ['time', 'episode', 'qpos', 'angle', 'target', 'decision_index',
                            'neural_time', 'neural_episode', 'neural_activity', 'action', 'grip_force']}
    start = time.perf_counter(); decisions = 0; results = []
    for episode, target in enumerate(targets[:2]):
        rig.reset(); angles = []
        for _ in range(60):
            observation = np.r_[target, rig.angle, rig.data.qpos[rig.active_qpos]].astype(np.float32)
            with torch.no_grad():
                action, neural = policy(torch.as_tensor(observation[None], device=device), return_state=True)
            command = action[0].cpu().numpy()
            trace['neural_time'].append(rig.data.time)
            trace['neural_episode'].append(episode)
            trace['neural_activity'].append(neural[:, 0].cpu().numpy())
            trace['action'].append(command)
            for _ in range(10):
                rig.step(command)
                trace['time'].append(rig.data.time); trace['episode'].append(episode)
                trace['qpos'].append(rig.data.qpos.copy()); trace['angle'].append(rig.angle)
                trace['target'].append(target); trace['decision_index'].append(decisions)
                rows = (rig.data.efc_type == 0) & (rig.data.efc_id == rig.grip_id)
                trace['grip_force'].append(float(np.linalg.norm(rig.data.efc_force[rows])))
            angles.append(rig.angle); decisions += 1
        max_error = float(np.max(np.abs(np.asarray(angles)[-20:] - target)))
        results.append({'episode': episode, 'target_rad': float(target),
                        'max_last_second_error_rad': max_error, 'passed': max_error <= 0.13})
    np.savez_compressed(out / 'trace.npz', **trace)
    nodes = feather.read_table(Path(args.graph) / 'nodes.feather')
    soma = np.array([v if v is not None else [np.nan] * 3 for v in nodes['somaLocation'].to_pylist()])
    valid = np.flatnonzero(np.isfinite(soma).all(axis=1))
    subset = np.sort(np.random.default_rng(12).choice(valid, min(12000, len(valid)), replace=False))
    np.savez_compressed(out / 'display-somata.npz', indices=subset, coordinates=soma[subset],
                        body_ids=np.array(nodes['bodyId'])[subset])
    metrics = {'claim': 'Learned stationary steering replay; no autonomous driving',
               'targets_source': 'First two held-out targets from the 100-trial evaluation, seed 61733',
               'body_sampling_hz': 200, 'neural_decision_hz': 20, 'physics_hz': 20000,
               'clock': 'Each recorded neural decision precedes the next ten 5 ms body samples.',
               'display': '12,000 fixed sampled measured soma locations; colors show signed model rate states, not spikes.',
               'checkpoint_sha256': hashlib.file_digest(open(args.checkpoint, 'rb'), 'sha256').hexdigest(),
               'graph_sha256': json.loads((Path(args.graph) / 'manifest.json').read_text())['graph_sha256'],
               'wall_seconds': time.perf_counter() - start, 'results': results}
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)


def render(args):
    import imageio.v2 as imageio
    import mujoco as mj
    from PIL import Image, ImageDraw, ImageFont
    from flyhard.cockpit import WheelRig

    out = Path(args.out); trace = np.load(out / 'trace.npz'); somata = np.load(out / 'display-somata.npz')
    rig = WheelRig(); data = mj.MjData(rig.model)
    renderer = mj.Renderer(rig.model, height=576, width=912)
    camera = mj.MjvCamera(); camera.lookat[:] = [0, 0, 1.1]
    camera.distance = 5.6; camera.azimuth = 135; camera.elevation = -24
    font_candidates = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                       '/System/Library/Fonts/Supplemental/Arial.ttf']
    font_path = next((p for p in font_candidates if Path(p).exists()), None)
    font = lambda size: ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)
    dark = (15, 20, 22); muted = (154, 168, 165); pale = (237, 241, 228); green = (173, 220, 119)
    # An orthographic projection of measured soma coordinates. No invented edges.
    positions = somata['coordinates'][:, [0, 2]].astype(float)
    positions -= positions.min(axis=0)
    positions *= min(385 / np.ptp(positions[:, 0]), 435 / np.ptp(positions[:, 1]))
    positions += np.array([966 + (385 - np.ptp(positions[:, 0])) / 2, 177])
    positions = positions.astype(int)
    activity = trace['neural_activity'][:, somata['indices']]
    nonzero = np.abs(activity[np.abs(activity) > 1e-8])
    scale = float(np.quantile(nonzero, 0.95)) if len(nonzero) else 1
    normalized = np.arcsinh(activity / max(scale * 0.05, 1e-8)) / np.arcsinh(20)
    normalized = normalized.clip(-1, 1)
    neural_panels = []
    for values in normalized:
        panel = Image.new('RGB', (1440, 720), dark); draw = ImageDraw.Draw(panel)
        for (x, y), value in zip(positions, values):
            base = np.array([54, 66, 65])
            destination = np.array([244, 171, 79] if value >= 0 else [95, 170, 231])
            color = tuple((base + abs(value) * (destination - base)).astype(int))
            draw.ellipse((x-1, y-1, x+1, y+1), fill=color)
        neural_panels.append(panel)
    replay_error = 0.0
    with imageio.get_writer(out / 'learned-steering.mp4', fps=30, quality=8, macro_block_size=1) as video:
        for i in range(0, len(trace['time']), 2):
            decision = int(trace['decision_index'][i]); t = float(trace['time'][i])
            data.qpos[:] = trace['qpos'][i]; data.time = t; mj.mj_forward(rig.model, data)
            replay_error = max(replay_error, float(np.max(np.abs(data.qpos - trace['qpos'][i]))))
            renderer.update_scene(data, camera=camera)
            frame = neural_panels[decision].copy()
            frame.paste(Image.fromarray(renderer.render()), (24, 111))
            draw = ImageDraw.Draw(frame)
            draw.text((27, 20), 'FLYHARD', fill=green, font=font(32))
            draw.text((232, 27), 'First learned steering skill', fill=pale, font=font(24))
            draw.text((27, 70), '165,122 neurons  /  25.56 million measured connections  /  one A6000', fill=muted, font=font(17))
            draw.text((963, 117), 'THE CONNECTOME MODEL', fill=green, font=font(18))
            draw.text((963, 147), 'Measured soma locations + recorded rate states', fill=muted, font=font(13))
            draw.rectangle((26, 112, 442, 150), fill=dark)
            draw.text((38, 121), f'HELD-OUT TRIAL {int(trace["episode"][i])+1}/2     t = {t:.2f} s', fill=pale, font=font(17))
            target, angle = float(trace['target'][i]), float(trace['angle'][i])
            draw.rectangle((26, 586, 933, 686), fill=dark)
            draw.text((42, 600), f'Requested {np.degrees(target):+.1f} deg', fill=muted, font=font(21))
            draw.text((364, 600), f'Physical wheel {np.degrees(angle):+.1f} deg', fill=green, font=font(21))
            draw.line((43, 653, 895, 653), fill=(62, 78, 71), width=4)
            for value, color, radius in [(target, muted, 9), (angle, green, 6)]:
                x = int(469 + value / 0.65 * 426)
                draw.ellipse((x-radius, 653-radius, x+radius, 653+radius), fill=color)
            draw.text((963, 623), '12,000 fixed sampled somata; signed asinh color', fill=muted, font=font(13))
            draw.text((963, 647), f'Neural decision at {trace["neural_time"][decision]:.2f} s', fill=pale, font=font(16))
            draw.text((27, 695), 'Actual model -> fly joint servos -> disclosed foot grip -> passive wheel  |  Replay 0.3x  |  Stationary task; no driving yet', fill=muted, font=font(14))
            video.append_data(np.asarray(frame))
            if i == 400: frame.save(out / 'preview.png')
    renderer.close()
    metrics = json.loads((out / 'metrics.json').read_text())
    metrics.update(replay_max_qpos_error=replay_error, video_fps=30, playback_speed=0.3,
                   video_frames=len(range(0, len(trace['time']), 2)))
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['capture', 'render'])
    parser.add_argument('--checkpoint', default='runs/e03-wheel-pilot/checkpoint.pt')
    parser.add_argument('--graph', default='data/graph-traced-v1')
    parser.add_argument('--out', default='runs/e03-learned-replay')
    args = parser.parse_args()
    (capture if args.mode == 'capture' else render)(args)


if __name__ == '__main__':
    main()
