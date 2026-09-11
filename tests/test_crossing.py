import math

import numpy as np
import pytest

from flyhard.crossing import (CROSSING_DEPTH, FRONT_OVERHANG, OBSERVATION_FIELDS, SENSING_RANGE,
                              cases, encode, in_conflict, kinematic_step, metrics,
                              observation, pedestrian_state)
from flyhard.crossing_teacher import rollout, target, threatens


def test_splits_are_disjoint_and_heldout_varies_beyond_the_seed():
    train, validation, heldout = (cases(s, 40) for s in ['train', 'validation', 'heldout'])
    seeds = [{c.seed for c in split} for split in (train, validation, heldout)]
    assert not seeds[0] & seeds[1] and not seeds[0] & seeds[2] and not seeds[1] & seeds[2]
    # The evaluated road width is absent from training, as for the three-point turn.
    assert {c.road_width for c in train} == {9.0, 11.0}
    assert {c.road_width for c in heldout} == {10.0}
    # Held-out walk speeds and triggers reach outside the demonstrated ranges.
    assert min(c.walk_speed for c in heldout) < min(c.walk_speed for c in train)
    assert max(c.trigger_distance for c in heldout) > max(c.trigger_distance for c in train)


def test_cases_are_deterministic():
    assert [c.record() for c in cases('heldout', 8)] == [c.record() for c in cases('heldout', 8)]


def test_every_split_has_quiet_cases_where_no_stop_is_required():
    for split in ['train', 'validation', 'heldout']:
        quiet = [c for c in cases(split, 40) if c.dwell_seconds > 1e5]
        assert len(quiet) == 10, split


def test_observation_field_count_matches_the_declared_names():
    case = cases('heldout', 1)[0]
    values = observation(case.start, case, case.kerb_y, 0., 0., 0.)
    assert values.shape == (len(OBSERVATION_FIELDS),) == (10,)
    assert np.isfinite(values).all()


def test_observation_hides_a_pedestrian_beyond_the_sensing_range():
    case = cases('heldout', 1)[0]
    far = np.array([-200., 8.])
    values = observation(far, case, case.kerb_y, 1.2, 0., 0.)
    assert values[2] == 0.
    assert values[3] == SENSING_RANGE and values[4] == 0. and values[5] == 0.


def test_observation_cannot_distinguish_a_quiet_case_before_the_pedestrian_moves():
    """A waiting pedestrian and one about to walk must look identical until they move."""
    quiet, crossing = cases('heldout', 4)[3], cases('heldout', 4)[0]
    assert quiet.dwell_seconds > 1e5 and crossing.dwell_seconds < 1.
    state = np.array([-30., 8.])
    shared = dict(kerb_side=1., road_width=10., walk_offset=2.)
    a = observation(state, quiet.__class__(**{**quiet.record(), **shared}), 5.6, 0., .2, 0.)
    b = observation(state, crossing.__class__(**{**crossing.record(), **shared}), 5.6, 0., .2, 0.)
    assert np.array_equal(a, b)


def test_encode_rejects_malformed_observations():
    with pytest.raises(ValueError):
        encode(np.zeros((1, 9), np.float32))
    with pytest.raises(ValueError):
        encode(np.full((1, 10), np.nan, np.float32))
    assert encode(np.zeros((3, 10), np.float32)).shape[0] == 3


def test_kinematic_step_never_reverses_under_braking():
    state = np.array([-10., 1.])
    for _ in range(60):
        state = kinematic_step(state, 0., 1.)
    assert state[1] == 0. and state[0] > -10.


def test_pedestrian_walks_only_after_the_trigger_and_its_dwell():
    case = cases('train', 1)[0]
    assert pedestrian_state(case, None, 5.)[2] is False
    y_at_trigger, _, walking = pedestrian_state(case, 2., 2.+case.dwell_seconds-.01)
    assert walking is False and y_at_trigger == case.kerb_y
    _, speed, walking = pedestrian_state(case, 2., 2.+case.dwell_seconds+.5)
    assert walking is True and speed*case.kerb_side < 0


def test_priority_is_held_by_anyone_walking_onto_the_crossing():
    case = cases('heldout', 1)[0]
    # Pedestrian still on the kerb but walking in: they hold priority from the
    # moment they step off, not from the moment they reach the swept band.
    assert threatens(-25., 8., case, case.kerb_y, -case.kerb_side*1.4)
    # Same position, standing still: no stop.
    assert not threatens(-25., 8., case, case.kerb_y, 0.)
    # Already past the band and moving away: no stop.
    assert not threatens(-25., 8., case, -case.kerb_y, -case.kerb_side*1.4)


def test_teacher_brakes_for_an_occupied_band_and_accelerates_when_clear():
    case = cases('heldout', 1)[0]
    braking = target(np.array([-20.-FRONT_OVERHANG, 8.]), case, 0., 0.)
    assert braking[0] == 0. and braking[1] > 0.
    cruising = target(np.array([-20.-FRONT_OVERHANG, 4.]), case, case.kerb_y, 0.)
    assert cruising[0] > 0. and cruising[1] == 0.


def test_teacher_never_presses_both_pedals():
    for case in cases('train', 24):
        _, targets, _ = rollout(case)
        assert not np.any((targets[:, 0] > .01) & (targets[:, 1] > .01))
        assert targets.min() >= 0. and targets.max() <= 1.


def test_metrics_flag_contact_and_unnecessary_stops():
    case = cases('heldout', 1)[0]
    # Car drives through the band while the pedestrian stands in it.
    through = [{'state': np.array([x, 8.]), 'pedestrian_y': 0., 'walking': True}
               for x in np.arange(-20., 20., .4)]
    scored = metrics(through, case)
    assert scored['stop_required'] and scored['contact'] and not scored['passed']

    # Car halts for a pedestrian who is never in the road.
    halted = [{'state': np.array([-6.+.001*i, max(0., 6.-.05*i)]), 'pedestrian_y': case.kerb_y,
               'walking': False} for i in range(300)]
    scored = metrics(halted, case)
    assert not scored['stop_required'] and scored['unnecessary_stop'] and not scored['passed']


@pytest.mark.parametrize('split', ['train', 'validation', 'heldout'])
def test_teacher_solves_its_own_task_on_every_split(split):
    """The demonstrator must clear the gate it is teaching, or the labels are unusable."""
    results = [metrics(rollout(case)[2], case) for case in cases(split, 40)]
    passed = sum(r['passed'] for r in results)
    assert not any(r['contact'] for r in results), 'teacher hit a pedestrian'
    assert not any(r['entered_on_pedestrian'] for r in results), 'teacher entered an occupied crossing'
    assert passed >= 38, f'{split}: teacher passed only {passed}/40'


def test_teacher_never_enters_an_occupied_crossing_when_a_stop_is_required():
    scored = [metrics(rollout(case)[2], case) for case in cases('heldout', 40)]
    needed = [m for m in scored if m['stop_required']]
    assert len(needed) >= 20, f'only {len(needed)} held-out cases demand a stop'
    assert all(not m['entered_on_pedestrian'] for m in needed)
    assert all(not m['contact'] for m in needed)
    assert all(not m['stopped_in_crossing'] for m in needed)


def test_a_pedestrian_still_on_the_crossing_forces_a_full_stop():
    """Slowing and resuming is correct once they have finished crossing. Still being
    on it when the car reaches the line is the case that must end at a standstill."""
    stopped, resumed = 0, 0
    for case in cases('heldout', 40):
        trajectory = rollout(case)[2]
        scored = metrics(trajectory, case)
        if not scored['stop_required']:
            continue
        occupied_at_line = next((in_conflict(row['pedestrian_y']) for row in trajectory
                                 if row['state'][0]+FRONT_OVERHANG >= 0), False)
        if occupied_at_line:
            assert scored['yielded_before_line'], f'{case.seed} did not stop for an occupied crossing'
            stopped += 1
        else:
            resumed += scored['yielded_before_line'] is False
    assert stopped >= 2, 'no held-out case put the pedestrian on the line'
    assert resumed >= 8, 'the teacher never resumes after a pedestrian clears'


def test_quiet_cases_are_driven_through_without_stopping():
    quiet = [c for c in cases('heldout', 40) if c.dwell_seconds > 1e5]
    for case in quiet:
        scored = metrics(rollout(case)[2], case)
        assert not scored['stop_required'] and not scored['unnecessary_stop'] and scored['passed']


def test_rollout_observations_and_targets_line_up():
    case = cases('train', 1)[0]
    observations, targets, trajectory = rollout(case)
    assert len(observations) == len(targets) == len(trajectory)
    assert observations.shape[1] == 10 and targets.shape[1] == 2
    assert encode(observations).shape[0] == len(observations)
