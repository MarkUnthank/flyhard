#!/usr/bin/env python3
"""Native CARLA cabin camera survey, with matching RGB and metric depth."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import time

import carla
import numpy as np
from PIL import Image


VIEWS = {
    'driver': [-0.10, -0.35, 1.35, -6, 0],
    'shoulder': [-0.75, 0.05, 1.38, -9, -16],
    'passenger': [-0.55, 0.36, 1.35, -10, -26],
    'rear': [-1.10, 0.10, 1.44, -10, -14],
    'shoulder-high': [-0.75, 0.10, 1.55, -17, -17],
    'driver-low': [-0.10, -0.35, 1.13, -4, 0],
}


def receive(channel, frame):
    image = channel.get(timeout=30)
    while image.frame < frame:
        image = channel.get(timeout=30)
    assert image.frame == frame
    return image


def camera_blueprint(world, kind, width, height, fov):
    bp = world.get_blueprint_library().find('sensor.camera.'+kind)
    for name,value in [('image_size_x',width),('image_size_y',height),('fov',fov),
                       ('sensor_tick',0),('lens_k',0),('lens_kcube',0)]:
        bp.set_attribute(name,str(value))
    if kind == 'rgb':
        bp.set_attribute('motion_blur_intensity','0')
    return bp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',default='runs/interior-camera-spike')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    client = carla.Client('127.0.0.1',2000)
    client.set_timeout(40)
    world = client.get_world()
    original_settings = world.get_settings()
    original_weather = world.get_weather()
    actors = []
    width,height,fov = 1280,720,90
    results = {}
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 0.04
        settings.substepping = True
        settings.max_substep_delta_time = 0.01
        settings.max_substeps = 4
        world.apply_settings(settings)
        world.set_weather(carla.WeatherParameters.ClearNoon)
        source = json.loads(Path('runs/carla-calm-v2/config.json').read_text())
        bp = world.get_blueprint_library().find('vehicle.mini.cooper_s_2021')
        bp.set_attribute('color','48,84,43')
        vehicle = world.spawn_actor(bp,world.get_map().get_spawn_points()[source['spawn_index']])
        actors.append(vehicle)
        vehicle.set_autopilot(False)
        vehicle.apply_control(carla.VehicleControl(brake=1))
        for _ in range(50):world.tick()
        print(json.dumps({'vehicle_bounds':str(vehicle.bounding_box),'map':world.get_map().name}),flush=True)
        for name,(x,y,z,pitch,yaw) in VIEWS.items():
            transform = carla.Transform(carla.Location(x=x,y=y,z=z),carla.Rotation(pitch=pitch,yaw=yaw))
            channels = {kind:queue.Queue() for kind in ['rgb','depth']}
            sensors = {}
            for kind in channels:
                sensor = world.spawn_actor(camera_blueprint(world,kind,width,height,fov),transform,
                    attach_to=vehicle,attachment_type=carla.AttachmentType.Rigid)
                sensors[kind] = sensor
                actors.append(sensor)
                sensor.listen(channels[kind].put)
            for _ in range(30):
                frame = world.tick()
                images = {kind:receive(channel,frame) for kind,channel in channels.items()}
            rgb = np.frombuffer(images['rgb'].raw_data,np.uint8).reshape(height,width,4)[:,:,:3][:,:,::-1].copy()
            raw = np.frombuffer(images['depth'].raw_data,np.uint8).reshape(height,width,4).astype(np.float32)
            depth = (raw[:,:,2]+256*raw[:,:,1]+65536*raw[:,:,0])*(1000/(256**3-1))
            Image.fromarray(rgb).save(out/f'{name}.png')
            np.save(out/f'{name}-depth.npy',depth)
            results[name] = {'frame':frame,'rgb_frame':images['rgb'].frame,'depth_frame':images['depth'].frame,
                'camera_relative':{'x':x,'y':y,'z':z,'pitch':pitch,'yaw':yaw,'roll':0},
                'camera_world_matrix':sensors['rgb'].get_transform().get_matrix(),
                'vehicle_world_matrix':vehicle.get_transform().get_matrix(),
                'min_depth_m':float(depth.min()),'image_std':float(rgb.std()),
                'png_sha256':hashlib.sha256((out/f'{name}.png').read_bytes()).hexdigest()}
            for sensor in sensors.values():
                sensor.stop(); sensor.destroy(); actors.remove(sensor)
            print(json.dumps({'view':name,'frame':frame,'min_depth_m':float(depth.min())}),flush=True)
        result = {'status':'captured','native_carla_camera':True,'fly_in_carla':False,
            'width':width,'height':height,'fov_horizontal':fov,'camera_attachment':'Rigid',
            'lens_k':0,'lens_kcube':0,'vehicle':'vehicle.mini.cooper_s_2021',
            'carla_version':client.get_server_version(),'views':results,
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (out/'camera-survey.json').write_text(json.dumps(result,indent=2))
    finally:
        for actor in reversed(actors):
            if isinstance(actor,carla.Sensor):actor.stop()
            actor.destroy()
        world.apply_settings(original_settings)
        world.set_weather(original_weather)


if __name__ == '__main__':main()
