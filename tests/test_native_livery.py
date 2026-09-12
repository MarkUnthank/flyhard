import hashlib
import json

import numpy as np
import pytest

from flyhard.native_livery import attachment_offset, verify_import


def test_native_alignment_reflects_y_and_preserves_metres():
    # Deliberately asymmetric centre: catches swapped handedness and 100x scale.
    bounds = [[-2.4, -0.8, 0.1], [2.0, 1.2, 1.9]]
    vehicle = [0.3, 0.05, 0.9]
    offset = attachment_offset(bounds, vehicle)
    np.testing.assert_allclose(offset, [0.5, 0.25, -0.1])
    imported_center_metres = np.mean(bounds, axis=0) * [1, -1, 1]
    np.testing.assert_allclose(imported_center_metres + offset, vehicle)


@pytest.mark.parametrize('bounds', [
    [[0, 0, 0], [-1, 1, 1]], [[0, 0, 0], [1, float('nan'), 1]], [[0, 1, 2]],
])
def test_invalid_source_bounds_fail_before_spawning(bounds):
    with pytest.raises(ValueError):
        attachment_offset(bounds, [0, 0, 1])


def test_fresh_export_reuses_native_assets_only_when_model_and_artwork_match(tmp_path):
    texture = b'unchanged paid artwork'
    (tmp_path / 'ad-1.png').write_bytes(texture)
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'revision': 19, 'layoutVersion': 5,
        'sponsors': [{'slotId': 'ad-1', 'texture': 'ad-1.png'}],
    }))
    hashes = {'sponsored-mini.blend': 'new save metadata',
              'sponsored-mini.glb': 'identical embedded model'}
    (tmp_path / 'sha256.json').write_text(json.dumps(hashes))
    receipt = {
        'revision': 19, 'layout': 5, 'source_model_sha256': 'original save metadata',
        'source_model_glb_sha256': hashes['sponsored-mini.glb'],
        'native_asset_directory': '/Game/Flyhard/Livery/test',
        'native_meshes': [
            {'slot_id': None, 'mesh_path': '/Game/Flyhard/Livery/test/Frame.Frame', 'bounds_error_cm': 0},
            {'slot_id': 'ad-1', 'mesh_path': '/Game/Flyhard/Livery/test/Ad.Ad', 'bounds_error_cm': 0,
             'source_texture_sha256': hashlib.sha256(texture).hexdigest()},
        ],
    }
    imported = tmp_path / 'import.json'
    imported.write_text(json.dumps(receipt))
    assert verify_import(tmp_path, imported) == receipt
    hashes['sponsored-mini.glb'] = 'changed geometry with same sponsor revision'
    (tmp_path / 'sha256.json').write_text(json.dumps(hashes))
    with pytest.raises(RuntimeError, match='different car model'):
        verify_import(tmp_path, imported)
    hashes['sponsored-mini.glb'] = receipt['source_model_glb_sha256']
    (tmp_path / 'sha256.json').write_text(json.dumps(hashes))
    (tmp_path / 'ad-1.png').write_bytes(b'changed paid artwork')
    with pytest.raises(RuntimeError, match='artwork differs'):
        verify_import(tmp_path, imported)
