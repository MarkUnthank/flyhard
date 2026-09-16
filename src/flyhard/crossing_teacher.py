"""Training-only stopping demonstrator. Never imported by learned inference.

The teacher reasons from the same measured quantities the policy receives, so its
labels are reachable rather than oracular. It predicts whether the pedestrian will
occupy the swept band by the time the car arrives, and brakes only for that.
"""
import math
import numpy as np

from flyhard.crossing import (COAST_DECEL, CONFLICT_HALF_WIDTH, CROSSING_DEPTH, FRONT_OVERHANG,
                              PEDESTRIAN_RADIUS, PLAN_DECEL, STOP_SETBACK, brake_for_decel,
                              in_conflict, stop_begins_at, throttle_for_speed)

RELEASE_MARGIN = .9   # Extra lateral clearance demanded before resuming.


def threatens(front, speed, case, pedestrian_y, lateral_speed):
    """Does the pedestrian hold right of way over the swept band?

    Asking whether they will be in the band at the arrival instant is the wrong
    question: it licenses racing someone who has already stepped onto the paint
    but has not yet reached the car's line. At a marked crossing a pedestrian who
    is on it, or walking onto it, has priority until they are past and moving away.
    """
    if front > case.walk_offset+CROSSING_DEPTH:
        return False
    if in_conflict(pedestrian_y):
        return True
    # Walking towards the centreline, and not yet past the swept band.
    return lateral_speed*pedestrian_y < -1e-6


def clear(pedestrian_y, lateral_speed):
    """Safe to resume: past the swept band and still moving away from it."""
    beyond = abs(pedestrian_y) > CONFLICT_HALF_WIDTH+PEDESTRIAN_RADIUS+RELEASE_MARGIN
    return beyond and pedestrian_y*lateral_speed >= 0


def target(state, case, pedestrian_y, lateral_speed):
    """Return the demonstrated (throttle, brake) pair for one control tick.

    The approach speed is held until the stop has to begin, then the car coasts down
    with the brake trimming the last of the deceleration, so the pedal is engaged and
    modulated for the whole stop. An earlier version braked only in the final metres,
    which put the brake label in a handful of frames out of hundreds and gave the
    policy almost nothing to clone.
    """
    front = state[0]+FRONT_OVERHANG
    speed = state[1]
    to_line = -front

    yielding = (threatens(front, speed, case, pedestrian_y, lateral_speed)
                and not clear(pedestrian_y, lateral_speed))
    if not yielding:
        return cruise(case, speed)

    to_stop = to_line-STOP_SETBACK
    if to_stop <= .05 or (speed < .4 and to_stop < 1.5):
        return np.array([0., 1.], np.float32)             # Hold at the line.

    needed = speed*speed/(2*max(to_stop, .05))
    if needed < PLAN_DECEL and speed > .5 and to_stop > 2.:
        # Still outside the stopping distance. Braking here would park the car tens
        # of metres short, so hold the approach speed until the stop must begin. The
        # distance guard stops the car blipping the throttle in the final metre once
        # coasting has already brought it under the planned deceleration.
        return cruise(case, speed)
    # Inside it: coasting supplies COAST_DECEL and the pedal carries the rest, so the
    # brake stays engaged and modulated for the whole stop rather than for one frame.
    return np.array([0., float(np.clip(brake_for_decel(needed), 0., 1.))], np.float32)


def cruise(case, speed, target=None):
    """Hold a speed using the measured throttle/speed map, not an invented gain."""
    target = case.approach_speed if target is None else float(target)
    if target <= .05:
        return np.array([0., 0.], np.float32)
    if speed > target+1.2:
        return np.array([0., float(np.clip(brake_for_decel(COAST_DECEL+(speed-target)*.8), 0, .5))],
                        np.float32)
    aim = target+1.5*(target-speed)
    return np.array([float(np.clip(throttle_for_speed(aim), 0, 1.)), 0.], np.float32)


def rollout(case, steps=460, dt=.05, rng=None, jitter=0.):
    """Run the demonstrator through the longitudinal diagnostic, returning labelled samples.

    Produces the observation the policy would see and the action the teacher took.
    With `jitter`, the run starts from a perturbed state and carries small actuation
    noise, so the policy sees states a slightly wrong earlier action would have reached.
    """
    from flyhard.crossing import kinematic_step, observation, pedestrian_state

    state = case.start.astype(float)
    if jitter and rng is not None:
        state[0] += rng.uniform(-6., 6.)*jitter
        state[1] = max(0., state[1]+rng.uniform(-3., 2.5)*jitter)
    triggered_at = None
    throttle = brake = 0.
    observations, targets, trajectory = [], [], []
    for step in range(steps):
        now = step*dt
        front = state[0]+FRONT_OVERHANG
        if triggered_at is None and -front <= case.trigger_distance:
            triggered_at = now
        pedestrian_y, lateral_speed, walking = pedestrian_state(case, triggered_at, now)
        observations.append(observation(state, case, pedestrian_y, lateral_speed, throttle, brake))
        action = target(state, case, pedestrian_y, lateral_speed)
        targets.append(action)
        trajectory.append({'state': state.copy(), 'pedestrian_y': pedestrian_y,
                           'walking': walking, 'throttle': float(action[0]), 'brake': float(action[1])})
        throttle, brake = float(action[0]), float(action[1])
        if jitter and rng is not None:
            throttle = float(np.clip(throttle+rng.normal(0, .04)*jitter, 0., 1.))
            brake = float(np.clip(brake+rng.normal(0, .04)*jitter, 0., 1.))
        state = kinematic_step(state, throttle, brake, dt)
        if state[0]+FRONT_OVERHANG > case.walk_offset+CROSSING_DEPTH+12:
            break
    return (np.asarray(observations, np.float32), np.asarray(targets, np.float32), trajectory)
