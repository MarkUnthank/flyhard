"""Render the current paid vehicle for social cards, with a transparent studio.

Blender --background --python-exit-code 1 --python scripts/render_social_car.py
  -- --asset DIR --output DIR
"""
import argparse
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from flyhard.live_livery import verify_live_livery

parser = argparse.ArgumentParser()
parser.add_argument('--asset', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
if not bpy.app.background:
    raise RuntimeError('Use background mode')
manifest = verify_live_livery(args.asset, args.output)
bpy.ops.wm.open_mainfile(filepath=str(args.asset / 'sponsored-mini.blend'))
scene = bpy.context.scene
scene.world = bpy.data.worlds.new('Social studio world')
scene.world.color = (.3, .3, .3)
bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.01))
bpy.context.object.name = 'Studio shadow catcher'
bpy.context.object.is_shadow_catcher = True
for name, loc, energy, size in [('Key', (2,1,7),1800,5), ('Rim',(-4,-3,5),1400,4), ('Fill',(4,-4,3),950,4)]:
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector((0,0,1))-obj.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(6.4, 7, 4.5))
camera = bpy.context.object
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 6.1
camera.rotation_euler = (Vector((0,0,1.1))-camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera = camera
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.film_transparent = True
scene.render.resolution_x = 1600
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'AgX'
scene.render.filepath = str(args.output / 'social-car.png')
bpy.ops.render.render(write_still=True)
