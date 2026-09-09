#!/usr/bin/env python3
"""Prepare original segmented fly meshes and recorded poses for Unreal import.

This produces interchange geometry, not cooked CARLA assets. No Unreal or
CARLA vehicle assets are redistributed. Physics coordinates remain untouched.
Requires trimesh for sphere/capsule tessellation.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil

import mujoco as mj
import numpy as np
import trimesh

from flyhard.cockpit import WheelRig


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',default='runs/interior-replay-v1')
    parser.add_argument('--out',default='runs/interior-native-assets-v1')
    parser.add_argument('--scale',type=float,default=.16)
    parser.add_argument('--anchor',type=float,nargs=3,default=[.27,-.41,1.03])
    args = parser.parse_args()
    root,out = Path(args.run),Path(args.out); out.mkdir(parents=True,exist_ok=False)
    config = json.loads((root/'config.json').read_text())
    records = json.loads((root/'frames.json').read_text())
    with np.load(root/'body-trace.npz') as archive:body = {k:archive[k] for k in archive.files}
    rig = WheelRig(support_hand=config['support_hand']); model,data = rig.model,rig.data
    mj.mj_forward(model,data)
    visible = mj.MjvOption().geomgroup
    meshes,materials,parts = [],[],[]
    conversion_error = 0.
    for bid in range(1,model.nbody):
        mesh_indices = []
        for gid in np.flatnonzero(model.geom_bodyid == bid):
            if not visible[model.geom_group[gid]]:continue
            kind,size = model.geom_type[gid],model.geom_size[gid]
            if kind == mj.mjtGeom.mjGEOM_MESH:
                mid = model.geom_dataid[gid]
                va,vn = model.mesh_vertadr[mid],model.mesh_vertnum[mid]
                fa,fn = model.mesh_faceadr[mid],model.mesh_facenum[mid]
                vertices = model.mesh_vert[va:va+vn].copy()
                faces = model.mesh_face[fa:fa+fn].copy()
            else:
                if kind == mj.mjtGeom.mjGEOM_SPHERE:
                    mesh = trimesh.creation.icosphere(subdivisions=2,radius=size[0])
                elif kind == mj.mjtGeom.mjGEOM_CAPSULE:
                    mesh = trimesh.creation.capsule(height=2*size[1],radius=size[0],count=[8,12])
                else:raise ValueError(f'Unsupported visible primitive: {kind}')
                vertices,faces = mesh.vertices,mesh.faces
            geom_rotation = data.geom_xmat[gid].reshape(3,3)
            body_rotation = data.xmat[bid].reshape(3,3)
            world_vertices = vertices@geom_rotation.T+data.geom_xpos[gid]
            local_vertices = (world_vertices-data.xpos[bid])@body_rotation
            restored = local_vertices@body_rotation.T+data.xpos[bid]
            conversion_error = max(conversion_error,float(np.max(np.abs(restored-world_vertices))))
            mat_id = model.geom_matid[gid]
            rgba = model.mat_rgba[mat_id] if mat_id >= 0 else model.geom_rgba[gid]
            mesh_indices.append(len(meshes))
            meshes.append({'name':f'geom_{gid:03}','body_id':bid,
                'vertices_m':(local_vertices*args.scale).tolist(),'triangles':faces.tolist(),
                'rgba':rgba.tolist(),'source_geom_id':int(gid)})
        if mesh_indices:
            name = mj.mj_id2name(model,mj.mjtObj.mjOBJ_BODY,bid)
            parts.append({'body_id':bid,'name':name,'asset_name':'FH_'+name.replace('/','_'),
                'mesh_indices':mesh_indices,'parent_body_id':int(model.body_parentid[bid])})
    assert conversion_error < 1e-10
    (out/'geometry.json').write_text(json.dumps({'coordinates':'Right handed X forward, Y left, Z up; metres.',
        'parts':parts,'meshes':meshes},separators=(',',':')))
    mirror = np.diag([1.,-1.,1.]); anchor = np.asarray(args.anchor)
    poses = []
    for frame in records:
        bi = frame['body_index']
        data.qpos[:] = body['qpos'][bi]; data.qvel[:] = body['qvel'][bi]
        data.ctrl[:] = body['ctrl'][bi]; data.time = body['time'][bi]
        mj.mj_forward(model,data)
        transforms = []
        for part in parts:
            bid = part['body_id']; rotation = data.xmat[bid].reshape(3,3)
            position = mirror@(data.xpos[bid]-rig.center)*args.scale+anchor
            transforms.append({'body_id':bid,'position_car_m':position.tolist(),
                'rotation_car_matrix':(mirror@rotation@mirror).tolist(),
                'position_rig_m':(data.xpos[bid]*args.scale).tolist(),
                'rotation_rig_matrix':rotation.tolist()})
        poses.append({'index':frame['index'],'carla_frame':frame['frame'],'body_time':frame['body_time'],
            'body_index':bi,'parts':transforms})
    (out/'poses.json').write_text(json.dumps(poses,separators=(',',':')))
    distribution = importlib.metadata.distribution('flygym')
    license_file = next(f for f in distribution.files if str(f).endswith('/licenses/LICENSE'))
    shutil.copy2(distribution.locate_file(license_file),out/'LICENSE-FlyGym-Apache-2.0.txt')
    (out/'ATTRIBUTION.txt').write_text('Fly geometry: NeuroMechFly via FlyGym 2.1.0, Neuroengineering Laboratory, EPFL.\n'
        'https://github.com/NeLy-EPFL/flygym\nApache License 2.0; full license included.\n'
        'Modified by Flyhard: segmented body meshes exported from the compiled MuJoCo model, scaled for display; original colors retained.\n'
        'Wheel geometry: Flyhard project, MIT license. No CARLA vehicle or Unreal Engine assets included.\n')
    report = {'status':'interchange_assets_prepared','native_unreal_import_tested':False,
        'body_parts':len(parts),'visible_geometries':len(meshes),
        'vertices':sum(len(m['vertices_m']) for m in meshes),
        'triangles':sum(len(m['triangles']) for m in meshes),'pose_frames':len(poses),
        'max_mesh_body_transform_roundtrip_error_rig_units':conversion_error,
        'wheel_anchor_car_m':args.anchor,'metres_per_rig_unit':args.scale,
        'source_body_trace_sha256':sha(root/'body-trace.npz'),'source_frames_sha256':sha(root/'frames.json'),
        'geometry_sha256':sha(out/'geometry.json'),'poses_sha256':sha(out/'poses.json'),
        'script_sha256':sha(__file__),'flygym_version':importlib.metadata.version('flygym'),
        'mujoco_version':mj.__version__,'trimesh_version':trimesh.__version__,
        'pending':['Import FBX in CARLA-compatible Unreal 4.26 editor and verify axis/unit conversion.',
            'Disable mesh collision; cook assets for CARLA 0.9.16.',
            'Spawn movable display actors, disable actor physics, attach/update from recorded poses.',
            'Verify fly/wheel registration, transparency, lighting and frame synchronization in native CARLA.']}
    (out/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__ == '__main__':main()
