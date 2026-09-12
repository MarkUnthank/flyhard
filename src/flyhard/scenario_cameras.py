"""Three synchronized views of a traffic scenario. Cameras never feed the policy.

wide   world-fixed at the point of interest, so the car and the other road user
       are both in frame and the cause of a stop is readable.
chase  rigidly attached behind and above the car.
cabin  rigidly attached inside, over the fly's controls.

The wide view is deliberately not attached to the car: a scenario is about what
the car does relative to something else, and an ego-mounted wide shot hides that.
Every view also captures depth, which the sponsor compositor needs.
"""
import json
import math
from pathlib import Path
import queue

import carla
import imageio.v2 as imageio
import numpy as np
from PIL import Image

WIDTH, HEIGHT = 1248, 960
ATTACHED = {
    # Behind and above, looking slightly down over the roof.
    'chase': (carla.Transform(carla.Location(x=-7.4, y=0., z=3.05),
                              carla.Rotation(pitch=-11.5, yaw=0.)), 72),
    # Inside, over the wheel and pedals.
    'cabin': (carla.Transform(carla.Location(x=-.45, y=.08, z=1.35),
                              carla.Rotation(pitch=-12, yaw=-23)), 90),
}


def look_at(position, target):
    delta = np.asarray(target, float)-np.asarray(position, float)
    return carla.Transform(carla.Location(*map(float, position)), carla.Rotation(
        pitch=math.degrees(math.atan2(delta[2], np.linalg.norm(delta[:2]))),
        yaw=math.degrees(math.atan2(delta[1], delta[0]))))


def wide_pose(focus, approach_yaw, *, back=17., side=11., height=6.2):
    """Place the wide camera off the near side of the approach, looking at the focus.

    `focus` is the world location the scenario is about, usually the crossing or
    junction, and `approach_yaw` is the ego's heading in degrees.
    """
    focus = np.asarray([focus.x, focus.y, focus.z], float)
    heading = math.radians(approach_yaw)
    forward = np.array([math.cos(heading), math.sin(heading), 0.])
    right = np.array([-math.sin(heading), math.cos(heading), 0.])
    position = focus-forward*back+right*side+np.array([0., 0., height])
    return look_at(position, focus+np.array([0., 0., .9]))


class ScenarioCameras:
    def __init__(self, env, root, focus, approach_yaw, fps=20):
        self.env, self.root, self.fps = env, Path(root), fps
        # Render at the capture rate, not at the physics rate. CARLA steps physics
        # several times per control period, and rendering six sensors on every one of
        # those steps only to throw two frames in three away tripled the cost of a take.
        self.tick = 1./fps
        self.frames = []
        self.views = {}
        poses = dict(ATTACHED)
        poses['wide'] = (wide_pose(focus, approach_yaw), 50)
        for name, (pose, fov) in poses.items():
            attached = name in ATTACHED
            directory = self.root/'cameras'/name
            (directory/'depth').mkdir(parents=True, exist_ok=True)
            sensors, inboxes = [], []
            for kind in ['rgb', 'depth']:
                bp = env.world.get_blueprint_library().find('sensor.camera.'+kind)
                for key, value in {'image_size_x': str(WIDTH), 'image_size_y': str(HEIGHT),
                                   'fov': str(fov), 'sensor_tick': f'{self.tick:.6f}'}.items():
                    bp.set_attribute(key, value)
                if kind == 'rgb':
                    bp.set_attribute('motion_blur_intensity', '0.0')
                sensor = (env.world.spawn_actor(bp, pose, attach_to=env.ego,
                                                attachment_type=carla.AttachmentType.Rigid)
                          if attached else env.world.spawn_actor(bp, pose))
                inbox = queue.Queue()
                sensor.listen(inbox.put)
                sensors.append(sensor)
                inboxes.append(inbox)
                env.actors.append(sensor)
            writer = imageio.get_writer(directory/'rgb.mp4', fps=fps, codec='libx264',
                                        macro_block_size=1,
                                        ffmpeg_params=['-crf', '15', '-preset', 'ultrafast', '-threads', '2'])
            self.views[name] = {'sensors': sensors, 'inboxes': inboxes, 'pose': pose, 'fov': fov,
                                'writer': writer, 'directory': directory, 'attached': attached}

    def capture(self, index, frame, timestamp):
        """Pull one synchronized frame per view. Returns per-view metadata for the receipt.

        `relative_matrix` is the camera pose in the vehicle frame, which is what
        SponsorView needs; it is recomputed each frame for the unattached wide view.
        """
        vehicle = np.asarray(self.env.ego.get_transform().get_matrix())
        # Sensors fire once per capture period, so exactly one image is waiting per
        # sensor. Its frame lands anywhere inside the period depending on the phase
        # CARLA happened to start on; anything older than a full period is stale.
        period = max(1, round(1./self.fps/self.env.dt))
        metadata = {}
        for name, view in self.views.items():
            images = []
            for inbox in view['inboxes']:
                while True:
                    image = inbox.get(timeout=60)
                    if image.frame > frame-period:
                        images.append(image)
                        break
            assert images[0].frame == images[1].frame, (name, images[0].frame, images[1].frame)
            arrays = [np.frombuffer(im.raw_data, np.uint8).reshape(HEIGHT, WIDTH, 4)[:, :, :3][:, :, ::-1].copy()
                      for im in images]
            view['writer'].append_data(arrays[0])
            Image.fromarray(arrays[1]).save(view['directory']/'depth'/f'{index:05}.png', compress_level=1)
            world = np.asarray(view['sensors'][0].get_transform().get_matrix())
            relative = np.linalg.inv(vehicle)@world
            entry = {'rgb_frame': images[0].frame, 'depth_frame': images[1].frame,
                     'timestamp': images[0].timestamp, 'frame_lag': int(frame-images[0].frame),
                     'fov': view['fov'], 'attached': view['attached'],
                     'relative_matrix': relative.tolist(), 'world_matrix': world.tolist()}
            if view['attached']:
                # A rigid mount must not drift; the wide view legitimately moves in the vehicle frame.
                error = float(np.max(np.abs(relative-np.asarray(view['pose'].get_matrix()))))
                assert error < .0002, (name, error)
                entry['pose_error'] = error
            metadata[name] = entry
        # Kept, not just returned: the sponsor compositor needs the per-frame camera
        # pose in the vehicle frame, and without it the footage cannot be sponsored
        # later without re-running CARLA.
        self.frames.append({'index': index, 'frame': frame, 'timestamp': timestamp,
                            'views': metadata})
        return metadata

    def relative_paths(self):
        """Camera map for a clips.Take, relative to the take directory."""
        return {name: f'cameras/{name}/rgb.mp4' for name in self.views}

    def close(self):
        for view in self.views.values():
            view['writer'].close()
        (self.root/'cameras.json').write_text(json.dumps(
            {'width': WIDTH, 'height': HEIGHT, 'fps': self.fps,
             'views': {name: {'fov': view['fov'], 'attached': view['attached'],
                              'rgb': f'cameras/{name}/rgb.mp4',
                              'depth': f'cameras/{name}/depth'}
                       for name, view in self.views.items()},
             'frames': self.frames}, indent=1)+'\n')
