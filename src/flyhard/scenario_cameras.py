"""Three synchronized views of a traffic scenario. Cameras never feed the policy.

wide   world-fixed at the point of interest, so the car and the other road user
       are both in frame and the cause of a stop is readable.
chase  rigidly attached behind and above the car.
cabin  rigidly attached inside, over the fly's controls.

The wide view is deliberately not attached to the car: a scenario is about what
the car does relative to something else, and an ego-mounted wide shot hides that.
A scenario that travels hundreds of metres sets its own attached wide camera.

Every view also captures depth, and the sponsor layer is composited against it as
each frame arrives rather than afterwards. Writing depth out was costing about half
a second per control step, three times everything else in the loop put together, so
it is used in memory and discarded. Both the clean and the sponsored video are kept.
"""
import json
import math
from pathlib import Path
import queue
import threading
import time

import carla
import imageio.v2 as imageio
import numpy as np

WIDTH, HEIGHT = 1248, 960
ATTACHED = {
    # Behind and above, looking slightly down over the roof.
    'chase': (carla.Transform(carla.Location(x=-7.4, y=0., z=3.05),
                              carla.Rotation(pitch=-11.5, yaw=0.)), 72),
    # Inside, over the wheel and pedals.
    'cabin': (carla.Transform(carla.Location(x=-.45, y=.08, z=1.35),
                              carla.Rotation(pitch=-12, yaw=-23)), 90),
}


def depth_metres(rgb):
    """CARLA packs depth into 24 bits across the colour channels, scaled to 1 km."""
    packed = (rgb[:, :, 0].astype(np.float32)+rgb[:, :, 1].astype(np.float32)*256.
              + rgb[:, :, 2].astype(np.float32)*65536.)
    return 1000.*packed/(256.**3-1)


class Encoder:
    """One video stream, written from its own thread.

    Handing a frame to ffmpeg means copying a few megabytes down a pipe and waiting.
    Five streams did that one after another inside the capture loop, which cost more
    than everything else in the loop put together. The frames still arrive in order and
    the queue is bounded, so a slow encoder pushes back rather than eating memory.
    """

    def __init__(self, writer, depth=8):
        self.writer = writer
        self.queue = queue.Queue(maxsize=depth)
        self.failure = None
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _drain(self):
        while True:
            frame = self.queue.get()
            if frame is None:
                return
            try:
                self.writer.append_data(frame)
            except Exception as exc:            # Surfaced on the next append or close.
                self.failure = exc
                return

    def append_data(self, frame):
        if self.failure is not None:
            raise self.failure
        self.queue.put(frame)

    def close(self):
        self.queue.put(None)
        self.thread.join(timeout=300)
        self.writer.close()
        if self.failure is not None:
            raise self.failure


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
    def __init__(self, env, root, focus, approach_yaw, fps=20, wide_attached=None,
                 sponsor=None, sponsored_views=('wide', 'chase')):
        self.env, self.root, self.fps = env, Path(root), fps
        self.sponsor = sponsor
        self.sponsored_views = set(sponsored_views) if sponsor else set()
        self.sponsor_pixels = {}
        # Render at the capture rate, not at the physics rate. CARLA steps physics
        # several times per control period, and rendering six sensors on every one of
        # those steps only to throw two frames in three away tripled the cost of a take.
        self.tick = 1./fps
        self.frames = []
        self.views = {}
        # Where the capture loop's time goes. Cheap enough to leave on: six perf_counter
        # calls a step against a step that costs hundreds of milliseconds.
        self.timing = {'sensor_wait': 0., 'decode': 0., 'encode': 0., 'sponsor': 0.,
                       'total': 0., 'steps': 0}
        poses = dict(ATTACHED)
        # A world-fixed wide shot reads best when the scenario happens in one place. On
        # a scenario that covers hundreds of metres the world sets its own wide camera,
        # attached but far enough out that it is still a wide shot.
        attached_wide = wide_attached or (env.wide_attached() if hasattr(env, 'wide_attached')
                                          else None)
        if attached_wide:
            ATTACHED_WIDE = {'wide': attached_wide}
            poses.update(ATTACHED_WIDE)
            self.attached_names = set(ATTACHED) | {'wide'}
        else:
            poses['wide'] = (wide_pose(focus, approach_yaw), 50)
            self.attached_names = set(ATTACHED)
        for name, (pose, fov) in poses.items():
            attached = name in self.attached_names
            directory = self.root/'cameras'/name
            directory.mkdir(parents=True, exist_ok=True)
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
            def open_writer(filename):
                return Encoder(imageio.get_writer(
                    directory/filename, fps=fps, codec='libx264', macro_block_size=1,
                    ffmpeg_params=['-crf', '15', '-preset', 'ultrafast', '-threads', '2']))
            self.views[name] = {'sensors': sensors, 'inboxes': inboxes, 'pose': pose, 'fov': fov,
                                'writer': open_writer('rgb.mp4'), 'directory': directory,
                                'attached': attached,
                                'sponsored': open_writer('rgb-sponsored.mp4')
                                             if name in self.sponsored_views else None}
            self.sponsor_pixels[name] = 0

    def capture(self, index, frame, timestamp):
        """Pull one synchronized frame per view. Returns per-view metadata for the receipt.

        `relative_matrix` is the camera pose in the vehicle frame, which is what
        SponsorView needs; it is recomputed each frame for the unattached wide view.
        """
        clock = self.timing
        started = time.perf_counter()
        vehicle = np.asarray(self.env.ego.get_transform().get_matrix())
        # Sensors fire once per capture period, so exactly one image is waiting per
        # sensor. Its frame lands anywhere inside the period depending on the phase
        # CARLA happened to start on; anything older than a full period is stale.
        period = max(1, round(1./self.fps/self.env.dt))
        metadata = {}
        for name, view in self.views.items():
            images = []
            waited = time.perf_counter()
            for inbox in view['inboxes']:
                while True:
                    image = inbox.get(timeout=60)
                    if image.frame > frame-period:
                        images.append(image)
                        break
            clock['sensor_wait'] += time.perf_counter()-waited
            assert images[0].frame == images[1].frame, (name, images[0].frame, images[1].frame)
            mark = time.perf_counter()
            arrays = [np.frombuffer(im.raw_data, np.uint8).reshape(HEIGHT, WIDTH, 4)[:, :, :3][:, :, ::-1].copy()
                      for im in images]
            clock['decode'] += time.perf_counter()-mark
            mark = time.perf_counter()
            view['writer'].append_data(arrays[0])
            clock['encode'] += time.perf_counter()-mark
            if view['sponsored'] is not None:
                mark = time.perf_counter()
                composited, covered = self.sponsor.render(
                    np.linalg.inv(vehicle)@np.asarray(view['sensors'][0].get_transform().get_matrix()),
                    view['fov'], arrays[0], depth_metres(arrays[1]))
                clock['sponsor'] += time.perf_counter()-mark
                mark = time.perf_counter()
                view['sponsored'].append_data(composited)
                clock['encode'] += time.perf_counter()-mark
                self.sponsor_pixels[name] += covered
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
        clock['total'] += time.perf_counter()-started
        clock['steps'] += 1
        return metadata

    def timing_report(self):
        """Milliseconds per control step in each stage of capture, for tuning runs."""
        steps = max(self.timing['steps'], 1)
        return {k: round(v/steps*1000, 2) for k, v in self.timing.items() if k != 'steps'}

    def relative_paths(self, sponsored=False):
        """Camera map for a clips.Take, relative to the take directory."""
        return {name: (f'cameras/{name}/rgb-sponsored.mp4'
                       if sponsored and view['sponsored'] is not None
                       else f'cameras/{name}/rgb.mp4')
                for name, view in self.views.items()}

    def close(self):
        for view in self.views.values():
            view['writer'].close()
            if view['sponsored'] is not None:
                view['sponsored'].close()
        (self.root/'cameras.json').write_text(json.dumps(
            {'width': WIDTH, 'height': HEIGHT, 'fps': self.fps,
             'views': {name: {'fov': view['fov'], 'attached': view['attached'],
                              'rgb': f'cameras/{name}/rgb.mp4',
                              'sponsored': (f'cameras/{name}/rgb-sponsored.mp4'
                                            if view['sponsored'] is not None else None),
                              'sponsor_pixels': int(self.sponsor_pixels[name])}
                       for name, view in self.views.items()},
             'depth': 'used live for the sponsor composite and not written; re-compositing '
                      'with correct occlusion would need another CARLA pass',
             'frames': self.frames}, indent=1)+'\n')
