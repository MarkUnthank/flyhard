import numpy as np

from flyhard.roundabout_metrics import episode_complete, score_signals


def test_completion_uses_route_goal_including_short_exit():
    episode = {"max_progress": 91.779274, "length": 94.779272,
               "exit_s": 69.800027, "max_route_error_m": 1.1}
    assert episode_complete(episode)
    assert not episode_complete({**episode, "max_route_error_m": 6.})
    assert not episode_complete({**episode, "max_progress": 85.})


def test_correct_activation_hold_and_cancellation():
    progress = np.arange(96.)
    signal = np.where((progress >= 40) & (progress <= 80), "right", "off")
    assert score_signals(progress, signal, {"exit_s": 70, "length": 98})["passed"]


def test_always_off_and_always_on_cannot_pass():
    progress = np.arange(96.)
    route = {"exit_s": 70, "length": 98}
    off = score_signals(progress, np.full(96, "off"), route)
    on = score_signals(progress, np.full(96, "right"), route)
    assert not off["passed"] and not off["checks"]["held_through_exit"]
    assert not on["passed"] and not on["checks"]["cancelled_after_exit"]


def test_early_signal_or_missing_cancellation_fails_even_if_exit_is_signalled():
    progress = np.arange(96.)
    route = {"exit_s": 70, "length": 98}
    early = np.where((progress >= 20) & (progress <= 80), "right", "off")
    late = np.where(progress >= 40, "right", "off")
    assert not score_signals(progress, early, route)["passed"]
    assert not score_signals(progress, late, route)["passed"]
