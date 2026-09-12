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
from flyhard.overtake import (CAR_LENGTH, LANE_WIDTH, MAX_STEER_DEG, SAFE_GAP, SENSING_RANGE,
                              SIDE_CLEARANCE, STEER_RATIO, WHEELBASE, kinematic_step,
                              lane_curvature, observation, traffic_state)

MIN_GAP = 16.           # Never closer than this while following. Swept, not guessed:
                        # at ten metres the demonstrator hit the vehicle it was following
                        # in a fifth of cases, and at sixteen it clears it by six.
FOLLOW_DECEL = 2.0      # Closing speed is limited to what this can wash off in the gap left.
PULL_OUT_GAP = 27.      # Close enough that overtaking is worth starting.
OUTSIDE_CLEAR = 40.     # Room demanded behind before moving into the outside lane.
PULL_OUT_SECONDS = 4.5  # Rate-limited lane change, measured off the demonstrator itself.
RETURN_SECONDS = 4.5
RETURN_GAP = SAFE_GAP+CAR_LENGTH+3.
# Sized from the measured steering response rather than from the model's own units.
# At fourteen metres a second a lane change wants about two hundredths of steer; the
# first version of this controller asked for a third of full lock and put the car into
# the guardrail. Hard steering at speed also scrubs off a third of the speed.
LATERAL_GAIN = .45      # Lateral closing speed demanded per metre of offset error.
MAX_HEADING = .13       # Radians of heading the lane change is allowed to take up.
HEADING_GAIN = .45      # Steer per radian of heading error. Lower gains let the car
                        # overshoot the lane centre on the way back in.
MAX_WHEEL = .09
WHEEL_RATE = .012       # Most the wheel may move in one control tick.


def steer_for_curvature(curvature):
    """Steering demand that holds the lane's own curvature, through the measured linkage."""
    angle = math.degrees(math.atan(WHEELBASE*float(curvature)))
    return angle/(MAX_STEER_DEG*STEER_RATIO)


def wheel_for(state, target_offset, previous=0., curvature=0.):
    """Lateral controller: aim off by a small heading, then straighten up.

    The lane's own curvature is fed forward rather than left to the feedback term. A
    purely proportional law settles at whatever heading error produces the steering the
    bend needs, and that error carries the car most of a metre off the centre line on a
    two-hundred-metre radius, which is enough to lose it into the barrier.

    Rate limited, because a steering wheel cannot jump and a snatched lane change is
    both unlike driving and unwatchable.
    """
    speed = max(state[3], 3.)
    wanted_heading = float(np.clip(LATERAL_GAIN*(target_offset-state[1])/speed,
                                   -MAX_HEADING, MAX_HEADING))
    demand = steer_for_curvature(curvature)+HEADING_GAIN*(wanted_heading-state[2])
    demand = float(np.clip(demand, -MAX_WHEEL, MAX_WHEEL))
    return float(np.clip(demand, previous-WHEEL_RATE, previous+WHEEL_RATE))


def follow_limit(lead_gap, lead_speed):
    """Fastest the car may go and still wash off its closing speed in the gap left.

    A plain proportional law on the gap overshoots: with six metres a second of closing
    it arrives at the gap it wanted still doing six, and ends up under a car length
    behind.
    """
    if lead_gap is None or lead_gap >= SENSING_RANGE:
        return math.inf
    return lead_speed+math.sqrt(2*FOLLOW_DECEL*max(lead_gap-MIN_GAP, 0.))


def phase(case, state, lead_gap, outside_gap, outside_speed, previous):
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
    return ('pulling_out' if close and not held_up(state, lead_gap, outside_gap, outside_speed,
                                                  case.lead_speed)
            else 'following')


def held_up(state, lead_gap, outside_gap, outside_speed, lead_speed):
    """Is something in the outside lane close enough to stop the ego moving over?

    The room needed is what the whole manoeuvre will consume, not a fixed distance.
    Passing a vehicle only a few metres a second slower takes ten seconds or more, and
    a car closing at five metres a second eats fifty metres in that time. Every term
    here, both closing speeds and the gap ahead, is something the policy is also given.
    """
    if outside_gap is None or outside_gap > 12.:
        return False
    # Two different closing speeds, because the ego runs at two different speeds. While
    # it is pulling out it is still held to the following speed, so something coming up
    # the outside gains on it far faster than the cruise figure suggests: a car only two
    # metres a second quicker than the ego is nine quicker than the vehicle being
    # passed. Using the cruise figure alone is what let the demonstrator pull out in
    # front of traffic it could not stay ahead of.
    while_out = max(outside_speed-lead_speed, 0.)
    while_passing = max(outside_speed-state[3], 0.)
    if while_out <= .2 and while_passing <= .2:
        return outside_gap > -14.
    relative = max(state[3]-lead_speed, .5)
    passing = (max(lead_gap or 0., 0.)+2*CAR_LENGTH+SAFE_GAP)/relative
    room = while_out*PULL_OUT_SECONDS+while_passing*(passing+RETURN_SECONDS)
    return outside_gap > -max(OUTSIDE_CLEAR, room+CAR_LENGTH)


def target(case, state, lead_gap, lead_speed, outside_gap, current, previous_wheel=0.,
           curvature=0.):
    """Return the demonstrated (throttle, brake, wheel) for one control tick."""
    speed = state[3]
    if current in {'pulling_out', 'passing'}:
        offset_target = LANE_WIDTH
        wanted = case.cruise_speed
        if state[1] < SIDE_CLEARANCE:
            # Still sharing the lane with the vehicle being passed. Pulling the wheel
            # over does not by itself make room, and a lane change takes about three
            # seconds; closing at eight metres a second that is twenty-four metres of
            # gap eaten, which is more than there was. Hold the following limit until
            # the car is genuinely out of the way, then go.
            wanted = min(wanted, follow_limit(lead_gap, lead_speed))
    elif current == 'returning':
        offset_target = 0.
        wanted = case.cruise_speed
    else:
        offset_target = 0.
        wanted = case.cruise_speed
        if current == 'following':
            wanted = min(wanted, follow_limit(lead_gap, lead_speed))
    wheel = wheel_for(state, offset_target, previous_wheel, curvature)
    wanted = max(0., wanted)
    if speed > wanted+.6:
        brake = brake_for_decel(COAST_DECEL+(speed-wanted)*.9)
        return np.array([0., float(np.clip(brake, 0., 1.)), wheel], np.float32)
    aim = wanted+1.2*(wanted-speed)
    return np.array([float(np.clip(throttle_for_speed(aim), 0., 1.)), 0., wheel], np.float32)


def rollout(case, steps=760, dt=.05, rng=None, jitter=0.):
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
        (lead_gap, lead_speed), (outside_gap, outside_speed) = traffic_state(case, now, state[0])
        curvature = lane_curvature(case, state[0])
        current = phase(case, state, lead_gap, outside_gap, outside_speed, current)
        observations.append(observation(state, case, lead_gap, lead_speed, outside_gap,
                                        outside_speed, curvature, throttle, brake, wheel))
        action = target(case, state, lead_gap, lead_speed, outside_gap, current, wheel, curvature)
        targets.append(action)
        trajectory.append({'state': state.copy(), 'lead_gap': lead_gap,
                           'outside_gap': outside_gap, 'phase': current,
                           'returning': current == 'returning'})
        throttle, brake, wheel = (float(action[0]), float(action[1]), float(action[2]))
        if jitter and rng is not None:
            throttle = float(np.clip(throttle+rng.normal(0, .04)*jitter, 0., 1.))
            brake = float(np.clip(brake+rng.normal(0, .04)*jitter, 0., 1.))
            wheel = float(np.clip(wheel+rng.normal(0, .02)*jitter, -1., 1.))
        state = kinematic_step(state, throttle, brake, wheel, curvature, dt)
        if current == 'hold' and case.should_overtake and lead_gap is not None \
                and lead_gap < -RETURN_GAP-14.:
            break
    return np.asarray(observations, np.float32), np.asarray(targets, np.float32), trajectory
