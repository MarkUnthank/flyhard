#!/usr/bin/env python3
"""Native CARLA held-out trials for one scenario, through measured pedals.

The learned policy chooses throttle and brake only. Offline IK drives the fly's legs
onto the pedals and CARLA receives the measured travel, never the demand. Steering is
a conventional lane-keeping request and is recorded as such.

With --record, each trial also writes wide/chase/cabin footage and registers a take in
the clip library, so one CARLA pass yields both the benchmark and the film material.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from flyhard.clips import ClipLibrary, Take
from flyhard.scenarios import get

CONTROL_DT = .05   # The policy runs at 20 Hz; CARLA steps physics at its own smaller dt.


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_policy(checkpoint, graph_dir, scenario, core, reset_core=False):
    from flyhard.scenario_policy import PedalPolicy
    with gzip.open(checkpoint, 'rb') as handle:
        saved = torch.load(handle, map_location='cpu', weights_only=False)
    if sha(Path(graph_dir)/'graph.npz') != saved['config']['graph_sha256']:
        raise RuntimeError('Graph identity mismatch')
    state = saved['model']
    # Checkpoints from the scenario-specific trainer predate the recorded feature
    # count; the encoder is the authority either way, so derive it and check.
    width = core.encode(np.zeros((1, len(core.OBSERVATION_FIELDS)), np.float32)).shape[1]
    if saved['config'].get('feature_count', width) != width:
        raise RuntimeError('Checkpoint was trained against a different encoder width')
    policy = PedalPolicy(np.load(Path(graph_dir)/'graph.npz'), state['sensory_ids'],
                         state['motor_ids'], width, saved['config']['seed'],
                         outputs=len(state['decoder']),
                         signed_outputs=scenario.signed_outputs)
    missing, extra = policy.load_state_dict(state, strict=False)
    assert set(missing) == {'core.crow', 'core.col', 'core.rows', 'core.base'} and not extra
    if reset_core:
        with torch.no_grad():
            policy.core.edge_gain.zero_()
            policy.core.leak.zero_()
    return policy.cuda().eval(), saved


def describe(scenario, case, score):
    if scenario.name == 'overtake':
        if score['collided']:
            return 'collided while overtaking'
        if score['strayed']:
            return 'left the carriageway'
        if score['cut_in']:
            return 'pulled back in too early'
        if not score['overtake_required']:
            return ('held its lane, nothing to pass' if not score['used_outside_lane']
                    else 'pulled out with no reason to')
        return 'overtook and pulled back in' if score['overtook'] else 'never got past'
    if scenario.name == 'crossing':
        if score['contact']:
            return 'hit the pedestrian'
        if score['yielded_before_line']:
            return 'stopped for the pedestrian'
        return 'drove on, crossing clear' if not score['stop_required'] else 'failed to yield'
    if score['contact']:
        return 'collided in the junction'
    if score['unnecessary_stop']:
        return 'stopped when it had priority'
    if score['yielded_before_line']:
        return ('gave way to the ambulance' if case.emergency
                else 'gave way to the right')
    return 'took the junction' if not score['stop_required'] else 'failed to give way'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--graph', default='data/graph-traced-v1')
    parser.add_argument('--split', default='heldout')
    parser.add_argument('--count', type=int, default=8)
    parser.add_argument('--first', type=int, default=0, help='Skip this many cases of the split')
    parser.add_argument('--seconds', type=float, default=30.)
    parser.add_argument('--town')
    parser.add_argument('--record', help='Clip library root; records three camera angles per trial')
    parser.add_argument('--asset', help='Fresh live sponsor export; sponsors are composited '
                                        'onto the wide and chase views as each frame arrives')
    parser.add_argument('--reset-core', action='store_true',
                        help='Zero the learned core as a control condition')
    parser.add_argument('--attempt', type=int, default=1)
    args = parser.parse_args()

    scenario = get(args.scenario)
    core, _ = scenario.modules
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    policy, saved = load_policy(args.checkpoint, args.graph, scenario, core, args.reset_core)

    from flyhard.parking_rig import make_parking_rig
    env = scenario.load_world()(**({'town': args.town} if args.town else {}))
    rig = make_parking_rig()
    rig.prepare_controls()
    library = ClipLibrary(args.record) if args.record else None
    sponsor = manifest = None
    if args.asset:
        from flyhard.live_livery import verify_live_livery
        manifest = verify_live_livery(args.asset, out)
    results = []
    ticks = round(CONTROL_DT/env.dt)
    assert abs(ticks*env.dt-CONTROL_DT) < 1e-9, 'Control period must be whole CARLA ticks'
    try:
        (out/'site.json').write_text(json.dumps(env.metadata(), indent=2)+'\n')
        print(json.dumps({'site': env.metadata()}), flush=True)
        selected = core.cases(args.split, args.first+args.count)[args.first:]
        for case in selected:
            env.start(case)
            rig.reset()
            if manifest and sponsor is None:
                from flyhard.sponsor_view import SponsorView
                centre = env.ego.bounding_box.location
                sponsor = SponsorView(args.asset, manifest, [centre.x, centre.y, centre.z])
            cameras = None
            if library:
                take_dir = (library.root/scenario.name/'pending'
                            / f'{scenario.name}-s{case.seed:05d}-a{args.attempt:02d}')
                take_dir.mkdir(parents=True, exist_ok=True)
                from flyhard.scenario_cameras import ScenarioCameras
                cameras = ScenarioCameras(env, take_dir, env.focus(), env.approach_yaw,
                                          fps=round(1/CONTROL_DT), sponsor=sponsor)
            env.release()
            throttle = brake = 0.
            steer = 0.
            learned_steering = policy.outputs >= 3
            rows, trajectory, activity = [], [], []
            started = env.world.get_snapshot().timestamp.elapsed_seconds
            for step in range(round(args.seconds/CONTROL_DT)):
                now = env.world.get_snapshot().timestamp.elapsed_seconds-started
                values, extra = env.hazard(now)
                measured = (throttle, brake, steer) if learned_steering else (throttle, brake)
                observation = env.observe(*values, *measured)
                with torch.no_grad():
                    output, neural = policy(torch.tensor(core.encode(observation), device='cuda'),
                                            return_state=True)
                demand = output[0].cpu().numpy()
                activity.append(neural[:, 0].cpu().numpy().astype(np.float16))
                # Where steering is learned the fly turns the wheel; where it is not, the
                # wheel follows a conventional lane-keeping request and is disclosed as such.
                wanted_steer = float(demand[2]) if learned_steering else env.lane_steer()
                # Offline IK works the controls; CARLA gets the measured travel only.
                targets = rig.diagnostic_drive_action(wanted_steer/.5, float(demand[0]),
                                                      float(demand[1]), 1)
                for _ in range(10):
                    rig.step_drive(targets)
                pedals = rig.parking.measured
                throttle, brake = pedals['throttle'], pedals['brake']
                steer = rig.angle*.5 if learned_steering else wanted_steer
                env.apply_measured(throttle, brake, steer)
                for _ in range(ticks):
                    frame = env.world.tick()
                state = env.scenario_state()
                if cameras:
                    snapshot = env.world.get_snapshot()
                    cameras.capture(step, frame, snapshot.timestamp.elapsed_seconds)
                trajectory.append({'state': state.copy(), **extra})
                rows.append({'time': (step+1)*CONTROL_DT, 'carla_frame': frame,
                             'vehicle_matrix': env.ego.get_transform().get_matrix(),
                             'neural_index': len(activity)-1,
                             'observation': observation.tolist(),
                             'demand_throttle': float(demand[0]), 'demand_brake': float(demand[1]),
                             'measured_throttle': throttle, 'measured_brake': brake,
                             'demand_steer': float(demand[2]) if learned_steering else None,
                             'measured_steer': float(steer),
                             'steering_source': 'learned' if learned_steering else 'lane keeping',
                             'speed_m_s': float(state[-1]),
                             'front_to_line': float(state[0]+core.FRONT_OVERHANG), **extra})
                if env.collision_events or env.done(state):
                    break
            score = core.metrics(trajectory, case)
            score['native_collision_events'] = list(env.collision_events)
            # Scenarios name their own contact metric; CARLA's own collision sensor is
            # the authority either way, and a trial with a contact never passes.
            hit = 'contact' if 'contact' in score else 'collided'
            score[hit] = bool(score[hit] or env.collision_events)
            score['passed'] = bool(score['passed'] and not env.collision_events)
            duration = rows[-1]['time']
            results.append({'seed': case.seed, 'split': case.split,
                            'duration_seconds': duration, **score})
            print(json.dumps({k: v for k, v in results[-1].items()
                              if k != 'native_collision_events'}), flush=True)

            trial = out/str(case.seed)
            trial.mkdir()
            box = env.ego.bounding_box
            config = json.dumps(
                {'fps': round(1/CONTROL_DT), 'policy_hz': round(1/CONTROL_DT),
                 'physics_dt': env.dt, 'scenario': scenario.name, 'case': case.record(),
                 **env.metadata(),
                 'vehicle_bounds': {'location': [box.location.x, box.location.y, box.location.z],
                                    'extent': [box.extent.x, box.extent.y, box.extent.z]},
                 'motion': 'Measured pedal travel drives CARLA; offline IK moves the fly legs. '
                           'Steering is a conventional lane-keeping request, not a learned output.'},
                indent=2)+'\n'
            (trial/'config.json').write_text(config)
            (trial/'trace.json').write_text(json.dumps(rows)+'\n')
            np.savez_compressed(trial/'neural.npz', activity=np.asarray(activity))

            if cameras:
                cameras.close()
                # Keep the trial's own configuration beside the footage so the take is
                # self-contained: the sponsor compositor needs the vehicle bounds, and a
                # clip should never depend on a benchmark directory still existing.
                (take_dir/'trial.json').write_text(config)
                # The trace travels with the footage too: the edit picks its cut points
                # from what the car actually did, so a take has to carry its own timing.
                (take_dir/'trace.json').write_text(json.dumps(rows)+'\n')
                take = Take(scenario=scenario.name, seed=case.seed, attempt=args.attempt,
                            outcome='success' if score['passed'] else 'failure',
                            duration_seconds=duration, fps=round(1/CONTROL_DT),
                            cameras=cameras.relative_paths(sponsored=bool(sponsor)),
                            sponsor_revision=int(manifest['revision']) if manifest else 0,
                            sponsor_layout=int(manifest['layoutVersion']) if manifest else 0,
                            metrics={k: v for k, v in score.items()
                                     if k != 'native_collision_events'},
                            label=describe(scenario, case, score),
                            checkpoint_sha256=sha(args.checkpoint))
                final = library.directory(take)
                final.parent.mkdir(parents=True, exist_ok=True)
                if final.exists():
                    import shutil
                    shutil.rmtree(final)
                take_dir.rename(final)
                library.register(take)
    finally:
        env.close()
        if sponsor is not None:
            sponsor.close()

    passed = sum(r['passed'] for r in results)
    # Only the scenarios that are about stopping report a stop; the summary carries
    # whichever of these each scenario actually measured rather than inventing zeros.
    required = [r for r in results if r.get('stop_required')]
    counted = {key: sum(bool(r.get(key)) for r in results)
               for key in ('contact', 'collided', 'unnecessary_stop', 'strayed', 'cut_in',
                           'overtook') if any(key in r for r in results)}
    if required:
        counted['stop_required_trials'] = len(required)
        counted['yielded_when_required'] = sum(bool(r.get('yielded_before_line'))
                                               for r in required)
    summary = {'scenario': scenario.name, 'checkpoint': args.checkpoint,
               'checkpoint_sha256': sha(args.checkpoint), 'split': args.split,
               'trials': len(results), 'passed': passed,
               'pass_rate': round(passed/max(len(results), 1), 4), **counted,
               'reset_core': args.reset_core, 'results': results,
               'environment': 'native CARLA with measured pedal travel',
               'sponsor_revision': int(manifest['revision']) if manifest else None,
               'sponsor_note': ('Sponsor panels rasterised from the delivered meshes and '
                                'depth-composited onto the wide and chase views as each frame '
                                'arrived. Presentation only; no recorded metric, trajectory or '
                                'control value is affected.') if manifest else None,
               'claim': scenario.claim+' Frozen held-out cases; not general autonomous driving, '
                        'and steering is not learned.'}
    (out/'metrics.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}, indent=2), flush=True)
    if library:
        library.index()


if __name__ == '__main__':
    main()
