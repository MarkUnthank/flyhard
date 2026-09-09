#!/usr/bin/env python3
"""E02 wheel: 20 paired physical trials, enabled versus disabled foot grip."""
import argparse,json,time
from pathlib import Path
import numpy as np
import mujoco as mj
import imageio.v2 as imageio
from PIL import Image,ImageDraw
from flyhard.cockpit import WheelRig


def trial(rig,target,grip):
    rig.reset(grip=grip)
    times,angles,commands,positions,forces = [],[],[],[],[]
    for k in range(300):
        t=k*rig.command_period
        requested=target*min(t/0.5,1.0)
        action=rig.diagnostic_action(requested)
        rig.step(action)
        times.append(rig.data.time);angles.append(rig.angle);commands.append(action)
        positions.append(rig.data.qpos.copy())
        selected=(rig.data.efc_type==mj.mjtConstraint.mjCNSTR_EQUALITY)&(rig.data.efc_id==rig.grip_id)
        forces.append(float(np.linalg.norm(rig.data.efc_force[selected])))
    error=float(np.max(np.abs(np.array(angles)[-40:]-target)))
    return {'target':target,'grip':grip,'max_hold_error_rad':error,'final_angle':angles[-1],
            'max_grip_constraint_force':max(forces)}, {'time':times,'angle':angles,'action':commands,
            'qpos':positions,'grip_force':forces}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='runs/e02-wheel');p.add_argument('--trials',type=int,default=20)
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    config={'experiment':'E02-wheel','trials':args.trials,'seed':42,'target_range_rad':[0.18,0.42],
            'hold_error_limit_rad':0.08,'disabled_motion_limit_rad':0.02,
            'claim':'Diagnostic leg controller and engineered point grip; no neural learning or driving.',
            'actuation':'Only seven left foreleg joint targets; passive wheel; supported thorax.',
            'dt_seconds':WheelRig.timestep,'control_period_seconds':0.005,'playback_speed':0.3,
            'integrator':'implicitfast','wheel_damping':0.10,'wheel_spring':0.02,
            'grip_solref':[0.01,1],'grip_anchor':'left distal tarsus body origin, aligned at neutral keyframe'}
    (out/'config.json').write_text(json.dumps(config,indent=2))
    start=time.perf_counter();rig=WheelRig();rig.prepare_diagnostic_ik()
    print('IK max foot error (mm):',rig.ik_max_error_mm,flush=True)
    rng=np.random.default_rng(42);results=[];clips=[]
    for i in range(args.trials):
        target=float(rng.uniform(0.18,0.42)*(-1 if i%2 else 1))
        enabled,trace=trial(rig,target,True)
        disabled,control_trace=trial(rig,target,False)
        result={'trial':i,'enabled':enabled,'disabled':disabled,
                'passed':enabled['max_hold_error_rad']<=0.08 and abs(disabled['final_angle'])<=0.02}
        results.append(result);print(json.dumps(result),flush=True)
        np.savez_compressed(out/f'trial-{i:02}.npz',**trace,disabled_angle=control_trace['angle'])
        if i<2:clips.append((enabled,trace))
    renderer=mj.Renderer(rig.model,height=540,width=960);replay=mj.MjData(rig.model)
    cam=mj.MjvCamera();cam.lookat[:]=[0.4,0,1.3];cam.distance=6.7;cam.azimuth=130;cam.elevation=-22
    with imageio.get_writer(out/'wheel-proof.mp4',fps=30,macro_block_size=1,quality=8) as video:
        for meta,trace in clips:
            for i in range(0,len(trace['time']),2):
                replay.qpos[:]=trace['qpos'][i];replay.time=trace['time'][i];mj.mj_forward(rig.model,replay)
                renderer.update_scene(replay,camera=cam);frame=Image.fromarray(renderer.render());draw=ImageDraw.Draw(frame)
                draw.rectangle((0,0,960,48),fill=(17,22,27))
                draw.text((18,12),f"FLYHARD / E02   |   Physical steering test   |   wheel {trace['angle'][i]:+.3f} rad   |   target {meta['target']:+.3f}",fill='white')
                draw.rectangle((0,506,960,540),fill=(17,22,27))
                draw.text((18,516),'Joint servos -> foreleg -> engineered foot grip -> passive wheel. Playback 0.3x. No neural controller yet.',fill=(208,213,218))
                video.append_data(np.asarray(frame))
                if i==100 and meta==clips[0][0]:frame.save(out/'preview.png')
    renderer.close()
    metrics={**config,'passed_trials':sum(r['passed'] for r in results),'ik_max_error_mm':rig.ik_max_error_mm,
             'wheel_has_actuator':False,'wall_seconds':time.perf_counter()-start,'results':results,
             'status':'passed' if all(r['passed'] for r in results) and len(results)==20 else 'preliminary'}
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2))


if __name__=='__main__':main()
