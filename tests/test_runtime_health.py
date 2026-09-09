"""A startup retry must recover from an RPC client created too early."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


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
