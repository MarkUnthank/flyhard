"""What the cameras record, against what the scorer is shown.

A collision used to end the take on the frame of impact, which reads as a dropped clip
rather than as a crash. The cameras now keep rolling, and the two questions have to
stay separate: extending the recording must not extend the trial, or every metric
would quietly change.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

from evaluate_scenario import CONTROL_DT, capture_over


def test_an_undisturbed_trial_ends_where_the_scenario_says():
    assert capture_over(step=40, hit_at=None, done=True, aftermath=2.5)
    assert not capture_over(step=40, hit_at=None, done=False, aftermath=2.5)


def test_the_frame_of_impact_does_not_end_the_take():
    """This is the bug: the clip stopped on the frame the collision sensor fired."""
    assert not capture_over(step=40, hit_at=40, done=True, aftermath=2.5)


def test_the_scenario_s_own_finish_stops_mattering_once_something_has_been_hit():
    """After a crash the car is wherever physics put it, so `done` means nothing."""
    assert not capture_over(step=41, hit_at=40, done=True, aftermath=2.5)


def test_the_aftermath_runs_for_the_time_it_was_given():
    aftermath = 2.5
    steps = round(aftermath/CONTROL_DT)
    assert not capture_over(step=40+steps-1, hit_at=40, done=False, aftermath=aftermath)
    assert capture_over(step=40+steps, hit_at=40, done=False, aftermath=aftermath)


def test_no_aftermath_is_the_old_behaviour_exactly():
    assert capture_over(step=40, hit_at=40, done=False, aftermath=0.)


def test_the_scored_trajectory_is_the_one_that_ended_at_the_impact():
    """`scored` is the length at first contact; None before one, which slices to all."""
    trajectory = list(range(60))
    at_impact, scored = 41, 41
    assert trajectory[:scored] == trajectory[:at_impact]
    assert trajectory[:None] == trajectory


@pytest.mark.parametrize('aftermath', [0., .5, 2.5, 5.])
def test_the_aftermath_never_shortens_a_take(aftermath):
    assert not capture_over(step=40, hit_at=40, done=True, aftermath=aftermath) or aftermath == 0.
