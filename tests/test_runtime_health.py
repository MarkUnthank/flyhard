"""A startup retry must recover from an RPC client created too early."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_reconnect_after_initial_carla_connection_failure(monkeypatch):
    path=Path(__file__).resolve().parents[1]/'scripts/runtime_health.py'
    spec=importlib.util.spec_from_file_location('runtime_health',path)
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health)
    monkeypatch.setattr(health.time,'sleep',lambda _: None)
    world=SimpleNamespace(get_blueprint_library=lambda: SimpleNamespace(find=lambda _: object()))
    clients=[]

    class Client:
        def __init__(self, *_):
            self.failed_connection=not clients
            clients.append(self)

        def set_timeout(self, _):pass

        def get_world(self):
            if self.failed_connection:
                raise RuntimeError('Connection opened before the server was ready')
            return world

        def get_server_version(self):return '0.9.16'

    client,actual_world,version=health.wait_for_carla(Client,timeout=1)
    assert len(clients)==2
    assert client is clients[1] and actual_world is world and version=='0.9.16'


@pytest.mark.parametrize(('server', 'town', 'movable', 'expected_error'), [
    ('294096e-dirty', 'Town03', True, None),
    ('0.9.16', 'Town03', True, 'Expected CARLA server'),
    ('294096e-dirty', 'Town10HD_Opt', True, 'different map'),
    ('294096e-dirty', 'Town03', False, 'movable-accessory'),
])
def test_native_readiness_checks_build_map_and_patch(server, town, movable, expected_error):
    path=Path(__file__).resolve().parents[1]/'scripts/runtime_health.py'
    spec=importlib.util.spec_from_file_location('runtime_health',path)
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health)
    world=SimpleNamespace(
        get_map=lambda: SimpleNamespace(name='/Game/Carla/Maps/'+town),
        get_blueprint_library=lambda: SimpleNamespace(
            find=lambda _: SimpleNamespace(has_attribute=lambda _: movable)))
    client=SimpleNamespace(set_timeout=lambda _: None, get_world=lambda: world,
                           get_server_version=lambda: server)
    call=lambda: health.wait_for_carla(lambda *_: client, timeout=1,
        server_version='294096e-dirty', default_map='Town03', native=True)
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):call()
    else:
        assert call() == (client, world, server)
