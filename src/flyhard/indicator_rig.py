"""Isolated physical indicator stalk, operated through a fly foreleg point grip.

The spring-centred lever has three measured output zones. There is no latch or
stalk actuator; holding a signal requires continued leg force. This diagnostic
rig does not yet combine the stalk with the steering wheel.
"""
import mujoco as mj
import numpy as np
from scipy.optimize import least_squares

from flygym import Simulation
from flygym.compose import TetheredWorld
from flygym.utils.math import Rotation3D
from flyhard.cockpit import make_fly


class IndicatorRig:
    timestep = 5e-5
    command_period = 0.005
    max_joint_target_rate = 3.0
    state_threshold = 0.18
    target_angle = 0.35

    def __init__(self):
        probe_world = TetheredWorld()
        probe_world.add_fly(make_fly(), [0, 0, 0.7], Rotation3D("quat", [1, 0, 0, 0]))
        probe = Simulation(probe_world)
        mj.mj_forward(probe.mj_model, probe.mj_data)
        foot = probe.mj_data.body("nmf/lf_tarsus5").xpos.copy()
        self.radius = 0.45
        self.center = foot - [0, self.radius, 0]
        self.world = TetheredWorld()
        root = self.world.mjcf_root
        stalk = root.worldbody.add_body(name="indicator_stalk", pos=self.center)
        stalk.add_joint(name="indicator_hinge", type=mj.mjtJoint.mjJNT_HINGE,
                        axis=[1, 0, 0], limited=True, range=[-0.55, 0.55],
                        damping=0.04, stiffness=0.02)
        stalk.add_geom(name="indicator_lever", type=mj.mjtGeom.mjGEOM_CAPSULE,
                       fromto=[0, 0, 0, 0, self.radius, 0], size=[0.045, 0, 0],
                       mass=0.001, rgba=[0.3, 0.3, 0.3, 1], contype=0, conaffinity=0)
        stalk.add_geom(name="indicator_grip", type=mj.mjtGeom.mjGEOM_SPHERE,
                       pos=[0, self.radius, 0], size=[0.075, 0, 0], mass=0.0002,
                       rgba=[1, 0.6, 0.08, 1], contype=0, conaffinity=0)
        # Mirror the lever and grip mass behind the pivot. FlyGym uses 9810
        # mm/s² gravity; a one-sided lever otherwise sags independently of the
        # fly. This passive counterweight balances gravity without a torque
        # controller, position assignment, or an artificial gravity override.
        stalk.add_geom(name="indicator_balance_arm", type=mj.mjtGeom.mjGEOM_CAPSULE,
                       fromto=[0, 0, 0, 0, -self.radius, 0], size=[0.045, 0, 0],
                       mass=0.001, rgba=[0.12, 0.12, 0.12, 1], contype=0, conaffinity=0)
        stalk.add_geom(name="indicator_counterweight", type=mj.mjtGeom.mjGEOM_SPHERE,
                       pos=[0, -self.radius, 0], size=[0.075, 0, 0], mass=0.0002,
                       rgba=[0.12, 0.12, 0.12, 1], contype=0, conaffinity=0)
        root.worldbody.add_geom(type=mj.mjtGeom.mjGEOM_BOX, pos=self.center - [0, 0.09, 0],
                                size=[0.10, 0.10, 0.17], rgba=[0.12, 0.12, 0.12, 1],
                                contype=0, conaffinity=0)
        root.add_equality(name="indicator_foot_grip", type=mj.mjtEq.mjEQ_CONNECT,
                          objtype=mj.mjtObj.mjOBJ_BODY, name1="nmf/lf_tarsus5", name2="indicator_stalk",
                          data=[0] * 11, solref=[0.01, 1], solimp=[0.99, 0.999, 0.001, 0.5, 2])
        self.world.add_fly(make_fly(), [0, 0, 0.7], Rotation3D("quat", [1, 0, 0, 0]))
        self.sim = Simulation(self.world, timestep=self.timestep)
        self.model, self.data = self.sim.mj_model, self.sim.mj_data
        self.model.opt.integrator = mj.mjtIntegrator.mjINT_IMPLICITFAST
        self.stalk_joint = self.model.joint("indicator_hinge").id
        self.stalk_qpos = self.model.jnt_qposadr[self.stalk_joint]
        self.grip_id = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_EQUALITY, "indicator_foot_grip")
        self.model.eq_data[self.grip_id, :3] = [0, 0, 0]
        self.model.eq_data[self.grip_id, 3:6] = [0, self.radius, 0]
        self.foot_id = self.model.body("nmf/lf_tarsus5").id
        self.actuators = [i for i in range(self.model.nu)
                          if "lf_" in mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_ACTUATOR, i)]
        joints = self.model.actuator_trnid[self.actuators, 0]
        self.active_qpos = self.model.jnt_qposadr[joints]
        self.bounds = self.model.jnt_range[joints].copy()
        for i, joint in enumerate(joints):
            if not self.model.jnt_limited[joint]:
                self.bounds[i] = [-np.pi, np.pi]
        assert self.stalk_joint not in self.model.actuator_trnid[:, 0]
        self.reset()
        self.neutral_actions = self.data.ctrl[self.actuators].copy()
        self.ik_actions = None

    def reset(self, grip=True):
        self.sim.reset()
        self.data.eq_active[self.grip_id] = grip
        mj.mj_forward(self.model, self.data)

    @property
    def angle(self):
        return float(self.data.qpos[self.stalk_qpos])

    @property
    def signal(self):
        # Output comes exclusively from the physically measured hinge position.
        return "left" if self.angle < -self.state_threshold else "right" if self.angle > self.state_threshold else "off"

    def step(self, action):
        action = np.asarray(action)
        assert action.shape == (7,) and np.isfinite(action).all()
        action = np.clip(action, self.bounds[:, 0], self.bounds[:, 1])
        current = self.data.ctrl[self.actuators]
        delta = self.max_joint_target_rate * self.command_period
        self.data.ctrl[self.actuators] = current + np.clip(action - current, -delta, delta)
        for _ in range(round(self.command_period / self.timestep)):
            mj.mj_step(self.model, self.data)
        assert np.isfinite(self.data.qpos).all() and abs(self.angle) < 0.7

    def prepare_diagnostic_ik(self):
        """Solve only on a separate probe; never assign live body/stalk poses."""
        probe = mj.MjData(self.model)
        probe.qpos[:] = self.data.qpos
        neutral = probe.qpos[self.active_qpos].copy()
        self.ik_angles = np.linspace(-self.target_angle, self.target_angle, 51)
        solutions, errors = [], []
        for theta in self.ik_angles:
            target = self.center + [0, self.radius * np.cos(theta), self.radius * np.sin(theta)]

            def residual(q):
                probe.qpos[self.active_qpos] = q
                mj.mj_forward(self.model, probe)
                return np.concatenate([probe.xpos[self.foot_id] - target, 0.002 * (q - neutral)])

            solution = least_squares(residual, neutral, bounds=(self.bounds[:, 0], self.bounds[:, 1]),
                                     max_nfev=90, ftol=1e-9, xtol=1e-9, gtol=1e-9)
            solutions.append(solution.x)
            errors.append(float(np.linalg.norm(residual(solution.x)[:3])))
        self.ik_actions = np.array(solutions)
        self.ik_max_error_mm = max(errors)

    def diagnostic_action(self, angle):
        if self.ik_actions is None:
            self.prepare_diagnostic_ik()
        return np.array([np.interp(angle, self.ik_angles, self.ik_actions[:, i]) for i in range(7)])
