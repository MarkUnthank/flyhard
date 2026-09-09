"""Stationary NeuroMechFly steering rig with a passive mechanical wheel.

The thorax is supported. An explicit point-grip constraint couples the left
front tarsus to the rim. Only fly joints have actuators; the wheel never does.
All geometry uses FlyGym's millimetre/milligram/second convention.
"""
import mujoco as mj
import numpy as np
from scipy.optimize import least_squares

from flygym import Simulation
from flygym.compose import NeuroMechFly, TetheredWorld, KinematicPosePreset, ActuatorType
from flygym.anatomy import Skeleton, AxisOrder, JointPreset, ActuatedDOFPreset
from flygym.utils.math import Rotation3D


def make_fly():
    fly = NeuroMechFly()
    skeleton = Skeleton(axis_order=AxisOrder.YAW_PITCH_ROLL, joint_preset=JointPreset.LEGS_ONLY)
    fly.add_joints(skeleton, neutral_pose=KinematicPosePreset.NEUTRAL)
    fly.add_actuators(skeleton.get_actuated_dofs_from_preset(ActuatedDOFPreset.LEGS_ACTIVE_ONLY),
                     actuator_type=ActuatorType.POSITION, kp=150.0, forcerange=(-30.0,30.0),
                     neutral_input=KinematicPosePreset.NEUTRAL)
    fly.colorize()
    fly.add_tracking_camera()
    return fly


class WheelRig:
    timestep = 5e-5
    command_period = 0.005
    max_joint_target_rate = 3.0  # rad/s; generic joint servo limit, no wheel knowledge

    def __init__(self):
        probe_fly = make_fly()
        probe_world = TetheredWorld()
        probe_world.add_fly(probe_fly, [0,0,0.7], Rotation3D('quat',[1,0,0,0]))
        probe = Simulation(probe_world)
        mj.mj_forward(probe.mj_model, probe.mj_data)
        foot_pos = probe.mj_data.body('nmf/lf_tarsus5').xpos.copy()
        self.radius = float(foot_pos[1])
        self.center = np.array([foot_pos[0], 0, foot_pos[2]])

        self.fly = make_fly()
        self.world = TetheredWorld()
        root = self.world.mjcf_root
        wheel = root.worldbody.add_body(name='wheel', pos=self.center)
        wheel.add_joint(name='wheel_hinge', type=mj.mjtJoint.mjJNT_HINGE, axis=[1,0,0],
                        limited=True, range=[-0.65,0.65], damping=0.10, stiffness=0.02)
        for i in range(32):
            a,b = i*2*np.pi/32, (i+1)*2*np.pi/32
            wheel.add_geom(name=f'rim_{i}', type=mj.mjtGeom.mjGEOM_CAPSULE, size=[0.045,0,0],
                fromto=[0,self.radius*np.cos(a),self.radius*np.sin(a),
                        0,self.radius*np.cos(b),self.radius*np.sin(b)],
                mass=0.0002, rgba=[0.07,0.08,0.07,1], contype=0, conaffinity=0)
        for a in [0,2*np.pi/3,4*np.pi/3]:
            wheel.add_geom(type=mj.mjtGeom.mjGEOM_CAPSULE, size=[0.025,0,0],
                fromto=[0,0,0,0,self.radius*np.cos(a),self.radius*np.sin(a)],
                mass=0.0001, rgba=[0.22,0.24,0.2,1], contype=0, conaffinity=0)
        wheel.add_geom(type=mj.mjtGeom.mjGEOM_SPHERE, size=[0.11,0,0], mass=0.0002,
                       rgba=[0.34,0.42,0.22,1],contype=0,conaffinity=0)
        wheel.add_geom(name='grip_marker', type=mj.mjtGeom.mjGEOM_SPHERE,
                       pos=[0,self.radius,0],size=[0.065,0,0],mass=1e-10,
                       rgba=[0.95,0.59,0.18,1],contype=0,conaffinity=0)
        root.worldbody.add_geom(type=mj.mjtGeom.mjGEOM_BOX, pos=[0,0,0.05],size=[2.4,1.9,0.05],
                               rgba=[0.21,0.3,0.19,1],contype=0,conaffinity=0)
        root.worldbody.add_geom(type=mj.mjtGeom.mjGEOM_BOX,pos=[0.25,0,1.34],size=[0.6,0.52,0.12],
                               rgba=[0.18,0.15,0.11,1],contype=0,conaffinity=0)
        root.worldbody.add_geom(type=mj.mjtGeom.mjGEOM_CAPSULE,size=[0.07,0,0],
                               fromto=[*self.center,2.1,0,self.center[2]],
                               rgba=[0.23,0.25,0.2,1],contype=0,conaffinity=0)
        root.add_equality(name='left_foreleg_grip', type=mj.mjtEq.mjEQ_CONNECT,
                          objtype=mj.mjtObj.mjOBJ_BODY, name1='nmf/lf_tarsus5', name2='wheel',
                          data=[0]*11, solref=[0.01,1],solimp=[0.99,0.999,0.001,0.5,2])
        self.world.add_fly(self.fly,[0,0,0.7],Rotation3D('quat',[1,0,0,0]))
        self.sim = Simulation(self.world,timestep=self.timestep)
        self.model,self.data = self.sim.mj_model,self.sim.mj_data
        self.model.opt.integrator = mj.mjtIntegrator.mjINT_IMPLICITFAST
        self.wheel_joint = self.model.joint('wheel_hinge').id
        self.wheel_qpos = self.model.jnt_qposadr[self.wheel_joint]
        self.wheel_qvel = self.model.jnt_dofadr[self.wheel_joint]
        self.grip_id = mj.mj_name2id(self.model,mj.mjtObj.mjOBJ_EQUALITY,'left_foreleg_grip')
        # MuJoCo infers the second anchor at qpos0; FlyGym's actual starting
        # posture is its nonzero neutral keyframe. Define both local anchor
        # points explicitly for that posture before any physics step.
        self.model.eq_data[self.grip_id,:3] = [0,0,0]
        self.model.eq_data[self.grip_id,3:6] = [0,self.radius,0]
        self.foot_id = self.model.body('nmf/lf_tarsus5').id
        self.actuators = [i for i in range(self.model.nu)
                          if 'lf_' in mj.mj_id2name(self.model,mj.mjtObj.mjOBJ_ACTUATOR,i)]
        joints = self.model.actuator_trnid[self.actuators,0]
        self.active_qpos = self.model.jnt_qposadr[joints]
        self.active_dofs = self.model.jnt_dofadr[joints]
        self.bounds = self.model.jnt_range[joints].copy()
        for i,j in enumerate(joints):
            if not self.model.jnt_limited[j]: self.bounds[i] = [-np.pi,np.pi]
        assert self.wheel_joint not in self.model.actuator_trnid[:,0]
        self.reset()
        self.neutral_actions = self.data.ctrl[self.actuators].copy()
        self.ik_angles = None

    def reset(self, grip=True):
        self.sim.reset()
        self.data.eq_active[self.grip_id] = grip
        mj.mj_forward(self.model,self.data)

    @property
    def angle(self):
        return float(self.data.qpos[self.wheel_qpos])

    def step(self, action, substeps=None):
        action = np.asarray(action)
        assert action.shape == (7,) and np.isfinite(action).all()
        action = np.clip(action,self.bounds[:,0],self.bounds[:,1])
        current = self.data.ctrl[self.actuators]
        delta = self.max_joint_target_rate*self.command_period
        self.data.ctrl[self.actuators] = current + np.clip(action-current,-delta,delta)
        for _ in range(substeps or round(self.command_period/self.timestep)):
            mj.mj_step(self.model,self.data)
        assert np.isfinite(self.data.qpos).all() and abs(self.angle)<1

    def prepare_diagnostic_ik(self):
        """Offline kinematic targets; never modifies the live physical state."""
        probe = mj.MjData(self.model)
        probe.qpos[:] = self.data.qpos
        neutral = probe.qpos[self.active_qpos].copy()
        self.ik_angles = np.linspace(-0.5,0.5,101)
        solutions,errors = [],[]
        for theta in self.ik_angles:
            target = self.center + [0,self.radius*np.cos(theta),self.radius*np.sin(theta)]
            def residual(q):
                probe.qpos[self.active_qpos] = q
                mj.mj_forward(self.model,probe)
                return np.concatenate([probe.xpos[self.foot_id]-target,0.002*(q-neutral)])
            solution = least_squares(residual,neutral,bounds=(self.bounds[:,0],self.bounds[:,1]),
                                     max_nfev=90,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            solutions.append(solution.x)
            errors.append(float(np.linalg.norm(residual(solution.x)[:3])))
        self.ik_actions = np.array(solutions)
        self.ik_max_error_mm = max(errors)

    def diagnostic_action(self,theta):
        if self.ik_angles is None:self.prepare_diagnostic_ik()
        return np.array([np.interp(theta,self.ik_angles,self.ik_actions[:,i]) for i in range(7)])
