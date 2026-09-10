#!/usr/bin/env python3
"""Choose continuous-time camera cuts around measured stalk transitions."""
import argparse
import json
from pathlib import Path


def edit_plan(frames, fps):
    right = next(i for i, f in enumerate(frames) if f['applied_signal'] == 'right')
    cancelled = next(i for i in range(right + 1, len(frames)) if frames[i]['applied_signal'] == 'off')
    # Give the viewer time to see the approach and the foreleg moving before
    # cutting to the light. Cut on real events without retiming the episode.
    shots = []
    for i, f in enumerate(frames):
        if i < max(0, right - round(1.45 * fps)):
            camera, title = 'orbit', 'Here comes the fly'
        elif i < right + round(.8 * fps):
            camera, title = 'cabin', 'Fly pulls the stalk'
        elif i < right + round(2.8 * fps):
            camera, title = 'indicator', 'Right indicator'
        elif i < cancelled - round(1.0 * fps):
            camera, title = 'front', 'Steering + indicating'
        elif i < cancelled + round(.8 * fps):
            camera, title = 'cabin', 'Fly cancels the signal'
        else:
            camera, title = 'orbit', 'Exit taken. Somehow.'
        shots.append({'index': i, 'camera': camera, 'title': title,
                      'body_closeup': camera in ['cabin', 'indicator'],
                      'sponsor_key': f'orbit-{i:05}' if camera == 'orbit' else camera})
    return {'fps': fps, 'signal_on_frame': right, 'signal_off_frame': cancelled,
            'same_episode': True, 'playback_speed': 1, 'frames': shots}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--run', required=True)
    args = p.parse_args(); root = Path(args.run)
    frames = json.loads((root / 'frames.json').read_text())
    config = json.loads((root / 'config.json').read_text())
    plan = edit_plan(frames, config['fps'])
    (root / 'edit-plan.json').write_text(json.dumps(plan, indent=2))
    unique = {}
    for shot in plan['frames']:
        camera = shot['camera']
        if camera == 'cabin':
            continue
        f = frames[shot['index']]
        pose = config['camera_relative_matrix'] if camera == 'front' else f['cameras'][camera]['relative_matrix']
        fov = config['fov_degrees'] if camera == 'front' else f['cameras'][camera]['fov']
        unique[shot['sponsor_key']] = {'key': shot['sponsor_key'], 'relative_matrix': pose, 'fov': fov}
    (root / 'sponsor-shots.json').write_text(json.dumps(list(unique.values()), indent=2))
    print(json.dumps({'frames': len(frames), 'signal_on': plan['signal_on_frame'] / config['fps'],
                      'cancelled': plan['signal_off_frame'] / config['fps'], 'sponsor_views': len(unique)}))


if __name__ == '__main__':
    main()
