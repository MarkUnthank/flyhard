#!/usr/bin/env python3
"""Train goal-conditioned steering and signed speed inside the measured graph."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import pyarrow.feather as feather
import torch
from flyhard.parking import encode,OBSERVATION_FIELDS
from flyhard.parking_policy import ParkingPolicy


def sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def load_policy(checkpoint,graph_dir='data/graph-traced-v1',reset_core=False):
    with gzip.open(checkpoint,'rb') as f:saved=torch.load(f,map_location='cpu',weights_only=False)
    if sha(Path(graph_dir)/'graph.npz')!=saved['config']['graph_sha256']:raise RuntimeError('Graph identity mismatch')
    s=saved['model'];policy=ParkingPolicy(np.load(Path(graph_dir)/'graph.npz'),s['sensory_ids'],s['motor_ids'],saved['config']['seed'])
    missing,extra=policy.load_state_dict(s,strict=False)
    assert set(missing)=={'core.crow','core.col','core.rows','core.base'} and not extra
    if reset_core:
        with torch.no_grad():policy.core.edge_gain.zero_();policy.core.leak.zero_()
    return policy.cuda().eval(),saved


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--out',required=True)
    p.add_argument('--graph',default='data/graph-traced-v1');p.add_argument('--steps',type=int,default=1600)
    p.add_argument('--batch',type=int,default=24);p.add_argument('--seed',type=int,default=420)
    p.add_argument('--resume');args=p.parse_args()
    root=Path(args.data);out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(8);torch.manual_seed(args.seed);rng=np.random.default_rng(args.seed)
    train=np.load(root/'train.npz');val=np.load(root/'validation.npz')
    tx=torch.tensor(encode(train['observations']),device='cuda');ty=torch.tensor(train['targets'],device='cuda')
    take=np.linspace(0,len(val['targets'])-1,min(768,len(val['targets'])),dtype=int)
    vx=torch.tensor(encode(val['observations'][take]),device='cuda');vy=torch.tensor(val['targets'][take],device='cuda')
    nodes=feather.read_table(Path(args.graph)/'nodes.feather');classes=np.array(nodes['superclass'].fill_null('').to_pylist())
    if args.resume:
        policy,previous=load_policy(args.resume,args.graph);policy.train()
    else:
        policy=ParkingPolicy(np.load(Path(args.graph)/'graph.npz'),np.flatnonzero(classes=='vnc_sensory'),np.flatnonzero(classes=='vnc_motor'),args.seed).cuda()
        policy.calibrate(tx[rng.choice(len(tx),64,replace=False)])
    fixed={n:b.detach().cpu().clone() for n,b in policy.named_buffers() if not n.startswith('core.')}
    config={**vars(args),'graph_sha256':sha(Path(args.graph)/'graph.npz'),'cases_sha256':sha(root/'cases.json'),
        'data_sha256':{n:sha(root/n) for n in ['train.npz','validation.npz']},'observation_fields':OBSERVATION_FIELDS,
        'claim':'Supervised goal-conditioned parking from structured relative geometry; no visual perception or general autonomy.',
        'learned':'Measured-edge gains and neuron leaks; fixed sensory population code and motor decoder.',
        'outputs':['requested wheel angle','requested speed magnitude','gear logits: reverse, neutral, forward'],
        'action_format':'discrete-gear-v1',
        'motor_adapter':'Fixed velocity regulator and offline IK move 28 fly leg joints; only measured wheel/pedal/selector positions drive CARLA.',
        'heldout_used_for_training':False,'state_reset_each_decision':True,
        'source_sha256':{n:sha(n) for n in ['src/flyhard/parking.py','src/flyhard/parking_policy.py','src/flyhard/parking_rig.py',__file__]}}
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    opt=torch.optim.Adam(policy.parameters(),lr=.04);history=[];best=float('inf');start=time.monotonic();gradient=None
    def objective(features,targets):
        wheel,speed,logits=policy.training_outputs(features)
        gear=torch.where(targets[:,1]<-.1,0,torch.where(targets[:,1]>.1,2,1))
        return ((wheel-targets[:,0])/.35).square()+((speed-targets[:,1].abs())/1.2).square()+torch.nn.functional.cross_entropy(logits,gear,reduction='none')
    def validate():
        total=0.
        with torch.no_grad():
            for i in range(0,len(vx),args.batch):total+=float(objective(vx[i:i+args.batch],vy[i:i+args.batch]).sum())
        return total/len(vx)
    initial=validate();print(json.dumps({'initial_validation_loss':initial}),flush=True)
    for step in range(1,args.steps+1):
        idx=rng.choice(len(tx),args.batch);opt.zero_grad(set_to_none=True)
        loss=objective(tx[idx],ty[idx]).mean();loss.backward()
        if gradient is None:
            gradient={n:bool(torch.isfinite(p.grad).all() and torch.count_nonzero(p.grad)>0) for n,p in policy.named_parameters()}
            assert all(gradient.values())
        torch.nn.utils.clip_grad_norm_(policy.parameters(),1.);opt.step()
        if step==1 or step%100==0:
            score=validate();row={'step':step,'training_loss':float(loss.detach()),'validation_loss':score,'seconds':time.monotonic()-start}
            history.append(row);print(json.dumps(row),flush=True);(out/'history.json').write_text(json.dumps(history,indent=2)+'\n')
            if score<best:
                best=score
                with gzip.open(out/'checkpoint.tmp.gz','wb',compresslevel=3) as f:torch.save({'model':policy.checkpoint_state(),'config':config,'step':step},f)
                (out/'checkpoint.tmp.gz').replace(out/'checkpoint.pt.gz')
    assert all(torch.equal(b.detach().cpu(),fixed[n]) for n,b in policy.named_buffers() if n in fixed)
    (out/'metrics.json').write_text(json.dumps({'status':'trained; physical parking evaluation pending','initial_validation_loss':initial,
        'best_validation_loss':best,'training_seconds':time.monotonic()-start,'gradient_audit':gradient,
        'frozen_interfaces_unchanged':True,'checkpoint_sha256':sha(out/'checkpoint.pt.gz')},indent=2)+'\n')


if __name__=='__main__':main()
