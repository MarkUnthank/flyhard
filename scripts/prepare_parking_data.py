#!/usr/bin/env python3
"""Freeze train/validation/held-out cases, then create training-only labels."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from flyhard.parking import cases,observation,REAR_TO_CENTER,collision
from flyhard.parking_teacher import plan,target

p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
splits={'train':cases('train',128),'validation':cases('validation',16),'heldout':cases('heldout',50)}
(out/'cases.json').write_text(json.dumps({k:[c.record() for c in v] for k,v in splits.items()},indent=2)+'\n')
started=time.monotonic();counts={}
for split in ['train','validation']:
    observations,targets,seeds=[],[],[];missing=0
    for case in splits[split]:
        rng=np.random.default_rng(case.seed)
        path=plan([case.approach_x-REAR_TO_CENTER,case.approach_y,case.approach_yaw,0],case)
        if path is None:missing+=1;continue
        points=path.waypoints()
        for waypoint in points[::2]:
            for _ in range(2):
                state=np.array([waypoint.x,waypoint.y,waypoint.yaw,waypoint.driving_direction*rng.uniform(0,1.2)])
                state[:3]+=rng.normal(0,[.065,.055,.025])
                selector=float(rng.choice([-1,0,1]))
                if collision(state,case):continue
                label=target(state,case,selector)
                if label is None:continue
                observations.append(observation(state,case,selector));targets.append(label);seeds.append(case.seed)
        # Dense stopping examples around the target, with varied residual speed.
        for _ in range(30):
            state=np.r_[[-REAR_TO_CENTER,0,0]+rng.normal(0,[.07,.07,.03]),rng.uniform(-.7,.7)]
            observations.append(observation(state,case,rng.choice([-1,0,1])))
            targets.append([0.,0.]);seeds.append(case.seed)
        print(json.dumps({'split':split,'case':case.seed,'rows':len(targets),'seconds':time.monotonic()-started}),flush=True)
    np.savez_compressed(out/(split+'.npz'),observations=np.asarray(observations,np.float32),
                        targets=np.asarray(targets,np.float32),case_seeds=np.asarray(seeds))
    counts[split]={'rows':len(targets),'planner_failed_cases':missing}
receipt={'cases_sha256':hashlib.sha256((out/'cases.json').read_bytes()).hexdigest(),
         'splits':counts,'heldout_cases':50,'heldout_labels_generated':False,
         'teacher':'rsplan 1.0.10, training only; no planner call or steering request at learned inference',
         'wall_seconds':time.monotonic()-started}
(out/'data-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
