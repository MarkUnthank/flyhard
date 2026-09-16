#!/usr/bin/env python3
"""Record one genuine learned parking attempt and its synchronized causal traces."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time
import numpy as np
import torch
from evaluate_parking import run_episode
from train_parking import load_policy,sha
from flyhard.parking import ParkingCase
from flyhard.parking_rig import make_parking_rig
from flyhard.parking_world import ParkingWorld
from flyhard.live_livery import verify_live_livery


def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--data',required=True)
    p.add_argument('--out',required=True);p.add_argument('--asset',required=True)
    p.add_argument('--seconds',type=float,default=30);p.add_argument('--case-index',type=int,default=0)
    p.add_argument('--split',choices=['train','validation'],default='validation')
    p.add_argument('--mask-selector',action='store_true')
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    manifest=verify_live_livery(args.asset,out);torch.set_num_threads(4)
    policy,saved=load_policy(args.checkpoint)
    case=ParkingCase(**json.loads((Path(args.data)/'cases.json').read_text())[args.split][args.case_index])
    rig=make_parking_rig();rig.prepare_controls();env=ParkingWorld();started=time.monotonic()
    config={'fps':20,'scenario':'parallel parking','case':asdict(case),'checkpoint_sha256':sha(args.checkpoint),
            'policy_hz':4,'measured_control_hz':20,'action_hold_seconds':.25,
            'selector_sensory_masked':args.mask_selector,
            'checkpoint_step':saved['step'],'sponsor_revision':manifest['revision'],'sponsor_layout':manifest['layoutVersion'],
            'claim':'One learned parking attempt from structured relative geometry; this is not the 50-trial benchmark.',
            'motion':'Only measured passive wheel, pedals and selector drive CARLA; fixed IK and velocity regulator.',
            'native_integration':'CARLA vehicle geometry; sponsor surfaces composited during presentation.'}
    def ready(env):
        box=env.ego.bounding_box
        config['vehicle_bounds']={'location':[box.location.x,box.location.y,box.location.z],
                                  'extent':[box.extent.x,box.extent.y,box.extent.z]}
        config['obstacles']=[{'matrix':a.get_transform().get_matrix(),'type':a.type_id} for a in env.actors if a.type_id.startswith('vehicle.') and a.id!=env.ego.id]
        config['origin']=env.origin.tolist();config['scene_yaw']=env.yaw
        env.client.start_recorder(str((out/'world-recorder.log').resolve()),True)
    try:
        result,rows,poses,activity=run_episode(env,rig,policy,case,args.seconds,True,ready,mask_selector=args.mask_selector)
        env.client.stop_recorder()
        (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
        (out/'frames.json').write_text(json.dumps(rows)+'\n')
        np.savez_compressed(out/'body-trace.npz',**{key:np.array([p[key] for p in poses]) for key in ['qpos','qvel','ctrl','time']})
        np.savez_compressed(out/'neural-trace.npz',activity=np.asarray(activity),time=np.array([r['time']-.05 for r in rows]))
        result['wall_seconds']=time.monotonic()-started
        (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    finally:
        env.client.stop_recorder();env.close()


if __name__=='__main__':main()
