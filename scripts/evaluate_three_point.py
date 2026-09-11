#!/usr/bin/env python3
"""Small frozen-case diagnostic; optional native CARLA through measured controls."""
import argparse,json,time
from pathlib import Path
import numpy as np
import torch
from flyhard.three_point import TurnCase,observation,encode,metrics,kinematic_step
from flyhard.parking import motor_requests
from train_three_point import load_policy,sha


def summary(results):
    return {'trials':len(results),'successes':sum(r['success'] for r in results),
        'collision_rate':float(np.mean([r['collision'] for r in results])),
        **{'mean_'+key:float(np.mean([r[key] for r in results])) for key in
           ['position_error_m','yaw_error_deg','time_seconds','direction_changes']}}


def kinematic(policy,cases,seconds,curvature_scale=1.):
    states=np.stack([c.start for c in cases]);selector=np.zeros(len(cases));wheel=np.zeros(len(cases))
    done=np.zeros(len(cases),bool);hold=np.zeros(len(cases),int);changes=np.zeros(len(cases),int)
    previous=np.zeros(len(cases),int);directions=[[] for c in cases];rows=[[] for c in cases];results=[None]*len(cases)
    for i in range(round(seconds/.1)):
        inputs=np.stack([observation(s,c,g,w) for s,c,g,w in zip(states,cases,selector,wheel)])
        with torch.no_grad():actions=policy(torch.tensor(encode(inputs),device='cuda')).cpu().numpy()
        for k,case in enumerate(cases):
            if done[k]:continue
            target,speed=actions[k];wheel[k]+=np.clip(target-wheel[k],-.04,.04)
            # Direction changes brake to rest before acceleration; this is a
            # simple vehicle diagnostic, not the measured body interface.
            desired=int(np.sign(speed)) if abs(speed)>.1 else 0
            if desired!=selector[k] and abs(states[k,3])>.12:speed=0
            else:selector[k]=desired
            states[k]=kinematic_step(states[k],wheel[k],speed,curvature_scale=curvature_scale)
            score=metrics(states[k],case);direction=int(np.sign(states[k,3])) if abs(states[k,3])>.12 else 0
            if direction and previous[k] and direction!=previous[k]:changes[k]+=1
            if direction:
                if not directions[k] or directions[k][-1]!=direction:directions[k].append(direction)
                previous[k]=direction
            hold[k]=hold[k]+1 if score['pose_passed'] and abs(states[k,3])<.12 else 0
            rows[k].append({'time':(i+1)*.1,'state':states[k].tolist(),'requested_angle':float(target),
                'requested_signed_speed':float(actions[k,1]),'wheel_angle':float(wheel[k]),'selector':float(selector[k]),**score})
            if score['collision'] or hold[k]>=5 or i==round(seconds/.1)-1:
                done[k]=True;results[k]={'seed':case.seed,'split':case.split,
                    'success':bool(hold[k]>=5 and directions[k]==[1,-1,1] and not score['collision']),
                    'time_seconds':(i+1)*.1,'direction_changes':int(changes[k]),'directions':directions[k],**score}
        if done.all():break
    return results,rows


def native_world():
    import carla
    from flyhard.parking_world import ParkingWorld
    class TurnWorld(ParkingWorld):
        def __init__(self):
            self.client=carla.Client('localhost',2000);self.client.set_timeout(20)
            self.world=self.client.get_world()
            if self.world.get_actors().filter('vehicle.*'):raise RuntimeError('Turn pilot requires its own empty server')
            self.original=self.world.get_settings();settings=self.world.get_settings()
            settings.synchronous_mode=True;settings.fixed_delta_seconds=.05;settings.no_rendering_mode=True
            settings.substepping=True;settings.max_substep_delta_time=.01;settings.max_substeps=5
            self.world.apply_settings(settings)
            # Place the virtual 10 m corridor inside an actual uninterrupted
            # group of driving lanes; the old parking origin was near a curb.
            selected=None
            for wp in self.world.get_map().generate_waypoints(12):
                if wp.is_junction:continue
                lanes=[wp];pending=[wp];seen={wp.id}
                while pending:
                    current=pending.pop()
                    for side in ['get_left_lane','get_right_lane']:
                        q=getattr(current,side)()
                        if q and q.road_id==wp.road_id and q.lane_type==carla.LaneType.Driving and q.id not in seen:
                            seen.add(q.id);lanes.append(q);pending.append(q)
                if sum(q.lane_width for q in lanes)<10.4:continue
                near=wp.next(18)+wp.previous(18)
                if len(near)!=2 or any(q.is_junction or abs((q.transform.rotation.yaw-wp.transform.rotation.yaw+180)%360-180)>3 for q in near):continue
                selected=(wp,lanes);break
            if selected is None:
                self.world.apply_settings(self.original)
                raise RuntimeError('No sufficiently wide, straight driving corridor found')
            wp,lanes=selected;self.yaw=wp.transform.rotation.yaw
            self.origin=np.mean([[q.transform.location.x,q.transform.location.y,q.transform.location.z] for q in lanes],axis=0)
            self.origin[2]+=.2;angle=np.radians(self.yaw)
            self.rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            self.actors=[];self.events=[];self.ego=None;self.case=None
            self.scene={'map':self.world.get_map().name,'origin':self.origin.tolist(),'yaw':self.yaw,
                'road_id':wp.road_id,'lane_ids':[q.lane_id for q in lanes],
                'actual_lane_width_m':sum(q.lane_width for q in lanes)}

        def start(self,case):
            self.clear();self.case=case;lib=self.world.get_blueprint_library()
            bp=lib.find('vehicle.mini.cooper_s_2021');bp.set_attribute('role_name','three_point_hero')
            bp.set_attribute('color','48,84,43')
            self.ego=self.world.spawn_actor(bp,self.transform(case.start_x,case.start_y,case.start_yaw))
            self.actors.append(self.ego);self.ego.apply_control(carla.VehicleControl(brake=1))
            for _ in range(40):self.world.tick()
            sensor=self.world.spawn_actor(lib.find('sensor.other.collision'),carla.Transform(),attach_to=self.ego)
            sensor.listen(lambda e:self.events.append({'frame':e.frame,'other_actor':e.other_actor.type_id,'impulse':e.normal_impulse.length()}))
            self.actors.append(sensor)
            return self.state()
    return TurnWorld()


def native(policy,cases,seconds,out):
    from flyhard.parking_rig import make_parking_rig
    env=native_world();(out/'scene.json').write_text(json.dumps(env.scene,indent=2)+'\n');print(json.dumps(env.scene),flush=True)
    rig=make_parking_rig();rig.prepare_controls();results=[];traces=[]
    try:
        for case in cases:
            state=env.start(case);rig.reset();rows=[];poses=[];activity=[];hold=0;previous=0;changes=0;directions=[]
            for i in range(round(seconds/.05)):
                if i%5==0:
                    inputs=observation(state,case,rig.parking.selector.value,rig.angle)
                    with torch.no_grad():output,neural=policy(torch.tensor(encode(inputs),device='cuda'),return_state=True)
                    action=output[0].cpu().numpy();activity.append(neural[:,0].cpu().numpy().astype(np.float16))
                    wheel,speed=action
                measured=env.apply_measured(rig)
                request=motor_requests(wheel,speed,state[3],rig.parking.measured['gear'])
                request[0]=np.clip(wheel*1.07,-.5,.5)
                for _ in range(10):rig.step_drive(rig.diagnostic_drive_action(*request))
                frame=env.world.tick();state=env.state();score=metrics(state,case)
                score['collision']=bool(score['collision'] or env.events)
                direction=int(np.sign(state[3])) if abs(state[3])>.12 else 0
                if direction and previous and direction!=previous:changes+=1
                if direction:
                    if not directions or directions[-1]!=direction:directions.append(direction)
                    previous=direction
                hold=hold+1 if score['pose_passed'] and abs(state[3])<.12 else 0
                rows.append({'time':(i+1)*.05,'body_time':float(rig.data.time),'carla_frame':frame,
                    'vehicle_matrix':env.ego.get_transform().get_matrix(),'neural_index':len(activity)-1,
                    'applied_steer':measured['steer'],'speed_m_s':abs(float(state[3])),
                    'state':state.tolist(),'decision_observation':inputs.tolist(),'policy_decision':i%5==0,
                    'requested_angle':float(wheel),'requested_signed_speed':float(speed),
                    'applied_controls':measured,'measured_after_tick':rig.parking.measured,
                    'wheel_after_tick':rig.angle,**score})
                poses.append((rig.data.qpos.copy(),rig.data.qvel.copy(),rig.data.ctrl.copy(),float(rig.data.time)))
                if score['collision'] or hold>=10:break
            result={'seed':case.seed,'split':case.split,'success':bool(hold>=10 and directions==[1,-1,1] and not score['collision']),
                'time_seconds':rows[-1]['time'],'direction_changes':changes,'directions':directions,'native_collision_events':env.events.copy(),**score}
            trial=out/str(case.seed);trial.mkdir()
            box=env.ego.bounding_box
            config={'fps':20,'policy_hz':4,'case':case.record(),**env.scene,'scene_yaw':env.yaw,
                'vehicle_bounds':{'location':[box.location.x,box.location.y,box.location.z],'extent':[box.extent.x,box.extent.y,box.extent.z]},
                'initial_state':rows[0]['state'],
                'motion':'Measured passive wheel, pedals and selector drive native CARLA; fixed IK and velocity regulator.'}
            physics=env.ego.get_physics_control()
            (trial/'physics.json').write_text(json.dumps({'steering_curve':[[v.x,v.y] for v in physics.steering_curve],
                'wheels':[{'max_steer_angle':w.max_steer_angle,'radius':w.radius,'position':[w.position.x,w.position.y,w.position.z]} for w in physics.wheels]},indent=2)+'\n')
            (trial/'config.json').write_text(json.dumps(config,indent=2)+'\n')
            np.savez_compressed(trial/'neural-trace.npz',activity=np.array(activity),time=np.arange(len(activity))*.25)
            (trial/'frames.json').write_text(json.dumps(rows)+'\n')
            (trial/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
            np.savez_compressed(trial/'body-trace.npz',**{k:np.array([p[i] for p in poses]) for i,k in enumerate(['qpos','qvel','ctrl','time'])})
            results.append(result);traces.append(rows);print(json.dumps(result),flush=True)
    finally:env.close()
    return results,traces


def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--data',required=True)
    p.add_argument('--out',required=True);p.add_argument('--native',action='store_true');p.add_argument('--reset-core',action='store_true')
    p.add_argument('--split',default='heldout',choices=['validation','heldout']);p.add_argument('--count',type=int,default=8)
    p.add_argument('--curvature-scale',type=float,default=1.);p.add_argument('--seconds',type=float,default=35);p.add_argument('--asset');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4)
    if a.native:
        if not a.asset:p.error('Native recording requires fresh --asset')
        from flyhard.live_livery import verify_live_livery
        verify_live_livery(a.asset,out)
    selected=[TurnCase(**c) for c in json.loads((Path(a.data)/'cases.json').read_text())[a.split][:a.count]]
    spec={**vars(a),'cases':[c.record() for c in selected], 'checkpoint_sha256':sha(a.checkpoint),
        'gate':'Stationary 0.5s within 0.6m/12deg of opposite-heading target, forward/reverse/forward with exactly two direction changes, no contact or boundary crossing',
        'environment':'native CARLA with measured wheel/pedals/selector' if a.native else 'kinematic bicycle diagnostic; no body or CARLA claim',
        'source_sha256':{n:sha(n) for n in ['src/flyhard/three_point.py','src/flyhard/three_point_policy.py',__file__]}}
    (out/'spec.json').write_text(json.dumps(spec,indent=2)+'\n')
    policy,_=load_policy(a.checkpoint,reset_core=a.reset_core);started=time.monotonic()
    results,rows=native(policy,selected,a.seconds,out) if a.native else kinematic(policy,selected,a.seconds,a.curvature_scale)
    if not a.native:
        for c,trace in zip(selected,rows):(out/f'{c.seed}.json').write_text(json.dumps(trace)+'\n')
    report={**summary(results),'wall_seconds':time.monotonic()-started,'reset_core':a.reset_core,'native':a.native,'trials_detail':results}
    (out/'metrics.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
