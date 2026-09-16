"""Blender GPU rendering of the supplied sponsor surfaces, with car occlusion.

Run using Blender --background --python-exit-code 1 --python this.py -- --run ...
The attached rear-left camera has a constant car-relative transform. One exact
projection suffices for the rigid body panels; native CARLA depth handles other
vehicles occluding them in each video frame. This is a presentation composite,
not an Unreal asset replacement.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
import numpy as np


p = argparse.ArgumentParser()
p.add_argument("--run")
p.add_argument("--out", required=True)
p.add_argument("--asset", required=True, help="Fresh live sponsor export")
p.add_argument("--qa-only", action="store_true")
p.add_argument("--shots", help="JSON list of camera poses for a directed cut")
args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
started = time.perf_counter()
asset, out = Path(args.asset).resolve(), Path(args.out).resolve()
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from flyhard.live_livery import verify_live_livery
manifest = verify_live_livery(asset, out)
bpy.ops.wm.open_mainfile(filepath=str(asset / "sponsored-mini.blend"))
scene = bpy.context.scene
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "CUDA"
prefs.get_devices()
devices = []
for device in prefs.devices:
    device.use = device.type == "CUDA"
    if device.use:
        devices.append(device.name)
assert any("A40" in d or "NVIDIA" in d for d in devices), devices
scene.render.engine = "CYCLES"
scene.cycles.device = "GPU"
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.film_transparent = True
scene.render.resolution_x = 1248
scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
logos = [bpy.data.objects[s["mesh"]] for s in manifest["sponsors"]]
car = [o for o in bpy.data.objects if o.type == "MESH" and o not in logos]
assert {o.name for o in car} == {"MINI_BODY", "SM_DoorGlass_Ext1_FL", "SM_DoorGlass_Ext1_FR", "SM_DoorL_Mini2021", "SM_DoorR_Mini2021", "SM_GlassExt_1", "SM_Lights_Mini2021"}
allowed = set(car + logos)
for obj in bpy.data.objects:
    obj.hide_render = obj not in allowed
    obj.hide_set(False)
vertices = [o.matrix_world @ v.co for o in car for v in o.data.vertices]
bounds = np.array([list(v) for v in vertices])
minimum, maximum = bounds.min(axis=0), bounds.max(axis=0)
offset = np.zeros(3)
config = None
if args.run:
    config = json.loads((Path(args.run) / "config.json").read_text())
    native_center = np.asarray(config["vehicle_bounds"]["location"]) * [1, -1, 1]
    offset = native_center - (minimum + maximum) / 2
# Transform the entire asset together; per-logo scale/rotation and UVs remain intact.
root = bpy.data.objects.new("Recorded vehicle frame", None)
scene.collection.objects.link(root)
for obj in car + logos:
    world = obj.matrix_world.copy()
    obj.parent = root
    obj.matrix_world = world
root.location = offset
bpy.context.view_layer.update()

camera_data = bpy.data.cameras.new("CARLA matched camera")
camera = bpy.data.objects.new("CARLA matched camera", camera_data)
scene.collection.objects.link(camera); camera.hide_render = False
scene.camera = camera
camera_data.type = "PERSP"
camera_data.sensor_fit = "HORIZONTAL"
fov = config["fov_degrees"] if config is not None else 75
camera_data.angle = math.radians(fov)
camera_data.clip_start = .05
camera_data.clip_end = 1000


def set_camera(relative):
    source = np.asarray(relative)
    reflect = np.diag([1, -1, 1])
    rotation = reflect @ source[:3, :3]
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack([rotation[:, 1], rotation[:, 2], -rotation[:, 0]])
    matrix[:3, 3] = reflect @ source[:3, 3]
    camera.matrix_world = Matrix(matrix.tolist())
    bpy.context.view_layer.update()


def look_from(position, target):
    camera.location = position
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()


for name, position, energy, size in [("Key", (-3, 4, 7), 1000, 5), ("Fill", (2, -3, 5), 650, 4), ("Rear", (-4, -2, 4), 600, 3)]:
    data = bpy.data.lights.new(name, "AREA"); data.energy = energy; data.shape = "DISK"; data.size = size
    light = bpy.data.objects.new(name, data); scene.collection.objects.link(light)
    light.location = position
    light.rotation_euler = (Vector([0, 0, .8]) - light.location).to_track_quat("-Z", "Y").to_euler()
world = bpy.data.worlds.new("Neutral world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (.4, .4, .4, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = .3
scene.world = world
for label, position in ([] if args.shots else [("left-door", (-3.6, 5.3, 2.3)), ("rear", (-5.8, 1.0, 2.5))]):
    look_from(position, [0, 0, .8])
    scene.render.filepath = str(out / (label + ".png"))
    bpy.ops.render.render(write_still=True)

if not args.qa_only:
    assert config is not None
    def render_projection(relative, fov, destination):
        destination.mkdir(parents=True, exist_ok=True)
        set_camera(relative)
        camera_data.angle = math.radians(fov)
        # A full-car match frame is retained to inspect camera/origin alignment.
        if not args.shots:
            scene.render.filepath = str(destination / "camera-match.png")
            bpy.ops.render.render(write_still=True)
        holdout = bpy.data.materials.new("Vehicle depth holdout")
        holdout.use_nodes = True
        nodes = holdout.node_tree.nodes; nodes.clear()
        shader = nodes.new("ShaderNodeHoldout"); output = nodes.new("ShaderNodeOutputMaterial")
        holdout.node_tree.links.new(shader.outputs[0], output.inputs["Surface"])
        for obj in car:
            obj.data.materials.clear(); obj.data.materials.append(holdout)
            obj.visible_shadow = False
        scene.cycles.use_denoising = False
        scene.cycles.samples = 16 if args.shots else 32
        scene.render.filepath = str(destination / "sponsor-layer.png")
        bpy.ops.render.render(write_still=True)
        # Raycast the unchanged supplied surfaces for per-pixel depth in metres.
        points, faces = [], []
        for obj in logos:
            base = len(points)
            points.extend([obj.matrix_world @ v.co for v in obj.data.vertices])
            faces.extend([tuple(base + i for i in poly.vertices) for poly in obj.data.polygons])
        tree = BVHTree.FromPolygons(points, faces)
        rendered = bpy.data.images.load(str(destination / "sponsor-layer.png"), check_existing=False)
        pixels = np.array(rendered.pixels[:], dtype=np.float32).reshape(960, 1248, 4)[::-1]
        depth = np.full((960, 1248), np.inf, dtype=np.float32)
        origin = camera.matrix_world.translation
        rotation = camera.matrix_world.to_3x3()
        forward = rotation @ Vector([0, 0, -1])
        fx = 1248 / (2 * math.tan(math.radians(fov) / 2))
        for y, x in np.argwhere(pixels[:, :, 3] > .01):
            ray = rotation @ Vector([(x + .5 - 624) / fx, -(y + .5 - 480) / fx, -1])
            hit, _, _, _ = tree.ray_cast(origin, ray.normalized())
            if hit is not None:
                depth[y, x] = (hit - origin).dot(forward)
        np.save(destination / "sponsor-depth.npy", depth)

    if args.shots:
        shot_list = json.loads(Path(args.shots).read_text())
        for i, shot in enumerate(shot_list):
            render_projection(shot["relative_matrix"], shot["fov"], out / shot["key"])
            print(json.dumps({"sponsor_view": i + 1, "total": len(shot_list), "key": shot["key"]}), flush=True)
    else:
        render_projection(config["camera_relative_matrix"], fov, out)
metrics = {"revision": manifest["revision"], "layout": manifest["layoutVersion"], "surfaces": [s["mesh"] for s in manifest["sponsors"]],
           "source_blend_sha256": hashlib.sha256((asset / "sponsored-mini.blend").read_bytes()).hexdigest(),
           "source_bounds_blender_metres": [minimum.tolist(), maximum.tolist()],
           "vehicle_origin_translation_metres": offset.tolist(), "gpu_devices": devices,
           "camera_relative_matrix": config["camera_relative_matrix"] if config else None,
           "fov_degrees": fov,
           "method": "Supplied textured surfaces, rendered with original car as depth holdout; native camera depth used by video compositor.",
           "wall_seconds": time.perf_counter() - started}
(out / "metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics), flush=True)
