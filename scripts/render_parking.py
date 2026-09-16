#!/usr/bin/env python3
"""Edit the saved parking trajectory, body and neural samples into a 60 fps video.

Vehicle transforms are presentation replay, with physics disabled. They are never
used to evaluate parking or fed back to the controller. No corrections are added.
"""
import argparse
import json
import math
from pathlib import Path
import queue
import subprocess
import time
import carla
import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.spatial.transform import Rotation,Slerp
from flyhard.parking import ParkingCase,rectangle
from flyhard.parking_world import ParkingWorld
from flyhard.parking_rig import make_parking_rig
from flyhard.live_livery import verify_live_livery
from flyhard.sponsor_view import SponsorView
from flyhard.shot_cameras import look_at
from flyhard.steering_hud import draw_steering_readout
from flyhard.video_branding import draw_site_brand
from train_parking import sha

W,H=1248,960


def transform(matrix):
    m=np.asarray(matrix);pitch=math.degrees(math.asin(np.clip(m[2,0],-1,1)))
    return carla.Transform(carla.Location(*map(float,m[:3,3])),carla.Rotation(
        pitch=pitch,yaw=math.degrees(math.atan2(m[1,0],m[0,0])),roll=-math.degrees(math.atan2(m[2,1],m[2,2]))))


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True)
    p.add_argument('--asset',required=True);p.add_argument('--previews',action='store_true')
    p.add_argument('--port',type=int,default=2000)
    args=p.parse_args();root=Path(args.run);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    manifest=verify_live_livery(args.asset,out)
    frames=json.loads((root/'frames.json').read_text());config=json.loads((root/'config.json').read_text())
    result=json.loads((root/'metrics.json').read_text());body=dict(np.load(root/'body-trace.npz'))
    with imageio.get_reader(root/'cns-layer.mp4') as reader:neural=[im for im in reader]
    assert len(neural)==len(frames)
    matrices=np.asarray([f['vehicle_matrix'] for f in frames]);rotations=Slerp(np.arange(len(frames)),Rotation.from_matrix(matrices[:,:3,:3]))
    # Reset native physics/collision state between presentation replays.
    client=carla.Client('localhost',args.port);client.set_timeout(90);client.load_world('Town03')
    env=ParkingWorld(render=True,port=args.port);env.start(ParkingCase(**config['case']))
    for a in env.actors:
        if a.type_id.startswith('vehicle.'):a.set_simulate_physics(False)
    obstacles=[a for a in env.actors if a.type_id.startswith('vehicle.') and a.id!=env.ego.id]
    for actor,saved in zip(obstacles,config['obstacles']):actor.set_transform(transform(saved['matrix']))
    settings=env.world.get_settings();settings.fixed_delta_seconds=1/60;env.world.apply_settings(settings)
    rig=make_parking_rig();replay=mj.MjData(rig.model);renderer=mj.Renderer(rig.model,height=440,width=600)
    # Hide the test stand in the display only; leave the real control guides.
    option=mj.MjvOption();rig.model.geom_group[rig.model.geom_bodyid==0]=5;option.geomgroup[5]=0
    rig.model.geom_rgba[rig.model.geom_bodyid==rig.model.body('wheel').id,:3]=[.35,.35,.35]
    bodycam=mj.MjvCamera();bodycam.lookat[:]=[.2,0,.95];bodycam.distance=4.4;bodycam.azimuth=125;bodycam.elevation=-26
    sponsor=SponsorView(args.asset,manifest,config['vehicle_bounds']['location'])
    font={n:ImageFont.truetype('assets/fonts/Geist.ttf',n) for n in [20,22,24,26,28,40]}
    inboxes=[];sensors=[]
    for kind in ['rgb','depth']:
        bp=env.world.get_blueprint_library().find('sensor.camera.'+kind)
        for k,v in {'image_size_x':str(W),'image_size_y':str(H),'fov':'68','sensor_tick':'0','lens_k':'0','lens_kcube':'0'}.items():bp.set_attribute(k,v)
        if kind=='rgb':bp.set_attribute('motion_blur_intensity','0')
        sensor=env.world.spawn_actor(bp,carla.Transform());q=queue.Queue();sensor.listen(q.put)
        sensors.append(sensor);inboxes.append(q)
    bay=np.array([[p.x,p.y,.035,1.] for x,y in rectangle(0,0,0,env.case.length,env.case.width)
                  for p in [env.transform(x,y).location]])
    bay_points=np.concatenate([a[None]+np.linspace(0,1,800)[:,None]*(b-a)[None]
                               for a,b in zip(bay,np.roll(bay,-1,axis=0))])
    velocity=np.zeros(rig.model.nv);started=time.monotonic();records=[];previous_camera=None
    video=None if args.previews else subprocess.Popen(['ffmpeg','-nostdin','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
        '-s','1920x1080','-r','60','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','8',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(out/'flyhard-parking-25s.mp4')],stdin=subprocess.PIPE)
    native_rgb=native_depth=None
    if not args.previews:
        inputs=['ffmpeg','-nostdin','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r','60','-i','pipe:0','-an']
        native_rgb=subprocess.Popen(inputs+['-c:v','libx264','-preset','veryfast','-crf','15','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'native-camera.mp4')],stdin=subprocess.PIPE)
        native_depth=subprocess.Popen(inputs+['-c:v','ffv1','-level','3','-coder','1','-context','1','-g','1','-threads','2','-pix_fmt','bgr0',str(out/'native-depth.mkv')],stdin=subprocess.PIPE)
    previews={0,240,540,840,1139,1379}
    try:
        # 23 seconds of action, then a 2-second final hold with credits.
        for index in range(1500):
            if args.previews and index not in previews:continue
            source=min(index/1379,1)*(len(frames)-1);lo=int(source);hi=min(lo+1,len(frames)-1);mix=source-lo;r=frames[lo]
            matrix=np.eye(4);matrix[:3,:3]=rotations(source).as_matrix();matrix[:3,3]=(1-mix)*matrices[lo,:3,3]+mix*matrices[hi,:3,3]
            env.ego.set_transform(transform(matrix))
            # Cosmetic front-wheel steering follows the recorded native steer
            # command; it is not used for physics or benchmark measurements.
            for wheel in [carla.VehicleWheelLocation.FL_Wheel,carla.VehicleWheelLocation.FR_Wheel]:
                env.ego.set_wheel_steer_direction(wheel,float(r['applied_steer']*70))
            # Views hold for seconds at a time, keeping the gap easy to follow.
            if index<480:
                name='wide';position=env.transform(-1,13).location;position.z=15
                target=env.transform(0,1).location;target.z=.6
                camera=look_at([position.x,position.y,position.z],[target.x,target.y,target.z])
            elif index<840:
                name='left_door';relative=look_at([-3.5,-5.5,3.7],[0,0,.8])
                camera=transform(matrix@np.asarray(relative.get_matrix()))
            else:
                name='rear_wide';position=env.transform(-12,9).location;position.z=10
                target=env.transform(0,0).location;target.z=.6
                camera=look_at([position.x,position.y,position.z],[target.x,target.y,target.z])
            for sensor in sensors:sensor.set_transform(camera)
            if previous_camera!=name:
                for _ in range(35 if previous_camera is None else 5):env.world.tick()
                previous_camera=name
            frame_id=env.world.tick();images=[]
            for q in inboxes:
                while True:
                    im=q.get(timeout=60)
                    if im.frame>=frame_id:
                        assert im.frame==frame_id;images.append(im);break
            arrays=[np.frombuffer(im.raw_data,np.uint8).reshape(H,W,4)[:,:,:3][:,:,::-1].copy() for im in images]
            raw,packed=arrays
            if native_rgb:native_rgb.stdin.write(raw.tobytes());native_depth.stdin.write(packed.tobytes())
            d=packed.astype(np.float32);depth=(d[:,:,0]+256*d[:,:,1]+65536*d[:,:,2])*(1000/16777215)
            # Project the exact target geometry as a restrained, depth-tested
            # parking-bay outline. CARLA debug lines bloom excessively in HDR.
            camera_points=bay_points@np.linalg.inv(np.asarray(camera.get_matrix())).T
            focal=W/(2*math.tan(math.radians(68)/2));den=np.maximum(camera_points[:,0],.01)
            u=np.rint(W/2+focal*camera_points[:,1]/den).astype(int)
            v=np.rint(H/2-focal*camera_points[:,2]/den).astype(int)
            valid=(camera_points[:,0]>.1)&(u>=2)&(u<W-2)&(v>=2)&(v<H-2)
            ids=np.flatnonzero(valid);ids=ids[depth[v[ids],u[ids]]>=camera_points[ids,0]-.08]
            for dx in [-1,0,1]:
                for dy in [-1,0,1]:raw[v[ids]+dy,u[ids]+dx]=[217,190,92]
            relative=np.linalg.inv(matrix)@np.asarray(camera.get_matrix());raw,pixels=sponsor.render(relative,68,raw,depth)
            mj.mj_differentiatePos(rig.model,velocity,1.,body['qpos'][lo],body['qpos'][hi]);replay.qpos[:]=body['qpos'][lo]
            mj.mj_integratePos(rig.model,replay.qpos,velocity,mix);replay.qvel[:]=(1-mix)*body['qvel'][lo]+mix*body['qvel'][hi]
            replay.ctrl[:]=body['ctrl'][lo];replay.time=(1-mix)*body['time'][lo]+mix*body['time'][hi];mj.mj_forward(rig.model,replay)
            renderer.update_scene(replay,camera=bodycam,scene_option=option);renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX]=False
            canvas=Image.new('RGB',(1920,1080),'black');canvas.paste(Image.fromarray(raw),(24,64))
            canvas.paste(Image.fromarray(neural[lo]),(1296,64));canvas.paste(Image.fromarray(renderer.render()),(1296,584))
            draw=ImageDraw.Draw(canvas)
            title='flyhard | parallel parking'
            draw.text((24,23),title,font=font[26],fill='#eeeeee')
            draw.text((1296,23),'Fly brain',font=font[24],fill='#eee');draw_site_brand(canvas)
            draw.text((1296,540),'Wheel · pedals · gear',font=font[24],fill='#eeeeee')
            gear=r['applied_controls']['gear'];label={-1:'REVERSE',0:'NEUTRAL',1:'FORWARD'}[gear]
            draw.rounded_rectangle((48,87,270,136),radius=8,fill='black')
            draw.text((64,111),label,font=font[24],anchor='lm',fill='#ffbd59' if gear==-1 else '#eee')
            draw.text((1252,92),f"{r['speed_m_s']*3.6:.1f} km/h",font=font[24],anchor='ra',fill='white',stroke_width=2,stroke_fill='black')
            draw.text((48,980),f"Attempt 1 · {source*.05:.1f}s elapsed",font=font[22],fill='white',stroke_width=2,stroke_fill='black')
            draw_steering_readout(canvas,requested_angle=r['requested_angle'],wheel_angle=float(replay.qpos[rig.wheel_qpos]),applied_steer=r['applied_steer'])
            measured=r['applied_controls']
            draw.text((940,1052),f"Gas {measured['throttle']*100:.0f}%  Brake {measured['brake']*100:.0f}%",anchor='mm',font=font[22],fill='#ddd')
            if index>=1380:
                draw.rectangle((1296,584,1896,1023),fill='black')
                lines=['One attempt · benchmark pending','CARLA 0.9.16 · CVC / UAB','MaleCNS · Janelia','NeuroMechFly / FlyGym · EPFL',f"Livery r{manifest['revision']} · layout {manifest['layoutVersion']}",'Recorded motion replayed at 60 fps','Sponsor surfaces composited']
                for j,line in enumerate(lines):draw.text((1310,622+j*49),line,font=font[22],fill='#bbb')
            if video:video.stdin.write(np.asarray(canvas).tobytes())
            if index in previews:canvas.save(out/f'preview-{index:04}.png')
            records.append({'frame':index,'source_index':source,'camera':name,'sponsor_pixels':pixels,'neural_index':lo,
                            'camera_world_matrix':camera.get_matrix(),'vehicle_matrix':matrix.tolist(),'fov':68,'width':W,'height':H})
            if index%120==0 or args.previews:print(json.dumps({'frame':index,'source':source,'camera':name,'sponsor_pixels':pixels,'seconds':time.monotonic()-started}),flush=True)
    finally:
        for sensor in sensors:sensor.stop();sensor.destroy()
        encoder_codes=[]
        for encoder in [video,native_rgb,native_depth]:
            if encoder:
                try:encoder.stdin.close()
                except BrokenPipeError:pass
                encoder_codes.append(encoder.wait())
        renderer.close();sponsor.close();env.close()
        if any(encoder_codes):raise RuntimeError('Encoder failed')
    receipt={'status':'preview' if args.previews else 'rendered','fps':60,'duration':25,'frames':len(records),
             'presentation_title':'flyhard | parallel parking','hero_color_rgb':[48,84,43],'outcome_caption':False,
             'native_camera_cache':'Unsponsored native RGB and bit-exact packed depth retained for future sponsor-only recomposition.',
             'actual_result':result,'sponsor_revision':manifest['revision'],'sponsor_layout':manifest['layoutVersion'],
             'motion':'Recorded native CARLA rigid poses and MuJoCo joint positions interpolated only for presentation; physics disabled during replay. Cosmetic front-wheel angles use recorded steer times the measured 70 degree limit. Target bay outline projected from exact benchmark geometry with native depth occlusion.',
             'neural':'Measured model states held until next sample; no synthesized activations.',
             'source_sha256':{name:sha(root/name) for name in ['frames.json','body-trace.npz','neural-trace.npz']},'frame_map':records}
    if video:receipt['video_sha256']=sha(out/'flyhard-parking-25s.mp4')
    (out/'render-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
