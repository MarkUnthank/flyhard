"""Native CARLA give-way junction driven by measured fly pedals.

The crossing vehicle is a real CARLA actor driven by a deterministic lane follower
rather than a BasicAgent: a held-out case has to replay identically, and BasicAgent
picks its own speed profile and reacts to the ego, which would make the ego's own
decision unmeasurable. Its path is a straight run through the junction anyway.

All signals are frozen green so that any stop the car makes is caused by the other
vehicle and not by a light. Steering is a conventional lane-keeping request and is
disclosed as such; the learned policy supplies only brake and throttle, applied as
pedal travel measured off the fly's legs.
"""
import math

import carla
import numpy as np

from flyhard.crossing import (BRAKE_FREE_PLAY, FRONT_OVERHANG, THROTTLE_FREE_PLAY, past_free_play)
from flyhard.junction import (CONFLICT_HALF_SPAN, HOLD_POINT, JUNCTION_DEPTH, MAX_OTHER_START,
                              OTHER_HALF_LENGTH, observation)
from flyhard.parking import REAR_TO_CENTER

ORDINARY = ['vehicle.mercedes.coupe_2020', 'vehicle.audi.tt', 'vehicle.nissan.patrol_2021',
            'vehicle.seat.leon', 'vehicle.citroen.c3']
EMERGENCY = ['vehicle.ford.ambulance', 'vehicle.dodge.charger_police_2020']
EMERGENCY_LIGHTS = carla.VehicleLightState(
    carla.VehicleLightState.Special1 | carla.VehicleLightState.Special2 |
    carla.VehicleLightState.LowBeam | carla.VehicleLightState.Position)


def angular(a, b):
    return abs((a-b+180) % 360-180)


def angular_signed(a, b):
    return (a-b+180) % 360-180


class JunctionWorld:
    dt = 1/60

    def __init__(self, town='Town05', approach_metres=72.):
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
        weather.sun_altitude_angle = 48
        self.world.set_weather(weather)
        self.map = self.world.get_map()
        self.actors = []
        self.ego = self.other = None
        self.lights = list(self.world.get_actors().filter('traffic.traffic_light'))
        self.saved_lights = [(light, light.get_state(), light.is_frozen()) for light in self.lights]
        for light in self.lights:
            light.freeze(True)
            light.set_state(carla.TrafficLightState.Green)
        self.mirrored_side = False
        self.site = self.select_site(approach_metres)
        transform = self.site['ego_entry'].transform
        self.origin = transform.location
        self.forward = transform.get_forward_vector()
        self.right = transform.get_right_vector()
        self.approach_yaw = transform.rotation.yaw
        self.centre = self.origin+self.forward*(JUNCTION_DEPTH/2)
        self.side_forward = None   # Set per case: it depends which arm the case uses.

    def select_site(self, approach_metres):
        """A junction with a long straight ego approach and a usable arm on each side.

        Both sides matter: `right` cases need a vehicle that really is on the right and
        `left` cases one that really is on the left, so a junction offering only one of
        them would quietly film the wrong geometry.
        """
        junctions = {}
        for waypoint in self.map.generate_waypoints(5.):
            if waypoint.is_junction:
                junctions.setdefault(waypoint.get_junction().id, waypoint.get_junction())
        choices = []
        for junction in junctions.values():
            pairs = junction.get_waypoints(carla.LaneType.Driving)
            headings = {round(a.transform.rotation.yaw/90) % 4 for a, _ in pairs}
            if len(headings) not in {3, 4}:
                continue
            for entry, exit_ in pairs:
                if angular(entry.transform.rotation.yaw, exit_.transform.rotation.yaw) > 10:
                    continue
                before = entry.previous(approach_metres)
                after = exit_.next(34.)
                if not before or not after or before[0].is_junction or after[0].is_junction:
                    continue
                if angular(before[0].transform.rotation.yaw, entry.transform.rotation.yaw) > 6:
                    continue
                site = {'junction': junction.id, 'arms': len(headings), 'ego_entry': entry,
                        'ego_start': before[0], 'exit': exit_, 'road_id': entry.road_id,
                        'lane_id': entry.lane_id}
                site['side_arms'] = self.side_arms(site)
                if not site['side_arms']:
                    continue
                choices.append(site)
        if not choices:
            raise RuntimeError('No junction with a long straight approach and a usable side arm')
        return sorted(choices, key=lambda c: (-len(c['side_arms']), -c['arms'], c['junction'],
                                              c['road_id'], c['lane_id']))[0]

    def side_arms(self, site, approach_metres=MAX_OTHER_START+4.):
        # 60 m is what Town05 actually validates on both sides of a junction; longer
        # runs exist on one side only, which would make `left` and `right` different
        # places and the comparison meaningless.
        """Perpendicular entry lanes with a clean straight approach, keyed by side.

        The key is the sign of the lateral offset from the ego's own path, so a case
        asking for a vehicle from the right gets an arm that really is on the right.
        """
        transform = site['ego_entry'].transform
        origin, right = transform.location, transform.get_right_vector()
        yaw = transform.rotation.yaw
        found = {}
        for entry, _ in site['ego_entry'].get_junction().get_waypoints(carla.LaneType.Driving):
            if not 70 < angular(entry.transform.rotation.yaw, yaw) < 110:
                continue
            previous = entry.previous(approach_metres)
            if not previous or previous[0].is_junction:
                continue
            if angular(previous[0].transform.rotation.yaw, entry.transform.rotation.yaw) > 10:
                continue
            offset = entry.transform.location-origin
            lateral = offset.x*right.x+offset.y*right.y
            if abs(lateral) < 3.:
                continue
            side = math.copysign(1., lateral)
            # Prefer the arm whose entry sits furthest from the ego's own lane: that is
            # the through lane a car would come down, not a short turning stub.
            if side not in found or abs(lateral) > found[side][0]:
                found[side] = (abs(lateral), entry)
        return {side: entry for side, (_, entry) in found.items()}

    def side_entry_for(self, side):
        """The perpendicular entry lane on the requested side, or the other one, flagged."""
        arms = self.site['side_arms']
        if side in arms:
            return arms[side]
        # No usable arm on that side. Use the one there is and say so in the metadata
        # rather than silently filming the wrong geometry.
        self.mirrored_side = True
        return arms[next(iter(arms))]

    def along(self, location):
        delta = location-self.origin
        return delta.x*self.forward.x+delta.y*self.forward.y

    def other_position(self):
        """Signed distance of the crossing vehicle to the conflict centre, along its own path."""
        delta = self.other.get_location()-self.centre
        return delta.x*self.side_forward.x+delta.y*self.side_forward.y

    def start(self, case):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                actor.destroy()
        self.actors = []
        self.case = case
        self.collision_events = []
        library = self.world.get_blueprint_library()

        spawn = self.site['ego_entry'].previous(abs(case.start_x))
        if not spawn:
            raise RuntimeError('Ego approach is shorter than the requested start distance')
        pose = spawn[0].transform
        hero = library.find('vehicle.mini.cooper_s_2021')
        hero.set_attribute('color', '48,84,43')
        hero.set_attribute('role_name', 'hero')
        self.ego = self.world.spawn_actor(hero, carla.Transform(
            carla.Location(pose.location.x, pose.location.y, pose.location.z+.3), pose.rotation))
        self.actors.append(self.ego)
        self.ego.apply_control(carla.VehicleControl(brake=1., hand_brake=True))

        # The side arm the case asks for: the junction gives one perpendicular entry, and
        # the opposite one is reached by taking the entry whose heading is reversed.
        self.side = self.side_entry_for(case.other_side)
        self.side_forward = self.side.transform.get_forward_vector()
        self.side_origin = self.side.transform.location
        back = self.side.previous(abs(case.other_start))
        if not back:
            raise RuntimeError('Side approach is shorter than the requested start distance')
        names = EMERGENCY if case.emergency else ORDINARY
        other_bp = library.find(names[case.seed % len(names)])
        if other_bp.has_attribute('color') and not case.emergency:
            other_bp.set_attribute('color', '200,200,205')
        other_bp.set_attribute('role_name', 'other')
        self.other = self.world.spawn_actor(other_bp, carla.Transform(
            carla.Location(back[0].transform.location.x, back[0].transform.location.y,
                           back[0].transform.location.z+.3), back[0].transform.rotation))
        self.actors.append(self.other)
        self.other.apply_control(carla.VehicleControl(brake=1., hand_brake=True))
        if case.emergency:
            self.other.set_light_state(EMERGENCY_LIGHTS)

        sensor = self.world.spawn_actor(library.find('sensor.other.collision'),
                                        carla.Transform(), attach_to=self.ego)
        sensor.listen(lambda e: self.collision_events.append(
            {'frame': e.frame, 'other': e.other_actor.type_id, 'impulse': e.normal_impulse.length()}))
        self.actors.append(sensor)
        for _ in range(60):
            self.world.tick()

    def release(self):
        forward = self.ego.get_transform().get_forward_vector()
        self.ego.apply_control(carla.VehicleControl(throttle=.25, hand_brake=False))
        self.ego.set_target_velocity(forward*self.case.approach_speed)
        other_forward = self.other.get_transform().get_forward_vector()
        self.other.apply_control(carla.VehicleControl(throttle=.3, hand_brake=False))
        self.other.set_target_velocity(other_forward*self.case.other_speed)

    def scenario_state(self):
        front = self.along(self.ego.get_location())+self.ego.bounding_box.extent.x
        return np.array([front-FRONT_OVERHANG, self.ego.get_velocity().length()])

    def step_other(self):
        """Deterministic lane follower for the crossing vehicle. Returns (position, speed)."""
        other_s = self.other_position()
        speed = self.other.get_velocity().length()
        ego_rear = self.scenario_state()[0]-REAR_TO_CENTER
        waiting = (self.case.other_waits and other_s < HOLD_POINT
                   and ego_rear < JUNCTION_DEPTH+1.5)
        wanted = (min(self.case.other_speed, max(0., (HOLD_POINT-other_s)/1.2)) if waiting
                  else self.case.other_speed)
        # Aim along the straight line of its own arm rather than at the next waypoint:
        # inside the junction the waypoint graph curves into the turning lanes, and a
        # vehicle that turns mid-junction leaves the conflict box without crossing it.
        location = self.other.get_location()
        delta = location-self.side_origin
        travelled = delta.x*self.side_forward.x+delta.y*self.side_forward.y
        aim = self.side_origin+self.side_forward*(travelled+8.)
        offset = aim-location
        desired = math.degrees(math.atan2(offset.y, offset.x))
        steer = float(np.clip(angular_signed(desired, self.other.get_transform().rotation.yaw)/28.,
                              -1., 1.))
        error = wanted-speed
        self.other.apply_control(carla.VehicleControl(
            throttle=float(np.clip(error*.45, 0., .7)),
            brake=float(np.clip(-error*.35, 0., 1.)), steer=steer, hand_brake=False))
        return other_s, speed

    def hazard(self, now):
        """Advance the crossing vehicle and report what the policy may measure."""
        other_s, other_speed = self.step_other()
        return (other_s, other_speed), {'other_s': float(other_s),
                                        'other_speed': float(other_speed)}

    def done(self, state):
        return bool(state[0]+FRONT_OVERHANG > JUNCTION_DEPTH+14.)

    def focus(self):
        return self.centre

    def observe(self, other_s, other_speed, throttle, brake):
        return observation(self.scenario_state(), self.case, other_s, other_speed, throttle, brake)

    def apply_measured(self, throttle, brake, steer):
        self.ego.apply_control(carla.VehicleControl(
            throttle=float(np.clip(past_free_play(throttle, THROTTLE_FREE_PLAY), 0., 1.)),
            brake=float(np.clip(past_free_play(brake, BRAKE_FREE_PLAY), 0., 1.)),
            steer=float(np.clip(steer, -1., 1.)), hand_brake=False))

    def lane_steer(self):
        """Conventional lane keeping. Not a learned output and not presented as one."""
        location = self.ego.get_location()
        waypoint = self.map.get_waypoint(location, project_to_road=True,
                                         lane_type=carla.LaneType.Driving)
        delta = location-waypoint.transform.location
        offset = delta.x*self.right.x+delta.y*self.right.y
        heading = math.radians(angular_signed(self.ego.get_transform().rotation.yaw,
                                              waypoint.transform.rotation.yaw))
        return float(np.clip(-.35*offset-.8*heading, -.6, .6))

    def metadata(self):
        return {'map': self.map.name, 'junction_id': self.site['junction'],
                'arms': self.site['arms'], 'road_id': self.site['road_id'],
                'lane_id': self.site['lane_id'],
                'entry_transform': self.site['ego_entry'].transform.get_matrix(),
                'side_arms_available': sorted(float(k) for k in self.site['side_arms']),
                'mirrored_side_arm': bool(self.mirrored_side),
                'other_control': 'deterministic lane follower at a fixed target speed, so a '
                                 'held-out case replays identically; not a BasicAgent',
                'steering': 'Conventional lane-keeping request; the learned policy supplies '
                            'only brake and throttle, applied as measured pedal travel',
                'pedal_free_play': {'brake': BRAKE_FREE_PLAY, 'throttle': THROTTLE_FREE_PLAY},
                'lights': 'All signals frozen green, so any stop is caused by the other vehicle',
                'sirens': 'Blue lights are rendered by CARLA; siren audio is added in post and '
                          'is not part of the simulation'}

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
