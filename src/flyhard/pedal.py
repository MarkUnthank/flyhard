"""Independent E02 pedal rig: a middle leg presses a spring-loaded contact pad."""
import mujoco as mj
import numpy as np
from scipy.optimize import least_squares
from flygym import Simulation
from flygym.compose import TetheredWorld
from flygym.anatomy import BodySegment
from flygym.utils.math import Rotation3D
from flyhard.cockpit import make_fly


class PedalRig:
    timestep=5e-5
    command_period=0.005

    def __init__(self):
        probe_fly=make_fly();probe_world=TetheredWorld()
        probe_world.add_fly(probe_fly,[0,0,0.7],Rotation3D('quat',[1,0,0,0]))
        probe=Simulation(probe_world);mj.mj_forward(probe.mj_model,probe.mj_data)
        self.foot_rest=probe.mj_data.body('nmf/rm_tarsus5').xpos.copy()
        self.fly=make_fly();self.world=TetheredWorld();root=self.world.mjcf_root
        # Explicit engineered sole provides a well-defined contact surface.
        foot=self.fly.bodyseg_to_mjcfbody[BodySegment('rm_tarsus5')]
        foot.add_geom(name='pedal_sole',type=mj.mjtGeom.mjGEOM_SPHERE,size=[0.05,0,0],mass=1e-8,
                      rgba=[0.95,0.59,0.18,1],contype=2,conaffinity=4,friction=[0.6,0.005,0.0001],
                      solref=[0.001,1],solimp=[0.99,0.999,0.001,0.5,2])
        center=self.foot_rest-[0,0,0.09]
        pedal=root.worldbody.add_body(name='pedal',pos=center)
        pedal.add_joint(name='pedal_slide',type=mj.mjtJoint.mjJNT_SLIDE,axis=[0,0,-1],
                        limited=True,range=[0,0.25],stiffness=3,damping=0.02,springref=-0.05)
        pedal.add_geom(name='pedal_pad',type=mj.mjtGeom.mjGEOM_BOX,size=[0.24,0.25,0.04],mass=1e-5,
                       rgba=[0.2,0.23,0.18,1],contype=4,conaffinity=2,friction=[0.6,0.005,0.0001],
                       solref=[0.001,1],solimp=[0.99,0.999,0.001,0.5,2])
        root.worldbody.add_geom(type=mj.mjtGeom.mjGEOM_BOX,pos=[0,0,0.05],size=[2.4,1.9,0.05],
                               rgba=[0.21,0.3,0.19,1],contype=0,conaffinity=0)
        root.worldbody.add_geom(type=mj.mjtGeom.mjGEOM_BOX,pos=[0.25,0,1.34],size=[0.6,0.52,0.12],
                               rgba=[0.18,0.15,0.11,1],contype=0,conaffinity=0)
        self.world.add_fly(self.fly,[0,0,0.7],Rotation3D('quat',[1,0,0,0]))
        self.sim=Simulation(self.world,timestep=self.timestep);self.model,self.data=self.sim.mj_model,self.sim.mj_data
        self.model.opt.integrator=mj.mjtIntegrator.mjINT_IMPLICITFAST
        self.pedal_joint=self.model.joint('pedal_slide').id;self.pedal_qpos=self.model.jnt_qposadr[self.pedal_joint]
        self.sole=self.model.geom('nmf/pedal_sole').id
        self.foot_id=self.model.body('nmf/rm_tarsus5').id
        self.actuators=[i for i in range(self.model.nu) if 'rm_' in mj.mj_id2name(self.model,mj.mjtObj.mjOBJ_ACTUATOR,i)]
        joints=self.model.actuator_trnid[self.actuators,0];self.active_qpos=self.model.jnt_qposadr[joints]
        self.bounds=np.tile([-np.pi,np.pi],(7,1))
        assert self.pedal_joint not in self.model.actuator_trnid[:,0]
        self.reset();self.neutral_actions=self.data.ctrl[self.actuators].copy()
        self.ik_positions=None

    def reset(self,contact=True):
        self.model.geom_contype[self.sole]=2 if contact else 0
        self.model.geom_conaffinity[self.sole]=4 if contact else 0
        self.sim.reset();mj.mj_forward(self.model,self.data)

    @property
    def displacement(self):return float(self.data.qpos[self.pedal_qpos])

    def step(self,action):
        current=self.data.ctrl[self.actuators]
        self.data.ctrl[self.actuators]=current+np.clip(np.asarray(action)-current,-0.015,0.015)
        for _ in range(round(self.command_period/self.timestep)):mj.mj_step(self.model,self.data)
        assert np.isfinite(self.data.qpos).all() and abs(self.displacement)<0.5

    def prepare_diagnostic_ik(self):
        probe=mj.MjData(self.model);probe.qpos[:]=self.data.qpos;neutral=probe.qpos[self.active_qpos].copy()
        self.ik_positions=np.linspace(0,0.23,47);solutions=[];errors=[]
        for depression in self.ik_positions:
            target=self.foot_rest-[0,0,depression]
            def residual(q):
                probe.qpos[self.active_qpos]=q;mj.mj_forward(self.model,probe)
                return np.r_[probe.xpos[self.foot_id]-target,0.002*(q-neutral)]
            fit=least_squares(residual,neutral,bounds=(self.bounds[:,0],self.bounds[:,1]),max_nfev=90,
                              ftol=1e-9,xtol=1e-9,gtol=1e-9)
            solutions.append(fit.x);errors.append(float(np.linalg.norm(residual(fit.x)[:3])))
        self.ik_actions=np.array(solutions);self.ik_max_error_mm=max(errors)

    def diagnostic_action(self,position):
        if self.ik_positions is None:self.prepare_diagnostic_ik()
        return np.array([np.interp(position,self.ik_positions,self.ik_actions[:,i]) for i in range(7)])
