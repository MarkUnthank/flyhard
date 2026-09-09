import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("runpod_control", Path(__file__).parents[1] / "scripts/runpod_control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def test_guard_limits_are_independent():
    state = {"deadline_epoch": 100, "reserve_usd": 4, "initial_balance_usd": 20, "spend_cap_usd": 6}
    assert not control.must_stop(state, 19, 50)
    assert control.must_stop(state, 19, 100)
    assert control.must_stop(state, 14, 50)
    assert control.must_stop(state, 4, 50)


def test_topup_does_not_extend_deadline():
    state = {"deadline_epoch": 100, "reserve_usd": 4, "initial_balance_usd": 20, "spend_cap_usd": 6}
    assert control.must_stop(state, 500, 100)
