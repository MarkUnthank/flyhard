#!/usr/bin/env python3
"""Capture the learned horn, physical button, CARLA state and native 60 Hz video."""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import time

import carla
import numpy as np
from PIL import Image
import torch

from flyhard.driving_horn import History, encode
from flyhard.dynamic_horn_metrics import capture_score
from flyhard.horn_rig import make_horn_rig
from flyhard.dynamic_horn_world import DynamicHornWorld
from flyhard.live_livery import verify_live_livery
from flyhard.shot_cameras import look_at
from train_horn import sha
from train_driving_horn import load


def video_writer(path, depth=False, size='1248x960'):
    encoding = (['-c:v', 'ffv1', '-level', '3', '-coder', '1', '-context', '1', '-g', '1', '-pix_fmt', 'bgr0']
                if depth else ['-c:v', 'libx264', '-preset', 'fast', '-crf', '15', '-pix_fmt', 'yuv420p',
                               '-profile:v', 'baseline', '-bf', '0', '-refs', '1', '-movflags', '+faststart'])
    return subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
        '-s', size, '-r', '60', '-i', 'pipe:0', '-an', *encoding, '-threads', '2', str(path)], stdin=subprocess.PIPE)


def next_image(inbox, frame):
    while True:
        image = inbox.get(timeout=60)
        if image.frame >= frame:
            assert image.frame == frame
            return image


def capture(env, model, saved, args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    manifest = verify_live_livery(args.asset, out)
    env.start(args.kind)
    rig = make_horn_rig()
    rig.reset()
    # Fixed native rear-left camera includes both sponsor-rich car surfaces.
    pose = look_at([-7.8, -6.0, 4.2], [5.5, 0., 1.5])
    sensors, queues = [], []
    library = env.world.get_blueprint_library()
    for kind in ['rgb', 'depth']:
        bp = library.find('sensor.camera.'+kind)
        for key, value in {'image_size_x':'1248', 'image_size_y':'960', 'fov':'65',
                           'sensor_tick':'0', 'lens_k':'0', 'lens_kcube':'0'}.items():
            bp.set_attribute(key, value)
        if kind == 'rgb':
            bp.set_attribute('motion_blur_intensity', '0')
            bp.set_attribute('exposure_compensation', '-0.6')
        sensor = env.world.spawn_actor(bp, pose, attach_to=env.ego, attachment_type=carla.AttachmentType.Rigid)
        inbox = queue.Queue()
        sensor.listen(inbox.put)
        sensors.append(sensor)
        queues.append(inbox)
        env.actors.append(sensor)
    light_bp = library.find('sensor.camera.rgb')
    for key,value in {'image_size_x':'320','image_size_y':'240','fov':'35','sensor_tick':'0',
                      'lens_k':'0','lens_kcube':'0','motion_blur_intensity':'0','exposure_compensation':'-0.6'}.items():
        light_bp.set_attribute(key,value)
    light_pose = env.lamp_camera()
    lamp = env.world.spawn_actor(light_bp,light_pose)
    lamp_queue = queue.Queue()
    lamp.listen(lamp_queue.put)
    sensors.append(lamp); queues.append(lamp_queue); env.actors.append(lamp)
    cabin_pose = carla.Transform(carla.Location(x=-.45,y=.08,z=1.35),
                                 carla.Rotation(pitch=-12,yaw=-23))
    has_cabin = args.kind.startswith('cut_in') or args.kind == 'road_rage'
    if has_cabin:
        for kind in ['rgb','depth']:
            bp=library.find('sensor.camera.'+kind)
            for key,value in {'image_size_x':'1248','image_size_y':'960','fov':'90',
                              'sensor_tick':'0','lens_k':'0','lens_kcube':'0'}.items():
                bp.set_attribute(key,value)
            if kind=='rgb':bp.set_attribute('motion_blur_intensity','0')
            sensor=env.world.spawn_actor(bp,cabin_pose,attach_to=env.ego,attachment_type=carla.AttachmentType.Rigid)
            inbox=queue.Queue();sensor.listen(inbox.put)
            sensors.append(sensor);queues.append(inbox);env.actors.append(sensor)
    for _ in range(25):
        frame = env.world.tick()
        for inbox in queues:
            next_image(inbox, frame)
    start_time = env.world.get_snapshot().timestamp.elapsed_seconds
    out.chmod(0o777)
    recorder_path = str((out/'world-recorder.log').resolve())
    recorder_result = env.client.start_recorder(recorder_path, True)
    box = env.ego.bounding_box.location
    config = {**vars(args), 'fps':60, 'width':1248, 'height':960, 'fov_degrees':65,
              'camera_relative_matrix':pose.get_matrix(), 'scene':env.metadata(),
              'vehicle_blueprint':env.ego.type_id, 'vehicle_color':env.ego.attributes.get('color'),
              'vehicle_bounds':{'location':[box.x,box.y,box.z]},
              'checkpoint_sha256':sha(args.checkpoint), 'checkpoint_step':saved['step'],
              'horn_contact':{'close_at_travel':.55,'release_below_travel':.45},
              'livery_revision':manifest['revision'], 'livery_layout':manifest['layoutVersion'],
              'recorder_start_result':recorder_result,
              'lamp_camera_matrix':light_pose.get_matrix(), 'lamp_camera_fov':35,
              'cabin':{'relative_matrix':cabin_pose.get_matrix(),'fov':90} if has_cabin else None,
              'claim':'One learned connectome core commands LF steering and RF horn joints. Route requests, rage-mode cue, traffic and speed/braking are directed.',
              'clock':'10 Hz neural decisions command fourteen fly joints at 300 Hz. Physics and CARLA advance 1/60 s together. Sound follows measured button state at displayed frame times.',
              'source_sha256':{p:sha(p) for p in [__file__, 'src/flyhard/driving_horn.py', 'src/flyhard/driving_horn_policy.py', 'src/flyhard/horn_rig.py', 'src/flyhard/dynamic_horn_world.py']}}
    (out/'config.json').write_text(json.dumps(config, indent=2)+'\n')
    writers = [video_writer(out/'carla-camera.mp4'), video_writer(out/'native-depth.mkv', True),
               video_writer(out/'traffic-light.mp4',size='320x240')]
    if has_cabin:
        writers.extend([video_writer(out/'cabin-rgb.mp4'),video_writer(out/'cabin-depth.mkv',True)])
    frames, body, activity, observations, commands, neural_times = [], [], [], [], [], []
    history = History()
    env.release()
    started = time.monotonic()
    try:
        for i in range(round(args.seconds*60)):
            t = i/60
            target = env.step_traffic(t, args.green_at, rig.horn.pressed)
            if i % 6 == 0:
                observed = env.observed(target)
                encoded = encode(history.update(observed))
                with torch.no_grad():
                    action, state = model(torch.tensor(encoded[None], device='cuda'), return_state=True)
                command = action[0].cpu().numpy()
                activity.append(state[:,0].cpu().numpy())
                observations.append(observed)
                commands.append(command)
                neural_times.append(t)
            for _ in range(5):
                rig.step_controls(command)
            steer = float(np.clip(rig.angle*1.7, -.85, .85))
            env.apply_measured(steer)
            # A slow native dolly keeps the arrival, road and car in view.
            side = -1 if args.kind != 'cut_in_cross' else 1
            relative = look_at([-9.,side*(6.5+.6*np.sin(t*.5)),4.8],[7.,0.,1.2])
            for sensor in sensors[:2]: sensor.set_transform(relative)
            frame = env.world.tick()
            images = [next_image(q, frame) for q in queues]
            assert len({im.timestamp for im in images}) == 1
            arrays = [np.frombuffer(im.raw_data,np.uint8).reshape(im.height,im.width,4)[:,:,:3][:,:,::-1].copy() for im in images]
            for writer, pixels in zip(writers, arrays):
                writer.stdin.write(pixels.tobytes())
            now = env.observed(target)
            camera_time = images[0].timestamp-start_time
            assert abs(camera_time-rig.data.time) < 1e-4
            row = {'index':i, 'body_index':i, 'neural_index':len(activity)-1,
                   'carla_frame':frame, 'depth_frame':images[1].frame,
                   'lamp_frame':images[2].frame,
                   'camera_time':camera_time, 'body_time':float(rig.data.time),
                   'light_red':bool(now[0]), 'light_green':bool(now[1]),
                   'lead_present':bool(now[2]), 'gap_m':float(now[3]), 'speed_m_s':float(now[5]),
                   'requested_angle':float(observations[-1][-1]), 'route_request_now':target,
                   'wheel_angle':rig.angle, 'applied_steer':steer,
                   'throttle':float(env.last_control.throttle),'brake':float(env.last_control.brake),
                   'nearby_ids':[item['actor'].id for item in env.traffic if item['actor'].get_location().distance(env.ego.get_location())<14.],
                   'traffic':[{'id':item['actor'].id,'role':item['role'],'matrix':item['actor'].get_transform().get_matrix(),'speed':item['actor'].get_velocity().length()} for item in env.traffic],
                   'stalk_angle':0., 'signal':'off', 'horn_pressed':bool(rig.horn.pressed),
                   'horn_travel':rig.horn.value,
                   'vehicle_matrix':env.ego.get_transform().get_matrix(),
                   'camera_matrix':sensors[0].get_transform().get_matrix(),
                   'lead_matrix':env.lead.get_transform().get_matrix() if env.lead else None}
            if has_cabin:
                row['cabin']={'rgb_frame':images[3].frame,'depth_frame':images[4].frame,
                              'camera_time':images[3].timestamp-start_time,
                              'relative_matrix':(np.linalg.inv(np.asarray(row['vehicle_matrix']))@
                                  np.asarray(sensors[3].get_transform().get_matrix())).tolist()}
            frames.append(row)
            body.append({'time':float(rig.data.time), 'qpos':rig.data.qpos.copy(),
                         'qvel':rig.data.qvel.copy(), 'ctrl':rig.data.ctrl.copy(), 'decision_index':len(activity)-1})
            with (out/'frames.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')
            preview_indices={0,100,200,400,round(args.seconds*60)-1}
            if i in preview_indices:
                Image.fromarray(arrays[0]).save(out/f'carla-preview-{i:04}.png')
                Image.fromarray(arrays[1]).save(out/f'depth-preview-{i:04}.png')
                if has_cabin:
                    Image.fromarray(arrays[3]).save(out/f'cabin-preview-{i:04}.png')
                    Image.fromarray(arrays[4]).save(out/f'cabin-depth-preview-{i:04}.png')
            if i % 120 == 0:
                Image.fromarray(arrays[0]).save(out/f'carla-preview-{i:04}.png')
                print(json.dumps({'frame':i, 'green':row['light_green'], 'horn':row['horn_pressed'],
                                  'travel':row['horn_travel'], 'wall_seconds':time.monotonic()-started}), flush=True)
    finally:
        for writer in writers:
            writer.stdin.close()
        codes = [writer.wait() for writer in writers]
        env.client.stop_recorder()
        (out/'frames.json').write_text(json.dumps(frames, indent=2)+'\n')
        if body:
            np.savez_compressed(out/'body-trace.npz', **{k:np.asarray([b[k] for b in body]) for k in body[0]})
            np.savez_compressed(out/'neural-trace.npz', activity=np.asarray(activity), time=neural_times,
                                context=np.asarray(observations), commands=np.asarray(commands))
        assert not any(codes), codes
    observed_green = next((r['camera_time'] for r in frames if r['light_green']), args.green_at)
    metrics = {'status':'capture_complete', 'frames':len(frames), 'native_fps':60,
               'wall_seconds':time.monotonic()-started,
               'max_clock_error_seconds':max(abs(r['camera_time']-r['body_time']) for r in frames),
               'actual_green_seconds':observed_green,
               'score':capture_score(args.kind,frames),
               'collisions':env.collision_events,
               'recorder_sha256':sha(recorder_path)}
    neural_green = np.asarray(observations)[:,1].astype(bool)
    displayed_green = np.array([r['light_green'] for r in frames])
    valid_light = (bool(neural_green.all() and displayed_green.all()) if args.kind not in {'empty','wait_green'}
                   else all(not s[0] and s[-1] and not np.any(np.diff(s.astype(int))<0) for s in [neural_green,displayed_green]))
    metrics['scenario_light_sequence_valid'] = bool(valid_light)
    if not valid_light:metrics['status']='invalid_scenario'
    (out/'metrics.json').write_text(json.dumps(metrics, indent=2)+'\n')
    print(json.dumps(metrics, indent=2), flush=True)
    assert valid_light, 'The actual observed/displayed light sequence differs from the intended scenario'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--asset', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--kind', choices=['empty','wait_green','arrive_green','cut_in_t','cut_in_cross','road_rage'], required=True)
    p.add_argument('--seconds', type=float, default=8.)
    p.add_argument('--green-at', type=float, default=4.8)
    args = p.parse_args()
    torch.set_num_threads(4)
    model, saved = load(args.checkpoint)
    env = DynamicHornWorld()
    try:
        capture(env, model, saved, args)
    finally:
        env.close()


if __name__ == '__main__':
    main()
