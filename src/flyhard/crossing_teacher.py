"""Training-only stopping demonstrator. Never imported by learned inference.

The teacher reasons from the same measured quantities the policy receives, so its
labels are reachable rather than oracular. It predicts whether the pedestrian will
occupy the swept band by the time the car arrives, and brakes only for that.
"""
import math
import numpy as np

from flyhard.crossing import (BRAKE_DECEL, BRAKE_GAIN, COAST_DECEL, CONFLICT_HALF_WIDTH,
                              CROSSING_DEPTH, FRONT_OVERHANG, PEDESTRIAN_RADIUS,
                              in_conflict, stopping_distance, throttle_for_speed)

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
    """Return the demonstrated (throttle, brake) pair for one control tick."""
    front = state[0]+FRONT_OVERHANG
    speed = state[1]
    to_line = -front

    yielding = (threatens(front, speed, case, pedestrian_y, lateral_speed)
                and not clear(pedestrian_y, lateral_speed))
    if yielding:
        if to_line <= .15 and speed < .3:
            return np.array([0., 1.], np.float32)         # Hold at the line.
        # Lifting off alone sheds COAST_DECEL, which is firm. Braking the instant a
        # pedestrian is seen therefore parks the car tens of metres short. Hold speed
        # until the stop actually has to begin, then stop firmly at the line.
        begin_at = 1.25*stopping_distance(speed)+1.5
        if to_line > begin_at and speed > 1.:
            return cruise(case, speed)
        needed = speed*speed/(2*max(to_line, .12))
        # Coasting already supplies COAST_DECEL; the pedal provides only the excess.
        brake = float(np.clip((1.15*needed-COAST_DECEL)/BRAKE_GAIN, .06 if speed > .3 else .6, 1.))
        return np.array([0., brake], np.float32)

    return cruise(case, speed)


def cruise(case, speed):
    """Hold the approach speed using the measured throttle/speed map, not an invented gain."""
    target = case.approach_speed
    if speed > target+1.2:
        return np.array([0., float(np.clip((speed-target-1.2)*.25, 0, .4))], np.float32)
    aim = target+1.5*(target-speed)
    return np.array([float(np.clip(throttle_for_speed(aim), 0, 1.)), 0.], np.float32)


def rollout(case, steps=420, dt=.05):
    """Run the demonstrator through the longitudinal diagnostic, returning labelled samples.

    Produces the observation the policy would see and the action the teacher took.
    """
    from flyhard.crossing import kinematic_step, observation, pedestrian_state

    state = case.start.astype(float)
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
        state = kinematic_step(state, throttle, brake, dt)
        if state[0]+FRONT_OVERHANG > case.walk_offset+CROSSING_DEPTH+12:
            break
    return (np.asarray(observations, np.float32), np.asarray(targets, np.float32), trajectory)
