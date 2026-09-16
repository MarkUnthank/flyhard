import math

import numpy as np
import pytest

from flyhard.overtake import (CURVATURE_SCALE, KINDS, LANE_TOLERANCE, LANE_WIDTH,
                              OBSERVATION_FIELDS, SENSING_RANGE, WHEELBASE, cases, encode,
                              kinematic_step, lane_curvature, metrics, observation,
                              road_wheel_angle, traffic_state)
from flyhard.overtake_teacher import (MAX_WHEEL, OUTSIDE_CLEAR, phase, rollout,
                                      steer_for_curvature, target, wheel_for)


def test_splits_are_disjoint_and_heldout_reaches_outside_the_demonstrated_range():
    train, validation, heldout = (cases(s, 30) for s in ['train', 'validation', 'heldout'])
    seeds = [{c.seed for c in split} for split in (train, validation, heldout)]
    assert not seeds[0] & seeds[1] and not seeds[0] & seeds[2] and not seeds[1] & seeds[2]
    assert max(c.cruise_speed for c in heldout) > max(c.cruise_speed for c in train)
    assert min(c.cruise_speed for c in heldout) < min(c.cruise_speed for c in train)
    assert max(abs(c.curvature) for c in heldout) > max(abs(c.curvature) for c in train)


def test_cases_are_deterministic():
    assert [c.record() for c in cases('heldout', 9)] == [c.record() for c in cases('heldout', 9)]


def test_every_split_carries_all_three_kinds_in_equal_measure():
    for split in ['train', 'validation', 'heldout']:
        counted = {kind: sum(c.kind == kind for c in cases(split, 30)) for kind in KINDS}
        assert set(counted.values()) == {10}, (split, counted)


def test_only_the_overtaking_kinds_have_a_slower_vehicle_ahead():
    for case in cases('heldout', 30):
        if case.kind == 'no_need':
            assert case.lead_speed >= case.cruise_speed and not case.should_overtake
        else:
            assert case.lead_speed < case.cruise_speed and case.should_overtake
        assert case.has_outside == (case.kind == 'blocked')


def test_observation_field_count_matches_the_declared_names():
    case = cases('heldout', 1)[0]
    values = observation(case.start, case, 30., 10., None, 0., 0., 0., 0., 0.)
    assert values.shape == (len(OBSERVATION_FIELDS),) == (14,)
    assert np.isfinite(values).all()


def test_observation_hides_traffic_beyond_the_sensing_range():
    case = cases('heldout', 1)[0]
    values = observation(case.start, case, SENSING_RANGE+30., 10., -SENSING_RANGE-30., 18.,
                         0., 0., 0., 0.)
    assert values[3] == 0. and values[4] == SENSING_RANGE
    assert values[7] == 0. and values[8] == -SENSING_RANGE


def test_observation_reports_the_speeds_measured_rather_than_the_ones_asked_for():
    """In CARLA a van told to hold seven metres a second may be doing six."""
    case = cases('heldout', 1)[0]
    values = observation(case.start, case, 30., case.lead_speed-3., None, 0., 0., 0., 0., 0.)
    assert values[5] == pytest.approx(case.lead_speed-3.-case.cruise_speed, abs=1e-3)


def test_encode_rejects_malformed_observations():
    with pytest.raises(ValueError):
        encode(np.zeros((1, 13), np.float32))
    with pytest.raises(ValueError):
        encode(np.full((1, 14), np.nan, np.float32))
    assert encode(np.zeros((5, 14), np.float32)).shape[0] == 5


def test_curvature_reverses_along_the_road_and_stays_inside_the_case_amplitude():
    case = [c for c in cases('heldout', 30) if abs(c.curvature) > .004][0]
    sampled = [lane_curvature(case, x) for x in np.linspace(0., case.curve_period, 40)]
    assert max(sampled) > 0. > min(sampled), 'the bend never reverses'
    assert max(abs(k) for k in sampled) <= abs(case.curvature)+1e-9


def test_a_straight_wheel_on_a_bend_drifts_out_of_the_lane():
    """The reason the lane's curvature is part of what the policy is shown."""
    state = np.array([0., 0., 0., 15.])
    for _ in range(200):
        state = kinematic_step(state, .6, 0., 0., .0055)
    assert state[1] < -LANE_TOLERANCE, 'a straight wheel held the lane on a 180 m radius'


def test_the_curvature_feed_forward_holds_the_lane_the_straight_wheel_loses():
    state = np.array([0., 0., 0., 15.])
    wheel = 0.
    for _ in range(400):
        wheel = wheel_for(state, 0., wheel, .0055)
        state = kinematic_step(state, .6, 0., wheel, .0055)
    assert abs(state[1]) < .25, f'settled {state[1]:.2f} m off the centre line'


def test_the_feed_forward_is_the_steering_the_bend_geometrically_needs():
    for curvature in (-.008, -.003, .0, .004, .008):
        angle = road_wheel_angle(steer_for_curvature(curvature))
        assert math.tan(angle)/WHEELBASE == pytest.approx(curvature, abs=2e-5)


def test_the_wheel_is_rate_limited_and_never_reaches_full_lock():
    state = np.array([0., 0., 0., 15.])
    wheel = 0.
    for _ in range(10):
        moved = wheel_for(state, LANE_WIDTH, wheel, 0.)
        assert abs(moved-wheel) <= .0121
        wheel = moved
    assert abs(wheel) <= MAX_WHEEL


def test_the_phase_machine_only_pulls_out_when_the_outside_lane_has_room():
    blocked = [c for c in cases('heldout', 30) if c.kind == 'blocked'][0]
    state = np.array([0., 0., 0., blocked.cruise_speed])
    quick = blocked.cruise_speed+4.
    assert phase(blocked, state, 20., -20., quick, 'following') == 'following'
    # Same case, nothing behind in the outside lane: now the move is on.
    assert phase(blocked, state, 20., None, 0., 'following') == 'pulling_out'


def test_a_case_with_nothing_slower_ahead_never_leaves_its_lane():
    for case in [c for c in cases('heldout', 30) if c.kind == 'no_need']:
        _, _, trajectory = rollout(case)
        assert all(abs(row['state'][1]) <= LANE_TOLERANCE for row in trajectory)
        assert all(row['phase'] == 'hold' for row in trajectory)


def test_the_teacher_never_presses_both_pedals_and_keeps_the_wheel_small():
    for case in cases('train', 30):
        _, targets, _ = rollout(case)
        assert not np.any((targets[:, 0] > .01) & (targets[:, 1] > .01))
        assert targets[:, :2].min() >= 0. and targets[:, :2].max() <= 1.
        assert abs(targets[:, 2]).max() <= MAX_WHEEL


@pytest.mark.parametrize('split', ['train', 'validation', 'heldout'])
def test_teacher_solves_its_own_task_on_every_split(split):
    """The demonstrator must clear the gate it is teaching, or the labels are unusable."""
    results = [metrics(rollout(case)[2], case) for case in cases(split, 30)]
    assert not any(r['collided'] for r in results), 'teacher collided'
    assert not any(r['strayed'] for r in results), 'teacher left the carriageway'
    assert not any(r['cut_in'] for r in results), 'teacher pulled back in on top of the lead'
    assert sum(r['passed'] for r in results) == 30, f'{split}: {sum(r["passed"] for r in results)}/30'


def test_the_three_kinds_are_discriminated_rather_than_all_overtaken():
    scored = [(c, metrics(rollout(c)[2], c)) for c in cases('heldout', 30)]
    by_kind = {kind: [m for c, m in scored if c.kind == kind] for kind in KINDS}
    assert all(m['overtook'] for m in by_kind['clear'])
    assert all(m['overtook'] for m in by_kind['blocked'])
    assert not any(m['used_outside_lane'] for m in by_kind['no_need'])


def test_a_blocked_case_waits_for_the_outside_lane_before_moving_over():
    for case in [c for c in cases('heldout', 30) if c.kind == 'blocked']:
        _, _, trajectory = rollout(case)
        for index, row in enumerate(trajectory):
            if row['phase'] == 'pulling_out':
                break
        else:
            raise AssertionError('never pulled out')
        _, (outside_gap, _) = traffic_state(case, index*.05, trajectory[index]['state'][0])
        # Either it has gone by, or it is far enough back that the whole move fits in
        # front of it. What must never happen is moving over while it is alongside.
        assert outside_gap is None or outside_gap > 6. or outside_gap < -OUTSIDE_CLEAR, \
            f'decided to move over with it {outside_gap:.1f} m away'


def test_metrics_flag_a_collision_and_an_early_pull_in():
    case = [c for c in cases('heldout', 30) if c.kind == 'clear'][0]
    hit = [{'state': np.array([x, 0., 0., 15.]), 'lead_gap': 1., 'outside_gap': None}
           for x in np.arange(0., 20., .4)]
    assert metrics(hit, case)['collided'] and not metrics(hit, case)['passed']
    early = [{'state': np.array([x, 0., 0., 15.]), 'lead_gap': -3., 'outside_gap': None}
             for x in np.arange(0., 20., .4)]
    assert metrics(early, case)['cut_in'] and not metrics(early, case)['passed']


def test_metrics_flag_leaving_the_carriageway():
    case = [c for c in cases('heldout', 30) if c.kind == 'no_need'][0]
    off = [{'state': np.array([x, -3.2, 0., 15.]), 'lead_gap': 40., 'outside_gap': None}
           for x in np.arange(0., 20., .4)]
    assert metrics(off, case)['strayed'] and not metrics(off, case)['passed']


def test_rollout_observations_and_targets_line_up():
    observations, targets, trajectory = rollout(cases('train', 1)[0])
    assert len(observations) == len(targets) == len(trajectory)
    assert observations.shape[1] == 14 and targets.shape[1] == 3
    assert encode(observations).shape[0] == len(observations)


def test_the_encoder_scales_curvature_against_the_road_it_was_measured_on():
    values = np.zeros((1, 14), np.float32)
    values[0, 13] = CURVATURE_SCALE
    assert np.isfinite(encode(values)).all()
    assert encode(values).shape[1] == encode(np.zeros((1, 14), np.float32)).shape[1]
