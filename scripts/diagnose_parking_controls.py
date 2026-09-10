#!/usr/bin/env python3
"""Geometric-teacher/body diagnostic. This is explicitly not learned parking."""
import argparse,json,time
from pathlib import Path
import numpy as np
from flyhard.parking import cases,motor_requests
from flyhard.parking_teacher import target
from flyhard.parking_rig import make_parking_rig
from flyhard.parking_world import ParkingWorld,DT
p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
rig=make_parking_rig();rig.prepare_controls();env=ParkingWorld();rows=[];started=time.monotonic()
try:
 state=env.start(cases('train',1)[0]);hold=0
 for index in range(900):
  request=target(state,env.case,rig.parking.selector.value)
  if request is None:request=np.zeros(2)
  measured=env.apply_measured(rig)
  desired=motor_requests(*request,state[3],rig.parking.measured['gear'])
  for _ in range(round(DT/rig.command_period)):
   command=desired.copy();command[0]=np.clip(request[0]*1.07,-.5,.5)
   rig.step_drive(rig.diagnostic_drive_action(*command))
  env.world.tick();state=env.state();metrics=env.metrics(state)
  row={'time':(index+1)*DT,'state':state.tolist(),'request':request.tolist(),'applied':measured,**metrics}
  rows.append(row);hold=hold+1 if metrics['pose_passed'] and abs(state[3])<.12 else 0
  if index%40==0:print(json.dumps(row),flush=True)
  if metrics['collision'] or hold>=10:break
 result={'claim':'Geometric teacher and physical-body diagnostic; no learned policy','success':hold>=10,
         'wall_seconds':time.monotonic()-started,'final':rows[-1]}
 (out/'frames.json').write_text(json.dumps(rows)+'\n');(out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
finally:env.close()
