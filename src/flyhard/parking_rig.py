"""Passive pedals and selector, driven only by coupled fly leg joints.

Pedals are spring-return horizontal plungers, avoiding gravity as a source of
activation. Explicit foot straps use the same point-grip abstraction as the
existing wheel. No pedal, selector or wheel joint has an actuator.
"""
import mujoco as mj
import numpy as np
from scipy.optimize import least_squares


class PassiveSlider:
    def __init__(self, root, foot, name, leg, *, selector=False):
        self.name, self.leg, self.selector = name, leg, selector
        self.center = np.asarray(foot).copy()
        self.axis = np.array([0., 1., 0.]) if selector else np.array([1., 0., 0.])
        self.travel = .28
        self.range = [-self.travel, self.travel] if selector else [0., self.travel]
        body = root.worldbody.add_body(name=name, pos=self.center)
        body.add_joint(name=name + '_slide', type=mj.mjtJoint.mjJNT_SLIDE,
                       axis=self.axis, limited=True, range=self.range,
                       damping=.04, stiffness=.5, armature=.00002)
        body.add_geom(name=name + '_pad', type=mj.mjtGeom.mjGEOM_BOX,
                      size=[.035, .15, .10], mass=.0002,
                      rgba=([.95, .55, .08, 1] if selector else
                            [.3, .75, .45, 1] if name == 'throttle_pedal' else [.9, .25, .2, 1]),
                      contype=0, conaffinity=0)
        root.worldbody.add_geom(name=name + '_guide', type=mj.mjtGeom.mjGEOM_CAPSULE,
                               fromto=[*(self.center-self.axis*.32), *(self.center+self.axis*.38)],
                               size=[.025, 0, 0], rgba=[.22, .22, .22, 1], contype=0, conaffinity=0)
        root.add_equality(name=name + '_foot_grip', type=mj.mjtEq.mjEQ_CONNECT,
                          objtype=mj.mjtObj.mjOBJ_BODY, name1=f'nmf/{leg}_tarsus5', name2=name,
                          data=[0]*11, solref=[.01, 1], solimp=[.99, .999, .001, .5, 2])

    def bind(self, model, data):
        self.model, self.data = model, data
        joint = model.joint(self.name + '_slide').id
        self.qpos = model.jnt_qposadr[joint]
        self.grip_id = model.equality(self.name + '_foot_grip').id
        model.eq_data[self.grip_id, :6] = 0
        self.foot_id = model.body(f'nmf/{self.leg}_tarsus5').id
        self.actuators = [i for i in range(model.nu)
                          if self.leg + '_' in mj.mj_id2name(model, mj.mjtObj.mjOBJ_ACTUATOR, i)]
        joints = model.actuator_trnid[self.actuators, 0]
        self.active_qpos = model.jnt_qposadr[joints]
        self.bounds = model.jnt_range[joints].copy()
        self.bounds[~model.jnt_limited[joints].astype(bool)] = [-np.pi, np.pi]
        self.neutral_actions = data.ctrl[self.actuators].copy()
        self.ik_values = None
        assert len(self.actuators) == 7 and joint not in model.actuator_trnid[:, 0]

    @property
    def position(self):
        return float(self.data.qpos[self.qpos])

    @property
    def value(self):
        # Fixed instrument calibration; depends solely on measured slider travel.
        return float(np.clip(self.position/self.travel, -1 if self.selector else 0, 1))

    def apply(self, action, delta):
        action = np.asarray(action)
        if action.shape != (7,) or not np.isfinite(action).all():
            raise ValueError('Expected seven finite leg targets')
        desired = np.clip(action, self.bounds[:, 0], self.bounds[:, 1])
        current = self.data.ctrl[self.actuators]
        self.data.ctrl[self.actuators] = current + np.clip(desired-current, -delta, delta)

    def prepare_diagnostic_ik(self):
        probe = mj.MjData(self.model)
        probe.qpos[:] = self.data.qpos
        neutral = probe.qpos[self.active_qpos].copy()
        self.ik_values = np.linspace(-1 if self.selector else 0, 1, 51)
        actions, errors = [], []
        for value in self.ik_values:
            target = self.center + self.axis * self.travel * value
            def residual(q):
                probe.qpos[self.active_qpos] = q
                mj.mj_forward(self.model, probe)
                return np.r_[probe.xpos[self.foot_id]-target, .002*(q-neutral)]
            result = least_squares(residual, neutral, bounds=(self.bounds[:, 0], self.bounds[:, 1]),
                                   max_nfev=90, ftol=1e-9, xtol=1e-9, gtol=1e-9)
            actions.append(result.x)
            errors.append(float(np.linalg.norm(residual(result.x)[:3])))
        self.ik_actions = np.asarray(actions)
        self.ik_max_error_mm = max(errors)

    def diagnostic_action(self, value):
        if self.ik_values is None:
            self.prepare_diagnostic_ik()
        return np.array([np.interp(value, self.ik_values, self.ik_actions[:, i]) for i in range(7)])


class ParkingControls:
    def __init__(self, root, probe):
        self.throttle = PassiveSlider(root, probe.body('nmf/lm_tarsus5').xpos,
                                      'throttle_pedal', 'lm')
        self.brake = PassiveSlider(root, probe.body('nmf/rm_tarsus5').xpos,
                                   'brake_pedal', 'rm')
        self.selector = PassiveSlider(root, probe.body('nmf/rf_tarsus5').xpos,
                                      'gear_selector', 'rf', selector=True)
        self.controls = [self.throttle, self.brake, self.selector]

    def bind(self, model, data):
        self.model = model
        for control in self.controls:
            control.bind(model, data)

    @property
    def measured(self):
        position = self.selector.value
        return {'throttle': self.throttle.value, 'brake': self.brake.value,
                'gear': 1 if position > .5 else -1 if position < -.5 else 0,
                'selector': position}


def make_parking_rig():
    from flyhard.cockpit import WheelRig
    class ParkingRig(WheelRig):
        timestep = 5e-5
        command_period = .005

        def prepare_controls(self):
            self.prepare_diagnostic_ik()
            for control in self.parking.controls:
                control.prepare_diagnostic_ik()

        def diagnostic_drive_action(self, wheel, throttle, brake, gear):
            return np.r_[self.diagnostic_action(wheel),
                         self.parking.throttle.diagnostic_action(throttle),
                         self.parking.brake.diagnostic_action(brake),
                         self.parking.selector.diagnostic_action(gear)]

        def step_drive(self, action):
            action = np.asarray(action)
            if action.shape != (28,) or not np.isfinite(action).all():
                raise ValueError('Expected 28 finite leg-joint commands')
            for i, control in enumerate(self.parking.controls):
                control.apply(action[7+7*i:14+7*i], self.max_joint_target_rate*self.command_period)
            self.step(action[:7])

    return ParkingRig(parking_controls=True)
