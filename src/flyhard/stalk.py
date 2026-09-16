"""A passive, balanced stalk attached to one physical fly foreleg."""
import mujoco as mj
import numpy as np
from scipy.optimize import least_squares


class Stalk:
    threshold = 0.18
    target_angle = 0.35

    def __init__(self, root, foot, leg="rf"):
        self.leg = leg
        self.radius = 0.45 if leg == "lf" else -0.45
        self.center = foot - [0, self.radius, 0]
        body = root.worldbody.add_body(name="indicator_stalk", pos=self.center)
        body.add_joint(name="indicator_hinge", type=mj.mjtJoint.mjJNT_HINGE,
                       axis=[1, 0, 0], limited=True, range=[-.55, .55], damping=.04, stiffness=.02)
        # Equal opposing masses balance gravity in FlyGym's mm/mg/s units.
        for side in [1, -1]:
            y = side * self.radius
            body.add_geom(type=mj.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, 0, y, 0],
                          size=[.045, 0, 0], mass=.001, rgba=[.22, .22, .22, 1], contype=0, conaffinity=0)
            body.add_geom(type=mj.mjtGeom.mjGEOM_SPHERE, pos=[0, y, 0], size=[.075, 0, 0],
                          mass=.0002, rgba=[1, .6, .08, 1] if side == 1 else [.12, .12, .12, 1],
                          contype=0, conaffinity=0)
        root.add_equality(name="indicator_foot_grip", type=mj.mjtEq.mjEQ_CONNECT,
                          objtype=mj.mjtObj.mjOBJ_BODY, name1=f"nmf/{leg}_tarsus5", name2="indicator_stalk",
                          data=[0] * 11, solref=[.01, 1], solimp=[.99, .999, .001, .5, 2])

    def bind(self, model, data):
        self.model, self.data = model, data
        joint = model.joint("indicator_hinge").id
        self.qpos = model.jnt_qposadr[joint]
        self.grip_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_EQUALITY, "indicator_foot_grip")
        model.eq_data[self.grip_id, :3] = [0, 0, 0]
        model.eq_data[self.grip_id, 3:6] = [0, self.radius, 0]
        self.foot_id = model.body(f"nmf/{self.leg}_tarsus5").id
        self.actuators = [i for i in range(model.nu)
                          if self.leg + "_" in mj.mj_id2name(model, mj.mjtObj.mjOBJ_ACTUATOR, i)]
        joints = model.actuator_trnid[self.actuators, 0]
        self.active_qpos = model.jnt_qposadr[joints]
        self.bounds = model.jnt_range[joints].copy()
        for i, j in enumerate(joints):
            if not model.jnt_limited[j]:
                self.bounds[i] = [-np.pi, np.pi]
        assert joint not in model.actuator_trnid[:, 0]
        self.neutral_actions = data.ctrl[self.actuators].copy()
        self.ik_angles = None

    @property
    def angle(self):
        return float(self.data.qpos[self.qpos])

    @property
    def signal(self):
        return "left" if self.angle < -self.threshold else "right" if self.angle > self.threshold else "off"

    def apply(self, action, delta):
        action = np.asarray(action)
        assert action.shape == (7,) and np.isfinite(action).all()
        action = np.clip(action, self.bounds[:, 0], self.bounds[:, 1])
        current = self.data.ctrl[self.actuators]
        self.data.ctrl[self.actuators] = current + np.clip(action - current, -delta, delta)

    def prepare_diagnostic_ik(self):
        # Kinematic labels use a separate probe; inference never assigns poses.
        probe = mj.MjData(self.model)
        probe.qpos[:] = self.data.qpos
        neutral = probe.qpos[self.active_qpos].copy()
        self.ik_angles = np.linspace(-self.target_angle, self.target_angle, 51)
        actions, errors = [], []
        for theta in self.ik_angles:
            target = self.center + [0, self.radius * np.cos(theta), self.radius * np.sin(theta)]

            def residual(q):
                probe.qpos[self.active_qpos] = q
                mj.mj_forward(self.model, probe)
                return np.r_[probe.xpos[self.foot_id] - target, .002 * (q - neutral)]

            result = least_squares(residual, neutral, bounds=(self.bounds[:, 0], self.bounds[:, 1]),
                                   max_nfev=90, ftol=1e-9, xtol=1e-9, gtol=1e-9)
            actions.append(result.x)
            errors.append(float(np.linalg.norm(residual(result.x)[:3])))
        self.ik_actions = np.asarray(actions)
        self.ik_max_error_mm = max(errors)

    def diagnostic_action(self, angle):
        if self.ik_angles is None:
            self.prepare_diagnostic_ik()
        return np.array([np.interp(angle, self.ik_angles, self.ik_actions[:, i]) for i in range(7)])
