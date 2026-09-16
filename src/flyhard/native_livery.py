"""Rigid native CARLA sponsor accessories, imported from the live Blender model."""
import hashlib
import json
from pathlib import Path

import numpy as np


def attachment_offset(source_bounds, vehicle_center):
    """Align Blender's car centre to CARLA's local vehicle bounding-box centre.

    Imported FBX vertices already use Unreal's centimetres and left-handed Y.
    CARLA's Python transform accepts metres, so this offset stays in metres.
    """
    bounds = np.asarray(source_bounds, dtype=float)
    center = np.asarray(vehicle_center, dtype=float)
    if bounds.shape != (2, 3) or center.shape != (3,):
        raise ValueError('Expected two 3D bounds and one 3D vehicle centre')
    if not np.isfinite(bounds).all() or not np.isfinite(center).all() or (bounds[1] < bounds[0]).any():
        raise ValueError('Invalid car bounds')
    return center - bounds.mean(axis=0) * [1, -1, 1]


def verify_import(asset, receipt_path):
    """Reject native geometry/artwork from a different live export."""
    asset = Path(asset)
    manifest = json.loads((asset / 'manifest.json').read_text())
    receipt = json.loads(Path(receipt_path).read_text())
    hashes = json.loads((asset / 'sha256.json').read_text())
    if (receipt['revision'], receipt['layout']) != (manifest['revision'], manifest['layoutVersion']):
        raise RuntimeError('Native import uses a different sponsor revision or layout')
    # A fresh .blend save includes volatile metadata. The equivalent embedded
    # GLB is deterministic and covers geometry, materials, UVs and artwork.
    if receipt['source_model_glb_sha256'] != hashes['sponsored-mini.glb']:
        raise RuntimeError('Native import uses a different car model')
    meshes = receipt['native_meshes']
    paid = {entry['slot_id']: entry for entry in meshes if entry['slot_id']}
    if len(meshes) != len(manifest['sponsors']) + 1 or len(paid) != len(manifest['sponsors']):
        raise RuntimeError('Native frame or paid surfaces are missing or duplicated')
    for sponsor in manifest['sponsors']:
        mesh = paid.get(sponsor['slotId'])
        texture = asset / sponsor['texture']
        if mesh is None or mesh['source_texture_sha256'] != hashlib.sha256(texture.read_bytes()).hexdigest():
            raise RuntimeError('Native artwork differs from the selected live snapshot')
    for mesh in meshes:
        if not mesh['mesh_path'].startswith(receipt['native_asset_directory'] + '/'):
            raise RuntimeError('Native mesh lies outside the verified import directory')
        if mesh['bounds_error_cm'] > 0.1:
            raise RuntimeError('Native mesh failed its coordinate conversion check')
    return receipt


def attach_livery(world, vehicle, asset, receipt_path):
    """Attach imported, collision-free geometry; the caller runs live preflight.

    This works in the CARLA editor and in a package containing the same assets.
    It requires the native StaticMeshFactory patch, never simulated prop mass.
    """
    import carla
    receipt = verify_import(asset, receipt_path)
    blueprint = world.get_blueprint_library().find('static.prop.mesh')
    if not blueprint.has_attribute('movable'):
        raise RuntimeError('CARLA server is missing the native movable-accessory patch')
    center = vehicle.bounding_box.location
    offset = attachment_offset(receipt['source_car_bounds_metres'], [center.x, center.y, center.z])
    transform = carla.Transform(carla.Location(*map(float, offset)))
    blueprint.set_attribute('movable', 'true')
    blueprint.set_attribute('mass', '0')
    blueprint.set_attribute('scale', '1')
    actors = []
    try:
        for mesh in receipt['native_meshes']:
            blueprint.set_attribute('mesh_path', mesh['mesh_path'])
            actor = world.spawn_actor(blueprint, transform, attach_to=vehicle,
                                     attachment_type=carla.AttachmentType.Rigid)
            actors.append(actor)
            actor.set_simulate_physics(False)
            actor.set_collisions(False)
            extent = actor.bounding_box.extent
            if max(extent.x, extent.y, extent.z) < 1e-4:
                raise RuntimeError('CARLA spawned an empty native mesh: ' + mesh['mesh_path'])
    except BaseException:
        for actor in reversed(actors):
            actor.destroy()
        raise
    return actors, offset


def attachment_errors(vehicle, actors, offset):
    inverse = np.asarray(vehicle.get_transform().get_inverse_matrix())
    expected = np.eye(4)
    expected[:3, 3] = offset
    errors = []
    for actor in actors:
        relative = inverse @ np.asarray(actor.get_transform().get_matrix())
        errors.append({'actor_id': actor.id,
                       'position_error_metres': float(np.linalg.norm(relative[:3, 3] - offset)),
                       'rotation_matrix_error': float(np.max(np.abs(relative[:3, :3] - expected[:3, :3])))})
    return errors
