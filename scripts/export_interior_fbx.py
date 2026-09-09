"""Run in Blender: --background --python this_file -- --assets PATH.

Export one rigid mesh per MuJoCo body, then reimport to check mesh geometry.
Blender conversion is checked here; Unreal import and cooking remain pending.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets',required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root = Path(args.assets).resolve(); out = root/'fbx'; out.mkdir(exist_ok=False)
    geometry = json.loads((root/'geometry.json').read_text())
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.
    exports = []; max_bounds_error = 0.
    for part in geometry['parts']:
        vertices,faces,indices,colors = [],[],[],[]
        for mi in part['mesh_indices']:
            mesh = geometry['meshes'][mi]; offset = len(vertices)
            vertices.extend(mesh['vertices_m'])
            faces.extend([[v+offset for v in face] for face in mesh['triangles']])
            indices.extend([len(colors)]*len(mesh['triangles'])); colors.append(mesh['rgba'])
        # Compiled MuJoCo meshes contain repeated triangles. Blender removes
        # duplicate faces on import; remove them explicitly and report it.
        source_triangle_count = len(faces)
        face_array = np.asarray(faces)
        _,keep = np.unique(np.sort(face_array,axis=1),axis=0,return_index=True)
        keep = np.sort(keep)
        duplicate_count = source_triangle_count-len(keep)
        ordered = np.sort(face_array[keep],axis=1)
        keep = keep[(ordered[:,0] != ordered[:,1]) & (ordered[:,1] != ordered[:,2])]
        faces = [faces[i] for i in keep]; indices = [indices[i] for i in keep]
        mesh = bpy.data.meshes.new(part['asset_name'])
        mesh.from_pydata(vertices,[],faces); mesh.update()
        obj = bpy.data.objects.new(part['asset_name'],mesh); bpy.context.collection.objects.link(obj)
        for number,rgba in enumerate(colors):
            material = bpy.data.materials.new(f'{part["asset_name"]}_{number}')
            material.diffuse_color = rgba; material.use_nodes = True
            shader = material.node_tree.nodes.get('Principled BSDF')
            shader.inputs['Base Color'].default_value = rgba
            shader.inputs['Roughness'].default_value = .65
            shader.inputs['Alpha'].default_value = rgba[3]
            mesh.materials.append(material)
        for polygon,material_index in zip(mesh.polygons,indices):
            polygon.material_index = material_index; polygon.use_smooth = True
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        path = out/f'{part["asset_name"]}.fbx'
        bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},
            apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',
            axis_forward='X',axis_up='Z',bake_anim=False,add_leaf_bones=False,
            mesh_smooth_type='FACE',use_mesh_modifiers=True,path_mode='AUTO')
        bounds = np.array([np.min(vertices,axis=0),np.max(vertices,axis=0)])
        bpy.data.objects.remove(obj,do_unlink=True)
        bpy.ops.import_scene.fbx(filepath=str(path),use_anim=False)
        imported = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        assert len(imported) == 1
        restored = imported[0]
        world_vertices = np.array([restored.matrix_world@v.co for v in restored.data.vertices])
        restored_bounds = np.array([world_vertices.min(axis=0),world_vertices.max(axis=0)])
        error = float(np.max(np.abs(bounds-restored_bounds))); max_bounds_error = max(max_bounds_error,error)
        assert error < 1e-5, f'FBX unit/axis roundtrip failed for {part["name"]}: {error}'
        assert len(restored.data.polygons) == len(faces), (part['name'],len(faces),len(restored.data.polygons))
        exports.append({'body_id':part['body_id'],'asset_name':part['asset_name'],
            'path':str(path.relative_to(root)),'bytes':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_triangles':source_triangle_count,'triangles':len(faces),
            'duplicate_faces_removed':duplicate_count,
            'degenerate_faces_removed':source_triangle_count-duplicate_count-len(faces),
            'bounds_roundtrip_error_m':error})
        bpy.data.objects.remove(restored,do_unlink=True)
    result = {'status':'exported_and_reimported_in_blender','unreal_tested':False,
        'blender':bpy.app.version_string,'axis_forward':'X','axis_up':'Z','source_units':'metres',
        'fbx_unit_scale_exported':True,'max_bounds_roundtrip_error_m':max_bounds_error,
        'geometry_sha256':hashlib.sha256((root/'geometry.json').read_bytes()).hexdigest(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'files':exports}
    (root/'fbx-export.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'status':result['status'],'files':len(exports),'max_bounds_roundtrip_error_m':max_bounds_error}),flush=True)


if __name__ == '__main__':main()
