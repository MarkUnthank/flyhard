#!/usr/bin/env python3
"""Synchronous CARLA camera/vehicle infrastructure check; scripted controls."""
import argparse,json,queue,time
from pathlib import Path
import carla
import numpy as np
import imageio.v2 as imageio
from PIL import Image,ImageDraw


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='runs/carla-smoke');args=p.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    client=carla.Client('127.0.0.1',2000);client.set_timeout(30)
    world=client.get_world();original=world.get_settings();actors=[]
    config={'experiment':'CARLA camera smoke test','version':client.get_server_version(),
            'fixed_delta_seconds':0.05,'camera_size':[960,540],'frames':120,
            'claim':'Scripted infrastructure check. No fly or neural controller supplies these commands.'}
    (out/'config.json').write_text(json.dumps(config,indent=2))
    try:
        settings=world.get_settings();settings.synchronous_mode=True;settings.fixed_delta_seconds=0.05
        settings.no_rendering_mode=False;settings.substepping=True;settings.max_substep_delta_time=0.01;settings.max_substeps=5
        world.apply_settings(settings)
        library=world.get_blueprint_library();bp=library.find('vehicle.mini.cooper_s_2021')
        if bp.has_attribute('color'):bp.set_attribute('color','48,84,43')
        vehicle=None
        for pose in world.get_map().get_spawn_points()[:20]:
            vehicle=world.try_spawn_actor(bp,pose)
            if vehicle:break
        assert vehicle is not None
        actors.append(vehicle)
        camera_bp=library.find('sensor.camera.rgb');camera_bp.set_attribute('image_size_x','960');camera_bp.set_attribute('image_size_y','540')
        camera_bp.set_attribute('fov','90');camera_bp.set_attribute('sensor_tick','0')
        camera=world.spawn_actor(camera_bp,carla.Transform(carla.Location(x=-5.5,z=2.8),carla.Rotation(pitch=-17)),attach_to=vehicle)
        actors.append(camera);frames=queue.Queue();camera.listen(frames.put)
        records=[];start=time.perf_counter()
        with imageio.get_writer(out/'carla-smoke.mp4',fps=20,quality=8,macro_block_size=1) as video:
            for i in range(config['frames']):
                throttle=0.0 if i<20 else 0.25
                steer=0.0 if i<60 else 0.12
                vehicle.apply_control(carla.VehicleControl(throttle=throttle,steer=steer))
                tick=world.tick()
                image=frames.get(timeout=20)
                while image.frame<tick:image=frames.get(timeout=20)
                assert image.frame==tick
                array=np.frombuffer(image.raw_data,dtype=np.uint8).reshape(540,960,4)[:,:,:3][:,:,::-1].copy()
                assert array.std()>1,'Camera produced a blank image'
                frame=Image.fromarray(array);draw=ImageDraw.Draw(frame)
                draw.rectangle((0,0,960,38),fill=(17,22,27))
                draw.text((18,12),f'FLYHARD / CARLA infrastructure check   |   synchronous frame {tick}   |   scripted inputs',fill='white')
                video.append_data(np.asarray(frame))
                if i==60:frame.save(out/'preview.png')
                loc=vehicle.get_location();vel=vehicle.get_velocity()
                records.append({'frame':tick,'camera_frame':image.frame,'timestamp':image.timestamp,
                                'throttle':throttle,'steer':steer,'position':[loc.x,loc.y,loc.z],
                                'speed_m_s':float(np.linalg.norm([vel.x,vel.y,vel.z]))})
        metrics={**config,'status':'passed','map':world.get_map().name,'matching_camera_frames':len(records),
                 'wall_seconds':time.perf_counter()-start,'final_speed_m_s':records[-1]['speed_m_s'],
                 'displacement_m':float(np.linalg.norm(np.array(records[-1]['position'])-records[0]['position']))}
        (out/'trace.json').write_text(json.dumps(records,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
        print(json.dumps(metrics,indent=2))
    finally:
        for actor in reversed(actors):
            if isinstance(actor,carla.Sensor):actor.stop()
            actor.destroy()
        world.apply_settings(original)


if __name__=='__main__':main()
