import importlib.util
import json
from pathlib import Path

import pytest

from flyhard.clips import ClipLibrary, Take, take_id

SPEC = importlib.util.spec_from_file_location(
    'assemble_film', Path(__file__).resolve().parents[1]/'scripts'/'assemble_film.py')
assemble = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assemble)


def make_take(root, scenario='crossing', seed=91000, attempt=1, outcome='success',
              duration=8., cameras=('wide', 'chase')):
    take = Take(scenario=scenario, seed=seed, attempt=attempt, outcome=outcome,
                duration_seconds=duration, fps=60,
                cameras={name: f'cameras/{name}/rgb.mp4' for name in cameras},
                label=f'{scenario} {outcome}')
    directory = ClipLibrary(root).directory(take)
    for name in cameras:
        path = directory/'cameras'/name/'rgb.mp4'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not-a-real-render-' + name.encode())
    return take


def test_take_id_is_stable_and_path_safe():
    assert take_id('crossing', 91000, 1) == 'crossing-s91000-a01'
    assert take_id('crossing', 91000, 1) == take_id('crossing', '91000', '1')
    with pytest.raises(ValueError):
        take_id('bad/name', 1, 1)


def test_register_verifies_every_camera_file_exists(tmp_path):
    library = ClipLibrary(tmp_path)
    take = make_take(tmp_path)
    directory = library.register(take)
    record = json.loads((directory/'take.json').read_text())
    assert record['id'] == 'crossing-s91000-a01'
    assert set(record['camera_sha256']) == {'wide', 'chase'}

    missing = Take(scenario='crossing', seed=1, attempt=1, outcome='success',
                   duration_seconds=3., fps=60, cameras={'wide': 'cameras/orbit/rgb.mp4'})
    with pytest.raises(FileNotFoundError):
        library.register(missing)


def test_invalid_takes_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        Take('crossing', 1, 1, 'maybe', 3., 60, {'wide': 'a.mp4'}).validate()
    with pytest.raises(ValueError):
        Take('crossing', 1, 1, 'success', 3., 60, {}).validate()
    with pytest.raises(ValueError):
        Take('crossing', 1, 1, 'success', 3., 60, {'drone': 'a.mp4'}).validate()
    with pytest.raises(ValueError):
        Take('crossing', 1, 1, 'success', 0., 60, {'wide': 'a.mp4'}).validate()


def test_find_filters_and_orders_deterministically(tmp_path):
    library = ClipLibrary(tmp_path)
    for seed, outcome in [(91002, 'failure'), (91000, 'success'), (91001, 'success')]:
        library.register(make_take(tmp_path, seed=seed, outcome=outcome))
    library.register(make_take(tmp_path, scenario='yield_right', seed=92000))

    assert [t['id'] for t in library.find(scenario='crossing')] == [
        'crossing-s91000-a01', 'crossing-s91001-a01', 'crossing-s91002-a01']
    assert [t['id'] for t in library.find(scenario='crossing', outcome='failure')] == [
        'crossing-s91002-a01']
    assert library.find(camera='cabin') == []
    assert library.find(min_seconds=99.) == []
    assert len(library.find()) == 4


def test_index_summarises_by_scenario_and_outcome(tmp_path):
    library = ClipLibrary(tmp_path)
    library.register(make_take(tmp_path, seed=91000, outcome='success', duration=8.))
    library.register(make_take(tmp_path, seed=91001, outcome='failure', duration=5.))
    payload = library.index()
    assert payload['take_count'] == 2
    assert payload['by_scenario']['crossing'] == {'success': 1, 'failure': 1, 'seconds': 13.}
    assert json.loads((tmp_path/'index.json').read_text())['take_count'] == 2


def test_resolve_rejects_unknown_take_and_camera(tmp_path):
    library = ClipLibrary(tmp_path)
    library.register(make_take(tmp_path))
    path, record = library.resolve('crossing-s91000-a01', 'wide')
    assert path.is_file() and record['outcome'] == 'success'
    with pytest.raises(KeyError):
        library.resolve('crossing-s91000-a01', 'cabin')
    with pytest.raises(KeyError):
        library.resolve('crossing-s99999-a01', 'wide')


def test_plan_resolution_builds_a_contiguous_timeline(tmp_path):
    library = ClipLibrary(tmp_path)
    library.register(make_take(tmp_path, seed=91000, outcome='success', duration=8.))
    library.register(make_take(tmp_path, seed=91002, outcome='failure', duration=6.))
    plan = {'sections': [{'title': 'Zebra crossing', 'scenario': 'crossing', 'shots': [
        {'take': 'crossing-s91000-a01', 'camera': 'wide', 'start': 0., 'duration': 4.},
        {'take': 'crossing-s91000-a01', 'camera': 'chase', 'start': 4., 'duration': 3.},
        {'take': 'crossing-s91002-a01', 'camera': 'wide', 'start': 0., 'duration': 5.,
         'transition': 'fade'}]}]}
    shots, total = assemble.resolve(plan, library)
    assert total == 12.
    assert [s['timeline_start'] for s in shots] == [0., 4., 7.]
    assert [s['outcome'] for s in shots] == ['success', 'success', 'failure']
    assert shots[0]['first_of_section'] and not shots[1]['first_of_section']


def test_plan_resolution_rejects_a_shot_longer_than_its_take(tmp_path):
    library = ClipLibrary(tmp_path)
    library.register(make_take(tmp_path, duration=8.))
    plan = {'sections': [{'title': 'T', 'scenario': 'crossing', 'shots': [
        {'take': 'crossing-s91000-a01', 'camera': 'wide', 'start': 6., 'duration': 5.}]}]}
    with pytest.raises(ValueError, match='only has'):
        assemble.resolve(plan, library)


def test_plan_resolution_rejects_unknown_transition(tmp_path):
    library = ClipLibrary(tmp_path)
    library.register(make_take(tmp_path))
    plan = {'sections': [{'title': 'T', 'scenario': 'crossing', 'shots': [
        {'take': 'crossing-s91000-a01', 'camera': 'wide', 'duration': 2., 'transition': 'swirl'}]}]}
    with pytest.raises(ValueError, match='transition'):
        assemble.resolve(plan, library)
