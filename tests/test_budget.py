import importlib.util
from pathlib import Path

import pytest

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


def test_blank_or_absent_key_is_reported_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.setattr(control, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="RUNPOD_API_KEY missing"):
        control.api_key()
    for blank in ("RUNPOD_API_KEY=\n", 'RUNPOD_API_KEY=""\n', "RUNPOD_API_KEY=''\n"):
        (tmp_path / ".env").write_text(blank)
        with pytest.raises(RuntimeError, match="RUNPOD_API_KEY missing"):
            control.api_key()
    (tmp_path / ".env").write_text("RUNPOD_API_KEY='abc'  # local\n")
    assert control.api_key() == "abc"
