"""Training-only overtaking demonstrator. Never imported by learned inference.

A four-state manoeuvre driven only from measured quantities: follow the slower
vehicle, pull out when the outside lane is clear, pass it, and return once there is
room behind. Steering comes from a lateral controller on the lane offset and heading
the policy also sees, so the label is a control law the policy can actually learn
rather than a path it would have to memorise.
"""
import math

import numpy as np

from flyhard.crossing import COAST_DECEL, brake_for_decel, throttle_for_speed
from flyhard.overtake import (CAR_LENGTH, LANE_WIDTH, SAFE_GAP, SENSING_RANGE, kinematic_step,
                              observation, traffic_state)

FOLLOW_GAP = 16.        # Held behind the slower vehicle while waiting for a gap.
PULL_OUT_GAP = 26.      # Close enough that overtaking is worth starting.
OUTSIDE_CLEAR = 34.     # Room demanded behind before moving into the outside lane.
RETURN_GAP = SAFE_GAP+CAR_LENGTH+3.
LATERAL_GAIN = .55
HEADING_GAIN = 1.5
MAX_WHEEL = .35         # The manoeuvre never needs more wheel than this at speed.


def wheel_for(state, target_offset):
    """Lateral controller: close the offset, then hold the heading straight."""
    offset_error = target_offset-state[1]
    wanted_heading = float(np.clip(LATERAL_GAIN*offset_error/max(state[3], 4.)*4., -.22, .22))
    demand = HEADING_GAIN*(wanted_heading-state[2])
    return float(np.clip(demand, -MAX_WHEEL, MAX_WHEEL))


def phase(case, state, lead_gap, outside_gap, previous):
    """Which part of the manoeuvre applies, from what can be measured right now."""
    offset = state[1]
    if not case.should_overtake or previous == 'hold':
        # `hold` is terminal: the move is done and the lane is the ego's own again.
        return 'hold'
    if previous == 'returning':
        return 'hold' if abs(offset) < .25 else 'returning'
    if previous == 'passing':
        # Only pull back in once the vehicle passed is far enough behind.
        if lead_gap is not None and lead_gap < -RETURN_GAP:
            return 'returning'
        return 'passing'
    if previous == 'pulling_out':
        return 'passing' if offset > LANE_WIDTH-.4 else 'pulling_out'
    # Still following. Pull out only when close enough to be worth it and the outside
    # lane has room: something coming up behind holds the ego in its own lane.
    close = lead_gap is not None and 0. < lead_gap < PULL_OUT_GAP
    return ('pulling_out' if close and not held_up(case, state, lead_gap, outside_gap)
            else 'following')


def held_up(case, state, lead_gap, outside_gap):
    """Is something in the outside lane close enough to stop the ego moving over?

    The room needed is what the whole manoeuvre will consume, not a fixed distance.
    Passing a vehicle only a few metres a second slower takes ten seconds or more, and
    a car closing at five metres a second eats fifty metres in that time. Every term
    here, both closing speeds and the gap ahead, is something the policy is also given.
    """
    if outside_gap is None or outside_gap > 12.:
        return False
    closing = case.outside_speed-state[3]
    if closing <= .2:
        return outside_gap > -14.
    relative = max(state[3]-case.lead_speed, .5)
    duration = (max(lead_gap or 0., 0.)+2*CAR_LENGTH+SAFE_GAP)/relative+4.
    return outside_gap > -max(OUTSIDE_CLEAR, closing*duration+CAR_LENGTH)


def target(case, state, lead_gap, outside_gap, current):
    """Return the demonstrated (throttle, brake, wheel) for one control tick."""
    speed = state[3]
    if current in {'pulling_out', 'passing'}:
        offset_target = LANE_WIDTH
        wanted = case.cruise_speed
    elif current == 'returning':
        offset_target = 0.
        wanted = case.cruise_speed
    else:
        offset_target = 0.
        wanted = case.cruise_speed
        if current == 'following' and lead_gap is not None and lead_gap < SENSING_RANGE:
            # Settle in behind at a fixed gap rather than closing on it.
            wanted = min(wanted, case.lead_speed+(lead_gap-FOLLOW_GAP)*.35)
    wheel = wheel_for(state, offset_target)
    wanted = max(0., wanted)
    if speed > wanted+.6:
        brake = brake_for_decel(COAST_DECEL+(speed-wanted)*.9)
        return np.array([0., float(np.clip(brake, 0., 1.)), wheel], np.float32)
    aim = wanted+1.2*(wanted-speed)
    return np.array([float(np.clip(throttle_for_speed(aim), 0., 1.)), 0., wheel], np.float32)


def rollout(case, steps=560, dt=.05, rng=None, jitter=0.):
    """Run the demonstrator through the diagnostic model, returning labelled samples."""
    state = case.start.astype(float)
    if jitter and rng is not None:
        state[1] += rng.uniform(-.5, .5)*jitter
        state[2] += rng.uniform(-.04, .04)*jitter
        state[3] = max(2., state[3]+rng.uniform(-3., 2.)*jitter)
    throttle = brake = wheel = 0.
    current = 'following' if case.should_overtake else 'hold'
    observations, targets, trajectory = [], [], []
    for step in range(steps):
        now = step*dt
        lead_gap, outside_gap = traffic_state(case, now, state[0])
        current = phase(case, state, lead_gap, outside_gap, current)
        observations.append(observation(state, case, lead_gap, outside_gap, throttle, brake, wheel))
        action = target(case, state, lead_gap, outside_gap, current)
        targets.append(action)
        trajectory.append({'state': state.copy(), 'lead_gap': lead_gap,
                           'outside_gap': outside_gap, 'phase': current,
                           'returning': current == 'returning'})
        throttle, brake, wheel = (float(action[0]), float(action[1]), float(action[2]))
        if jitter and rng is not None:
            throttle = float(np.clip(throttle+rng.normal(0, .04)*jitter, 0., 1.))
            brake = float(np.clip(brake+rng.normal(0, .04)*jitter, 0., 1.))
            wheel = float(np.clip(wheel+rng.normal(0, .02)*jitter, -1., 1.))
        state = kinematic_step(state, throttle, brake, wheel, dt)
        if current == 'hold' and case.should_overtake and lead_gap is not None \
                and lead_gap < -RETURN_GAP-14.:
            break
    return np.asarray(observations, np.float32), np.asarray(targets, np.float32), trajectory
