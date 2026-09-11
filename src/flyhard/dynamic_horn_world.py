"""Directed native CARLA traffic with measured fly steering and horn.

Vehicles move through CARLA physics. BasicAgent supplies disclosed route requests
and longitudinal control; the learned core commands the physical wheel/button.
"""
import math
import sys
import carla
import numpy as np
sys.path.insert(0, '/opt/carla/PythonAPI/carla')
from agents.navigation.basic_agent import BasicAgent
from agents.navigation.global_route_planner import GlobalRoutePlanner
from flyhard.horn_world import HornWorld


def angular(a, b):
    return abs((a-b+180)%360-180)


def straight(wp, distance):
    current = wp
    for _ in range(round(distance/2)):
        options = current.next(2.)
        if not options:
            break
        current = min(options,key=lambda w:angular(w.transform.rotation.yaw,current.transform.rotation.yaw))
    return current


def pose(wp):
    p = wp.transform
    return carla.Transform(carla.Location(p.location.x,p.location.y,p.location.z+.25),p.rotation)


class DynamicHornWorld(HornWorld):
    def __init__(self, town='Town03'):
        super().__init__(town)
        self.planner = GlobalRoutePlanner(self.map,1.5)
        self.traffic = []
        self.ego_agent = None
        self.started_horn_at = None
        self.collision_events = []

    def junctions(self):
        junctions = {}
        for wp in self.map.generate_waypoints(5.):
            if wp.is_junction:
                junctions.setdefault(wp.get_junction().id,wp.get_junction())
        choices = []
        for junction in junctions.values():
            pairs = junction.get_waypoints(carla.LaneType.Driving)
            headings = set(round(a.transform.rotation.yaw/90)%4 for a,b in pairs)
            if len(headings) not in {3,4}:
                continue
            for a,b in pairs:
                if angular(a.transform.rotation.yaw,b.transform.rotation.yaw)>12:
                    continue
                if not 8<a.transform.location.distance(b.transform.location)<42:
                    continue
                before=a.previous(28.)
                if not before or before[0].is_junction:
                    continue
                for side,end in pairs:
                    angle=angular(a.transform.rotation.yaw,side.transform.rotation.yaw)
                    if not 65<angle<115 or end.transform.location.distance(b.transform.location)>2.8:
                        continue
                    prior=side.previous(16.)
                    if not prior or prior[0].is_junction:
                        continue
                    choices.append({'junction':junction.id,'arms':len(headings),'ego_entry':a,
                                    'ego_start':before[0],'exit':b,'side_entry':side,'side_start':prior[0]})
        return sorted(choices,key=lambda c:(c['arms'],c['junction'],c['ego_entry'].road_id))

    def agent(self, vehicle, start, goal, speed, ignore=True):
        agent=BasicAgent(vehicle,target_speed=speed*3.6,map_inst=self.map,grp_inst=self.planner)
        agent.ignore_traffic_lights(ignore);agent.ignore_stop_signs(True);agent.ignore_vehicles(ignore)
        route=self.planner.trace_route(start.transform.location,goal.transform.location)
        if len(route)<8:
            raise RuntimeError('No usable native route')
        agent.set_global_plan(route)
        return agent,route

    def spawn(self, bp_name, waypoint, color, role):
        bp=self.world.get_blueprint_library().find(bp_name)
        if bp.has_attribute('color'):bp.set_attribute('color',color)
        bp.set_attribute('role_name',role)
        actor=self.world.spawn_actor(bp,pose(waypoint));self.actors.append(actor)
        actor.apply_control(carla.VehicleControl(brake=1,hand_brake=True))
        return actor

    def start(self, kind):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor,carla.Sensor):actor.stop()
                actor.destroy()
        self.actors=[];self.traffic=[];self.lead=None;self.kind=kind
        self.started_horn_at=None;self.collision_events=[];self.junction_description=None
        self.stopped_since=None;self.green_released=False
        is_cut=kind.startswith('cut_in')
        rage=kind=='road_rage'
        self.set_green(is_cut or rage or kind=='arrive_green')
        if is_cut or rage:
            choices=self.junctions()
            target_arms=3 if kind=='cut_in_t' else 4
            options=[c for c in choices if c['arms']==target_arms]
            if not options:
                raise RuntimeError(f'No {target_arms}-arm native side-road merge found')
            selected=options[0]
            self.junction_description={k:selected[k] for k in ['junction','arms']}
            start=selected['ego_start'] if rage else selected['ego_entry'].previous(20.)[0]
            goal=straight(selected['exit'],210 if rage else 95)
            # Bind the observed lamp to this junction, not the light-scene
            # approach selected by HornWorld during construction.
            matches=[(wp.transform.location.distance(selected['ego_entry'].transform.location),light,wp)
                     for light in self.lights for wp in light.get_stop_waypoints()
                     if angular(wp.transform.rotation.yaw,selected['ego_entry'].transform.rotation.yaw)<15]
            distance,light,stop=min(matches,key=lambda item:item[0])
            if distance>35:raise RuntimeError('No traffic light matches this route approach')
            self.light.set_state(carla.TrafficLightState.Red)
            self.light,self.stop=light,stop;self.requested_green=None;self.set_green(True)
            self.forward=start.transform.get_forward_vector();self.right=start.transform.get_right_vector()
        else:
            start=self.stop.previous(24.)[0];goal=straight(self.stop,110.)
        self.ego=self.spawn('vehicle.mini.cooper_s_2021',start,'48,84,43','hero')
        self.ego_agent,self.ego_route=self.agent(self.ego,start,goal,9 if rage else 6,ignore=is_cut or rage)
        path=np.array([[w.transform.location.x,w.transform.location.y] for w,_ in self.ego_route])
        segments=np.diff(path,axis=0);lengths=np.linalg.norm(segments,axis=1);keep=lengths>1e-6
        self.path_start=path[:-1][keep];self.path_delta=segments[keep];self.path_length=lengths[keep]
        self.path_cumulative=np.r_[0.,np.cumsum(self.path_length)[:-1]]
        self.route_light_ids=[]
        if is_cut or rage:
            for light in self.lights:
                for wp in light.get_stop_waypoints():
                    progress,lateral=self.path_position(wp.transform.location)
                    nearest=int(np.argmin(np.linalg.norm(self.path_start-np.array([wp.transform.location.x,wp.transform.location.y]),axis=1)))
                    heading=math.degrees(math.atan2(self.path_delta[nearest,1],self.path_delta[nearest,0]))
                    if lateral<2.5 and angular(heading,wp.transform.rotation.yaw)<20:
                        light.set_state(carla.TrafficLightState.Green);self.route_light_ids.append(light.id);break
        if not (is_cut or rage):
            self.ego_agent.ignore_vehicles(False)
        if kind in {'arrive_green','wait_green'}:
            lead_start=self.stop.previous(11.)[0]
            self.lead=self.spawn('vehicle.lincoln.mkz_2020',lead_start,'205,205,205','lead')
            agent,_=self.agent(self.lead,lead_start,goal,6,ignore=False)
            self.traffic.append({'actor':self.lead,'agent':agent,'role':'lead','start':lead_start})
        if is_cut:
            side=selected['side_start']
            self.lead=self.spawn('vehicle.audi.a2',side,'45,75,150','cut_in')
            agent,_=self.agent(self.lead,side,goal,5.2,ignore=True)
            self.traffic.append({'actor':self.lead,'agent':agent,'role':'cut_in','start':side})
        if rage:
            accumulated=0.;last=None;spawns=[]
            for wp,_ in self.ego_route:
                if last:accumulated+=wp.transform.location.distance(last.transform.location)
                last=wp
                if accumulated<24+len(spawns)*33 or wp.is_junction:continue
                neighbours=[wp.get_left_lane(),wp.get_right_lane()]
                adjacent=next((w for w in neighbours if w and w.lane_type==carla.LaneType.Driving),None)
                if not adjacent:continue
                try:
                    actor=self.spawn('vehicle.lincoln.mkz_2020',adjacent,
                                     ['175,175,175','35,75,115','155,90,35'][len(spawns)%3],f'encounter_{len(spawns)}')
                    end=straight(adjacent,110);agent,_=self.agent(actor,adjacent,end,2.5,ignore=True)
                    self.traffic.append({'actor':actor,'agent':agent,'role':'encounter','start':adjacent})
                    spawns.append(actor)
                except RuntimeError:
                    continue
                if len(spawns)==6:break
            if len(spawns)<3:raise RuntimeError('Not enough separated traffic encounters on route')
        sensor=self.world.spawn_actor(self.world.get_blueprint_library().find('sensor.other.collision'),carla.Transform(),attach_to=self.ego)
        sensor.listen(lambda e:self.collision_events.append({'frame':e.frame,'other':e.other_actor.type_id,
                                                           'impulse':e.normal_impulse.length()}))
        self.actors.append(sensor)
        for _ in range(75):self.world.tick()
        self.initial_position=self.ego.get_location()
        self.start_time=self.world.get_snapshot().timestamp.elapsed_seconds
        self.last_control=None

    def release(self):
        # Initial velocity starts the shot during arrival; subsequent motion uses physics.
        speed=9. if self.kind=='road_rage' else 6.
        f=self.ego.get_transform().get_forward_vector()
        self.ego.apply_control(carla.VehicleControl(throttle=.25,hand_brake=False))
        self.ego.set_target_velocity(f*speed)
        for item in self.traffic:
            actor=item['actor'];f=actor.get_transform().get_forward_vector()
            v=2.5 if item['role']=='encounter' else 5.2 if item['role']=='cut_in' else 6.
            actor.apply_control(carla.VehicleControl(throttle=.2,hand_brake=False))
            actor.set_target_velocity(f*v)

    def step_traffic(self,t,green_at,pressed):
        cut=self.kind.startswith('cut_in');rage=self.kind=='road_rage'
        if self.kind in {'empty','wait_green'}:
            stopped=self.ego.get_velocity().length()<.25 and (self.lead is None or self.lead.get_velocity().length()<.25)
            if stopped and self.stopped_since is None:self.stopped_since=t
            if not stopped and not self.green_released:self.stopped_since=None
            if t>=green_at and self.stopped_since is not None and t-self.stopped_since>=.8:
                self.green_released=True
        self.set_green(cut or rage or self.kind=='arrive_green' or self.green_released)
        if pressed and self.light.get_state()==carla.TrafficLightState.Green and self.started_horn_at is None:
            self.started_horn_at=t
        for item in self.traffic:
            control=item['agent'].run_step()
            if item['role']=='lead' and self.kind=='wait_green' and self.green_released and self.started_horn_at is None:
                control=carla.VehicleControl(brake=1.)
            if item['role']=='cut_in':
                item['agent'].set_target_speed((5.2 if t<3 else 8.)*3.6)
            item['actor'].apply_control(control)
        requested=self.ego_agent.run_step()
        if cut:
            requested.brake=0.;requested.throttle=max(.35,requested.throttle)
        if rage:
            requested.brake=0.;requested.throttle=max(.3,requested.throttle)
            requested.steer=float(np.clip(requested.steer+.35*math.sin(t*1.8)+.10*math.sin(t*4.3),-.57,.57))
        self.last_control=requested
        return float(np.clip(requested.steer/1.7,-.34,.34))

    def apply_measured(self,steer):
        control=self.last_control
        control.steer=float(steer)
        self.ego.apply_control(control)

    def path_position(self,position):
        xy=np.array([position.x,position.y])
        fraction=np.clip(np.sum((xy-self.path_start)*self.path_delta,axis=1)/self.path_length**2,0.,1.)
        distance=np.linalg.norm(xy-(self.path_start+fraction[:,None]*self.path_delta),axis=1)
        index=int(np.argmin(distance))
        return float(self.path_cumulative[index]+fraction[index]*self.path_length[index]),float(distance[index])

    def observed(self,request):
        state=self.light.get_state();position=self.ego.get_location()
        # Project actual positions onto the provided route centreline. A bend or
        # steering correction must not make a lead car vanish from its lane.
        ego_progress,_=self.path_position(position)
        leads=[];nearby=[]
        for item in self.traffic:
            car=item['actor'];delta=car.get_location()-position
            progress,lateral=self.path_position(car.get_location());along=progress-ego_progress
            distance=delta.length();nearby.append(distance)
            if 0<along<40 and lateral<2.:
                leads.append((max(0.,along-self.ego.bounding_box.extent.x-car.bounding_box.extent.x),car.get_velocity().length()))
        gap,lead_speed=min(leads) if leads else (40.,0.)
        nearest=min(nearby) if nearby else 40.
        return np.array([state==carla.TrafficLightState.Red,state==carla.TrafficLightState.Green,
                         bool(leads),gap,lead_speed,self.ego.get_velocity().length(),nearest<14.,
                         min(nearest,40.),self.kind=='road_rage',request],np.float32)

    def metadata(self):
        return {**super().metadata(),'kind':getattr(self,'kind',None),
                'junction':self.junction_description,'traffic_count':len(self.traffic),
                'controlled_route_light_ids':self.route_light_ids,
                'signal_scope':'Native lamp matched to the current scenario approach; route lamps held green for directed cut-in/rage scenes',
                'route_points':[[w.transform.location.x,w.transform.location.y,w.transform.location.z] for w,_ in self.ego_route],
                'directed':'BasicAgent route and speed control; cut-in/rage deliberately do not brake; only measured fly wheel supplies applied steering'}
