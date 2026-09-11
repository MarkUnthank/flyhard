#!/usr/bin/env python3
"""Train the single-core, two-foreleg steering/horn policy."""
import argparse, gzip, json, time
from pathlib import Path
import numpy as np
import pyarrow.feather as feather
import torch
from flyhard.driving_horn import cases, episode, FIELDS, HISTORY, HISTORY_INDICES, ENCODING
from flyhard.driving_horn_policy import DrivingHornPolicy
from flyhard.horn_rig import make_horn_rig
from train_horn import sha


def load(checkpoint, graph_dir='data/graph-traced-v1', device='cuda'):
    with gzip.open(checkpoint, 'rb') as f:
        saved = torch.load(f, map_location='cpu', weights_only=False)
    assert saved['config'].get('encoding') == ENCODING, 'Use the archived source for checkpoints with a different observation encoding'
    assert sha(Path(graph_dir)/'graph.npz') == saved['config']['graph_sha256']
    s = saved['model']
    model = DrivingHornPolicy(np.load(Path(graph_dir)/'graph.npz'), s['sensory_ids'], s['motor_ids'],
                              s['neutral'], s['action_scale'], saved['config']['seed'])
    missing, extra = model.load_state_dict(s, strict=False)
    assert set(missing) == {'core.crow','core.col','core.rows','core.base'} and not extra
    return model.to(device).eval(), saved


def event_negatives(items, labels):
    # Quiet frames around a potential event are harder than long uneventful
    # stretches. In particular, an empty road turning green must stay quiet.
    near=np.concatenate([(np.arange(round(c.duration*10))*.1>=c.event-.4) &
                         (np.arange(round(c.duration*10))*.1<c.event+1.2) for c in items])
    return np.flatnonzero(near & ~labels)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True); p.add_argument('--steps', type=int, default=1500)
    p.add_argument('--batch', type=int, default=32); p.add_argument('--seed', type=int, default=802)
    p.add_argument('--graph', default='data/graph-traced-v1')
    p.add_argument('--resume', help='Continue an immutable development checkpoint with a fresh optimizer')
    args = p.parse_args(); out = Path(args.out); out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4); torch.manual_seed(args.seed); rng = np.random.default_rng(args.seed)
    started = time.monotonic(); rig = make_horn_rig(); rig.prepare_controls()
    neutral = np.r_[rig.neutral_actions, rig.horn.neutral_actions]
    rest, press = rig.horn.diagnostic_action(0.), rig.horn.diagnostic_action(.95)
    limits = np.array([np.r_[rig.diagnostic_action(w), h] for w in [-.4,0,.4] for h in [rest,press]])
    scale = np.maximum(np.max(abs(limits-neutral), axis=0), .05)*1.25
    train, val = cases('train', 30), cases('validation', 4)
    def dataset(items):
        sequences = [episode(c) for c in items]
        x = np.concatenate([s[1] for s in sequences]); labels = np.concatenate([s[2] for s in sequences])
        angles = np.concatenate([s[3] for s in sequences])
        left = np.array([rig.diagnostic_action(w) for w in angles])
        y = np.c_[left, np.where(labels[:,None], press, rest)].astype(np.float32)
        groups = np.concatenate([np.full(len(s[2]), c.kind) for c,s in zip(items,sequences)])
        return x, y, labels, groups
    x,y,labels,groups = dataset(train); vx,vy,vl,vg = dataset(val)
    nodes = feather.read_table(Path(args.graph)/'nodes.feather')
    classes = np.array(nodes['superclass'].fill_null('').to_pylist())
    if args.resume:
        model,parent = load(args.resume,args.graph)
        assert parent['config']['seed']==args.seed
        assert np.allclose(model.neutral.cpu(),neutral) and np.allclose(model.action_scale.cpu(),scale)
    else:
        model = DrivingHornPolicy(np.load(Path(args.graph)/'graph.npz'), np.flatnonzero(classes=='vnc_sensory'),
                                  np.flatnonzero(classes=='vnc_motor'), neutral, scale, args.seed).cuda()
    positive, negative = np.flatnonzero(labels), np.flatnonzero(~labels)
    if not args.resume:
        model.calibrate(torch.tensor(x[np.r_[rng.choice(positive,32),rng.choice(negative,32)]], device='cuda'))
    frozen = {n:v.cpu().clone() for n,v in model.named_buffers() if not n.startswith('core.')}
    positive_groups = [np.flatnonzero(labels & (groups==kind)) for kind in sorted(set(groups[labels]))]
    hard_negative=event_negatives(train,labels);val_hard_negative=event_negatives(val,vl)
    val_positive = [np.flatnonzero(vl & (vg==kind)) for kind in sorted(set(vg[vl]))]
    # Short green-light presses receive the same positive weight as long holds.
    chosen = np.r_[np.concatenate([rng.choice(indices,60) for indices in val_positive]),
                   rng.choice(val_hard_negative,120),rng.choice(np.flatnonzero(~vl),120)]
    valx, valy = torch.tensor(vx[chosen],device='cuda'), torch.tensor(vy[chosen],device='cuda')
    config = {**vars(args), 'graph_sha256':sha(Path(args.graph)/'graph.npz'), 'fields':FIELDS,
              'encoding':ENCODING, 'history_indices':HISTORY_INDICES,
              'history_samples':HISTORY, 'history_hz':10, 'neural_steps':4, 'state_reset_each_decision':True,
              'train_cases':[c.as_dict() for c in train], 'validation_cases':[c.as_dict() for c in val],
              'learned':'Only connectome edge gains and neuron leaks',
              'engineered':'Four-second raw history; rage mode and wheel request; frozen sensory/motor interfaces; IK teaching targets; joint servos',
              'output':'Seven LF steering joints and seven RF horn joints from one core',
              'sampling':'Half positive, equally balanced across positive task kinds; half of negatives focus on the event window, including green with no lead car',
              'parent_checkpoint_sha256':sha(args.resume) if args.resume else None,
              'parent_step':parent['step'] if args.resume else None,
              'source_sha256':{f:sha(f) for f in [__file__,'src/flyhard/driving_horn.py','src/flyhard/driving_horn_policy.py','src/flyhard/horn_rig.py','src/flyhard/cockpit.py']}}
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    optimizer = torch.optim.Adam(model.parameters(), lr=.035); best=float('inf'); history=[]; gradients=None
    def validate():
        losses=[]
        with torch.no_grad():
            for i in range(0,len(valx),args.batch):
                losses.extend(((model(valx[i:i+args.batch])-valy[i:i+args.batch])/model.action_scale).square().mean(1).cpu().tolist())
        return float(np.mean(losses))
    def save_checkpoint(step,value):
        with gzip.open(out/'checkpoint.tmp.gz','wb',compresslevel=3) as f:
            torch.save({'model':model.checkpoint_state(),'config':config,'step':step,'validation_loss':value},f)
        (out/'checkpoint.tmp.gz').replace(out/'checkpoint.pt.gz')
    initial=validate(); print(json.dumps({'initial_loss':initial,'rows':len(x),'parameters':sum(v.numel() for v in model.parameters())}),flush=True)
    best=initial;save_checkpoint(0,initial)
    for step in range(1,args.steps+1):
        pos=np.array([rng.choice(positive_groups[j%len(positive_groups)]) for j in range(args.batch//2)])
        hard_count=(args.batch-len(pos))//2
        indices=np.r_[pos,rng.choice(hard_negative,hard_count),rng.choice(negative,args.batch-len(pos)-hard_count)]
        bx,by=torch.tensor(x[indices],device='cuda'),torch.tensor(y[indices],device='cuda')
        optimizer.zero_grad(set_to_none=True); loss=((model(bx)-by)/model.action_scale).square().mean()
        assert torch.isfinite(loss);loss.backward()
        if gradients is None:
            gradients={n:{'finite':bool(torch.isfinite(v.grad).all()),'nonzero':int(torch.count_nonzero(v.grad))} for n,v in model.named_parameters()}
            assert all(v['finite'] and v['nonzero'] for v in gradients.values())
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step==1 or step%100==0 or step==args.steps:
            value=validate();row={'step':step,'loss':float(loss.detach()),'validation_loss':value,'wall_seconds':time.monotonic()-started}
            history.append(row); print(json.dumps(row),flush=True)
            (out/'history.json').write_text(json.dumps(history,indent=2)+'\n')
            if value<best:
                best=value
                save_checkpoint(step,value)
    assert all(torch.equal(v.cpu(),frozen[n]) for n,v in model.named_buffers() if n in frozen)
    result={'initial_validation_loss':initial,'best_validation_loss':best,'wall_seconds':time.monotonic()-started,
            'gradient_audit':gradients,'frozen_interfaces_unchanged':True,'checkpoint_sha256':sha(out/'checkpoint.pt.gz'),
            'peak_torch_gpu_gb':torch.cuda.max_memory_allocated()/1e9}
    (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
