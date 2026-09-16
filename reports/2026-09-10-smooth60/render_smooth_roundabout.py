#!/usr/bin/env python3
"""Render the saved 3D world and body trajectories at 60 output frames/second."""
import argparse
import hashlib
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
from PIL import Image, ImageDraw, ImageFont
from OpenGL import GL

from flyhard.cockpit import WheelRig
from flyhard.interior_view import InteriorFlyView
from flyhard.live_livery import verify_live_livery
from flyhard.shot_cameras import look_at, orbit_pose
from flyhard.sponsor_view import SponsorView
from flyhard.steering_hud import draw_steering_readout
from flyhard.video_branding import draw_site_brand


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoder(path, width, height):
    return subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', '60', '-i', 'pipe:0', '-an',
        '-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '18', '-b:v', '0',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], stdin=subprocess.PIPE)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True); p.add_argument('--out', required=True)
    p.add_argument('--asset', required=True); p.add_argument('--previews', action='store_true')
    args = p.parse_args(); root, out = Path(args.run), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = verify_live_livery(args.asset, out)
    frames = json.loads((root / 'frames.json').read_text())
    config = json.loads((root / 'config.json').read_text())
    original_plan = json.loads((root / 'edit-plan.json').read_text())
    edit = json.loads(Path('configs/roundabout-edit-25s.json').read_text())
    timeline = []
    for shot in edit['shots'][:-1]:
        count = shot['output_frames'] * 3
        start = 10 + shot['source_start']
        # Stop within the recorded trajectory, before CARLA switches to autopilot.
        end = min(10 + shot['source_end'], 279.)
        framing = original_plan['frames'][start]
        timeline.extend({'source_index': start + j / count * (end - start),
                         'camera': framing['camera'], 'title': framing['title'],
                         'body_closeup': framing['body_closeup']} for j in range(count))
    assert len(timeline) == 1380
    with np.load(root / 'body-trace.npz') as archive:
        body = {k: archive[k] for k in archive.files}
    with imageio.get_reader(root / 'cns-layer.mp4') as reader:
        neural = [reader.get_next_data() for _ in frames]
    rig = WheelRig(indicator_stalk=True); replay = mj.MjData(rig.model)
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body('wheel').id, :3] = [.30, .30, .30]
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body('indicator_stalk').id, :3] = [.95, .48, .08]
    cabin_pose = frames[0]['cameras']['cabin']['relative_matrix']
    cabin = InteriorFlyView(rig, 1248, 960, cabin_pose, [.27, -.41, 1.03], metres_per_rig_unit=.16, horizontal_fov=90)
    renderer = mj.Renderer(rig.model, height=440, width=600)
    sponsor = SponsorView(args.asset, manifest, config['vehicle_bounds']['location'])
    body_camera = mj.MjvCamera()
    fonts = {n: ImageFont.truetype('assets/fonts/Geist.ttf', n) for n in [22, 24, 28]}
    velocity = np.zeros(rig.model.nv)
    client = carla.Client('localhost', 2000); client.set_timeout(90)
    client.stop_replayer(False)
    world = client.get_world()
    if world.get_map().name.split('/')[-1] != 'Town03': world = client.load_world('Town03')
    for actor in world.get_actors().filter('vehicle.*'): actor.destroy()
    original_settings = world.get_settings()
    settings = world.get_settings(); settings.synchronous_mode = True
    settings.fixed_delta_seconds = .05; settings.no_rendering_mode = True
    world.apply_settings(settings); world.set_weather(carla.WeatherParameters.ClearNoon)
    client.set_replayer_time_factor(1.)
    client.replay_file(str((root / 'world-recorder.log').resolve()), 0., 0., 0, False)
    for _ in range(11): world.tick()
    ego = next(a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name') == 'hero')
    previous_source = 10.
    client.set_replayer_time_factor(0.)
    settings.fixed_delta_seconds = 1 / 60; settings.no_rendering_mode = False
    world.apply_settings(settings)
    sensors, inboxes = [], []; last_camera = None
    video = None if args.previews else encoder(out / 'flyhard-smooth-60fps.mp4', 1920, 1080)
    native_video = None if args.previews else encoder(out / 'native-camera-60fps.mp4', 1248, 960)
    if not args.previews: (out / 'native-depth').mkdir(exist_ok=True)
    started = time.perf_counter(); records = []; poses = []; sponsor_counts = []
    wanted = {60, 450, 630, 900, 1170, 1320}
    try:
        for output_index, shot in enumerate(timeline):
            if args.previews and output_index not in wanted: continue
            source = math.floor(shot['source_index']) if args.previews else shot['source_index']
            lower = int(source); upper = min(lower + 1, len(frames) - 1)
            mix = source - lower; record = frames[lower]; name = shot['camera']
            if name == 'orbit': pose, fov = orbit_pose(source * .05), 65
            elif name == 'indicator': pose, fov = look_at([3.25, 1.95, .9], [1.96, .75, .62]), 48
            elif name == 'cabin':
                pose, fov = carla.Transform(carla.Location(x=-.45, y=.08, z=1.35), carla.Rotation(pitch=-12, yaw=-23)), 90
            else:
                pose, fov = carla.Transform(carla.Location(x=5.2, y=3.8, z=2.9), carla.Rotation(pitch=-16.4, yaw=-143.8)), 65
            if name != last_camera:
                client.set_replayer_time_factor(0.)
                for sensor in sensors: sensor.stop(); sensor.destroy()
                sensors, inboxes = [], []
                for kind in ['rgb', 'depth']:
                    bp = world.get_blueprint_library().find('sensor.camera.' + kind)
                    for key, value in {'image_size_x': '1248', 'image_size_y': '960', 'fov': str(fov), 'sensor_tick': '0.0'}.items(): bp.set_attribute(key, value)
                    if kind == 'rgb': bp.set_attribute('motion_blur_intensity', '0.0')
                    sensor = world.spawn_actor(bp, pose, attach_to=ego, attachment_type=carla.AttachmentType.Rigid)
                    inbox = queue.Queue(); sensor.listen(inbox.put)
                    sensors.append(sensor); inboxes.append(inbox)
                # Streaming/exposure warms while the recorded trajectory stays paused.
                for _ in range(60 if last_camera is None else 8): world.tick()
                last_camera = name
            for sensor in sensors: sensor.set_transform(pose)
            if args.previews:
                # Large seeks discard intermediate recorder positions. Cross one
                # further source interval to restore the correct adjacent pair.
                client.set_replayer_time_factor(max(0., (source - previous_source - 1) * 3))
                world.tick()
                client.set_replayer_time_factor(3.)
                world.tick()
                client.set_replayer_time_factor(0.)
                for _ in range(5): world.tick()
            else:
                client.set_replayer_time_factor(max(0., (source - previous_source) * 3))
            frame_id = world.tick(); previous_source = source
            images = []
            for inbox in inboxes:
                while True:
                    img = inbox.get(timeout=60)
                    if img.frame >= frame_id:
                        assert img.frame == frame_id
                        images.append(img); break
            assert images[0].timestamp == images[1].timestamp
            arrays = [np.frombuffer(im.raw_data, np.uint8).reshape(960,1248,4)[:, :, :3][:, :, ::-1].copy() for im in images]
            raw, packed_depth = arrays
            d = packed_depth.astype(np.float32)
            depth = (d[:, :, 0] + 256*d[:, :, 1] + 65536*d[:, :, 2]) * (1000 / 16777215)
            position = np.asarray(ego.get_transform().get_matrix())[:3, 3]
            expected = (1-mix)*np.asarray(frames[lower]['vehicle_matrix'])[:3,3] + mix*np.asarray(frames[upper]['vehicle_matrix'])[:3,3]
            error = float(np.linalg.norm(position-expected))
            if not args.previews: assert error < .12, (output_index, source, error)
            if native_video:
                native_video.stdin.write(raw.tobytes())
                Image.fromarray(packed_depth).save(out / 'native-depth' / f'{output_index:05}.png', compress_level=1)
            # MuJoCo's position interpolation handles hinge, ball and free joints.
            mj.mj_differentiatePos(rig.model, velocity, 1., body['qpos'][lower], body['qpos'][upper])
            replay.qpos[:] = body['qpos'][lower]
            mj.mj_integratePos(rig.model, replay.qpos, velocity, mix)
            replay.qvel[:] = (1-mix)*body['qvel'][lower] + mix*body['qvel'][upper]
            replay.ctrl[:] = body['ctrl'][lower]; replay.time = (1-mix)*body['time'][lower] + mix*body['time'][upper]
            mj.mj_forward(rig.model, replay)
            if name == 'cabin':
                raw, _, _ = cabin.render(replay, raw, depth)
                raw = np.asarray(Image.fromarray(raw).crop((110,190,1085,940)).resize((1248,960),Image.Resampling.LANCZOS))
                sponsor_pixels = 0
            else:
                raw, sponsor_pixels = sponsor.render(pose.get_matrix(), fov, raw, depth)
            if shot['body_closeup']:
                body_camera.lookat[:] = rig.stalk.center + [-.15,-.1,.22]
                body_camera.distance = 2.7; body_camera.azimuth = -105; body_camera.elevation = -17
            else:
                body_camera.lookat[:] = [.2,0,1.1]; body_camera.distance = 5.; body_camera.azimuth = 125; body_camera.elevation = -24
            renderer.update_scene(replay, camera=body_camera, scene_option=cabin.option)
            renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
            canvas = Image.new('RGB',(1920,1080),'black')
            canvas.paste(Image.fromarray(raw),(24,64)); canvas.paste(Image.fromarray(neural[lower]),(1296,64))
            canvas.paste(Image.fromarray(renderer.render()),(1296,584))
            draw = ImageDraw.Draw(canvas)
            draw.text((24,23),shot['title'],font=fonts[24],fill='#eee')
            draw.text((990,38),'SLOW MOTION',anchor='rm',font=fonts[22],fill='#aaa')
            draw.text((1272,23),f"{record['speed_m_s']*3.6:.0f} km/h",anchor='ra',font=fonts[28],fill='white')
            draw.text((1296,23),'Neural activity',font=fonts[24],fill='#eee')
            draw.text((1296,540),'Foreleg + stalk' if shot['body_closeup'] else 'Fly',font=fonts[24],fill='#eee')
            signal = record['applied_signal'].upper()
            draw.text((1896,540),'SIGNAL '+signal,anchor='ra',font=fonts[24],fill='#ffbd59' if signal!='OFF' else '#999')
            wheel_angle = float(replay.qpos[rig.wheel_qpos])
            draw_steering_readout(canvas,requested_angle=record['requested_angle'],wheel_angle=wheel_angle,applied_steer=record['applied_steer'])
            stalk_angle = (1-mix)*record['stalk_angle'] + mix*frames[upper]['stalk_angle']
            draw.text((970,1052),f'Stalk {np.degrees(stalk_angle):+.1f}°',anchor='mm',font=fonts[24],fill='#ddd')
            draw_site_brand(canvas)
            if video: video.stdin.write(np.asarray(canvas).tobytes())
            if output_index in wanted: canvas.save(out / f'preview-{output_index:04}.png')
            records.append({'output_frame':output_index,'output_time':output_index/60,'source_index':source,
                'camera':name,'native_frame':frame_id,'native_timestamp':images[0].timestamp,'position_error_m':error,
                'body_time':float(replay.time),'neural_index':lower,'wheel_angle':wheel_angle,'stalk_angle':stalk_angle,
                'requested_angle':record['requested_angle'],'applied_steer':record['applied_steer'],
                'signal':signal,'sponsor_pixels':sponsor_pixels})
            poses.append(replay.qpos.copy()); sponsor_counts.append(sponsor_pixels)
            if output_index % 60 == 0 or args.previews:
                print(json.dumps({'frame':output_index,'total':1380,'camera':name,'source_index':source,'pose_error':error,'sponsor_pixels':sponsor_pixels,'wall_seconds':time.perf_counter()-started}),flush=True)
        if video:
            card = Image.new('RGB',(1920,1080),'black'); draw=ImageDraw.Draw(card)
            lines=['Vehicle: CARLA 0.9.16 · CVC, Universitat Autònoma de Barcelona',
                   'Connectome: MaleCNS / Janelia · Fly: NeuroMechFly / FlyGym, EPFL',
                   f"Sponsor livery: revision {manifest['revision']} · layout {manifest['layoutVersion']}",
                   '60 fps replay of recorded 3D motion · cabin fly and sponsor surfaces composited']
            for j,line in enumerate(lines): draw.text((960,440+j*50),line,anchor='mm',font=fonts[24],fill='#ddd')
            draw_site_brand(card)
            for _ in range(120): video.stdin.write(np.asarray(card).tobytes())
    finally:
        client.set_replayer_time_factor(0.)
        for sensor in sensors: sensor.stop(); sensor.destroy()
        for writer in [video,native_video]:
            if writer:
                writer.stdin.close()
                if writer.wait()!=0: raise RuntimeError('Video encoding failed')
        client.stop_replayer(False)
        for actor in world.get_actors().filter('vehicle.*'): actor.destroy()
        world.apply_settings(original_settings)
        # PyRender terminates its EGL display; free MuJoCo contexts first.
        renderer.close(); cabin.close(); sponsor.close()
    np.savez_compressed(out / 'rendered-body.npz',qpos=np.asarray(poses))
    receipt={'status':'previewed' if args.previews else 'rendered','fps':60,'frames':len(records)+(0 if args.previews else 120),
        'duration_seconds':25,'native_motion_frames':len(records),'same_recorded_episode':True,
        'motion_method':'CARLA recorder trajectory interpolation and MuJoCo joint-position interpolation at output timestamps',
        'neural_activity':'Original recorded samples held until the next measured sample; no synthetic neural activations',
        'sponsor_revision':manifest['revision'],'sponsor_layout':manifest['layoutVersion'],
        'sponsor_count':len(manifest['sponsors']),'maximum_position_error_m':max(x['position_error_m'] for x in records),
        'source_body_sha256':sha(root/'body-trace.npz'),'world_recorder_sha256':sha(root/'world-recorder.log'),
        'source_geometry_sha256':sha(Path(args.asset)/'render-panels.npz'),'wall_seconds':time.perf_counter()-started,
        'frame_map':records}
    if video: receipt['video_sha256']=sha(out/'flyhard-smooth-60fps.mp4')
    (out/'render-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='frame_map'},indent=2),flush=True)


if __name__=='__main__': main()
