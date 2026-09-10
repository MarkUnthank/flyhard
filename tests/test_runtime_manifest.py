"""A release must identify exact cooked bytes and independently reviewed proof."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import runtime_manifest as runtime


def write_json(path, value):
    path.write_bytes(runtime.json_bytes(value))
    return path


@pytest.fixture
def candidate(tmp_path):
    root = tmp_path / 'build' / 'LinuxNoEditor'
    root.mkdir(parents=True)
    for name in [runtime.LAUNCHER, runtime.EXECUTABLE, 'CarlaUE4/Content/Maps/Town03.umap']:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(('bytes for ' + name).encode())
        file.chmod(0o755 if name in {runtime.LAUNCHER, runtime.EXECUTABLE} else 0o644)
    asset_dir = '/Game/Flyhard/Livery/r19_layout5_model'
    native_path = 'CarlaUE4/Content/Flyhard/Livery/r19_layout5_model/mesh.uasset'
    (root / native_path).parent.mkdir(parents=True)
    (root / native_path).write_bytes(b'cooked sponsor geometry and materials')
    imported = {'revision': 19, 'layout': 5, 'source_model_glb_sha256': 'b' * 64,
                'native_asset_directory': asset_dir,
                'native_meshes': [{'mesh_path': asset_dir + '/mesh.mesh'}]}
    write_json(root / runtime.IMPORT, imported)
    receipt = {'runtime': str(root), 'status': 'cooked; packaged-runtime simulator verification pending',
               'revision': 19, 'layout': 5, 'source_model_glb_sha256': 'b' * 64,
               'expected_server_version': '294096e-dirty', 'client_version': '0.9.16',
               'maps': ['/Game/Carla/Maps/Town03'],
               'carla_source': '2' * 40, 'engine_source': '3' * 40,
               'patch_sha256': '4' * 64, 'engine_lifecycle_patch_sha256': '5' * 64,
               'import_receipt_sha256': runtime.sha256(root / runtime.IMPORT),
               'shipping_executable_sha256': runtime.sha256(root / runtime.EXECUTABLE),
               'native_files': {native_path: runtime.sha256(root / native_path)}}
    receipt_path = write_json(tmp_path / 'package-receipt.json', receipt)
    selection = runtime.prepare_native(root, receipt_path)
    return root, selection, receipt_path


def proof_files(tmp_path, selection):
    proof = {'status': 'automated_checks_passed', 'runtime_mode': 'shipping',
             'runtime_manifest_sha256': selection['manifest_sha256'],
             'carla_server_version': '294096e-dirty', 'carla_client_version': '0.9.16',
             'map': '/Game/Carla/Maps/Town03', 'revision': 19, 'layout': 5,
             'native_actor_count': 1, 'physics_configuration_unchanged': True,
             'import_receipt_sha256': selection['native']['import_receipt_sha256'],
             'peak_speed_m_s': 4, 'max_attachment_position_error_m': 0.001,
             'max_attachment_rotation_error': 0.0001,
             'camera_comparisons': [{'view': view, 'sensor': sensor, 'changed_pixel_fraction': 0.1}
                                    for view in ['left-door', 'right-billboard', 'rear', 'front-roof']
                                    for sensor in ['rgb', 'depth']]}
    proof_path = write_json(tmp_path / 'proof.json', proof)
    visual_path = write_json(tmp_path / 'review.json', {
        'status': 'passed', 'runtime_manifest_sha256': selection['manifest_sha256'],
        'proof_sha256': runtime.sha256(proof_path)})
    return proof_path, visual_path


def test_candidate_requires_explicit_mode_and_selected_digest(candidate):
    root, selected, _ = candidate
    with pytest.raises(RuntimeError, match='explicit validation'):
        runtime.resolve(root / runtime.MANIFEST, selected['manifest_sha256'])
    with pytest.raises(ValueError, match='digest mismatch'):
        runtime.resolve(root / runtime.MANIFEST, '0' * 64, allow_candidate=True)
    assert runtime.resolve(root / runtime.MANIFEST, selected['manifest_sha256'], allow_candidate=True) == selected


def test_boot_checks_actual_executable_and_native_bytes(candidate):
    root, selected, _ = candidate
    (root / runtime.EXECUTABLE).write_bytes(b'corrupt actual server; launcher unchanged')
    with pytest.raises(RuntimeError, match='boot file differs'):
        runtime.resolve(root / runtime.MANIFEST, selected['manifest_sha256'], allow_candidate=True)


def test_full_promotion_rejects_changed_non_boot_content(candidate, tmp_path):
    root, selected, _ = candidate
    proof, review = proof_files(tmp_path, selected)
    (root / 'CarlaUE4/Content/Maps/Town03.umap').write_bytes(b'changed map')
    with pytest.raises(RuntimeError, match='Immutable runtime tree'):
        runtime.promote(root / runtime.MANIFEST, selected['manifest_sha256'], proof, tmp_path / 'releases', review)
    assert root.exists()


def test_saved_files_are_mutable_but_extra_assets_are_not(candidate, tmp_path):
    root, selected, _ = candidate
    saved = root / runtime.MUTABLE
    saved.mkdir(parents=True)
    (saved / 'session.log').write_text('mutable runtime output')
    runtime.resolve(root / runtime.MANIFEST, selected['manifest_sha256'], allow_candidate=True, full=True)
    (root / 'unexpected.uasset').write_bytes(b'extra cooked asset')
    with pytest.raises(RuntimeError, match='Immutable runtime tree'):
        runtime.resolve(root / runtime.MANIFEST, selected['manifest_sha256'], allow_candidate=True, full=True)


@pytest.mark.parametrize(('field', 'value'), [
    ('runtime_mode', 'editor'), ('runtime_manifest_sha256', 'a' * 64),
    ('status', 'automated checks passed; visual review and packaging pending'),
    ('carla_server_version', '0.9.16'), ('map', 'Town10HD_Opt'),
    ('import_receipt_sha256', 'a' * 64), ('max_attachment_position_error_m', 0.02),
    ('max_attachment_rotation_error', float('nan')), ('peak_speed_m_s', 0),
    ('camera_comparisons', []), ('physics_configuration_unchanged', False),
])
def test_unreviewed_editor_wrong_candidate_or_failed_checks_cannot_promote(candidate, tmp_path, field, value):
    root, selected, _ = candidate
    proof, review = proof_files(tmp_path, selected)
    data = json.loads(proof.read_text())
    data[field] = value
    proof.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        runtime.promote(root / runtime.MANIFEST, selected['manifest_sha256'], proof, tmp_path / 'releases', review)
    assert root.exists()


def test_visual_review_is_bound_to_exact_automated_proof(candidate, tmp_path):
    root, selected, _ = candidate
    proof, review = proof_files(tmp_path, selected)
    with pytest.raises(ValueError, match='visual review'):
        runtime.promote(root / runtime.MANIFEST, selected['manifest_sha256'], proof, tmp_path / 'releases')
    data = json.loads(proof.read_text())
    data['additional_observation'] = 'The old review does not cover this edited proof.'
    write_json(proof, data)
    with pytest.raises(ValueError, match='visual review'):
        runtime.promote(root / runtime.MANIFEST, selected['manifest_sha256'], proof, tmp_path / 'releases', review)


def test_promote_moves_verified_tree_and_keeps_bound_proof(candidate, tmp_path):
    root, selected, _ = candidate
    proof, review = proof_files(tmp_path, selected)
    promoted = runtime.promote(root / runtime.MANIFEST, selected['manifest_sha256'], proof, tmp_path / 'releases', review)
    assert not root.exists()
    assert promoted['status'] == 'verified'
    assert promoted['package_id'] == selected['package_id']
    assert promoted['manifest_sha256'] != selected['manifest_sha256']
    assert runtime.resolve(promoted['manifest'], promoted['manifest_sha256'], full=True) == promoted
    (Path(promoted['root']) / runtime.PROOF).write_text('{}')
    with pytest.raises(RuntimeError, match='proof differs'):
        runtime.resolve(promoted['manifest'], promoted['manifest_sha256'])


def test_no_runtime_path_can_escape_root(candidate, tmp_path):
    root, selected, _ = candidate
    secret = tmp_path / 'outside'
    secret.write_bytes(b'not runtime content')
    (root / runtime.EXECUTABLE).unlink()
    (root / runtime.EXECUTABLE).symlink_to(secret)
    with pytest.raises(ValueError, match='escapes'):
        runtime.resolve(root / runtime.MANIFEST, selected['manifest_sha256'], allow_candidate=True)


def test_official_migration_checks_archive_pin_and_all_extracted_bytes(tmp_path, monkeypatch):
    root = tmp_path / 'official'
    root.mkdir()
    archive = tmp_path / 'official.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in [runtime.LAUNCHER, runtime.EXECUTABLE, 'CarlaUE4/Content/map.umap']:
            data = ('official ' + name).encode()
            member = tarfile.TarInfo('./' + name)
            member.size = len(data)
            member.mode = 0o755
            tar.addfile(member, io.BytesIO(data))
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            file.chmod(0o755)
    with pytest.raises(ValueError, match='archive SHA-256'):
        runtime.prepare_official(root, archive)
    monkeypatch.setattr(runtime, 'OFFICIAL_SHA256', runtime.sha256(archive))
    (root / 'CarlaUE4/Content/map.umap').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='differs from the pinned archive'):
        runtime.prepare_official(root, archive)
    (root / 'CarlaUE4/Content/map.umap').write_bytes(b'official CarlaUE4/Content/map.umap')
    selected = runtime.prepare_official(root, archive)
    assert selected['kind'] == 'official' and selected['status'] == 'candidate'
    assert selected['server_version'] == '0.9.16'


def test_launch_selection_requires_pin_and_echoed_identity(candidate):
    spec = importlib.util.spec_from_file_location('flyhard_launch', ROOT / 'deploy/launch.py')
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    _, selected, _ = candidate
    release = {'runtime_layout': 'network-volume', 'runtime_manifest': '/workspace/native/runtime-manifest.json',
               'runtime_manifest_sha256': selected['manifest_sha256']}
    assert launch.runtime_environment(release, True)['FLYHARD_RUNTIME_CANDIDATE'] == '1'
    for bad in [None, '/workspace/../tmp/runtime-manifest.json', '/tmp/runtime-manifest.json']:
        with pytest.raises(ValueError):
            launch.runtime_environment({**release, 'runtime_manifest': bad}, False)
    state = {'network_volume_id': 'volume', 'expected_runtime_manifest': release['runtime_manifest'],
             'expected_runtime_manifest_sha256': selected['manifest_sha256'], 'allow_candidate_runtime': True}
    ready = {'runtime_asset': {**selected, 'manifest': release['runtime_manifest']},
             'carla': '294096e-dirty', 'carla_client': '0.9.16', 'map': 'Town03'}
    launch.check_runtime_selection(ready, state)
    with pytest.raises(RuntimeError, match='packaged simulator proof'):
        launch.check_runtime_selection(ready, {**state, 'allow_candidate_runtime': False})
    with pytest.raises(RuntimeError, match='differs from the selected'):
        launch.check_runtime_selection({**ready, 'runtime_asset': {}}, state)
