"""Export the freshly generated sponsor meshes and billboard for Unreal 4.26.

Run with Blender --background --python-exit-code 1 --python ... -- --asset DIR
--output DIR. This produces interchange files; native cooking is a later gate.
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bounds(objects):
    points = np.array([list(o.matrix_world @ v.co) for o in objects for v in o.data.vertices])
    return np.array([points.min(0), points.max(0)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    asset, out = args.asset.resolve(), args.output.resolve()
    if out.exists():
        raise RuntimeError('Use a new output directory to preserve prior evidence')
    manifest = verify_live_livery(asset, out)
    model = asset / 'sponsored-mini.blend'
    bpy.ops.wm.open_mainfile(filepath=str(model))
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0
    frame = [o for o in bpy.data.objects if o.type == 'MESH' and o.get('role') == 'billboard_structure']
    if len(frame) != 17:
        raise RuntimeError(f'Expected the approved 17-part billboard, found {len(frame)}')
    groups = [('SM_BillboardFrame', frame, None)]
    for sponsor in manifest['sponsors']:
        objects = [o for o in bpy.data.objects if o.type == 'MESH'
                   and o.get('slot_id') == sponsor['slotId'] and o.get('role') == 'logo_surface']
        if len(objects) != 1 or objects[0].name != sponsor['mesh']:
            raise RuntimeError(f'Sponsor mesh does not match the manifest: {sponsor["slotId"]}')
        texture = out / (sponsor['slotId'] + '.png')
        shutil.copyfile(asset / sponsor['texture'], texture)
        for material in objects[0].data.materials:
            material.name = 'M_' + sponsor['slotId'].replace('-', '')
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    node.image.filepath = str(texture)
        groups.append(('SM_' + sponsor['slotId'].replace('-', ''), objects, sponsor))
    exports = []
    for name, objects, sponsor in groups:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            for modifier in list(obj.modifiers):
                bpy.ops.object.modifier_apply(modifier=modifier.name)
        expected = bounds(objects)
        original_uvs = [np.array([tuple(x.uv) for x in o.data.uv_layers.active.data])
                         if o.data.uv_layers.active else None for o in objects]
        file = out / (name + '.fbx')
        bpy.ops.export_scene.fbx(filepath=str(file), use_selection=True,
            object_types={'MESH'}, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
            axis_forward='X', axis_up='Z', bake_anim=False, add_leaf_bones=False,
            mesh_smooth_type='FACE', use_mesh_modifiers=True, path_mode='COPY', embed_textures=True)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.import_scene.fbx(filepath=str(file), use_anim=False)
        restored = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        error = float(np.max(np.abs(bounds(restored) - expected)))
        if len(restored) != len(objects) or error >= 1e-5:
            raise RuntimeError(f'FBX changed geometry: {name}, bounds error {error}')
        if sponsor:
            restored_uv = np.array([tuple(x.uv) for x in restored[0].data.uv_layers.active.data])
            if not np.allclose(original_uvs[0], restored_uv, atol=1e-6):
                raise RuntimeError(f'FBX changed artwork UVs: {name}')
        exports.append({'name': name, 'file': file.name, 'sha256': sha(file),
                        'slot_id': sponsor['slotId'] if sponsor else None,
                        'texture': sponsor['slotId'] + '.png' if sponsor else None,
                        'texture_sha256': sha(out / (sponsor['slotId'] + '.png')) if sponsor else None,
                        'mesh_count': len(objects), 'bounds_metres': expected.tolist(),
                        'roundtrip_bounds_error_metres': error})
        for obj in restored:
            bpy.data.objects.remove(obj, do_unlink=True)
    car_bounds = np.load(asset / 'render-panels.npz')['car_bounds']
    receipt = {'status': 'interchange_verified; Unreal import and cooking pending',
               'ready_for_carla_recording': False, 'revision': manifest['revision'],
               'layout': manifest['layoutVersion'], 'source_model_sha256': sha(model),
               'source_model_glb_sha256': sha(asset / 'sponsored-mini.glb'),
               'source_car_bounds_metres': car_bounds.tolist(), 'exports': exports}
    (out / 'export-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
