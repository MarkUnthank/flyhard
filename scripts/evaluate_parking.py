#!/usr/bin/env python3
"""Evaluate learned parking through the body in native CARLA, with reset control."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import torch
from flyhard.parking import ParkingCase,observation,encode,motor_requests
from flyhard.parking_rig import make_parking_rig
from flyhard.parking_world import ParkingWorld,DT
from train_parking import load_policy,sha


def run_episode(env,rig,policy,case,seconds=45,record_neural=False,on_start=None,record_body=False,mask_selector=False,on_frame=None):
    state=env.start(case);rig.reset();rows=[];poses=[];activity=[];changes=0;previous_direction=0;hold=0
    if on_start is not None:on_start(env);state=env.state()
    # The passive selector needs time to complete a stroke. Hold each learned
    # action for 250 ms; the measured controls and velocity regulator still run
    # at 20 Hz. No geometric or steering correction is added by this scheduler.
    decision_ticks=5
    for index in range(round(seconds/DT)):
        inputs=observation(state,case,rig.parking.selector.value)
        if index%decision_ticks==0:
            decision_input=inputs.copy()
            if mask_selector:decision_input[4]=0.
            with torch.no_grad():
                output,neural=policy(torch.tensor(encode(decision_input),device='cuda'),True)
                wheel,speed=output[0].cpu().numpy()
        measured=env.apply_measured(rig)
        request=motor_requests(wheel,speed,state[3],rig.parking.measured['gear'])
        for _ in range(round(DT/rig.command_period)):
            # Fixed calibration from the isolated wheel hold diagnostic.
            compensated=request.copy();compensated[0]=np.clip(wheel*1.07,-.5,.5)
            rig.step_drive(rig.diagnostic_drive_action(*compensated))
        frame=env.world.tick();state=env.state();metrics=env.metrics(state)
        direction=1 if state[3]>.12 else -1 if state[3]<-.12 else 0
        if direction and previous_direction and direction!=previous_direction:changes+=1
        if direction:previous_direction=direction
        hold=hold+1 if metrics['pose_passed'] and abs(state[3])<.12 else 0
        row={'index':index,'carla_frame':frame,'time':(index+1)*DT,'body_time':float(rig.data.time),
             'neural_index':index,'state':state.tolist(),'observation':inputs.tolist(),
             'policy_decision':index%decision_ticks==0,'decision_observation':decision_input.tolist(),
             'requested_angle':float(wheel),'requested_signed_speed':float(speed),
             'wheel_angle':rig.angle,'applied_steer':measured['steer'],'applied_controls':measured,
             'measured_controls':rig.parking.measured,'speed_m_s':abs(float(state[3])),
             'vehicle_matrix':env.ego.get_transform().get_matrix(),**metrics}
        rows.append(row)
        if on_frame is not None:on_frame(env,rig,row)
        if index%100==0:print(json.dumps({'sample':index,'seconds':row['time'],'position_error_m':row['position_error_m'],'gear':measured['gear']}),flush=True)
        if record_neural:
            activity.append(neural[:,0].cpu().numpy().astype(np.float16))
        if record_neural or record_body:
            poses.append({'qpos':rig.data.qpos.copy(),'qvel':rig.data.qvel.copy(),
                          'ctrl':rig.data.ctrl.copy(),'time':rig.data.time})
        if metrics['collision'] or hold>=10:break
    final=rows[-1]
    result={'seed':case.seed,'split':case.split,'success':bool(hold>=10 and not final['collision']),
            'collision':any(r['collision'] for r in rows),'position_error_m':final['position_error_m'],
            'yaw_error_deg':final['yaw_error_deg'],'inside_bay':final['inside_bay'],
            'time_seconds':final['time'],'direction_changes':changes,
            'native_collision_events':env.events.copy()}
    return result,rows,poses,activity


def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--data',required=True)
    p.add_argument('--out',required=True);p.add_argument('--split',choices=['validation','heldout'],default='validation')
    p.add_argument('--count',type=int,default=3);p.add_argument('--seconds',type=float,default=45)
    p.add_argument('--start-index',type=int,default=0,help='First case index for a fixed, independent benchmark shard')
    p.add_argument('--case-indices',help='Explicit comma-separated case indices for a fixed shard')
    p.add_argument('--reset-core',action='store_true');p.add_argument('--record',action='store_true')
    p.add_argument('--asset');p.add_argument('--mask-selector',action='store_true')
    p.add_argument('--camera',action='store_true')
    p.add_argument('--port',type=int,default=2000)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--max-new-trials',type=int,help='Checkpoint a long evaluation after this many new trials')
    args=p.parse_args()
    if args.camera and not args.record:p.error('--camera requires --record')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=args.resume);torch.set_num_threads(4)
    spec={key:getattr(args,key) for key in ['split','count','start_index','case_indices','seconds','reset_core','record','mask_selector','camera']}
    spec.update(checkpoint_sha256=sha(args.checkpoint),cases_sha256=sha(Path(args.data)/'cases.json'))
    spec_path=out/'evaluation-spec.json'
    if args.resume:
        if json.loads(spec_path.read_text())!=spec:raise RuntimeError('Resume configuration differs from the saved benchmark')
    else:spec_path.write_text(json.dumps(spec,indent=2)+'\n')
    results=json.loads((out/'trials.json').read_text()) if args.resume and (out/'trials.json').exists() else []
    completed={r['seed'] for r in results};new_trials=0
    if args.record:
        if not args.asset:p.error('--record requires current --asset')
        from flyhard.live_livery import verify_live_livery
        manifest=verify_live_livery(args.asset,out)
    policy,saved=load_policy(args.checkpoint,reset_core=args.reset_core)
    all_cases=json.loads((Path(args.data)/'cases.json').read_text())[args.split][:args.count]
    indices=[int(i) for i in args.case_indices.split(',')] if args.case_indices else list(range(args.start_index,len(all_cases)))
    if len(set(indices))!=len(indices) or any(i<0 or i>=len(all_cases) for i in indices):p.error('Invalid or duplicate case index')
    selected=[(i+1,ParkingCase(**all_cases[i])) for i in indices]
    rig=make_parking_rig();rig.prepare_controls();env=ParkingWorld(render=args.camera,port=args.port);started=time.monotonic()
    camera=None
    if args.camera:
        from flyhard.parking_camera import ParkingTrialCamera
        camera=ParkingTrialCamera(env,args.asset,manifest)
    try:
        for number,case in selected:
            if case.seed in completed:continue
            if args.max_new_trials is not None and new_trials>=args.max_new_trials:break
            trial=out/str(case.seed);trial_started=time.monotonic()
            def ready(env):
                trial.mkdir();box=env.ego.bounding_box
                if camera:camera.begin(trial,number)
                config={'fps':20,'case':case.record(),'trial_number':number,'core_reset':args.reset_core,
                        'selector_sensory_masked':args.mask_selector,'policy_hz':4,'measured_control_hz':20,
                        'vehicle_bounds':{'location':[box.location.x,box.location.y,box.location.z],
                                          'extent':[box.extent.x,box.extent.y,box.extent.z]},
                        'origin':env.origin.tolist(),'scene_yaw':env.yaw,
                        'obstacles':[{'matrix':a.get_transform().get_matrix(),'type':a.type_id} for a in env.actors if a.type_id.startswith('vehicle.') and a.id!=env.ego.id],
                        'sponsor_revision':manifest['revision'],'sponsor_layout':manifest['layoutVersion']}
                (trial/'config.json').write_text(json.dumps(config,indent=2)+'\n')
                env.client.start_recorder(str((trial/'world-recorder.log').resolve()),True)
            result,rows,poses,_=run_episode(env,rig,policy,case,args.seconds,
                on_start=ready if args.record else None,record_body=args.record,mask_selector=args.mask_selector,
                on_frame=camera.capture if camera else None)
            if args.record:
                env.client.stop_recorder()
                if camera:camera.finish()
                (trial/'frames.json').write_text(json.dumps(rows)+'\n')
                np.savez_compressed(trial/'body-trace.npz',**{key:np.array([p[key] for p in poses]) for key in ['qpos','qvel','ctrl','time']})
                (trial/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
            else:(out/(str(case.seed)+'.json')).write_text(json.dumps(rows)+'\n')
            result['wall_seconds']=time.monotonic()-trial_started;results.append(result);new_trials+=1
            (out/'trials.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(result),flush=True)
        summary={'checkpoint_sha256':sha(args.checkpoint),'cases_sha256':sha(Path(args.data)/'cases.json'),
                 'core_reset':args.reset_core,'trials':len(results),'success_rate':float(np.mean([x['success'] for x in results])),
                 'selector_sensory_masked':args.mask_selector,'policy_hz':4,'measured_control_hz':20,
                 'collision_rate':float(np.mean([x['collision'] for x in results])),
                 'mean_position_error_m':float(np.mean([x['position_error_m'] for x in results])),
                 'mean_yaw_error_deg':float(np.mean([x['yaw_error_deg'] for x in results])),
                 'mean_time_seconds':float(np.mean([x['time_seconds'] for x in results])),
                 'mean_direction_changes':float(np.mean([x['direction_changes'] for x in results])),
                 'full_gate_passed':args.split=='heldout' and len(results)==50 and sum(x['success'] for x in results)>=40,
                 'status':'complete' if len(results)==len(selected) else 'partial',
                 'wall_seconds':sum(r['wall_seconds'] for r in results),'claim':'Scoped parallel parking from structured geometry'}
        (out/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
    finally:
        if args.record:env.client.stop_recorder()
        if camera:camera.close()
        env.close()


if __name__=='__main__':main()
