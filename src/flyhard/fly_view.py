"""Draw the fly and its controls into the cabin view of a recorded take.

The cabin camera looks at the place a driver's wheel and pedals would be, and until
now that place was empty: the fly was only ever shown in a panel beside the car. This
renders the same MuJoCo rig that produced the trial's pedal travel, from the cabin
camera's own pose, and composites it into the frame.

Nothing here is re-simulated. The rig is replayed from the control demands the trial
recorded, tick for tick, so what you see working the pedals is the run that happened.

Two presentation choices are stated rather than hidden. The rig is modelled at the
fly's own scale, where the wheel is about two body lengths across, so it is drawn at
WHEEL_DIAMETER to read on screen at all; and the composite is a plain alpha blend,
because the cabin depth buffer is not kept, so the rig is never hidden behind the
dashboard. Neither affects a recorded metric, a trajectory or a control value.
"""
import math

import mujoco as mj
import numpy as np

# Where the rig's wheel hub sits in the car's own frame, in metres. Solved from the
# cabin camera's own pose rather than guessed: it is the point 0.72 m along the ray
# through the pixel where the Mini's own wheel sits, so the fly's controls land on the
# car's, and the fly ends up between them and the camera, which is where a driver is.
HUB_IN_CAR = (0.133, -0.271, 1.114)
WHEEL_DIAMETER = 0.19     # Metres on screen. The rig's own wheel is 1.94 fly lengths.
REPLAY_STEPS = 10         # Physics steps per control tick, matching the evaluator.
REFLECT = np.array([1., -1., 1.])   # CARLA is left handed where MuJoCo is right handed.


def free_camera(position, forward, distance=2.5):
    """MuJoCo free camera placed at `position` looking along `forward`.

    A free camera is lookat plus azimuth, elevation and distance, which is five degrees
    of freedom and no roll. The cabin camera has no roll either, so this is exact
    rather than an approximation. MuJoCo's angles give the viewing direction itself and
    it then steps back along that direction by `distance`, which is checked in the tests
    rather than assumed; getting the sign wrong puts the camera through the subject.
    """
    forward = np.asarray(forward, float)
    forward = forward/max(np.linalg.norm(forward), 1e-9)
    camera = mj.MjvCamera()
    camera.type = mj.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = np.asarray(position, float)+forward*distance
    camera.distance = distance
    camera.azimuth = math.degrees(math.atan2(forward[1], forward[0]))
    camera.elevation = math.degrees(math.asin(float(np.clip(forward[2], -1., 1.))))
    return camera


class FlyView:
    def __init__(self, width, height, hub=HUB_IN_CAR, wheel_diameter=WHEEL_DIAMETER):
        from flyhard.parking_rig import make_parking_rig
        self.width, self.height = int(width), int(height)
        self.rig = make_parking_rig()
        self.rig.prepare_controls()
        self.rig.reset()
        self.hub = np.asarray(hub, float)
        self.scale = float(wheel_diameter)/(2*self.rig.radius)
        self.model = self.rig.model
        self.renderer = mj.Renderer(self.model, height=self.height, width=self.width)
        # Hide the test stand: it is the bench the rig is measured on, not part of a
        # car. The pedals, selector and wheel stay, because the fly is working them.
        self.option = mj.MjvOption()
        self.model.geom_group[self.model.geom_bodyid == 0] = 5
        self.option.geomgroup[5] = 0
        self.stand = {i for i in range(self.model.ngeom) if self.model.geom_bodyid[i] == 0}
        self.model.geom_rgba[self.model.geom_bodyid == self.model.body('wheel').id, :3] = .32

    def replay(self, steer, throttle, brake):
        """Advance the rig by one control tick of the trial's own demands."""
        targets = self.rig.diagnostic_drive_action(float(steer)/.5, float(throttle),
                                                   float(brake), 1)
        for _ in range(REPLAY_STEPS):
            self.rig.step_drive(targets)

    def camera_for(self, relative, fov):
        """Place the MuJoCo camera where the cabin camera is, in the rig's own frame."""
        relative = np.asarray(relative, float)
        # The rig is anchored by its wheel centre, not by the fly's own origin: the
        # fly sits behind its wheel, so anchoring on the origin put the camera inside it.
        # CARLA's car frame is left handed and MuJoCo's is right handed, so the lateral
        # axis is mirrored between them, the same correction the sponsor meshes need.
        position = REFLECT*(relative[:3, 3]-self.hub)/self.scale+self.rig.center
        camera = free_camera(position, REFLECT*relative[:3, 0])
        # CARLA states a horizontal field of view; MuJoCo wants the vertical one.
        self.model.vis.global_.fovy = math.degrees(
            2*math.atan(math.tan(math.radians(float(fov))/2)*self.height/self.width))
        return camera

    def render(self, relative, fov, rgb):
        """Composite the rig over one cabin frame. Returns (frame, pixels drawn)."""
        camera = self.camera_for(relative, fov)
        self.renderer.update_scene(self.rig.data, camera, self.option)
        self.renderer.enable_segmentation_rendering()
        segmentation = self.renderer.render()[:, :, 0]
        self.renderer.disable_segmentation_rendering()
        self.renderer.update_scene(self.rig.data, camera, self.option)
        colour = self.renderer.render()
        drawn = (segmentation >= 0) & ~np.isin(segmentation, list(self.stand))
        result = np.where(drawn[:, :, None], colour, rgb).astype(np.uint8)
        return result, int(np.count_nonzero(drawn))

    def close(self):
        self.renderer.close()
