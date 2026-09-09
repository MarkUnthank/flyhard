#!/usr/bin/env python3
import argparse,json,time
from pathlib import Path
import numpy as np
import mujoco as mj
import imageio.v2 as imageio
from PIL import Image,ImageDraw
from flyhard.pedal import PedalRig


def trial(rig,target,contact):
    rig.reset(contact=contact);trace={'time':[],'qpos':[],'displacement':[],'normal_contact_force':[]}
    for k in range(300):
        t=k*rig.command_period
        requested=target*min(t/0.3,1) if t<0.8 else target*max(1-(t-0.8)/0.3,0)
        rig.step(rig.diagnostic_action(requested))
        force=0.;wrench=np.zeros(6)
        for i in range(rig.data.ncon):
            if rig.sole in [rig.data.contact[i].geom1,rig.data.contact[i].geom2]:
                mj.mj_contactForce(rig.model,rig.data,i,wrench);force+=abs(float(wrench[0]))
        trace['time'].append(rig.data.time);trace['qpos'].append(rig.data.qpos.copy())
        trace['displacement'].append(rig.displacement);trace['normal_contact_force'].append(force)
    d=np.array(trace['displacement'])
    return {'target_mm':target,'contact_enabled':contact,'max_hold_error_mm':float(np.max(np.abs(d[100:150]-target))),
            'max_depression_mm':float(d.max()),'released_displacement_mm':float(d[-1]),'max_contact_force':max(trace['normal_contact_force'])},trace


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='runs/e02-pedal');p.add_argument('--trials',type=int,default=20)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    config={'experiment':'E02-pedal','trials':a.trials,'seed':71,'physics_dt_s':PedalRig.timestep,
            'contact':'Explicit spherical sole on right middle distal tarsus contacts passive sprung pad.',
            'pad_travel_mm':0.25,'pad_mass_mg':1e-5,'spring':3,'spring_reference_mm':-0.05,'damping':0.02,
            'contact_solref':[0.001,1],'contact_solimp':[0.99,0.999,0.001,0.5,2],
            'hold_error_limit_mm':0.04,'release_limit_mm':0.02,'disabled_motion_limit_mm':0.02,
            'claim':'Physical contact diagnostic; not learned pedal operation.'}
    (out/'config.json').write_text(json.dumps(config,indent=2));start=time.perf_counter();rig=PedalRig();rig.prepare_diagnostic_ik()
    rng=np.random.default_rng(71);results=[];clips=[]
    for i in range(a.trials):
        target=float(rng.uniform(0.12,0.2));enabled,trace=trial(rig,target,True);disabled,other=trial(rig,target,False)
        passed=enabled['max_hold_error_mm']<0.04 and abs(enabled['released_displacement_mm'])<0.02 and disabled['max_depression_mm']<0.02 and enabled['max_contact_force']>0
        result={'trial':i,'enabled':enabled,'disabled':disabled,'passed':passed};results.append(result);print(json.dumps(result),flush=True)
        np.savez_compressed(out/f'trial-{i:02}.npz',target=target,**trace,disabled_displacement=other['displacement'])
        if i<2:clips.append(trace)
    renderer=mj.Renderer(rig.model,height=540,width=960);data=mj.MjData(rig.model)
    cam=mj.MjvCamera();cam.lookat[:]=[0,-0.3,1.1];cam.distance=6;cam.azimuth=115;cam.elevation=-24
    with imageio.get_writer(out/'pedal-proof.mp4',fps=30,quality=8,macro_block_size=1) as video:
        for trace in clips:
            for i in range(0,len(trace['time']),2):
                data.qpos[:]=trace['qpos'][i];data.time=trace['time'][i];mj.mj_forward(rig.model,data)
                renderer.update_scene(data,camera=cam);frame=Image.fromarray(renderer.render());draw=ImageDraw.Draw(frame)
                draw.rectangle((0,0,960,48),fill=(17,22,27));draw.text((18,12),f"FLYHARD / E02  |  Physical pedal test  |  depression {trace['displacement'][i]:.3f} mm",fill='white')
                draw.rectangle((0,506,960,540),fill=(17,22,27));draw.text((18,516),'Joint servos -> middle leg -> sole contact -> passive spring pedal. Playback 0.3x. No neural controller yet.',fill=(208,213,218))
                video.append_data(np.asarray(frame))
                if i==130:frame.save(out/'preview.png')
    renderer.close();metrics={**config,'passed_trials':sum(r['passed'] for r in results),'ik_max_error_mm':rig.ik_max_error_mm,
        'wall_seconds':time.perf_counter()-start,'results':results,'status':'passed' if all(r['passed'] for r in results) and len(results)==20 else 'preliminary'}
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2))


if __name__=='__main__':main()
