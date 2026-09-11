#!/usr/bin/env python3
"""Check horn mechanics and a disconnected-foot intervention before training."""
import argparse,json,time
from pathlib import Path
import numpy as np
from flyhard.horn_rig import make_horn_rig


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();rig=make_horn_rig();rig.prepare_controls();rows=[]
    for attached in [True,False]:
        rig.reset(grip=attached)
        for target in [0.,.95,0.,.95,0.]:
            action=rig.horn.diagnostic_action(target);measurements=[]
            for _ in range(round(.8 / rig.command_period)):
                rig.step_horn(action);measurements.append(rig.horn.value)
            err=float(np.max(np.abs(np.asarray(measurements)[-20:]-(target if attached else 0.))))
            row={'attached':attached,'target':target,'measured':measurements[-1],
                 'hold_error':err,'pressed':rig.horn.pressed,'passed':err<(.15 if attached else .02)}
            rows.append(row);print(json.dumps(row),flush=True)
    result={'passed':all(r['passed'] for r in rows),'trials':rows,
            'ik_max_error_mm':rig.horn.ik_max_error_mm,'wall_seconds':time.monotonic()-started,
            'physics_timestep':rig.timestep,'motor_period':rig.command_period,
            'horn_has_actuator':False,'coupling':'Engineered forefoot point grip',
            'beep_source':'Measured passive button travel >= 55%'}
    (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
    np.savez_compressed(out/'ik-teacher.npz',values=rig.horn.ik_values,
                        actions=rig.horn.ik_actions,neutral=rig.horn.neutral_actions)
    print(json.dumps(result),flush=True);assert result['passed']


if __name__=='__main__':main()
