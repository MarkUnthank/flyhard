#!/usr/bin/env python3
"""Freeze and physically validate the combined steering and horn controller."""
import argparse, concurrent.futures, json, multiprocessing, time
from pathlib import Path
import numpy as np
import torch
from flyhard.driving_horn import Case, cases, episode
from train_driving_horn import load
from train_horn import sha

RIG=None


def initialize():
    global RIG
    from flyhard.horn_rig import make_horn_rig
    torch.set_num_threads(1);RIG=make_horn_rig()


def physical(item):
    case,commands,condition=item;rig=RIG;rig.reset(grip=condition!='disconnected')
    _,_,truth,wheel=episode(Case(**case));press=[];angles=[];travel=[]
    for i in range(len(commands)*6):
        for _ in range(5):rig.step_controls(commands[i//6])
        press.append(rig.horn.pressed);angles.append(rig.angle);travel.append(rig.horn.value)
    press=np.array(press);expected=np.repeat(truth,6);times=(np.arange(len(press))+1)/60
    onset=np.flatnonzero(press&~np.r_[False,press[:-1]])
    expected_onset=np.flatnonzero(expected&~np.r_[False,expected[:-1]])
    timings=[float(times[np.flatnonzero(press & (times>=times[index]) & (times<=times[index]+.8))[0]]-times[index])
             if np.any(press & (times>=times[index]) & (times<=times[index]+.8)) else None for index in expected_onset]
    wheel_error=np.abs(np.array(angles)-np.repeat(wheel,6))
    allowed=np.zeros(len(press),bool)
    for index in np.flatnonzero(expected):allowed[index:min(index+31,len(press))]=True
    coverage=float(np.mean(press[expected])) if expected.any() else None
    horn_pass=(not press.any()) if not expected.any() else (
        len(onset)==len(expected_onset) and all(t is not None for t in timings)
        and coverage>.65 and not np.any(press&~allowed))
    return {'case':case,'condition':condition,'beep_count':int(len(onset)),
            'beep_onsets':times[onset].tolist(),'expected_beeps':int(len(expected_onset)),
            'timings':timings,'hold_coverage':coverage,'horn_passed':bool(horn_pass),
            'wheel_mean_error_rad':float(wheel_error[60:].mean()),
            'wheel_95_error_rad':float(np.quantile(wheel_error[60:],.95)),
            'all_quiet':bool(not press.any()),'maximum_travel':float(max(travel)),
            'times':times.tolist(),'pressed':press.tolist(),'button':travel,'wheel':angles}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkpoint',required=True);p.add_argument('--out',required=True)
    p.add_argument('--split',choices=['validation','test'],default='validation');p.add_argument('--per-kind',type=int,default=2)
    p.add_argument('--conditions',nargs='+',default=['learned','reset_core','disconnected']);p.add_argument('--workers',type=int,default=6)
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4)
    started=time.monotonic();items=cases(args.split,args.per_kind);x=np.concatenate([episode(c)[1] for c in items])
    (out/'plan.json').write_text(json.dumps({'checkpoint_sha256':sha(args.checkpoint),'split':args.split,
        'cases':[c.as_dict() for c in items],'conditions':args.conditions,'physics_hz':60000,'measurement_hz':60,
        'horn_contact':{'close_at_travel':.55,'release_below_travel':.45},
        'policy_hz':10,'motor_hz':300,'scope':'Structured-state inputs through physical wheel and button, not randomized CARLA traffic'},indent=2)+'\n')
    result={};learned=None
    for condition in args.conditions:
        if condition=='disconnected' and learned is not None:commands=learned
        else:
            model,_=load(args.checkpoint)
            if condition=='reset_core':
                with torch.no_grad():model.core.edge_gain.zero_();model.core.leak.zero_()
            chunks=[]
            with torch.no_grad():
                for i in range(0,len(x),40):chunks.append(model(torch.tensor(x[i:i+40],device='cuda')).cpu().numpy())
            commands=np.concatenate(chunks).reshape(len(items),-1,14)
            if condition=='learned':learned=commands.copy()
        np.savez_compressed(out/(condition+'-commands.npz'),commands=commands)
        rows=[]
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn'),initializer=initialize) as pool:
            for row in pool.map(physical,[(c.as_dict(),a,condition) for c,a in zip(items,commands)]):
                rows.append(row)
                (out/(condition+'-trials.json')).write_text(json.dumps(rows)+'\n')
                print(json.dumps({k:v for k,v in row.items() if k not in ['times','pressed','button','wheel']}),flush=True)
        result[condition]={kind:{'trials':len(group:=[r for r in rows if r['case']['kind']==kind]),
                                'horn_passed':sum(r['horn_passed'] for r in group),
                                'quiet':sum(r['all_quiet'] for r in group),
                                'wheel_mean_error':float(np.mean([r['wheel_mean_error_rad'] for r in group]))}
                           for kind in sorted({c.kind for c in items})}
        (out/'metrics.json').write_text(json.dumps({'results':result,'wall_seconds':time.monotonic()-started},indent=2)+'\n')
    print(json.dumps({'status':'complete','results':result,'wall_seconds':time.monotonic()-started}),flush=True)


if __name__=='__main__':main()
