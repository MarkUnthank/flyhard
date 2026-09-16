"""Owned CARLA parking scene; applied controls come only from measured mechanics."""
import math
import numpy as np
import carla
from flyhard.parking import (REAR_TO_CENTER,WHEEL_TO_CARLA,collision,pose_metrics)

DT=.05


class ParkingWorld:
    def __init__(self,render=False,port=2000):
        self.client=carla.Client('localhost',port);self.client.set_timeout(90)
        self.world=self.client.get_world()
        if self.world.get_map().name.rsplit('/',1)[-1]!='Town03':self.world=self.client.load_world('Town03')
        if self.world.get_actors().filter('vehicle.*'):raise RuntimeError('Parking needs an owned empty server')
        self.original=self.world.get_settings();settings=self.world.get_settings()
        settings.synchronous_mode=True;settings.fixed_delta_seconds=DT
        settings.no_rendering_mode=not render;settings.substepping=True
        settings.max_substep_delta_time=.01;settings.max_substeps=5
        self.world.apply_settings(settings);self.world.set_weather(carla.WeatherParameters.ClearNoon)
        self.origin=np.array([-6.4485092163,61.0420188904,.2753071487])
        self.yaw=89.6374588013;angle=math.radians(self.yaw)
        self.rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        self.actors=[];self.events=[];self.ego=None;self.case=None

    def transform(self,x,y,yaw=0):
        xy=self.origin[:2]+self.rotation@np.array([x,y])
        return carla.Transform(carla.Location(float(xy[0]),float(xy[1]),float(self.origin[2])),
                               carla.Rotation(yaw=self.yaw+math.degrees(yaw)))

    def clear(self):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if actor.type_id.startswith('sensor.'):actor.stop()
                actor.destroy()
        self.actors=[];self.events=[];self.ego=None

    def start(self,case):
        self.clear();self.case=case;library=self.world.get_blueprint_library()
        for i,(x,y,_,_) in enumerate(case.obstacles):
            bp=library.find('vehicle.mini.cooper_s_2021')
            bp.set_attribute('role_name','parking_obstacle')
            if bp.has_attribute('color'):bp.set_attribute('color',['55,55,55','180,40,40'][i])
            actor=self.world.spawn_actor(bp,self.transform(x,y));self.actors.append(actor)
            actor.apply_control(carla.VehicleControl(brake=1,hand_brake=True))
        bp=library.find('vehicle.mini.cooper_s_2021');bp.set_attribute('role_name','hero')
        if bp.has_attribute('color'):bp.set_attribute('color','48,84,43')
        self.ego=self.world.spawn_actor(bp,self.transform(case.approach_x,case.approach_y,case.approach_yaw))
        self.actors.append(self.ego);self.ego.apply_control(carla.VehicleControl(brake=1))
        for _ in range(80):self.world.tick()
        sensor=self.world.spawn_actor(library.find('sensor.other.collision'),carla.Transform(),attach_to=self.ego)
        def event(e):
            self.events.append({'frame':e.frame,'other_actor':e.other_actor.type_id,
                                'impulse':e.normal_impulse.length()})
        sensor.listen(event);self.actors.append(sensor)
        return self.state()

    def state(self):
        transform=self.ego.get_transform();center=transform.transform(self.ego.bounding_box.location)
        local=self.rotation.T@(np.array([center.x,center.y])-self.origin[:2])
        yaw=math.radians(transform.rotation.yaw-self.yaw)
        yaw=math.atan2(math.sin(yaw),math.cos(yaw))
        rear=local-REAR_TO_CENTER*np.array([math.cos(yaw),math.sin(yaw)])
        velocity=self.ego.get_velocity();forward=transform.get_forward_vector()
        speed=velocity.x*forward.x+velocity.y*forward.y
        return np.array([*rear,yaw,speed])

    def apply_measured(self,rig):
        measured=rig.parking.measured
        # No policy output is passed to VehicleControl. The gear comes from the
        # selector position, and the pedals/wheel from passive joint positions.
        control=carla.VehicleControl(throttle=measured['throttle'],brake=measured['brake'],
            steer=float(np.clip(rig.angle*WHEEL_TO_CARLA,-1,1)),
            manual_gear_shift=True,gear=measured['gear'],reverse=measured['gear']<0)
        self.ego.apply_control(control)
        return {'throttle':control.throttle,'brake':control.brake,'steer':control.steer,
                'gear':control.gear,'reverse':control.reverse,'selector':measured['selector']}

    def metrics(self,state):
        return {**pose_metrics(state,self.case),'collision':bool(self.events or collision(state,self.case))}

    def close(self):
        self.clear();self.world.apply_settings(self.original)
