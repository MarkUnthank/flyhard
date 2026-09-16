"""Build an editable taxi-roof concept from a freshly verified live livery.

Blender --background --python scripts/build_taxi_billboard.py -- --asset DIR --output DIR
The production snapshot stays immutable. Exports a derived Blender/GLB and inventory.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from flyhard.live_livery import verify_live_livery
parser = argparse.ArgumentParser()
parser.add_argument('--asset', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
if not bpy.app.background:
    raise RuntimeError('Run in background mode to protect open Blender scenes')
asset, out = args.asset.resolve(), args.output.resolve()
if (out / 'taxi-billboard.blend').exists():
    raise RuntimeError('Choose a new output directory; do not overwrite a reviewed model')
manifest = verify_live_livery(asset, out)
bpy.ops.wm.open_mainfile(filepath=str(asset / 'sponsored-mini.blend'))
inv = json.loads((asset / 'inventory.json').read_text())
slot = next(s for s in inv['slots'] if s['id'] == 'ad-59')
old = bpy.data.objects[slot['panel']]
material = old.data.materials[0]
group = old.parent
panel_name = old.name
bpy.data.objects.remove(old, do_unlink=True)
for obj in list(bpy.data.objects):
    if obj.get('role') == 'billboard_structure':
        bpy.data.objects.remove(obj, do_unlink=True)
group['title'] = 'roof billboard · both sides'
collection = bpy.data.collections.new('TAXI BILLBOARD • frame and mounts')
bpy.context.scene.collection.children.link(collection)

def mat(name, color, metallic=0, roughness=.4):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metallic
    p.inputs['Roughness'].default_value = roughness
    return m
frame = mat('Billboard • charcoal powder-coated aluminium', (.023,.031,.026), .55, .32)
rubber = mat('Mounts • rubber roof pads', (.018,.022,.019), 0, .8)
backing = mat('Billboard • warm white face backing', (.92,.93,.89), 0, .42)

def box(name, center, size, material, bevel=.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object; obj.name = name; obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for c in list(obj.users_collection): c.objects.unlink(obj)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    if bevel:
        mod=obj.modifiers.new('Soft manufactured edges','BEVEL'); mod.width=bevel;mod.segments=3
        obj.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    obj['role']='billboard_structure'
    return obj

vertices, polygons = [], []
for obj in bpy.data.objects:
    if obj.type != 'MESH' or obj.get('slot_id'): continue
    start = len(vertices)
    vertices.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
    polygons.extend(tuple(start+i for i in poly.vertices) for poly in obj.data.polygons)
roof = BVHTree.FromPolygons(vertices, polygons)
scale = .85
cx,cz=-.35,1.84+.24*scale
width,height,depth=1.65*scale,.48*scale,.14*scale
for x in [cx-.55*scale,cx+.55*scale]:
    hit = roof.ray_cast(Vector((x,0,3)), Vector((0,0,-1)))[0]
    if hit is None: raise RuntimeError('Missing roof mount contact')
    z = hit.z
    box('Roof mounting pad', (x,0,z+.012), (.24,.50,.045), rubber,.018)
    box('Roof mounting foot', (x,0,z+.06), (.14,.30,.055), frame)
    bottom, top = z+.087, cz-height/2+.015
    box('Upright bracket', (x,0,(bottom+top)/2), (.075,.10,top-bottom), frame,.01)
box('Billboard enclosed core',(cx,0,cz),(width,.115*scale,height),frame)
for side in [-1,1]:
    y=side*depth/2
    box('White display backing',(cx,y,cz),(width-.052*scale,.008*scale,height-.052*scale),backing,.006*scale)
    for z in [cz-height/2,cz+height/2]:
        box('Horizontal bezel',(cx,y,z),(width+.036*scale,.038*scale,.036*scale),frame,.009*scale)
    for x in [cx-width/2,cx+width/2]:
        box('End bezel',(x,y,cz),(.036*scale,.038*scale,height),frame,.009*scale)
# One mesh, two outward-facing quads: one slot, one material, readable on both sides.
w,h=width-.058*scale,height-.058*scale
verts=[]; faces=[]
for side in [1,-1]:
    u=Vector((-side,0,0)); v=Vector((0,0,1)); center=Vector((cx,side*.079*scale,cz))
    start=len(verts)
    verts.extend([center+u*a*w/2+v*b*h/2 for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]])
    faces.append(tuple(start+i for i in range(4)))
mesh=bpy.data.meshes.new('Billboard • linked two-face advertising mesh')
mesh.from_pydata(verts,[],faces);mesh.update()
panel=bpy.data.objects.new(panel_name,mesh);bpy.context.scene.collection.objects.link(panel)
panel.parent=group;panel['slot_id']='ad-59';panel['role']='logo_surface'
panel['sponsor_brand']=next(s['brand'] for s in manifest['sponsors'] if s['slotId']=='ad-59')
panel['livery_revision']=manifest['revision'];panel['display_faces']=2
mesh.materials.append(material)
image=next(n.image for n in material.node_tree.nodes if n.type=='TEX_IMAGE')
# Fit existing roof artwork without stretching. Only empty top/bottom margins are cropped.
vspan=(image.size[0]/image.size[1])/(w/h)
uv=mesh.uv_layers.new(name='UVMap')
coords=[(0,.5-vspan/2),(1,.5-vspan/2),(1,.5+vspan/2),(0,.5+vspan/2)]
for face in mesh.polygons:
    for index,coord in zip(face.loop_indices,coords): uv.data[index].uv=coord
slot.update(name='roof billboard · both sides',face='left',width_m=w,height_m=h,
            position=[cx,cz,-.079*scale],display_faces=2)
group['width_m']=w;group['height_m']=h
inv['model_url']='./taxi-billboard.glb'
inv['concept']='Taxi billboard prototype; not the deployed production layout'
(out/'ad-spaces.json').write_text(json.dumps(inv,indent=2)+'\n')
scene=bpy.context.scene
scene['source_livery_revision']=manifest['revision']
scene['roof_placement']='ad-59, same paid owner, two billboard faces'
scene['asset_status']='Blender design preview; native CARLA import not yet performed'
bpy.ops.file.pack_all()
bpy.ops.export_scene.gltf(filepath=str(out/'taxi-billboard.glb'),export_format='GLB',export_extras=True,export_cameras=False,export_lights=False)
# Studio is kept editable in the blend but excluded from the GLB above.
floor_mat=mat('Studio • soft ivory',(.72,.75,.70),0,.85)
box('Studio floor',(0,0,-.06),(200,200,.1),floor_mat,0)
scene.world=bpy.data.worlds.new('Studio world')
scene.world.color=(.30,.30,.30)
for name,loc,power,size in [('Large softbox',(2,1,7),1800,5),('Rear rim',(-4,-3,5),1400,4),('Front fill',(4,-4,3),950,4)]:
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=loc
    obj.rotation_euler=(Vector((0,0,1))-obj.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(6.4,7,4.5))
cam=bpy.context.object;cam.name='Camera • front left billboard';cam.data.type='ORTHO';cam.data.ortho_scale=6.25
cam.rotation_euler=(Vector((0,0,1.10))-cam.location).to_track_quat('-Z','Y').to_euler();scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=1500;scene.render.resolution_y=1050;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
# Open directly onto the composed view in Blender.
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
bpy.ops.wm.save_as_mainfile(filepath=str(out/'taxi-billboard.blend'))
scene.render.filepath=str(out/'front-left.png');bpy.ops.render.render(write_still=True)
cam.location=(-6,-7,4.2);cam.rotation_euler=(Vector((0,0,1.10))-cam.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(out/'rear-right.png');bpy.ops.render.render(write_still=True)
(out/'design-receipt.json').write_text(json.dumps({'revision':manifest['revision'],'source_asset':str(asset),'slot':'ad-59','faces':2,'frame_metres':[width,depth,height],'artwork_metres':[w,h],'unchanged_sponsors':[s['slotId'] for s in manifest['sponsors'] if s['slotId']!='ad-59'],'status':'Blender concept; not deployed or imported into CARLA'},indent=2)+'\n')
