"""Storage lifecycle regressions: budget shutdown must preserve project data."""
import importlib.util
from pathlib import Path
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shutdown_retains_ordinary_workspace(monkeypatch):
    control = load('control', 'scripts/runpod_control.py')
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args))
    control.release_compute({'id': 'ordinary', 'mounts': {'persistent': {'path': '/workspace', 'size': 40}}})
    assert calls == [('POST', '/v2/pods/ordinary/action', {'action': 'stop'})]


def test_shutdown_releases_network_compute_without_deleting_volume(monkeypatch):
    control = load('control', 'scripts/runpod_control.py')
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args))
    control.release_compute({'id': 'durable', 'mounts': {'network': [{'path': '/workspace', 'volumeId': 'keep'}]}})
    assert calls == [('DELETE', '/v2/pods/durable')]


def test_other_network_path_cannot_justify_deleting_ephemeral_workspace(monkeypatch):
    control = load('control', 'scripts/runpod_control.py')
    monkeypatch.setattr(control, 'request', lambda *args: pytest.fail('Must not mutate resources'))
    with pytest.raises(RuntimeError, match='no durable /workspace'):
        control.release_compute({'id': 'wrong', 'mounts': {'network': [{'path': '/models', 'volumeId': 'keep'}]}})


def test_image_update_preserves_displaced_edits_and_data(tmp_path):
    sync = load('sync', 'docker/sync_workspace.py')
    bundle, workspace = tmp_path/'image', tmp_path/'workspace'
    (bundle/'src').mkdir(parents=True)
    (bundle/'src/model.py').write_text('image one')
    (workspace/'runs').mkdir(parents=True)
    (workspace/'runs/capture.mp4').write_bytes(b'irreplaceable recording')
    sync.sync_workspace(bundle, workspace, 'one')
    (workspace/'src/model.py').write_text('iteration edit')
    receipt = sync.sync_workspace(bundle, workspace, 'one')
    assert (workspace/'src/model.py').read_text() == 'iteration edit'
    assert receipt['locally_modified'] == ['src/model.py']
    (bundle/'src/model.py').write_text('image two')
    receipt = sync.sync_workspace(bundle, workspace, 'two')
    assert (workspace/'src/model.py').read_text() == 'image two'
    assert (Path(receipt['backup'])/'src/model.py').read_text() == 'iteration edit'
    assert (workspace/'runs/capture.mp4').read_bytes() == b'irreplaceable recording'
    assert not receipt['locally_modified']


def test_image_removal_preserves_retired_source(tmp_path):
    sync = load('sync', 'docker/sync_workspace.py')
    bundle, workspace = tmp_path/'image', tmp_path/'workspace'
    (bundle/'src').mkdir(parents=True)
    (bundle/'src/old.py').write_text('old source')
    sync.sync_workspace(bundle, workspace, 'one')
    (bundle/'src/old.py').unlink()
    receipt = sync.sync_workspace(bundle, workspace, 'two')
    assert not (workspace/'src/old.py').exists()
    assert (Path(receipt['backup'])/'src/old.py').read_text() == 'old source'
