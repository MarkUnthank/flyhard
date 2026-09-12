"""Native CARLA dual-carriageway overtake driven by measured fly controls.

This is the scenario where the fly steers. The learned policy produces throttle,
brake and steering wheel travel, and CARLA receives only what is measured off the
fly's limbs after the linkage's free play.

Both other vehicles are deterministic constant-speed lane followers running the
straight line of their own lane, not BasicAgents: a held-out case has to replay
identically, and an agent that reacted to the ego would make the ego's own decision
unmeasurable.
"""
import math

import carla
import numpy as np

from flyhard.crossing import BRAKE_FREE_PLAY, THROTTLE_FREE_PLAY, past_free_play
from flyhard.overtake import FRONT_OVERHANG, LANE_WIDTH, observation

LEAD_BLUEPRINTS = ['vehicle.carlamotors.carlacola', 'vehicle.mercedes.sprinter',
                   'vehicle.nissan.patrol_2021']
OUTSIDE_BLUEPRINTS = ['vehicle.audi.tt', 'vehicle.dodge.charger_2020', 'vehicle.seat.leon']


def angular(a, b):
    return abs((a-b+180) % 360-180)


def angular_signed(a, b):
    return (a-b+180) % 360-180


class OvertakeWorld:
    dt = 1/60

    def __init__(self, town='Town04', straight_metres=340.):
        self.client = carla.Client('127.0.0.1', 2000)
        self.client.set_timeout(180.)
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
        weather.sun_altitude_angle = 55
        self.world.set_weather(weather)
        self.map = self.world.get_map()
        self.actors = []
        self.ego = self.lead = self.outside = None
        self.site = self.select_site(straight_metres)
        transform = self.site['start'].transform
        self.origin = transform.location
        self.forward = transform.get_forward_vector()
        self.right = transform.get_right_vector()
        self.approach_yaw = transform.rotation.yaw

    def select_site(self, straight_metres):
        """A lane with a same-direction lane to its left and a long straight run ahead."""
        best = None
        for waypoint in self.map.generate_waypoints(12.):
            if waypoint.is_junction:
                continue
            left = waypoint.get_left_lane()
            if left is None or left.lane_type != carla.LaneType.Driving:
                continue
            if left.lane_id*waypoint.lane_id < 0:
                continue            # Opposing carriageway, not an overtaking lane.
            straight, node = 0., waypoint
            while straight < straight_metres:
                following = node.next(12.)
                if not following or following[0].is_junction:
                    break
                if angular(following[0].transform.rotation.yaw, waypoint.transform.rotation.yaw) > 8:
                    break
                node, straight = following[0], straight+12.
            if straight < straight_metres:
                continue
            candidate = {'start': waypoint, 'left': left, 'straight_m': straight,
                         'road_id': waypoint.road_id, 'lane_id': waypoint.lane_id}
            if best is None or (candidate['straight_m'], -candidate['road_id']) > \
                    (best['straight_m'], -best['road_id']):
                best = candidate
        if best is None:
            raise RuntimeError(f'No lane with an overtaking lane and {straight_metres:.0f} m straight')
        return best

    def along(self, location):
        delta = location-self.origin
        return delta.x*self.forward.x+delta.y*self.forward.y

    def lateral(self, location):
        """Positive to the left, matching flyhard.overtake's frame."""
        delta = location-self.origin
        return -(delta.x*self.right.x+delta.y*self.right.y)

    def place(self, distance, lane_offset, z=.3):
        """A pose `distance` along the carriageway, `lane_offset` metres left of the ego lane."""
        ahead = self.site['start'].next(max(distance, .01)) if distance > 0 else \
            self.site['start'].previous(max(-distance, .01))
        node = ahead[0] if ahead else self.site['start']
        base = node.transform
        location = base.location-base.get_right_vector()*lane_offset
        return carla.Transform(carla.Location(location.x, location.y, location.z+z), base.rotation)

    def spawn(self, blueprint, transform, colour=None, role='other'):
        library = self.world.get_blueprint_library()
        bp = library.find(blueprint)
        if colour and bp.has_attribute('color'):
            bp.set_attribute('color', colour)
        bp.set_attribute('role_name', role)
        actor = self.world.spawn_actor(bp, transform)
        self.actors.append(actor)
        actor.apply_control(carla.VehicleControl(brake=1., hand_brake=True))
        return actor

    def start(self, case):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                actor.destroy()
        self.actors = []
        self.case = case
        self.collision_events = []
        self.ego = self.spawn('vehicle.mini.cooper_s_2021', self.place(1., 0.), '48,84,43', 'hero')
        self.max_steer = max(w.max_steer_angle for w in self.ego.get_physics_control().wheels)
        self.lead = self.spawn(LEAD_BLUEPRINTS[case.seed % len(LEAD_BLUEPRINTS)],
                               self.place(1.+case.lead_gap, 0.), '190,190,195', 'lead')
        self.outside = None
        if case.has_outside:
            self.outside = self.spawn(
                OUTSIDE_BLUEPRINTS[case.seed % len(OUTSIDE_BLUEPRINTS)],
                self.place(1.+case.outside_gap, LANE_WIDTH), '25,25,30', 'outside')
        sensor = self.world.spawn_actor(
            self.world.get_blueprint_library().find('sensor.other.collision'),
            carla.Transform(), attach_to=self.ego)
        sensor.listen(lambda e: self.collision_events.append(
            {'frame': e.frame, 'other': e.other_actor.type_id, 'impulse': e.normal_impulse.length()}))
        self.actors.append(sensor)
        for _ in range(60):
            self.world.tick()

    def release(self):
        for actor, speed in [(self.ego, self.case.cruise_speed), (self.lead, self.case.lead_speed),
                             (self.outside, self.case.outside_speed)]:
            if actor is None:
                continue
            forward = actor.get_transform().get_forward_vector()
            actor.apply_control(carla.VehicleControl(throttle=.4, hand_brake=False))
            actor.set_target_velocity(forward*speed)

    def hold_lane(self, actor, lane_offset, wanted):
        """Deterministic straight-line follower at a fixed speed in a fixed lane."""
        location = actor.get_location()
        travelled = self.along(location)
        aim = self.place(travelled+12., lane_offset, z=0.).location
        offset = aim-location
        desired = math.degrees(math.atan2(offset.y, offset.x))
        steer = float(np.clip(angular_signed(desired, actor.get_transform().rotation.yaw)/26.,
                              -1., 1.))
        error = wanted-actor.get_velocity().length()
        actor.apply_control(carla.VehicleControl(
            throttle=float(np.clip(error*.4, 0., .85)), brake=float(np.clip(-error*.3, 0., 1.)),
            steer=steer, hand_brake=False))

    def scenario_state(self):
        """[x, lateral offset, heading error, speed] in the carriageway frame."""
        transform = self.ego.get_transform()
        location = transform.location
        return np.array([self.along(location)+self.ego.bounding_box.extent.x-FRONT_OVERHANG,
                         self.lateral(location),
                         math.radians(-angular_signed(transform.rotation.yaw, self.approach_yaw)),
                         self.ego.get_velocity().length()])

    def gaps(self):
        ego_x = self.along(self.ego.get_location())
        lead = self.along(self.lead.get_location())-ego_x
        outside = (self.along(self.outside.get_location())-ego_x
                   if self.outside is not None else None)
        return lead, outside

    def hazard(self, now):
        self.hold_lane(self.lead, 0., self.case.lead_speed)
        if self.outside is not None:
            self.hold_lane(self.outside, LANE_WIDTH, self.case.outside_speed)
        lead, outside = self.gaps()
        return (lead, outside), {'lead_gap': float(lead),
                                 'outside_gap': None if outside is None else float(outside)}

    def done(self, state):
        """Finished once the move is complete and settled, or once it is clearly not happening."""
        lead, _ = self.gaps()
        if not self.case.should_overtake:
            return bool(state[0] > 260.)
        return bool(lead < -26. and abs(state[1]) < .6)

    def focus(self):
        return self.origin

    def wide_attached(self):
        """The wide view follows the car here: the manoeuvre covers hundreds of metres,
        so a fixed camera would lose both vehicles within a couple of seconds."""
        return (carla.Transform(carla.Location(x=-15.5, y=-9.5, z=6.4),
                                carla.Rotation(pitch=-11.5, yaw=27.)), 62)

    def observe(self, lead_gap, outside_gap, throttle, brake, steer):
        return observation(self.scenario_state(), self.case, lead_gap, outside_gap,
                           throttle, brake, steer)

    def apply_measured(self, throttle, brake, steer):
        """CARLA receives only measured travel, past the linkage's free play.

        `steer` has already been read off the fly's wheel and converted into CARLA's
        own units, so it is applied as it stands. Positive lateral is to the left and
        CARLA's positive steer is to the right, hence the sign.
        """
        self.ego.apply_control(carla.VehicleControl(
            throttle=float(np.clip(past_free_play(throttle, THROTTLE_FREE_PLAY), 0., 1.)),
            brake=float(np.clip(past_free_play(brake, BRAKE_FREE_PLAY), 0., 1.)),
            steer=float(np.clip(-steer, -1., 1.)), hand_brake=False))

    def metadata(self):
        return {'map': self.map.name, 'road_id': self.site['road_id'],
                'lane_id': self.site['lane_id'], 'straight_metres': self.site['straight_m'],
                'start_transform': self.site['start'].transform.get_matrix(),
                'max_steer_angle_deg': getattr(self, 'max_steer', None),
                'traffic_control': 'deterministic straight-line followers at fixed speeds, so a '
                                   'held-out case replays identically; not BasicAgents',
                'steering': 'Learned. The policy outputs steering wheel travel and CARLA receives '
                            'the angle measured off the fly, through the vehicle max steer angle',
                'pedal_free_play': {'brake': BRAKE_FREE_PLAY, 'throttle': THROTTLE_FREE_PLAY}}

    def close(self):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                actor.destroy()
        self.world.apply_settings(self.original_settings)
