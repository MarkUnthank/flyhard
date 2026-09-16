"""A controlled CARLA intersection; the horn policy sees observed state only.

Traffic-light scheduling and approach/braking are scenario infrastructure, not
learned driving. No scenario label or switch timestamp enters the observations.
"""
import math
import carla
import numpy as np


class HornWorld:
    dt = 1 / 60

    def __init__(self, town='Town03'):
        self.client = carla.Client('127.0.0.1', 2000)
        self.client.set_timeout(120.)
        self.world = self.client.get_world()
        if not self.world.get_map().name.endswith(town):
            self.world = self.client.load_world(town)
        self.original_settings = self.world.get_settings()
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = self.dt
        settings.substepping = True
        settings.max_substep_delta_time = .01
        settings.max_substeps = 10
        settings.no_rendering_mode = False
        self.world.apply_settings(settings)
        weather = carla.WeatherParameters.ClearNoon
        weather.sun_altitude_angle = 52
        self.world.set_weather(weather)
        self.map = self.world.get_map()
        self.actors = []
        self.ego = self.lead = None
        self.lights = list(self.world.get_actors().filter('traffic.traffic_light'))
        self.saved_lights = [(light, light.get_state(), light.is_frozen()) for light in self.lights]
        for light in self.lights:
            light.freeze(True)
            light.set_state(carla.TrafficLightState.Red)
        choices = []
        for light in self.lights:
            for waypoint in light.get_stop_waypoints():
                previous = waypoint.previous(30.)
                if not previous or previous[0].is_junction:
                    continue
                yaw_error = abs((previous[0].transform.rotation.yaw - waypoint.transform.rotation.yaw + 180) % 360 - 180)
                if yaw_error < 4:
                    choices.append((light.id, waypoint.road_id, waypoint.lane_id, light, waypoint))
        if not choices:
            raise RuntimeError('No straight, traffic-light-controlled approach found')
        _, _, _, self.light, self.stop = sorted(choices, key=lambda v: v[:3])[0]
        self.requested_green = None
        self.forward = self.stop.transform.get_forward_vector()
        self.right = self.stop.transform.get_right_vector()

    def behind(self, distance):
        options = self.stop.previous(distance)
        if not options:
            raise RuntimeError('Approach ends before the requested position')
        p = options[0].transform
        return carla.Transform(carla.Location(x=p.location.x, y=p.location.y, z=p.location.z+.35), p.rotation)

    def start(self, kind, gap=7.2):
        for actor in reversed(self.actors):
            if actor.is_alive:
                actor.destroy()
        self.actors = []
        library = self.world.get_blueprint_library()
        self.lead = None
        self.kind = kind
        self.set_green(kind == 'arrive_green')
        lead_bp = library.find('vehicle.lincoln.mkz_2020')
        lead_bp.set_attribute('color', '190,190,190')
        lead_bp.set_attribute('role_name', 'horn_scenario_lead')
        if kind != 'no_car':
            self.lead = self.world.spawn_actor(lead_bp, self.behind(3.))
            self.actors.append(self.lead)
            self.lead.apply_control(carla.VehicleControl(brake=1., hand_brake=True))
        hero_bp = library.find('vehicle.mini.cooper_s_2021')
        hero_bp.set_attribute('color', '48,84,43')
        hero_bp.set_attribute('role_name', 'hero')
        # Distance is measured between collision-box ends, not actor centres.
        self.ego = self.world.spawn_actor(hero_bp, self.behind(3.+4.8+gap))
        self.actors.append(self.ego)
        self.ego.apply_control(carla.VehicleControl(brake=1., hand_brake=True))
        for _ in range(90):
            self.world.tick()
        self.initial_position = self.ego.get_location()
        self.start_time = self.world.get_snapshot().timestamp.elapsed_seconds

    def set_green(self, green):
        # set_state is asynchronous. Reissuing red then green every tick can
        # expose transient red observations even while the camera shows green.
        # The other approaches were set to red once during scene construction.
        if green != self.requested_green:
            self.light.set_state(carla.TrafficLightState.Green if green else carla.TrafficLightState.Red)
            self.requested_green = green

    def observe(self):
        state = self.light.get_state()
        position = self.ego.get_location()
        lead_present, gap, lead_speed = False, 30., 0.
        if self.lead is not None and self.lead.is_alive:
            delta = self.lead.get_location() - position
            along = delta.x*self.forward.x + delta.y*self.forward.y
            lateral = abs(delta.x*self.right.x + delta.y*self.right.y)
            lead_present = 0 < along < 35 and lateral < 1.6
            if lead_present:
                gap = max(0., along-self.ego.bounding_box.extent.x-self.lead.bounding_box.extent.x)
                lead_speed = self.lead.get_velocity().length()
        return np.array([state == carla.TrafficLightState.Red,
                         state == carla.TrafficLightState.Green, lead_present, gap,
                         lead_speed, self.ego.get_velocity().length()], dtype=np.float32)

    def approach_control(self, elapsed, steer):
        # Horn-only experiment: this conventional controller positions the car.
        target = .8 if self.kind == 'arrive_green' and elapsed < 2.5 else 0.
        speed = self.ego.get_velocity().length()
        if target == 0:
            return carla.VehicleControl(brake=1., hand_brake=True, steer=steer)
        return carla.VehicleControl(throttle=float(np.clip(.22+.5*(target-speed), 0., .6)),
                                   brake=float(np.clip(.8*(speed-target), 0., .5)), steer=steer)

    def metadata(self):
        return {'map': self.map.name, 'traffic_light_id': self.light.id,
                'stop_transform': self.stop.transform.get_matrix(),
                'road_id': self.stop.road_id, 'lane_id': self.stop.lane_id,
                'light_transform': self.light.get_transform().get_matrix()}

    def lamp_camera(self):
        from flyhard.shot_cameras import look_at
        boxes = self.light.get_light_boxes()
        box = min(boxes, key=lambda b: b.location.distance(self.stop.transform.location))
        centre = box.location
        target = [centre.x, centre.y, centre.z]
        position = [centre.x-3*self.forward.x, centre.y-3*self.forward.y, centre.z]
        return look_at(position, target)

    def close(self):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                actor.destroy()
        for light, state, frozen in self.saved_lights:
            if light.is_alive:
                light.set_state(state)
                light.freeze(frozen)
        self.world.apply_settings(self.original_settings)
