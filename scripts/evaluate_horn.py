#!/usr/bin/env python3
"""Held-out horn timing through measured body-operated controls and interventions."""
import argparse,concurrent.futures,json,multiprocessing,time
from dataclasses import replace
from pathlib import Path
import numpy as np
import torch
from flyhard.horn import DT,HornCase,episode,make_cases,score
from train_horn import load_policy,sha

RIG=None


def init_worker():
    global RIG
    from flyhard.horn_rig import make_horn_rig
    torch.set_num_threads(1)
    RIG=make_horn_rig();RIG.prepare_controls()


def physical_trial(item):
    case_dict,commands,connected=item;case=HornCase(**case_dict);rig=RIG
    rig.reset(grip=connected);times=[];pressed=[];positions=[];wheel=[]
    for i in range(round(case.duration*60)):
        action=commands[min(i//6,len(commands)-1)]
        for _ in range(5):rig.step_horn(action)
        times.append((i+1)/60);pressed.append(rig.horn.pressed);positions.append(rig.horn.value);wheel.append(rig.angle)
        assert abs(rig.data.time-times[-1])<1e-8
    result=score(case,times,pressed)
    result.update(connected=connected,maximum_button_travel=float(max(positions)),
                  maximum_wheel_angle=float(max(map(abs,wheel))),all_quiet=not any(pressed),
                  times=times,button=positions,pressed=pressed)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True);p.add_argument('--out',required=True)
    p.add_argument('--graph',default='data/graph-traced-v1');p.add_argument('--split',choices=['validation','test'],default='test')
    p.add_argument('--per-kind',type=int,default=30);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--seconds',type=float,default=10.)
    p.add_argument('--batch',type=int,default=48);p.add_argument('--conditions',nargs='+',default=['learned','reset_core','disconnected'])
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=False);started=time.monotonic();torch.set_num_threads(4)
    cases=[replace(c,duration=args.seconds) for c in make_cases(args.split,args.per_kind)]
    assert all(c.duration>c.green_at+1.6 for c in cases), 'Trials must include the complete release window'
    episodes=[episode(c) for c in cases]
    x=np.concatenate([v[1] for v in episodes]);model,saved=load_policy(args.checkpoint,args.graph)
    plan={'checkpoint_sha256':sha(args.checkpoint),'split':args.split,'cases':[c.as_dict() for c in cases],
          'conditions':args.conditions,'gate':'At least 90% timely single-beep positives and at most 5% false-beep episodes in each negative family',
          'observations':'Synthetic structured traffic-state sequences; physical joint/button dynamics evaluated in MuJoCo',
          'timely_seconds':.8,'late_release_seconds':1.6,'press_threshold':.55,
          'no_outcome_selection':True,'motor_targets_hz':300,'measured_control_hz':60,'policy_hz':10,
          'checkpoint_step':saved['step'],
          'source_sha256':{p:sha(p) for p in [__file__,'src/flyhard/horn.py','src/flyhard/horn_rig.py','src/flyhard/cockpit.py']}}
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    learned_commands=None;results={}
    for condition in args.conditions:
        if condition not in {'learned','reset_core','disconnected'}:raise ValueError(condition)
        if condition=='disconnected' and learned_commands is not None:commands=learned_commands
        else:
            if condition=='reset_core':
                with torch.no_grad():model.core.edge_gain.zero_();model.core.leak.zero_()
            else:model,saved=load_policy(args.checkpoint,args.graph)
            chunks=[]
            with torch.no_grad():
                for i in range(0,len(x),args.batch):chunks.append(model(torch.tensor(x[i:i+args.batch],device='cuda')).cpu().numpy())
            commands=np.concatenate(chunks).reshape(len(cases),-1,7)
            if condition=='learned':learned_commands=commands.copy()
        np.savez_compressed(out/(condition+'-commands.npz'),commands=commands)
        rows=[]
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker) as pool:
            futures={pool.submit(physical_trial,(case.as_dict(),command,condition!='disconnected')):i for i,(case,command) in enumerate(zip(cases,commands))}
            for future in concurrent.futures.as_completed(futures):
                rows.append(future.result());rows.sort(key=lambda r:r['seed'])
                (out/(condition+'-trials.json')).write_text(json.dumps(rows,indent=2)+'\n')
                if len(rows)%10==0 or len(rows)==len(cases):print(json.dumps({'condition':condition,'completed':len(rows),'total':len(cases),'wall_seconds':time.monotonic()-started}),flush=True)
        by_kind={}
        for kind in sorted({c.kind for c in cases}):
            group=[r for r in rows if r['kind']==kind];lat=[r['reaction_seconds'] for r in group if r['reaction_seconds'] is not None]
            by_kind[kind]={'trials':len(group),'passed':sum(r['passed'] for r in group),
                           'false_beeps':sum(r['false_beep'] for r in group),'quiet':sum(r['all_quiet'] for r in group),
                           'mean_reaction_seconds':float(np.mean(lat)) if lat else None,
                           'max_reaction_seconds':float(max(lat)) if lat else None}
        gate=all((r['passed']/r['trials']>=.9 if kind=='wait_then_green' else r['false_beeps']/r['trials']<=.05) for kind,r in by_kind.items())
        results[condition]={'by_kind':by_kind,'gate_passed':gate,'all_quiet':all(r['all_quiet'] for r in rows)}
        (out/'metrics.json').write_text(json.dumps({'results':results,'wall_seconds':time.monotonic()-started},indent=2)+'\n')
        print(json.dumps({'condition':condition,**results[condition]}),flush=True)
    print(json.dumps({'status':'complete','results':results,'wall_seconds':time.monotonic()-started}),flush=True)


if __name__=='__main__':main()
