"""Native CARLA pedestrian crossing driven by measured fly pedals.

Town05 is the default because it is the only stock town with a painted crossing
away from a junction that still has a long straight approach: 71 of Town03's 73
crosswalks sit inside junctions, and Town04 and Town10HD have none usable.

The walker is a real CARLA actor moved with WalkerControl each tick rather than by
WalkerAIController: a held-out case has to replay identically, and the AI
controller picks its own path and start-up latency through the navigation mesh.
On a marked crossing the path is a straight line anyway.

Steering is a conventional lane-keeping request and is disclosed as such. The
learned policy supplies only the brake and throttle demand, and CARLA receives
pedal travel measured off the fly's legs.
"""
import math

import carla
import numpy as np

# Free play lives in flyhard.crossing so the kinematic teaching model and the car
# apply exactly the same linkage. Without it the small residual the policy's sigmoid
# cannot drive to zero acts as a permanent light brake, which stops the automatic
# gearbox engaging from rest and pins the car with the throttle open.
from flyhard.crossing import (BRAKE_FREE_PLAY, CROSSING_DEPTH, FRONT_OVERHANG, SENSING_RANGE,
                              THROTTLE_FREE_PLAY, observation, past_free_play)

WALKER_Z = .92


def group_crosswalks(points):
    """CARLA returns crosswalk polygons as a flat point list, each closed by repeating its first point."""
    polygons, current = [], []
    for point in points:
        if current and point.distance(current[0]) < .01:
            current.append(point)
            polygons.append(current)
            current = []
        else:
            current.append(point)
    if len(current) >= 3:
        polygons.append(current)
    return [p for p in polygons if len(p) >= 4]


def angular(a, b):
    return abs((a-b+180) % 360-180)


class CrossingWorld:
    dt = 1/60

    def __init__(self, town='Town05', approach_metres=70.):
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
        self.world.apply_settings(settings)
        weather = carla.WeatherParameters.ClearNoon
        weather.sun_altitude_angle = 52
        self.world.set_weather(weather)
        self.map = self.world.get_map()
        self.actors = []
        self.ego = self.walker = None
        # Freeze every light red-free: this scenario is about the pedestrian, and a
        # signal cycling mid-approach would confound the measured stop.
        self.lights = list(self.world.get_actors().filter('traffic.traffic_light'))
        self.saved_lights = [(light, light.get_state(), light.is_frozen()) for light in self.lights]
        for light in self.lights:
            light.freeze(True)
            light.set_state(carla.TrafficLightState.Green)
        self.site = self.select_site(approach_metres)
        transform = self.site['stop'].transform
        self.origin = transform.location
        self.forward = transform.get_forward_vector()
        self.right = transform.get_right_vector()
        self.approach_yaw = transform.rotation.yaw

    def select_site(self, approach_metres):
        """Prefer a painted crosswalk on a straight, non-junction approach."""
        candidates = []
        for polygon in group_crosswalks(self.map.get_crosswalks()):
            centre = carla.Location(
                x=float(np.mean([p.x for p in polygon])), y=float(np.mean([p.y for p in polygon])),
                z=float(np.mean([p.z for p in polygon])))
            waypoint = self.map.get_waypoint(centre, project_to_road=True,
                                             lane_type=carla.LaneType.Driving)
            if waypoint is None or waypoint.is_junction:
                continue
            previous = waypoint.previous(approach_metres)
            if not previous or previous[0].is_junction:
                continue
            if angular(previous[0].transform.rotation.yaw, waypoint.transform.rotation.yaw) > 6:
                continue
            span = max(a.distance(b) for a in polygon for b in polygon)
            if not 4. < span < 24.:
                continue
            candidates.append({'painted': True, 'polygon': polygon, 'span': span,
                               'stop': waypoint.previous(CROSSING_DEPTH/2)[0], 'centre': centre,
                               'road_id': waypoint.road_id, 'lane_id': waypoint.lane_id})
        if candidates:
            return sorted(candidates, key=lambda c: (c['road_id'], c['lane_id']))[0]
        # No painted crossing with a usable approach. Fall back to a straight
        # segment and say so; a virtual crossing is still a valid benchmark.
        for waypoint in self.map.generate_waypoints(5.):
            if waypoint.is_junction:
                continue
            previous = waypoint.previous(approach_metres)
            following = waypoint.next(30.)
            if not previous or not following or previous[0].is_junction or following[0].is_junction:
                continue
            if angular(previous[0].transform.rotation.yaw, waypoint.transform.rotation.yaw) > 4:
                continue
            return {'painted': False, 'polygon': [], 'span': 0., 'stop': waypoint,
                    'centre': waypoint.transform.location,
                    'road_id': waypoint.road_id, 'lane_id': waypoint.lane_id}
        raise RuntimeError('No straight approach found for a crossing scenario')

    def along(self, location):
        delta = location-self.origin
        return delta.x*self.forward.x+delta.y*self.forward.y

    def lateral(self, location):
        delta = location-self.origin
        return delta.x*self.right.x+delta.y*self.right.y

    def start(self, case):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                actor.destroy()
        self.actors = []
        self.case = case
        self.triggered_at = None
        self.collision_events = []
        library = self.world.get_blueprint_library()

        spawn = self.site['stop'].previous(abs(case.start_x))
        if not spawn:
            raise RuntimeError('Approach is shorter than the requested start distance')
        pose = spawn[0].transform
        hero = library.find('vehicle.mini.cooper_s_2021')
        hero.set_attribute('color', '48,84,43')
        hero.set_attribute('role_name', 'hero')
        self.ego = self.world.spawn_actor(hero, carla.Transform(
            carla.Location(pose.location.x, pose.location.y, pose.location.z+.3), pose.rotation))
        self.actors.append(self.ego)
        self.ego.apply_control(carla.VehicleControl(brake=1., hand_brake=True))

        # Walker starts on the kerb, offset along the band by the case's walk offset.
        kerb = self.origin+self.forward*case.walk_offset+self.right*case.kerb_y
        walker_bp = library.filter('walker.pedestrian.*')[case.seed % len(library.filter('walker.pedestrian.*'))]
        if walker_bp.has_attribute('is_invincible'):
            walker_bp.set_attribute('is_invincible', 'false')
        facing = carla.Rotation(yaw=self.approach_yaw+(90. if case.kerb_side > 0 else -90.))
        self.walker = self.world.spawn_actor(walker_bp, carla.Transform(
            carla.Location(kerb.x, kerb.y, self.origin.z+WALKER_Z), facing))
        self.actors.append(self.walker)
        self.walker.apply_control(carla.WalkerControl(speed=0.))

        sensor = self.world.spawn_actor(library.find('sensor.other.collision'),
                                        carla.Transform(), attach_to=self.ego)
        sensor.listen(lambda e: self.collision_events.append(
            {'frame': e.frame, 'other': e.other_actor.type_id, 'impulse': e.normal_impulse.length()}))
        self.actors.append(sensor)
        for _ in range(60):
            self.world.tick()
        self.start_time = self.world.get_snapshot().timestamp.elapsed_seconds

    def release(self):
        """Give the car its approach speed; everything after this is physics and control."""
        forward = self.ego.get_transform().get_forward_vector()
        self.ego.apply_control(carla.VehicleControl(throttle=.25, hand_brake=False))
        self.ego.set_target_velocity(forward*self.case.approach_speed)

    def scenario_state(self):
        """[rear-axle x, speed] in the crossing frame, matching flyhard.crossing."""
        front = self.along(self.ego.get_location())+self.ego.bounding_box.extent.x
        return np.array([front-FRONT_OVERHANG, self.ego.get_velocity().length()])

    def step_walker(self, now):
        """Trigger and drive the pedestrian. Returns (lateral position, lateral speed, walking)."""
        state = self.scenario_state()
        front = state[0]+FRONT_OVERHANG
        if self.triggered_at is None and -front <= self.case.trigger_distance:
            self.triggered_at = now
        y = self.lateral(self.walker.get_location())
        walking = False
        speed = 0.
        if self.triggered_at is not None and now-self.triggered_at >= self.case.dwell_seconds:
            # Walk straight across, away from the starting kerb, until past the far side.
            if abs(y) < abs(self.case.kerb_y) or y*self.case.kerb_side > 0:
                walking = True
                speed = self.case.walk_speed
        direction = -self.case.kerb_side
        control = carla.WalkerControl()
        control.direction = carla.Vector3D(x=self.right.x*direction, y=self.right.y*direction, z=0.)
        control.speed = float(speed)
        self.walker.apply_control(control)
        return y, direction*speed if walking else 0., walking

    def hazard(self, now):
        """Advance the other road user and report what the policy may measure.

        Returns the values `observe` takes plus the fields the scorer needs, so one
        evaluation loop serves every scenario without knowing what the hazard is.
        """
        pedestrian_y, lateral_speed, walking = self.step_walker(now)
        return (pedestrian_y, lateral_speed), {'pedestrian_y': float(pedestrian_y),
                                               'walking': bool(walking)}

    def done(self, state):
        return bool(state[0]+FRONT_OVERHANG > self.case.walk_offset+14.)

    def focus(self):
        return self.site['centre']

    def observe(self, pedestrian_y, lateral_speed, throttle, brake):
        return observation(self.scenario_state(), self.case, pedestrian_y, lateral_speed, throttle, brake)

    def apply_measured(self, throttle, brake, steer):
        """CARLA receives only measured pedal travel, past the linkage's free play."""
        self.ego.apply_control(carla.VehicleControl(
            throttle=float(np.clip(past_free_play(throttle, THROTTLE_FREE_PLAY), 0., 1.)),
            brake=float(np.clip(past_free_play(brake, BRAKE_FREE_PLAY), 0., 1.)),
            steer=float(np.clip(steer, -1., 1.)), hand_brake=False))

    def lane_steer(self):
        """Conventional lane keeping. Not a learned output and not presented as one."""
        location = self.ego.get_location()
        waypoint = self.map.get_waypoint(location, project_to_road=True, lane_type=carla.LaneType.Driving)
        offset = self.lateral(location)-self.lateral(waypoint.transform.location)
        heading = math.radians(angular_signed(self.ego.get_transform().rotation.yaw,
                                              waypoint.transform.rotation.yaw))
        return float(np.clip(-.35*offset-.8*heading, -.6, .6))

    def metadata(self):
        return {'map': self.map.name, 'painted_crosswalk': self.site['painted'],
                'crosswalk_span_m': round(self.site['span'], 3),
                'road_id': self.site['road_id'], 'lane_id': self.site['lane_id'],
                'stop_transform': self.site['stop'].transform.get_matrix(),
                'walker_control': 'per-tick WalkerControl for a replayable held-out case; '
                                  'no WalkerAIController navigation',
                'steering': 'Conventional lane-keeping request; the learned policy supplies '
                            'only brake and throttle, applied as measured pedal travel',
                'pedal_free_play': {'brake': BRAKE_FREE_PLAY, 'throttle': THROTTLE_FREE_PLAY,
                                    'note': 'Fixed linkage free travel applied to measured pedal '
                                            'position before CARLA; identical in every trial'},
                'lights': 'All signals frozen green so the measured stop is caused by the pedestrian'}

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


def angular_signed(a, b):
    return (a-b+180) % 360-180
