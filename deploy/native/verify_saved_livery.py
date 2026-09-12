"""Reload the native assets in a fresh editor process before packaging them."""
import json
import os
from pathlib import Path

import unreal


source = Path(os.environ['FLYHARD_NATIVE_EXPORT'])
receipt = json.loads((source / 'unreal-import-receipt.json').read_text())
checks = []
for entry in receipt['native_meshes']:
    mesh = unreal.EditorAssetLibrary.load_asset(entry['mesh_path'])
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError('Saved mesh failed to reload: ' + entry['mesh_path'])
    bounds = mesh.get_bounds()
    actual = [bounds.origin.x, bounds.origin.y, bounds.origin.z,
              bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z]
    lo, hi = entry['bounds_cm']
    expected = [(lo[i] + hi[i]) / 2 for i in range(3)] + [(hi[i] - lo[i]) / 2 for i in range(3)]
    if max(abs(a - b) for a, b in zip(actual, expected)) > 0.001:
        raise RuntimeError('Saved mesh bounds changed: ' + entry['mesh_path'])
    materials = mesh.get_editor_property('static_materials')
    if not materials or any(x.get_editor_property('material_interface') is None for x in materials):
        raise RuntimeError('Saved mesh has missing materials: ' + entry['mesh_path'])
    if entry['slot_id']:
        for slot in materials:
            material = slot.get_editor_property('material_interface')
            if (material.get_editor_property('blend_mode') != unreal.BlendMode.BLEND_TRANSLUCENT
                    or material.get_editor_property('translucency_lighting_mode') != unreal.TranslucencyLightingMode.TLM_SURFACE
                    or material.get_editor_property('two_sided')):
                raise RuntimeError('Saved sponsor material lost its lighting or alpha settings')
    checks.append({'mesh_path': entry['mesh_path'], 'material_count': len(materials)})
(source / 'unreal-reload-receipt.json').write_text(json.dumps({
    'status': 'persisted geometry and materials reloaded in a fresh editor process',
    'native_asset_directory': receipt['native_asset_directory'], 'checks': checks,
}, indent=2) + '\n')
unreal.log('FLYHARD_NATIVE_RELOAD_VERIFIED')
