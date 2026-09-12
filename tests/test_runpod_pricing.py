"""Live-catalog pricing determines whether a paid builder may be launched."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "control_pricing", Path(__file__).resolve().parents[1] / "scripts/runpod_control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def test_cpu_price_is_per_vcpu(monkeypatch):
    def catalog(method, path):
        assert (method, path) == ("GET", "/v2/catalog/cpus/cpu3g")
        return {"vcpu": {"min": 2, "max": 32}, "price": {"securePerVcpu": 0.04}}
    monkeypatch.setattr(control, "request", catalog)
    assert control.compute_hourly({"cpu": {"id": "cpu3g", "vcpuCount": 16}}) == 0.64


@pytest.mark.parametrize("config", [
    {}, {"cpu": {"id": "cpu3g", "vcpuCount": 24}},
    {"cpu": {"id": "cpu3g", "vcpuCount": 16}, "gpu": {"id": "A40"}},
])
def test_invalid_compute_never_reaches_provider(monkeypatch, config):
    monkeypatch.setattr(control, "request", lambda *args: pytest.fail("Unexpected request"))
    with pytest.raises(RuntimeError):
        control.compute_hourly(config)


def test_gpu_price_is_per_device(monkeypatch):
    monkeypatch.setattr(control, "request", lambda *args: {"price": {"secure": 0.44}})
    assert control.compute_hourly({"gpu": {"id": "A40"}}) == 0.44


def test_replaced_watcher_cannot_mutate_new_session(monkeypatch, tmp_path):
    state = tmp_path / 'session.json'
    state.write_text(json.dumps({'closed': False, 'guard_pid': os.getpid() + 1}))
    monkeypatch.setattr(control, 'STATE', state)
    monkeypatch.setattr(control, 'resolve_pod', lambda *args: pytest.fail('Old watcher reached provider'))
    control.watch()


@pytest.mark.parametrize('balance,seconds,price,message', [
    (5.99,3600,.53,'credit'),
    (8.,3600,1.6,'Hourly'),
    (8.,21600,.53,'runtime'),
])
def test_bounded_launch_rejects_before_allocation(monkeypatch,tmp_path,balance,seconds,price,message):
    config = tmp_path/'pod.json'
    config.write_text(json.dumps({'name':'unit-test','gpu':{'id':'test'},'disk':100,
        'budget':{'runtime_seconds':seconds,'reserve_usd':4,'spend_cap_usd':2,'max_hourly_usd':1.5}}))
    monkeypatch.setattr(control,'STATE',tmp_path/'state.json')
    monkeypatch.setattr(control,'balance',lambda:{'clientBalance':balance})
    monkeypatch.setattr(control,'compute_hourly',lambda _:price)
    monkeypatch.setattr(control,'request',lambda *a:pytest.fail('Rejected budget reached provider'))
    with pytest.raises(RuntimeError,match=message):
        control.launch(config)
