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
car = [o for o in bpy.data.objects
       if o.type == 'MESH' and o not in logos and not o.get('slot_id')]
points = np.array([list(o.matrix_world @ v.co) for o in car for v in o.data.vertices])
arrays = {'car_bounds': np.array([points.min(0), points.max(0)])}
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
