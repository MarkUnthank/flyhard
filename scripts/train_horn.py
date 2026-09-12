#!/usr/bin/env python3
"""Train connectome edge gains/leaks to command seven horn-operating leg joints."""
import argparse,gzip,hashlib,json,time
from pathlib import Path
import numpy as np
import pyarrow.feather as feather
import torch

from flyhard.horn import DT,FIELDS,HISTORY,episode,make_cases
from flyhard.horn_policy import HornPolicy


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def load_policy(checkpoint,graph_dir='data/graph-traced-v1',device='cuda'):
    with gzip.open(checkpoint,'rb') as f:saved=torch.load(f,map_location='cpu',weights_only=False)
    assert sha(Path(graph_dir)/'graph.npz')==saved['config']['graph_sha256']
    s=saved['model'];model=HornPolicy(np.load(Path(graph_dir)/'graph.npz'),s['sensory_ids'],
        s['motor_ids'],s['neutral'],s['action_scale'],saved['config']['seed'])
    missing,unexpected=model.load_state_dict(s,strict=False)
    assert set(missing)=={'core.crow','core.col','core.rows','core.base'} and not unexpected
    return model.to(device).eval(),saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True);p.add_argument('--mechanics',required=True)
    p.add_argument('--graph',default='data/graph-traced-v1');p.add_argument('--steps',type=int,default=900)
    p.add_argument('--batch',type=int,default=24);p.add_argument('--seed',type=int,default=501)
    p.add_argument('--device',default='cuda');args=p.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    torch.set_num_threads(4);torch.manual_seed(args.seed);rng=np.random.default_rng(args.seed)
    mechanics=Path(args.mechanics);assert json.loads((mechanics/'metrics.json').read_text())['passed']
    ik=np.load(mechanics/'ik-teacher.npz');neutral=ik['neutral'];actions=ik['actions'];values=ik['values']
    rest=np.array([np.interp(0.,values,actions[:,i]) for i in range(7)],dtype=np.float32)
    press=np.array([np.interp(.95,values,actions[:,i]) for i in range(7)],dtype=np.float32)
    scale=np.maximum(np.max(np.abs(np.stack([rest,press])-neutral),axis=0),.05)*1.25
    train_cases=make_cases('train',40);validation_cases=make_cases('validation',5)
    def dataset(cases):
        rows=[episode(c) for c in cases]
        x=np.concatenate([r[1] for r in rows]);labels=np.concatenate([r[2] for r in rows])
        y=np.where(labels[:,None],press,rest).astype(np.float32)
        return x,y,labels
    x,y,labels=dataset(train_cases);vx,vy,vlabels=dataset(validation_cases)
    nodes=feather.read_table(Path(args.graph)/'nodes.feather')
    classes=np.array(nodes['superclass'].fill_null('').to_pylist())
    model=HornPolicy(np.load(Path(args.graph)/'graph.npz'),np.flatnonzero(classes=='vnc_sensory'),
                    np.flatnonzero(classes=='vnc_motor'),neutral,scale,args.seed).to(args.device)
    pos,neg=np.flatnonzero(labels),np.flatnonzero(~labels)
    calibration=np.r_[rng.choice(pos,32),rng.choice(neg,32)]
    model.calibrate(torch.tensor(x[calibration],device=args.device))
    fixed={n:b.detach().cpu().clone() for n,b in model.named_buffers() if not n.startswith('core.')}
    validation=np.r_[np.flatnonzero(vlabels),rng.choice(np.flatnonzero(~vlabels),300,replace=False)]
    valx=torch.tensor(vx[validation],device=args.device);valy=torch.tensor(vy[validation],device=args.device)
    config={**vars(args),'graph_sha256':sha(Path(args.graph)/'graph.npz'),
            'mechanics_sha256':sha(mechanics/'metrics.json'),'ik_sha256':sha(mechanics/'ik-teacher.npz'),
            'train_cases':[c.as_dict() for c in train_cases],
            'validation_cases':[c.as_dict() for c in validation_cases],
            'fields':FIELDS,'history_samples':HISTORY,'sample_period':DT,'learning_rate':.04,
            'neural_steps':4,'state_reset_each_decision':True,
            'inputs':'Fixed rolling buffer of raw traffic observations; no scenario ID, time, transition flag or horn target',
            'learned':'Only measured connectome edge gains and neuron leak parameters',
            'frozen':'Raw-history buffer, generic random sensory features, sensory/motor populations, motor decoder, joint servos',
            'output':'Seven right-foreleg joint targets; passive measured button travel controls sound',
            'claim':'Supervised structured-state horn timing task, not vision or autonomous driving',
            'code_sha256':{name:sha(name) for name in ['scripts/train_horn.py','src/flyhard/horn.py',
                'src/flyhard/horn_policy.py','src/flyhard/horn_rig.py','src/flyhard/cockpit.py']}}
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    np.savez_compressed(out/'motor-targets.npz',rest=rest,press=press,scale=scale)
    optimizer=torch.optim.Adam(model.parameters(),lr=.04);history=[];best=float('inf');gradient=None
    def validate():
        losses=[]
        with torch.no_grad():
            for i in range(0,len(valx),args.batch):
                pred=model(valx[i:i+args.batch]);losses.extend(((pred-valy[i:i+args.batch])/model.action_scale).square().mean(dim=1).cpu().tolist())
        return float(np.mean(losses))
    initial=validate();print(json.dumps({'initial_validation_loss':initial,'train_rows':len(x),
                                       'positive_rows':len(pos),'neurons':model.core.n,'edges':model.core.edge_gain.numel()}),flush=True)
    training_started=time.monotonic()
    for step in range(1,args.steps+1):
        take=np.r_[rng.choice(pos,args.batch//2),rng.choice(neg,args.batch-args.batch//2)]
        bx=torch.tensor(x[take],device=args.device);by=torch.tensor(y[take],device=args.device)
        optimizer.zero_grad(set_to_none=True);prediction=model(bx)
        loss=((prediction-by)/model.action_scale).square().mean();assert torch.isfinite(loss)
        loss.backward()
        if gradient is None:
            gradient={n:{'finite':bool(torch.isfinite(v.grad).all()),'nonzero':int(torch.count_nonzero(v.grad))} for n,v in model.named_parameters()}
            assert all(v['finite'] and v['nonzero']>0 for v in gradient.values())
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step==1 or step%100==0 or step==args.steps:
            value=validate();row={'step':step,'loss':float(loss.detach()),'validation_loss':value,'training_seconds':time.monotonic()-training_started}
            history.append(row);print(json.dumps(row),flush=True);(out/'history.json').write_text(json.dumps(history,indent=2)+'\n')
            if value<best:
                best=value
                with gzip.open(out/'checkpoint.tmp.gz','wb',compresslevel=3) as f:torch.save({'model':model.checkpoint_state(),'config':config,'step':step,'validation_loss':value},f)
                (out/'checkpoint.tmp.gz').replace(out/'checkpoint.pt.gz')
    assert all(torch.equal(b.detach().cpu(),fixed[n]) for n,b in model.named_buffers() if n in fixed)
    result={'status':'trained_pending_physical_evaluation','initial_validation_loss':initial,'best_validation_loss':best,
            'gradient_audit':gradient,'frozen_interfaces_unchanged':True,'parameters':sum(v.numel() for v in model.parameters()),
            'wall_seconds':time.monotonic()-started,'training_seconds':time.monotonic()-training_started,
            'checkpoint_sha256':sha(out/'checkpoint.pt.gz'),'peak_gpu_gb':torch.cuda.max_memory_allocated()/1e9 if args.device=='cuda' else None}
    (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
