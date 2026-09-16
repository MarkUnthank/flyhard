import numpy as np
import pytest

from flyhard.junction import (CLEAR_MARGIN, CONFLICT_HALF_SPAN, JUNCTION_DEPTH, KINDS,
                              MAX_OTHER_START, OBSERVATION_FIELDS, OTHER_HALF_LENGTH,
                              SENSING_RANGE, cases, encode, gone, metrics, observation,
                              occupies, separation, step_other, visible)
from flyhard.junction_teacher import rollout, target, yields


def test_splits_are_disjoint_and_heldout_reaches_outside_the_demonstrated_range():
    train, validation, heldout = (cases(s, 60) for s in ['train', 'validation', 'heldout'])
    seeds = [{c.seed for c in split} for split in (train, validation, heldout)]
    assert not seeds[0] & seeds[1] and not seeds[0] & seeds[2] and not seeds[1] & seeds[2]
    assert min(c.approach_speed for c in heldout) < min(c.approach_speed for c in train)
    assert max(c.approach_speed for c in heldout) > max(c.approach_speed for c in train)
    assert min(c.other_speed for c in heldout) < min(c.other_speed for c in train)
    assert max(c.other_speed for c in heldout) > max(c.other_speed for c in train)


def test_cases_are_deterministic():
    assert [c.record() for c in cases('heldout', 9)] == [c.record() for c in cases('heldout', 9)]


def test_every_split_carries_all_three_kinds_in_equal_measure():
    for split in ['train', 'validation', 'heldout']:
        counted = {kind: sum(c.kind == kind for c in cases(split, 60)) for kind in KINDS}
        assert set(counted.values()) == {20}, (split, counted)


def test_the_crossing_vehicle_starts_inside_the_arm_the_native_site_validates():
    for split in ['train', 'validation', 'heldout']:
        assert all(-MAX_OTHER_START <= c.other_start < 0 for c in cases(split, 60))


def test_kinds_put_the_other_vehicle_on_the_side_the_behaviour_is_about():
    for case in cases('heldout', 60):
        if case.kind == 'right':
            assert case.other_side == 1. and case.must_yield
        elif case.kind == 'left':
            assert case.other_side == -1. and not case.must_yield and case.other_waits
        else:
            assert case.emergency and case.must_yield and abs(case.other_side) == 1.


def test_observation_field_count_matches_the_declared_names():
    case = cases('heldout', 1)[0]
    values = observation(case.start, case, case.other_start, case.other_speed, 0., 0.)
    assert values.shape == (len(OBSERVATION_FIELDS),) == (11,)
    assert np.isfinite(values).all()


def test_observation_hides_a_vehicle_that_is_out_of_range_or_already_gone():
    case = cases('heldout', 1)[0]
    far = observation(np.array([-50., 8.]), case, -400., case.other_speed, 0., 0.)
    assert far[2] == 0. and far[3] == -SENSING_RANGE and far[6] == SENSING_RANGE
    past = observation(np.array([-10., 8.]), case, CLEAR_MARGIN+1., case.other_speed, 0., 0.)
    assert past[2] == 0.


def test_observation_never_names_the_case_kind():
    """Side and blue lights are visible; `right`, `left` and `priority` are not."""
    right = [c for c in cases('heldout', 60) if c.kind == 'right'][0]
    priority = [c for c in cases('heldout', 60) if c.kind == 'priority' and c.other_side > 0][0]
    shared = dict(approach_speed=8.5, start_x=-55., other_speed=7., other_side=1.)
    a = observation(np.array([-20., 8.]), right.__class__(**{**right.record(), **shared}),
                    -20., 7., 0., 0.)
    b = observation(np.array([-20., 8.]), priority.__class__(**{**priority.record(), **shared}),
                    -20., 7., 0., 0.)
    # Exactly one field differs, and it is the one an ambulance actually shows you.
    differing = [OBSERVATION_FIELDS[i] for i in range(len(a)) if a[i] != b[i]]
    assert differing == ['other_is_emergency']


def test_encode_rejects_malformed_observations():
    with pytest.raises(ValueError):
        encode(np.zeros((1, 10), np.float32))
    with pytest.raises(ValueError):
        encode(np.full((1, 11), np.nan, np.float32))
    assert encode(np.zeros((4, 11), np.float32)).shape[0] == 4


def test_the_conflict_box_and_clearance_agree_about_where_the_vehicle_is():
    case = cases('heldout', 1)[0]
    assert occupies(case, 0.)
    assert not occupies(case, OTHER_HALF_LENGTH+CONFLICT_HALF_SPAN+.1)
    assert separation(JUNCTION_DEPTH/2, 0.) == 0.     # Nose on the box centre, it is touching.
    assert separation(-20., -30.) > 20.
    assert gone(CLEAR_MARGIN+.1) and not gone(CLEAR_MARGIN-.1)


def test_a_vehicle_that_must_give_way_waits_until_the_ego_is_completely_through():
    """`left` is the negative case only if its vehicle actually holds back."""
    case = [c for c in cases('heldout', 60) if c.kind == 'left'][0]
    other = -30.
    for _ in range(600):                      # Ego still short of the junction.
        other, _ = step_other(case, other, -8., .05)
    assert other < 0. and not occupies(case, other), 'it drove into the box anyway'
    for _ in range(200):                      # Ego's rear now clear of the box.
        other, _ = step_other(case, other, JUNCTION_DEPTH+4., .05)
    assert other > CLEAR_MARGIN, 'it never went once the ego was through'


def test_the_teacher_gives_way_only_to_vehicles_that_hold_priority():
    right, left, priority = (
        [c for c in cases('heldout', 60) if c.kind == kind][0] for kind in KINDS)
    approaching = dict(front=-18., speed=8.5, other_s=-16., other_speed=7.)
    assert yields(right, **approaching)
    assert not yields(left, **approaching), 'stopped for traffic from the left'
    assert yields(priority, **approaching)
    # Nothing coming: no stop for any kind.
    assert not any(yields(c, front=-18., speed=8.5, other_s=-200., other_speed=7.)
                   for c in (right, left, priority))
    # Already clear of the box: no stop either.
    assert not yields(right, front=-18., speed=8.5, other_s=CLEAR_MARGIN+2., other_speed=7.)


def test_the_teacher_never_presses_both_pedals():
    for case in cases('train', 30):
        _, targets, _ = rollout(case)
        assert not np.any((targets[:, 0] > .01) & (targets[:, 1] > .01))
        assert targets.min() >= 0. and targets.max() <= 1.


def test_the_teacher_commits_rather_than_abandoning_a_stop_it_can_no_longer_make():
    """Braking from inside the box is worse than clearing it; the rule is the line."""
    case = [c for c in cases('heldout', 60) if c.kind == 'priority'][0]
    inside = target(np.array([2., 8.]), case, -6., 7.)
    assert inside[0] > 0. and inside[1] == 0., 'it braked with its nose already in the box'


@pytest.mark.parametrize('split', ['train', 'validation', 'heldout'])
def test_teacher_solves_its_own_task_on_every_split(split):
    """The demonstrator must clear the gate it is teaching, or the labels are unusable."""
    results = [metrics(rollout(case)[2], case) for case in cases(split, 60)]
    assert not any(r['contact'] for r in results), 'teacher hit the crossing vehicle'
    assert not any(r['entered_occupied'] for r in results), 'teacher entered an occupied box'
    assert not any(r['too_close'] for r in results)
    assert sum(r['passed'] for r in results) == 60, f'{split}: {sum(r["passed"] for r in results)}/60'


def test_the_three_kinds_are_actually_discriminated_rather_than_all_stopped_for():
    scored = [(c, metrics(rollout(c)[2], c)) for c in cases('heldout', 60)]
    stopped = {kind: sum(m['yielded_before_line'] for c, m in scored if c.kind == kind)
               for kind in KINDS}
    assert stopped['left'] == 0, 'gave way to traffic from the left'
    assert stopped['right'] >= 8 and stopped['priority'] >= 8, stopped
    assert all(m['cleared_junction'] for _, m in scored), 'a case never got through'


def test_metrics_flag_driving_into_an_occupied_box():
    case = [c for c in cases('heldout', 60) if c.kind == 'right'][0]
    through = [{'state': np.array([x, 8.]), 'other_s': 0., 'other_speed': 7.}
               for x in np.arange(-20., 20., .4)]
    scored = metrics(through, case)
    assert scored['stop_required'] and scored['contact'] and not scored['passed']


def test_metrics_flag_stopping_for_a_vehicle_that_had_no_priority():
    case = [c for c in cases('heldout', 60) if c.kind == 'left'][0]
    halted = [{'state': np.array([-6.+.001*i, max(0., 6.-.05*i)]), 'other_s': -80.,
               'other_speed': 7.} for i in range(300)]
    scored = metrics(halted, case)
    assert not scored['stop_required'] and scored['unnecessary_stop'] and not scored['passed']


def test_metrics_ignore_what_happens_once_the_ego_is_out_of_the_junction():
    """A vehicle entering the box behind a departed ego is not the ego's conflict."""
    case = [c for c in cases('heldout', 60) if c.kind == 'right'][0]
    leaving = [{'state': np.array([x, 8.]), 'other_s': -60. if x < JUNCTION_DEPTH+4. else 0.,
                'other_speed': 7.} for x in np.arange(-30., 40., .4)]
    scored = metrics(leaving, case)
    assert not scored['entered_occupied'] and not scored['contact'] and scored['passed']


def test_rollout_observations_and_targets_line_up():
    observations, targets, trajectory = rollout(cases('train', 1)[0])
    assert len(observations) == len(targets) == len(trajectory)
    assert observations.shape[1] == 11 and targets.shape[1] == 2
    assert encode(observations).shape[0] == len(observations)


def test_visibility_is_measured_from_where_the_ego_actually_is():
    case = cases('heldout', 1)[0]
    assert visible(case, -20., -20.)
    assert not visible(case, JUNCTION_DEPTH+1., -20.), 'seen from beyond the junction'
    assert not visible(case, -20., -SENSING_RANGE*2)
