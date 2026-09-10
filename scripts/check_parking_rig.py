#!/usr/bin/env python3
"""Verify parking mechanics before training; no learned capability claim."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from flyhard.parking_rig import make_parking_rig

p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
started=time.monotonic();rig=make_parking_rig();rig.prepare_controls()
rows=[]
for attached in [True,False]:
    rig.reset(grip=attached)
    for target in [[.3,.8,0,1],[-.3,0,.8,-1],[.3,.5,.5,1],[0,0,0,0]]:
        samples=[]
        action=rig.diagnostic_drive_action(*target)
        for _ in range(180):
            rig.step_drive(action)
            m=rig.parking.measured
            samples.append([rig.angle,m['throttle'],m['brake'],m['selector']])
        expected=np.array(target) if attached else np.zeros(4)
        errors=np.max(np.abs(np.array(samples)[-30:]-expected),axis=0)
        row={'coupling':attached,'target':target,'measured':samples[-1],
             'hold_errors':errors.tolist(),'passed':bool(np.all(errors<([.13,.14,.14,.14] if attached else [.02,.02,.02,.02])))}
        rows.append(row);print(json.dumps(row),flush=True)
        (out/'trials.json').write_text(json.dumps(rows,indent=2)+'\n')
result={'passed':all(x['passed'] for x in rows),'trials':len(rows),
        'wall_seconds':time.monotonic()-started,'timestep':rig.timestep,
        'ik_max_error_mm':{x.name:x.ik_max_error_mm for x in rig.parking.controls},
        'claim':'Offline IK mechanics diagnostic, not learned parking',
        'actuators_on_controls':False}
(out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
assert result['passed']
