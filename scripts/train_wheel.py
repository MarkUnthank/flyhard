#!/usr/bin/env python3
"""E03/E04 bounded first learned stationary skill, one training seed."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import pyarrow.feather as feather
import torch
from flyhard.cockpit import WheelRig
from flyhard.motor_policy import WheelPolicy


def observation(rig,target):
    return np.r_[target,rig.angle,rig.data.qpos[rig.active_qpos]].astype(np.float32)


def advance(rig,action):
    for _ in range(10):rig.step(action)


def physical_evaluation(policy,rig,targets,out,tag,device,keep_traces=False):
    results=[]
    policy.eval()
    for index,target in enumerate(targets):
        rig.reset();angles=[];trace={'time':[],'qpos':[],'action':[],'angle':[],'neural_activity':[]}
        failure=None
        for step in range(60):
            obs=torch.tensor(observation(rig,target)[None],device=device)
            with torch.no_grad():action,state=policy(obs,return_state=True)
            command=action[0].cpu().numpy()
            try:advance(rig,command)
            except AssertionError:
                failure='physical numerical instability';break
            angles.append(rig.angle)
            if keep_traces and index<2:
                trace['time'].append(rig.data.time);trace['qpos'].append(rig.data.qpos.copy())
                trace['action'].append(command);trace['angle'].append(rig.angle)
                # Activity at decision start caused the following 50 ms of body motion.
                trace['neural_activity'].append(state[:,0].cpu().numpy())
        error=float(np.max(np.abs(np.array(angles)[-20:]-target))) if len(angles)==60 else None
        result={'target':float(target),'passed':failure is None and error<=0.13,
                'max_last_second_error_rad':error,'failure':failure}
        results.append(result)
        if keep_traces and index<2:np.savez_compressed(out/f'{tag}-trace-{index}.npz',target=target,**trace)
        (out/f'{tag}-evaluation.json').write_text(json.dumps(results,indent=2))
        if index%20==0:print(json.dumps({'stage':tag,'trials':index+1,'passed':sum(x['passed'] for x in results)}),flush=True)
    policy.train()
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--graph',default='data/graph-traced-v1');p.add_argument('--out',default='runs/e03-wheel-pilot')
    p.add_argument('--steps',type=int,default=600);p.add_argument('--seconds',type=int,default=900);p.add_argument('--batch',type=int,default=16)
    p.add_argument('--seed',type=int,default=123);args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();torch.manual_seed(args.seed);torch.set_num_threads(4);device='cuda' if torch.cuda.is_available() else 'cpu'
    manifest=json.loads((Path(args.graph)/'manifest.json').read_text())
    config={**vars(args),'experiment':'E03/E04 wheel pilot','device':device,'graph_sha256':manifest['graph_sha256'],
            'teacher':'Offline inverse kinematics -> physical joint servos. Teacher never used during learned evaluation.',
            'interfaces':'Frozen random signed sensory mapping and motor-neuron readout; only core edge gains and leaks train.',
            'sensory_population':'vnc_sensory','motor_population':'vnc_motor','neural_steps_per_decision':4,
            'neural_state_reset_each_decision':True,'control_period_seconds':0.05,'physics_timestep':WheelRig.timestep,
            'joint_target_slew_limit_rad_s':WheelRig.max_joint_target_rate,
            'heldout_physical_targets':100,'heldout_seed':61733,'pass_threshold':'90/100 within 0.13 rad for the entire last second of a 3 second trial',
            'training_seed_count':1,'learning_rate':0.04,'claim':'Preliminary stationary steering only; no visual driving or biological functional mapping.'}
    (out/'config.json').write_text(json.dumps(config,indent=2))
    rig=WheelRig();rig.prepare_diagnostic_ik();neutral=rig.neutral_actions.copy()
    scale=np.maximum(np.max(np.abs(rig.ik_actions-neutral),axis=0),0.05)
    graph=np.load(Path(args.graph)/'graph.npz');nodes=feather.read_table(Path(args.graph)/'nodes.feather')
    classes=np.asarray(nodes['superclass'].fill_null('').to_pylist())
    policy=WheelPolicy(graph,np.flatnonzero(classes=='vnc_sensory'),np.flatnonzero(classes=='vnc_motor'),neutral,scale,args.seed).to(device)
    train_rng=np.random.default_rng(17001)
    train_targets=np.r_[np.linspace(-0.45,0.45,32),train_rng.uniform(-0.45,0.45,8)]
    observations=[];actions=[]
    for target in train_targets:
        rig.reset();expert=rig.diagnostic_action(target)
        for _ in range(30):
            observations.append(observation(rig,target));actions.append(expert)
            advance(rig,expert)
    x=torch.tensor(np.array(observations),device=device);y=torch.tensor(np.array(actions),dtype=torch.float32,device=device)
    np.savez_compressed(out/'demonstrations.npz',observations=x.cpu().numpy(),actions=y.cpu().numpy(),targets=train_targets)
    # Calibration uses sensory observations only; no desired-action labels.
    policy.calibrate_frozen_decoder(x[::30])
    eval_rng=np.random.default_rng(config['heldout_seed']);eval_targets=eval_rng.uniform(0.18,0.42,100)*np.tile([1,-1],50)
    initial_state={name:t.detach().cpu().clone() for name,t in policy.state_dict().items()}
    # Baseline uses the same 100 held-out physical target angles as the trained model.
    baseline=physical_evaluation(policy,rig,eval_targets,out,'initial',device)
    opt=torch.optim.Adam(policy.parameters(),lr=config['learning_rate'])
    train_start=time.perf_counter();history=[];grad_stats=None
    if device=='cuda':torch.cuda.reset_peak_memory_stats()
    for step in range(args.steps):
        if time.perf_counter()-train_start>args.seconds:break
        idx=torch.randint(0,len(x),(args.batch,),device=device)
        opt.zero_grad(set_to_none=True);pred=policy(x[idx]);loss=((pred-y[idx])/policy.action_scale).square().mean()
        assert torch.isfinite(loss);loss.backward()
        if grad_stats is None:
            grad_stats={name:{'finite':bool(torch.isfinite(param.grad).all()),'nonzero':int(torch.count_nonzero(param.grad))}
                        for name,param in policy.named_parameters()}
            assert all(v['finite'] and v['nonzero']>0 for v in grad_stats.values())
        torch.nn.utils.clip_grad_norm_(policy.parameters(),1.0);opt.step()
        record={'step':step+1,'loss':float(loss.detach()),'elapsed_seconds':time.perf_counter()-train_start}
        history.append(record)
        if step%50==0:print(json.dumps(record),flush=True);(out/'history.json').write_text(json.dumps(history,indent=2))
    training_seconds=time.perf_counter()-train_start
    torch.save({'model':policy.state_dict(),'optimizer':opt.state_dict(),'config':config,'steps':len(history)},out/'checkpoint.pt')
    trained=physical_evaluation(policy,rig,eval_targets,out,'trained',device,keep_traces=True)
    trained_success=sum(r['passed'] for r in trained)
    # Resetting just the trained edge/leak parameters leaves both frozen interfaces
    # identical. Thus the initial evaluation is also the matched core-reset control.
    fixed_unchanged=all(torch.equal(t.cpu(),initial_state[name]) for name,t in policy.state_dict().items()
                        if name not in ['core.edge_gain','core.leak'])
    assert fixed_unchanged
    metrics={**config,'status':'preliminary_pass' if trained_success>=90 else 'valid_negative_result',
             'initial_successes':sum(r['passed'] for r in baseline),'trained_successes':trained_success,
             'evaluation_trials_per_condition':100,'fixed_interfaces_and_topology_unchanged':fixed_unchanged,
             'trainable_parameters':sum(t.numel() for t in policy.parameters()),'gradient_audit':grad_stats,
             'optimizer_steps':len(history),'training_seconds':training_seconds,'wall_seconds':time.perf_counter()-start,
             'first_loss':history[0]['loss'],'last_loss':history[-1]['loss'],
             'edge_gain_mean_absolute_change':float(policy.core.edge_gain.detach().abs().mean()),
             'peak_gpu_allocated_gb':torch.cuda.max_memory_allocated()/1e9 if device=='cuda' else None,
             'next_decision':'Three-seed replication and pedal skill if successful; diagnose the failed layer otherwise.'}
    (out/'history.json').write_text(json.dumps(history,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2),flush=True)


if __name__=='__main__':main()
