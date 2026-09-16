"""Synchronized alternative CARLA views; cameras never feed the policy."""
import math
from pathlib import Path
import queue

import carla
import imageio.v2 as imageio
import numpy as np
from PIL import Image


WIDTH, HEIGHT = 1248, 960


def look_at(position, target):
    delta = np.asarray(target) - position
    return carla.Transform(carla.Location(*map(float, position)), carla.Rotation(
        pitch=math.degrees(math.atan2(delta[2], np.linalg.norm(delta[:2]))),
        yaw=math.degrees(math.atan2(delta[1], delta[0]))))


def orbit_pose(seconds):
    # Travel from the sponsor-covered left rear, around the nose, to the right.
    theta = math.radians(-145 + 22 * seconds)
    return look_at([6.1 * math.cos(theta), 6.1 * math.sin(theta), 2.55], [0, 0, .85])


class ShotCameras:
    def __init__(self, env, root):
        self.env, self.root = env, Path(root)
        self.views = {}
        poses = {
            'orbit': (orbit_pose(0), 65),
            'indicator': (look_at([3.25, 1.95, .9], [1.96, .75, .62]), 48),
            'cabin': (carla.Transform(carla.Location(x=-.45, y=.08, z=1.35),
                                     carla.Rotation(pitch=-12, yaw=-23)), 90),
        }
        for name, (pose, fov) in poses.items():
            directory = self.root / 'cameras' / name
            (directory / 'depth').mkdir(parents=True)
            sensors, inboxes = [], []
            for kind in ['rgb', 'depth']:
                bp = env.world.get_blueprint_library().find('sensor.camera.' + kind)
                for key, value in {'image_size_x': str(WIDTH), 'image_size_y': str(HEIGHT),
                                   'fov': str(fov), 'sensor_tick': '0.0'}.items():
                    bp.set_attribute(key, value)
                if kind == 'rgb':
                    bp.set_attribute('motion_blur_intensity', '0.0')
                sensor = env.world.spawn_actor(bp, pose, attach_to=env.ego,
                                               attachment_type=carla.AttachmentType.Rigid)
                inbox = queue.Queue(); sensor.listen(inbox.put)
                sensors.append(sensor); inboxes.append(inbox); env.actors.append(sensor)
            writer = imageio.get_writer(directory / 'rgb.mp4', fps=20, codec='libx264',
                macro_block_size=1, ffmpeg_params=['-crf', '15', '-preset', 'ultrafast', '-threads', '2'])
            self.views[name] = {'sensors': sensors, 'inboxes': inboxes, 'pose': pose,
                                'fov': fov, 'writer': writer, 'directory': directory}

    def advance(self, seconds):
        view = self.views['orbit']; view['pose'] = orbit_pose(seconds)
        for sensor in view['sensors']:
            sensor.set_transform(view['pose'])

    def capture(self, index, frame, timestamp):
        metadata = {}
        for name, view in self.views.items():
            images = []
            for inbox in view['inboxes']:
                while True:
                    image = inbox.get(timeout=60)
                    if image.frame >= frame:
                        assert image.frame == frame and abs(image.timestamp - timestamp) < 1e-6
                        images.append(image); break
            arrays = [np.frombuffer(im.raw_data, np.uint8).reshape(HEIGHT, WIDTH, 4)[:, :, :3][:, :, ::-1].copy() for im in images]
            view['writer'].append_data(arrays[0])
            Image.fromarray(arrays[1]).save(view['directory'] / 'depth' / f'{index:05}.png', compress_level=1)
            if index in [0, 60, 80, 90, 110, 160, 220, 240]:
                Image.fromarray(arrays[0]).save(view['directory'] / f'preview-{index:04}.png')
            world_matrix = np.asarray(view['sensors'][0].get_transform().get_matrix())
            actual_relative = np.linalg.inv(np.asarray(self.env.ego.get_transform().get_matrix())) @ world_matrix
            pose_error = float(np.max(np.abs(actual_relative - np.asarray(view['pose'].get_matrix()))))
            assert pose_error < .0002, (name, pose_error)
            metadata[name] = {'rgb_frame': images[0].frame, 'depth_frame': images[1].frame,
                              'timestamp': images[0].timestamp, 'fov': view['fov'],
                              'relative_matrix': view['pose'].get_matrix(),
                              'world_matrix': world_matrix.tolist(), 'pose_error': pose_error}
        return metadata

    def close(self):
        for view in self.views.values():
            view['writer'].close()
