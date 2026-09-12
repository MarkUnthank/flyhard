"""Blender: export exact world-space sponsor triangles and UVs for raster replay."""
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

asset = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
manifest = json.loads((asset / 'manifest.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(asset / 'sponsored-mini.blend'))
logos = [bpy.data.objects[s['mesh']] for s in manifest['sponsors']]
car = [o for o in bpy.data.objects if o.type == 'MESH' and not o.get('slot_id')]
points = np.array([list(o.matrix_world @ v.co) for o in car for v in o.data.vertices])
arrays = {'car_bounds': np.array([points.min(0), points.max(0)])}
structure = [o for o in bpy.data.objects if o.type == 'MESH' and o.get('role') == 'billboard_structure']
structure_points, structure_colors = [], []
depsgraph = bpy.context.evaluated_depsgraph_get()
for original in structure:
    obj = original.evaluated_get(depsgraph)
    mesh = obj.to_mesh()
    mesh.calc_loop_triangles()
    for triangle in mesh.loop_triangles:
        material = mesh.materials[triangle.material_index] if mesh.materials else None
        color = list(material.diffuse_color) if material else [.12, .12, .12, 1]
        if material and material.use_nodes:
            principled = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if principled:
                color = list(principled.inputs['Base Color'].default_value)
        for vertex in triangle.vertices:
            structure_points.append(list(obj.matrix_world @ mesh.vertices[vertex].co))
            structure_colors.append(color)
    obj.to_mesh_clear()
arrays['structure_vertices'] = np.asarray(structure_points, dtype=np.float32).reshape(-1, 3)
arrays['structure_colors'] = np.asarray(structure_colors, dtype=np.float32).reshape(-1, 4)
arrays['structure_names'] = np.asarray([o.name for o in structure])
for sponsor in manifest['sponsors']:
    obj = bpy.data.objects[sponsor['mesh']]
    obj.data.calc_loop_triangles()
    points, uv = [], []
    for triangle in obj.data.loop_triangles:
        for vertex, loop in zip(triangle.vertices, triangle.loops):
            points.append(list(obj.matrix_world @ obj.data.vertices[vertex].co))
            uv.append(list(obj.data.uv_layers.active.data[loop].uv))
    arrays[sponsor['slotId'] + '_vertices'] = np.asarray(points, dtype=np.float32)
    arrays[sponsor['slotId'] + '_uv'] = np.asarray(uv, dtype=np.float32)
np.savez_compressed(asset / 'render-panels.npz', **arrays)
hashes = json.loads((asset / 'sha256.json').read_text())
hashes['render-panels.npz'] = hashlib.sha256((asset / 'render-panels.npz').read_bytes()).hexdigest()
(asset / 'sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
print(json.dumps({'sponsor_meshes': len(logos), 'revision': manifest['revision'], 'status': 'exported'}))
