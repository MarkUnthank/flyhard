#!/usr/bin/env python3
"""Audit saved trial/control clocks and replay a fixed sample of policy outputs."""
import argparse,json,math
from pathlib import Path
import numpy as np
import torch
from flyhard.parking import WHEEL_TO_CARLA,encode
from train_parking import load_policy,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--checkpoint',required=True);p.add_argument('--out',required=True);args=p.parse_args()
    root=Path(args.run);trials=json.loads((root/'trials.json').read_text());stats=json.loads((root/'metrics.json').read_text())
    assert len(trials)==50 and sha(args.checkpoint)==stats['checkpoint_sha256']
    policy,_=load_policy(args.checkpoint);checked=0;decisions=0;per_trial=[]
    for trial in trials:
        case=root/str(trial['seed']);rows=json.loads((case/'frames.json').read_text());body=np.load(case/'body-trace.npz')
        assert len(rows)==len(body['time'])==round(trial['time_seconds']*20)
        assert all(row['index']==i and row['camera']['frame']==row['carla_frame'] for i,row in enumerate(rows))
        assert all(abs(row['body_time']-row['time'])<1e-6 for row in rows)
        assert np.max(np.abs(body['time']-np.array([r['time'] for r in rows])))<1e-6
        assert all(b['carla_frame']-a['carla_frame']==1 for a,b in zip(rows,rows[1:]))
        for previous,current in zip(rows,rows[1:]):
            applied=current['applied_controls'];measured=previous['measured_controls']
            assert abs(applied['steer']-np.clip(previous['wheel_angle']*WHEEL_TO_CARLA,-1,1))<1e-6
            for name in ['throttle','brake','gear','selector']:assert abs(applied[name]-measured[name])<1e-6,(trial['seed'],name)
        signs=np.sign(np.array([r['state'][3] for r in rows]));signs[np.abs([r['state'][3] for r in rows])<=.12]=0
        moving=signs[signs!=0];changes=int(np.count_nonzero(np.diff(moving)))
        assert changes==trial['direction_changes']
        assert any(r['collision'] for r in rows)==trial['collision']
        assert abs(rows[-1]['position_error_m']-trial['position_error_m'])<1e-9
        assert abs(rows[-1]['yaw_error_deg']-trial['yaw_error_deg'])<1e-9
        assert bool(rows[-1]['inside_bay'])==trial['inside_bay']
        final_hold=0
        for row in reversed(rows):
            if not row['pose_passed'] or abs(row['state'][3])>=.12:break
            final_hold+=1
        assert trial['success']==bool(final_hold>=10 and not trial['collision'])
        decision_rows=[r for r in rows if r['policy_decision']]
        chosen=np.unique(np.linspace(0,len(decision_rows)-1,min(5,len(decision_rows)),dtype=int))
        for index in chosen:
            row=decision_rows[index]
            obs=np.array(row['decision_observation'],np.float32)
            if stats['selector_sensory_masked']:assert obs[4]==0
            with torch.no_grad():value=policy(torch.tensor(encode(obs),device='cuda'))[0].cpu().numpy()
            assert np.allclose(value,[row['requested_angle'],row['requested_signed_speed']],atol=1e-5,rtol=1e-5),(trial['seed'],row['index'])
            decisions+=1
        checked+=len(rows);per_trial.append({'seed':trial['seed'],'frames':len(rows),'sampled_model_replays':len(chosen),'controls_match_measured_body':True})
    receipt={'status':'passed','trials':50,'synchronized_frames_checked':checked,'model_output_replays':decisions,
             'control_latency':'Each CARLA tick uses the physical controls measured at its start; the saved body pose is the end of that tick.',
             'checkpoint_sha256':sha(args.checkpoint),'per_trial':per_trial}
    Path(args.out).write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='per_trial'}))


if __name__=='__main__':main()
