#!/usr/bin/env python3
"""Audit native causal control logs and a fixed sample of saved policy decisions."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from flyhard.three_point import encode
from train_three_point import load_policy,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
    root=Path(a.run);spec=json.loads((root/'spec.json').read_text());report=json.loads((root/'metrics.json').read_text())
    assert spec['native']
    policy,_=load_policy(spec['checkpoint'],reset_core=spec['reset_core']);torch.set_num_threads(4)
    frames=0;checks=0;max_clock=0.;max_action=0.;max_control=0.
    for case in spec['cases']:
        trial=root/str(case['seed']);rows=json.loads((trial/'frames.json').read_text());body=np.load(trial/'body-trace.npz')
        assert len(body['qpos'])==len(rows)==len(body['time'])
        assert all(b['carla_frame']-a['carla_frame']==1 for a,b in zip(rows,rows[1:]))
        for i,row in enumerate(rows):
            max_clock=max(max_clock,abs(row['time']-row['body_time']),abs(body['time'][i]-row['body_time']))
            assert row['policy_decision']==(i%5==0)
            if i and not row['policy_decision']:
                assert row['requested_angle']==rows[i-1]['requested_angle']
                assert row['requested_signed_speed']==rows[i-1]['requested_signed_speed']
            if not i:continue
            previous=rows[i-1];m=previous['measured_after_tick'];c=row['applied_controls']
            for key in ['throttle','brake','selector']:
                max_control=max(max_control,abs(c[key]-m[key]))
            max_control=max(max_control,abs(c['steer']-np.clip(previous['wheel_after_tick']*1.7,-1,1)))
            assert c['gear']==m['gear'] and c['reverse']==(m['gear']<0)
        decisions=[r for r in rows if r['policy_decision']]
        sample=[decisions[i] for i in np.linspace(0,len(decisions)-1,min(10,len(decisions)),dtype=int)]
        # Recompute individually, matching the recorded batch size of one.
        for row in sample:
            with torch.no_grad():action=policy(torch.tensor(encode(row['decision_observation']),device='cuda'))[0].cpu().numpy()
            max_action=max(max_action,float(np.max(np.abs(action-[row['requested_angle'],row['requested_signed_speed']]))));checks+=1
        frames+=len(rows)
    assert max_clock<1e-5 and max_control<1e-6 and max_action<1e-5
    result={'status':'verified','native_frames':frames,'recomputed_decisions':checks,
        'max_body_clock_error_seconds':max_clock,'max_applied_control_error':max_control,
        'max_recomputed_action_error':max_action,'checkpoint_sha256':sha(spec['checkpoint']),
        'source_sha256':sha(__file__),'behavioural_successes':report['successes'],
        'claim':'Control causality audit, not a behavioural pass'}
    (root/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
