"""Build a frozen sponsor-only model from export-livery.mjs's public snapshot.

Run with Blender 4.2+ in background mode, never inside a working artist scene.
"""
import hashlib
import json
from pathlib import Path
import sys
import bpy

if not bpy.app.background:
    raise RuntimeError("Run with blender --background to protect your open scene")
bundle = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
manifest = json.loads((bundle / "livery.json").read_text())
checksums = json.loads((bundle / "sha256.json").read_text())
for name, digest in checksums.items():
    path = (bundle / name).resolve()
    if not path.is_relative_to(bundle):
        raise RuntimeError("Invalid asset path")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Changed or corrupt export asset: {name}")
for name in ["sponsored-mini.blend", "sponsored-mini.glb"]:
    if (bundle / name).exists():
        raise RuntimeError(f"Refusing to overwrite {name}; make a fresh export")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(bundle / "source-mini.glb"))
paid = {p["slotId"]: p for p in manifest["placements"]}
removed = []
for obj in list(bpy.data.objects):
    slot_id = obj.get("slot_id")
    if slot_id and (slot_id not in paid or obj.get("role") == "availability_marker"):
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)
for slot_id, placement in paid.items():
    panel = bpy.data.objects.get(placement["slot"]["panel"])
    if panel is None or panel.type != "MESH" or not panel.data.uv_layers:
        raise RuntimeError(f"Missing UV logo surface: {slot_id}")
    image = bpy.data.images.load(str(bundle / placement["texture"]), check_existing=False)
    image.colorspace_settings.name = "sRGB"
    image.alpha_mode = "STRAIGHT"
    image.pack()
    material = bpy.data.materials.new(f"Sponsor_{slot_id}")
    material.use_nodes = True
    material.surface_render_method = "DITHERED"
    nodes = material.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.55
    shader.inputs["Metallic"].default_value = 0.05
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    material.node_tree.links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
    panel.data.materials.clear()
    panel.data.materials.append(material)
    panel["sponsor_brand"] = placement["brand"]
    panel["sponsor_url"] = placement["url"]
    panel["livery_revision"] = manifest["revision"]
    panel["source_artwork"] = placement["textureUrl"]
bpy.context.scene["livery_revision"] = manifest["revision"]
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(bundle / "sponsored-mini.blend"))
bpy.ops.export_scene.gltf(
    filepath=str(bundle / "sponsored-mini.glb"), export_format="GLB",
    export_extras=True, export_cameras=False, export_lights=False,
)
report = {"revision": manifest["revision"], "sponsors": sorted(paid),
          "removed_objects": len(removed), "blender": bpy.app.version_string}
(bundle / "model-report.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
