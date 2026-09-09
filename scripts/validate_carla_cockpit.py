#!/usr/bin/env python3
"""Independently reconcile saved physics, neural decisions and CARLA readbacks."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from flyhard.cockpit import WheelRig


def validate(path):
    config = json.loads((path / 'config.json').read_text())
    frames = json.loads((path / 'frames.json').read_text())
    body = np.load(path / 'body-trace.npz')
    neural = np.load(path / 'neural-trace.npz')
    rig = WheelRig()
    assert frames and len(body['time']) == 8 * len(frames)
    assert np.isfinite(body['qpos']).all() and np.isfinite(neural['activity']).all()
    assert np.allclose(np.diff(body['time']), 0.005, rtol=0, atol=1e-10)
    assert np.allclose(np.diff(neural['time']), 0.05, rtol=0, atol=1e-10)
    assert np.array_equal(body['wheel'], body['qpos'][:, rig.wheel_qpos])
    # Start fresh and drive the body solely with the saved neural actions.
    # Loading recorded qpos for a render alone would not establish this link.
    rig.reset(grip=not config['disable_grip'])
    replay_qpos_error = 0.0
    replay_ctrl_error = 0.0
    for sample, decision in enumerate(body['decision_index']):
        rig.step(neural['action'][decision])
        replay_qpos_error = max(replay_qpos_error, float(np.max(np.abs(rig.data.qpos-body['qpos'][sample]))))
        replay_ctrl_error = max(replay_ctrl_error, float(np.max(np.abs(rig.data.ctrl-body['ctrl'][sample]))))
    assert replay_qpos_error < 1e-10 and replay_ctrl_error < 1e-12
    worst_mapping_error = 0.0
    for index, record in enumerate(frames):
        sample = record['body_index']
        assert sample == (index+1)*8-1
        assert record['frame'] == record['camera_frame']
        if index:
            assert record['frame'] == frames[index-1]['frame']+1
        assert abs(record['camera_time']-body['time'][sample]) < 1e-4
        assert record['wheel_angle'] == body['wheel'][sample]
        expected_source = body['qpos'][sample-8, rig.wheel_qpos] if index else 0.0
        source_time = body['time'][sample-8] if index else 0.0
        assert record['wheel_read_angle'] == expected_source
        assert record['wheel_read_time'] == source_time
        mapped = float(np.clip(config['steer_gain']*expected_source/config['wheel_full_scale_rad'], -1, 1))
        worst_mapping_error = max(worst_mapping_error, abs(mapped-record['applied_steer']))
        decision = record['neural_index']
        assert decision == int(body['decision_index'][sample])
        assert 0 <= body['time'][sample]-neural['time'][decision] <= 0.05+1e-9
    assert worst_mapping_error < 1e-7
    return {'frames_verified': len(frames), 'body_samples_verified': len(body['time']),
        'neural_decisions_verified': len(neural['time']),
        'max_applied_steer_error_from_recorded_qpos': worst_mapping_error,
        'physics_replay_max_qpos_error_from_neural_actions': replay_qpos_error,
        'physics_replay_max_ctrl_error_from_neural_actions': replay_ctrl_error,
        'max_abs_wheel_rad': float(np.max(np.abs(body['wheel']))),
        'max_abs_steer': max(abs(f['applied_steer']) for f in frames),
        'max_grip_force': float(np.max(body['grip_force'])),
        'final_lateral_m': frames[-1]['lateral_m'],
        'collisions': len(json.loads((path / 'collisions.json').read_text())),
        'capture_config': config}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='runs/carla-cockpit-v1')
    parser.add_argument('--control', default='runs/carla-cockpit-grip-disabled-v1')
    args = parser.parse_args()
    primary, control = Path(args.run), Path(args.control)
    a, b = validate(primary), validate(control)
    ca, cb = a.pop('capture_config'), b.pop('capture_config')
    assert not ca['disable_grip'] and cb['disable_grip']
    for key in ['checkpoint_sha256','graph_sha256','spawn_index','seconds','speed','turn_schedule','steer_gain']:
        assert ca[key] == cb[key]
    assert a['frames_verified'] == b['frames_verified']
    assert a['max_abs_wheel_rad'] > 0.18 and a['max_grip_force'] > 0
    assert b['max_abs_wheel_rad'] < 0.02 and b['max_grip_force'] == 0
    assert b['max_abs_steer'] < 0.01*a['max_abs_steer']
    fa = json.loads((primary/'frames.json').read_text())
    fb = json.loads((control/'frames.json').read_text())
    lateral_difference = max(abs(x['lateral_m']-y['lateral_m']) for x,y in zip(fa,fb))
    assert lateral_difference > 0.3
    result = {'status': 'passed', 'primary': a, 'grip_disabled': b,
        'max_lateral_difference_m': lateral_difference,
        'validator_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'claim': 'For this instructed sequence, learned leg actuation through the grip causes physical wheel motion and CARLA steering. Speed/turn requests are scripted.'}
    (primary/'validation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
