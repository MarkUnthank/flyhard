"""Blender background: export the approved billboard for CARLA Unreal import.

Preserves advertising mesh, UVs, alpha, and independent material slots.
This is an interchange export, never a claim of a cooked CARLA asset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from flyhard.live_livery import verify_live_livery


def bounds(objects):
    points = np.array([list(o.matrix_world @ v.co) for o in objects for v in o.data.vertices])
    return np.array([points.min(0), points.max(0)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if not bpy.app.background:
        raise RuntimeError('Use Blender background mode')
    out = args.output.resolve()
    if (out / 'export-receipt.json').exists():
        raise RuntimeError('Choose a new output directory to retain prior evidence')
    manifest = verify_live_livery(args.asset, out)
    design = json.loads((args.model.parent / 'design-receipt.json').read_text())
    if design['revision'] != manifest['revision']:
        raise RuntimeError('Rebuild billboard against the latest livery before export')
    source_hashes = json.loads((args.asset / 'sha256.json').read_text())
    design_preflight = json.loads((args.model.parent / 'livery-preflight.json').read_text())
    if design_preflight['verified_files']['sponsored-mini.blend'] != source_hashes['sponsored-mini.blend']:
        raise RuntimeError('Billboard was built from a different source model')
    bpy.ops.wm.open_mainfile(filepath=str(args.model.resolve()))
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.
    structure = [o for o in bpy.data.objects if o.get('role') == 'billboard_structure' and o.name != 'Studio floor']
    art = [o for o in bpy.data.objects if o.get('slot_id') == 'ad-59' and o.type == 'MESH']
    assert len(structure) == 17, len(structure)
    assert len(art) == 1 and len(art[0].data.polygons) == 2
    sponsor = next(s for s in manifest['sponsors'] if s['slotId'] == 'ad-59')
    texture = out / 'ad-59.png'
    shutil.copyfile(args.asset / sponsor['texture'], texture)
    for node in art[0].data.materials[0].node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            node.image.filepath = str(texture)
    art[0].data.materials[0].name = 'M_RoofAd59'
    art[0].data.materials[0].diffuse_color = (1, 1, 1, 1)
    # Keep the original Blender car frame. The Unreal import must align it to
    # the native Mini body; no guessed pivot correction is baked into geometry.
    source_bounds = np.load(args.asset / 'render-panels.npz')['car_bounds']
    exports = []
    for name, objects in [('SM_TaxiBillboardFrame', structure), ('SM_TaxiBillboardAd59', art)]:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            # Evaluate bevels now so round-trip geometry can be checked exactly.
            for modifier in list(obj.modifiers):
                bpy.ops.object.modifier_apply(modifier=modifier.name)
        expected = bounds(objects)
        uv_count = sum(len(o.data.uv_layers.active.data) if o.data.uv_layers.active else 0 for o in objects)
        filename = out / (name + '.fbx')
        bpy.ops.export_scene.fbx(filepath=str(filename), use_selection=True,
            object_types={'MESH'}, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
            axis_forward='X', axis_up='Z', bake_anim=False, add_leaf_bones=False,
            mesh_smooth_type='FACE', use_mesh_modifiers=True, path_mode='COPY', embed_textures=True)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.import_scene.fbx(filepath=str(filename), use_anim=False)
        restored = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        error = float(np.max(np.abs(bounds(restored) - expected)))
        assert error < 1e-5, (name, error)
        assert len(restored) == len(objects)
        if name.endswith('Ad59'):
            assert sum(len(o.data.polygons) for o in restored) == 2
            original_uv = np.array([list(x.uv) for x in objects[0].data.uv_layers.active.data])
            restored_uv = np.array([list(x.uv) for x in restored[0].data.uv_layers.active.data])
            assert np.allclose(original_uv, restored_uv, atol=1e-6)
        exports.append({'file':filename.name, 'sha256':hashlib.sha256(filename.read_bytes()).hexdigest(),
            'mesh_count':len(objects), 'bounds_metres':expected.tolist(), 'uv_loops':uv_count,
            'roundtrip_bounds_error_metres':error})
        for obj in restored:
            bpy.data.objects.remove(obj, do_unlink=True)
    receipt = {'status':'FBX exported and reimported in Blender; Unreal import and cooking pending',
        'ready_for_carla_recording':False, 'revision':manifest['revision'], 'layout':manifest['layoutVersion'],
        'model_sha256':hashlib.sha256(args.model.read_bytes()).hexdigest(),
        'texture_sha256':hashlib.sha256(texture.read_bytes()).hexdigest(),
        'blender':bpy.app.version_string, 'axis_forward':'X', 'axis_up':'Z', 'units':'metres with FBX unit conversion',
        'source_car_bounds_metres':source_bounds.tolist(),
        'source_car_center_metres':source_bounds.mean(axis=0).tolist(), 'exports':exports}
    (out / 'export-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
