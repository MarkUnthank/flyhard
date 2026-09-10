"""Reproject the active panels onto the original CARLA body.

blender --background --python-exit-code 1 --python rebuild-layout.py -- /path/to/mini-livery
The base body is unchanged. Every panel and marker is generated from layout.json.
"""
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

if not bpy.app.background:
    raise RuntimeError("Run Blender in background mode")
root = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
layout = json.loads((root / "layout.json").read_text())
inventory = json.loads((root / "ad-spaces.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(root / "the-driving-fly-mini.blend"))
car = bpy.data.collections["MINI • original CARLA geometry"]
ads = bpy.data.collections["AD SPACES • individually addressable"]
vertices, polygons = [], []
for obj in car.all_objects:
    if obj.type != "MESH":
        continue
    start = len(vertices)
    vertices.extend([obj.matrix_world @ v.co for v in obj.data.vertices])
    polygons.extend([tuple(start + i for i in p.vertices) for p in obj.data.polygons])
bvh = BVHTree.FromPolygons(vertices, polygons)
basis = {
    "left": ((-1, 0, 0), (0, 0, 1)),
    "right": ((1, 0, 0), (0, 0, 1)),
    "front": ((0, 1, 0), (0, 0, 1)),
    "back": ((0, -1, 0), (0, 0, 1)),
    "top": ((0, 1, 0), (-1, 0, 0)),
}
report = []
font = next((f for f in bpy.data.fonts if "Barlow" in f.name), bpy.data.fonts.get("Bfont"))
cream = bpy.data.materials.new("Layout • lettering")
cream.diffuse_color = (1, .97, .85, 1)
cream.use_nodes = True
cream.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = cream.diffuse_color
for order, spec in enumerate(layout["slots"], 1):
    slot = next(s for s in inventory["slots"] if s["id"] == spec["id"])
    old = bpy.data.objects[slot["panel"]]
    panel_material = old.data.materials[0]
    for obj in list(bpy.data.objects):
        if obj.get("slot_id") == spec["id"]:
            bpy.data.objects.remove(obj, do_unlink=True)
    u_axis, v_axis = map(Vector, basis[spec["face"]])
    normal = u_axis.cross(v_axis)
    center = Vector(spec["center"])
    width, height = spec["width"], spec["height"]

    def project(x, y, offset=.004):
        point = center + u_axis * x + v_axis * y
        hit, hit_normal, _, _ = bvh.ray_cast(point + normal * 4, -normal, 8)
        if hit is None or hit_normal.dot(normal) < .08 or (hit - center).dot(normal) < -.60:
            return None
        return hit + hit_normal * offset

    def surface(name, coordinates, faces, role, material):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(coordinates, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        ads.objects.link(obj)
        obj.parent = group
        obj["slot_id"] = spec["id"]
        obj["role"] = role
        mesh.materials.append(material)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        return obj

    group = bpy.data.objects.new(f'{spec["id"].upper()}__{spec["name"].replace(" ", "_")}', None)
    ads.objects.link(group)
    for key, value in {"slot_id": spec["id"], "title": spec["name"], "status": "available",
                       "width_m": width, "height_m": height, "color": slot["color"]}.items():
        group[key] = value
    nx, ny = max(20, math.ceil(width / .025)), max(10, math.ceil(height / .025))
    points, uvs, indices = [], [], {}
    for j in range(ny + 1):
        for i in range(nx + 1):
            uv = (i / nx, j / ny)
            position = project((uv[0] - .5) * width, (uv[1] - .5) * height)
            if position is not None:
                indices[i, j] = len(points)
                points.append(position)
                uvs.append(uv)
    faces = []
    for j in range(ny):
        for i in range(nx):
            corners = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
            if all(c in indices for c in corners):
                faces.append(tuple(indices[c] for c in corners))
    coverage = len(faces) / (nx * ny)
    if coverage < .90:
        raise RuntimeError(f'{spec["id"]}: insufficient surface coverage ({coverage:.1%})')
    panel = surface(f'{spec["id"]}__logo_surface', points, faces, "logo_surface", panel_material)
    layer = panel.data.uv_layers.new(name="UVMap")
    for loop in panel.data.loops:
        layer.data[loop.index].uv = uvs[loop.vertex_index]

    # A projected dashed border remains legible on curved bodywork.
    border_points, border_faces = [], []
    thickness = min(.008, height * .03)
    rectangles = []
    for y in [-height * .485, height * .485]:
        count = max(5, round(width / .095))
        for i in range(count):
            x = -width * .48 + width * .96 * (i + .5) / count
            rectangles.append((x, y, width * .96 / count * .58, thickness))
    for x in [-width * .485, width * .485]:
        count = max(3, round(height / .07))
        for i in range(count):
            y = -height * .45 + height * .9 * (i + .5) / count
            rectangles.append((x, y, thickness, height * .9 / count * .58))
    for x, y, w, h in rectangles:
        corners = [project(x + dx * w / 2, y + dy * h / 2, .006)
                   for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]
        if all(p is not None for p in corners):
            start = len(border_points)
            border_points.extend(corners)
            border_faces.append(tuple(start + i for i in range(4)))
    surface(f'{spec["id"]}__border', border_points, border_faces, "availability_marker", cream)

    curve = bpy.data.curves.new(f'{spec["id"]}__lettering', "FONT")
    curve.body = "YOUR LOGO HERE" if width / height > 3 else "YOUR LOGO\nHERE"
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 1
    curve.space_line = .85
    curve.resolution_u = 4
    if font:
        curve.font = font
    text = bpy.data.objects.new(curve.name, curve)
    ads.objects.link(text)
    bpy.ops.object.select_all(action="DESELECT")
    text.select_set(True)
    bpy.context.view_layer.objects.active = text
    bpy.context.view_layer.update()
    scale = min(width * .77 / text.dimensions.x, height * .54 / text.dimensions.y)
    bpy.ops.object.convert(target="MESH")
    for vertex in text.data.vertices:
        x, y = vertex.co.x * scale, vertex.co.y * scale
        vertex.co = project(x, y, .007) or (center + u_axis * x + v_axis * y + normal * .007)
    text.parent = group
    text["slot_id"] = spec["id"]
    text["role"] = "availability_marker"
    text.data.materials.append(cream)
    point = project(0, 0)
    if point is None:
        raise RuntimeError(f'{spec["id"]}: missing center')
    slot.update(name=spec["name"], node=group.name, panel=panel.name, face=spec["face"],
                width_m=width, height_m=height, position=[point.x, point.z, -point.y], position_order=order)
    report.append({"id": spec["id"], "face": spec["face"], "width_m": width,
                   "height_m": height, "coverage": coverage})

active = {s["id"] for s in layout["slots"]}
for slot in inventory["slots"]:
    if slot["id"] not in active:
        slot["position_order"] = 100 + int(slot["id"][3:])
inventory["active_slot_ids"] = [s["id"] for s in layout["slots"]]
inventory["layout_version"] = layout["version"]
inventory["model_url"] = f'/model/the-driving-fly-mini-v{layout["version"]}.glb'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(root / "the-driving-fly-mini.blend"))
# Keep the web derivative compact while retaining sharp panel UVs.
for image in bpy.data.images:
    if image.type == "IMAGE" and max(image.size) > 2048:
        ratio = 2048 / max(image.size)
        image.scale(round(image.size[0] * ratio), round(image.size[1] * ratio))
bpy.ops.object.select_all(action="DESELECT")
for collection in [car, ads]:
    for obj in collection.all_objects:
        obj.hide_set(False)
        obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(root / "the-driving-fly-mini.glb"), export_format="GLB",
    use_selection=True, export_extras=True, export_cameras=False, export_lights=False,
    export_image_format="JPEG", export_image_quality=88,
    export_draco_mesh_compression_enable=True, export_draco_position_quantization=16,
    export_draco_texcoord_quantization=14)
(root / "ad-spaces.json").write_text(json.dumps(inventory, indent=2) + "\n")
(root / "layout-checks.json").write_text(json.dumps(report, indent=2) + "\n")
print("LAYOUT " + json.dumps(report))
