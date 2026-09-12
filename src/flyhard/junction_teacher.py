"""Training-only give-way demonstrator. Never imported by learned inference.

It reads the same measured quantities the policy gets: where the other vehicle is
along its own path, how fast it is closing, which side it came from and whether its
lights are on. The priority rule is applied to those, never to the case label.
"""
import numpy as np

from flyhard.crossing import (BRAKE_DECEL, COAST_DECEL, PLAN_DECEL, STOP_SETBACK, brake_for_decel,
                              kinematic_step, throttle_for_speed)
from flyhard.junction import (CONFLICT_HALF_SPAN, FRONT_OVERHANG, JUNCTION_DEPTH,
                              OTHER_HALF_LENGTH, gone, observation, step_other, visible)
from flyhard.parking import REAR_TO_CENTER


ACCEPT_GAP = 6.0        # Seconds of clearance demanded before taking the junction.
EMERGENCY_GAP = 9.0     # Blue lights are given a far bigger margin.


def yields(case, front, speed, other_s, other_speed):
    """Does the other vehicle hold priority over the box the ego is about to enter?

    Right of way is read from what is visible: a vehicle under blue lights always
    holds it, and otherwise only one arriving from the right. Whether that matters
    here is gap acceptance, the judgement a driver actually makes. Comparing the two
    arrival times rather than a fixed distance is what stops the ego committing to a
    stop it can no longer make and halting inside the junction.
    """
    if front > JUNCTION_DEPTH:
        return False
    if not (case.emergency or case.other_side > 0):
        return False
    if gone(other_s) or other_speed <= .3:
        return False
    if not visible(case, front, other_s):
        return False        # Not reported to the policy, so not a reachable label.
    reach = (-other_s-(OTHER_HALF_LENGTH+CONFLICT_HALF_SPAN))/other_speed
    if reach <= 0.:
        return True                                   # Already in the box.
    mine = max(-front, 0.)/max(speed, .5)
    return reach < mine+(EMERGENCY_GAP if case.emergency else ACCEPT_GAP)


def target(state, case, other_s, other_speed):
    """Return the demonstrated (throttle, brake) pair for one control tick."""
    front = state[0]+FRONT_OVERHANG
    speed = state[1]
    to_stop = -front-STOP_SETBACK

    if not yields(case, front, speed, other_s, other_speed):
        return cruise(case, speed)
    to_line = -front
    if to_line > .05 and speed*speed/(2*to_line) > BRAKE_DECEL and speed > 1.5:
        # The car genuinely cannot stop before the line any more. Halting would leave
        # it sitting in the junction, so it is committed and clears instead. The test
        # is against the line itself, not the setback: giving up a comfortable stopping
        # margin is always better than driving into whatever has priority.
        return cruise(case, speed)
    if to_line <= .05 and speed > 1.:
        # Already in the junction with speed on. Clearing it beats stopping in it.
        return cruise(case, speed)
    if to_stop <= .05 or (speed < .4 and to_stop < 1.5):
        return np.array([0., 1.], np.float32)
    needed = speed*speed/(2*max(to_stop, .05))
    if needed < PLAN_DECEL and speed > .5 and to_stop > 2.:
        return cruise(case, speed)
    return np.array([0., float(np.clip(brake_for_decel(needed), 0., 1.))], np.float32)


def cruise(case, speed):
    target = case.approach_speed
    if speed > target+1.2:
        return np.array([0., float(np.clip(brake_for_decel(COAST_DECEL+(speed-target)*.8), 0, .5))],
                        np.float32)
    return np.array([float(np.clip(throttle_for_speed(target+1.5*(target-speed)), 0, 1.)), 0.],
                    np.float32)


def rollout(case, steps=460, dt=.05, rng=None, jitter=0.):
    """Run the demonstrator through the longitudinal diagnostic, returning labelled samples."""
    from flyhard.junction import occupies
    state = case.start.astype(float)
    if jitter and rng is not None:
        state[0] += rng.uniform(-6., 6.)*jitter
        state[1] = max(0., state[1]+rng.uniform(-3., 2.5)*jitter)
    throttle = brake = 0.
    other_s, other_speed = case.other_start, case.other_speed
    observations, targets, trajectory = [], [], []
    for step in range(steps):
        observations.append(observation(state, case, other_s, other_speed, throttle, brake))
        action = target(state, case, other_s, other_speed)
        targets.append(action)
        trajectory.append({'state': state.copy(), 'other_s': other_s,
                           'other_speed': other_speed, 'occupies': occupies(case, other_s),
                           'throttle': float(action[0]), 'brake': float(action[1])})
        throttle, brake = float(action[0]), float(action[1])
        if jitter and rng is not None:
            throttle = float(np.clip(throttle+rng.normal(0, .04)*jitter, 0., 1.))
            brake = float(np.clip(brake+rng.normal(0, .04)*jitter, 0., 1.))
        state = kinematic_step(state, throttle, brake, dt)
        other_s, other_speed = step_other(case, other_s, state[0]-REAR_TO_CENTER, dt)
        if state[0]+FRONT_OVERHANG > JUNCTION_DEPTH+12:
            break
    return np.asarray(observations, np.float32), np.asarray(targets, np.float32), trajectory
