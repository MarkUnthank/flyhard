"""CARLA Town03 controlled routes with independently simulated traffic.

Route control and teacher/scoring annotations stay outside the learned policy.
The policy observes only CONTEXT_FIELDS, including a GPS destination cue.
"""
import math
import heapq
import itertools
from pathlib import Path
import sys

import carla
import numpy as np

sys.path.insert(0, "/opt/carla/PythonAPI/carla")
from agents.navigation.global_route_planner import GlobalRoutePlanner
from agents.navigation.local_planner import RoadOption
from agents.navigation.basic_agent import BasicAgent

from flyhard.indicator_policy import CENTRE, CONTEXT_FIELDS


DT = 0.05


def xyz(waypoint):
    p = waypoint.transform.location
    return np.array([p.x, p.y, p.z])


def set_signal(vehicle, signal):
    states = {"off": carla.VehicleLightState.NONE, "left": carla.VehicleLightState.LeftBlinker,
              "right": carla.VehicleLightState.RightBlinker}
    old = int(vehicle.get_light_state())
    blinkers = int(carla.VehicleLightState.LeftBlinker) | int(carla.VehicleLightState.RightBlinker)
    state = carla.VehicleLightState((old & ~blinkers) | int(states[signal]))
    vehicle.set_light_state(state)
    return int(state)


class RoundaboutWorld:
    def __init__(self, render=False, port=8000):
        self.client = carla.Client("127.0.0.1", 2000)
        self.client.set_timeout(60)
        self.world = self.client.get_world()
        if not self.world.get_map().name.endswith("/Town03"):
            self.world = self.client.load_world("Town03")
        self.original = self.world.get_settings()
        self.original_weather = self.world.get_weather()
        s = self.world.get_settings()
        s.synchronous_mode = True
        s.fixed_delta_seconds = DT
        s.no_rendering_mode = not render
        s.substepping = True
        s.max_substep_delta_time = 0.01
        s.max_substeps = 5
        self.world.apply_settings(s)
        self.world.set_weather(carla.WeatherParameters.ClearNoon)
        self.tm = self.client.get_trafficmanager(port)
        self.tm.set_synchronous_mode(True)
        self.port = port
        self.map = self.world.get_map()
        self.planner = GlobalRoutePlanner(self.map, 1.5)
        self.waypoints = self.map.generate_waypoints(2)
        self.actors = []
        self.traffic = []
        self.ego = None
        self.routes = self.build_routes()

    def build_routes(self):
        points = [(wp, xyz(wp)) for wp in self.waypoints]
        starts, goals = [], []
        for arm in range(4):
            radial = np.array([math.cos(arm * math.pi / 2), math.sin(arm * math.pi / 2)])
            candidates = []
            for wp, p in points:
                delta = p[:2] - CENTRE
                radius = np.linalg.norm(delta)
                if 48 <= radius <= 75 and np.dot(delta / radius, radial) > .94 and not wp.is_junction:
                    yaw = math.radians(wp.transform.rotation.yaw)
                    heading = np.array([math.cos(yaw), math.sin(yaw)])
                    candidates.append((abs(radius - 62), float(heading @ radial), wp))
            inbound = sorted(((r, wp) for r, h, wp in candidates if h < -.8), key=lambda item: item[0])
            outbound = sorted(((r, wp) for r, h, wp in candidates if h > .8), key=lambda item: item[0])
            if not inbound or not outbound:
                raise RuntimeError(f"Could not locate road arm {arm}")
            def lanes(items):
                chosen = {}
                for _, wp in items:
                    chosen.setdefault((wp.road_id, wp.section_id, wp.lane_id), wp)
                return list(chosen.values())
            starts.append(lanes(inbound))
            goals.append(lanes(outbound))
        routes = []
        self.skipped_routes = []
        for entry in range(4):
            candidates = []
            for dest in range(4):
                if entry == dest:
                    continue
                options = []
                for start in starts[entry]:
                    candidate = self.direct_route(start, dest)
                    if candidate:
                        points = np.array([xyz(wp) for wp, _ in candidate])
                        length = np.linalg.norm(np.diff(points, axis=0), axis=1).sum()
                        options.append((length, start, candidate))
                if not options:
                    self.skipped_routes.append({"entry": entry, "destination_arm": dest,
                                                "reason": "No reachable outgoing lane inside the bounded junction"})
                    continue
                _, start, plan = min(options, key=lambda item: item[0])
                positions = np.array([xyz(wp) for wp, _ in plan])
                distances = np.r_[0, np.linalg.norm(np.diff(positions, axis=0), axis=1).cumsum()]
                radius = np.linalg.norm(positions[:, :2] - CENTRE, axis=1)
                inside = np.flatnonzero(radius < 34)
                if len(inside) < 8:
                    raise RuntimeError("Planned route misses the roundabout")
                exit_s = float(distances[inside[-1]])
                candidates.append({"entry": entry, "destination_arm": dest, "plan": plan,
                                   "positions": positions, "distance": distances,
                                   "goal": positions[-1, :2], "exit_s": exit_s,
                                   "start_s": max(0., exit_s - 30.), "end_s": exit_s + 10.,
                                   "length": float(distances[-1]), "start": start})
            # Geometric exit order, including when a route is unavailable.
            for route in sorted(candidates, key=lambda x: x["length"]):
                exit_number = (entry - route["destination_arm"]) % 4
                route.update(exit_number=exit_number, id=f"entry{entry}-exit{exit_number}")
                routes.append(route)
        if len(routes) < 6:
            raise RuntimeError(f"Insufficient direct routes: {self.skipped_routes}")
        return routes

    def direct_route(self, start, destination_arm):
        """Follow the actual lane topology inside this junction, without city detours.

        The general route planner chose long detours for some destinations.
        Searching reachable waypoints selects an outgoing lane directly.
        No vehicle position is teleported along this path.
        """
        radial = np.array([math.cos(destination_arm * math.pi / 2), math.sin(destination_arm * math.pi / 2)])
        counter = itertools.count()
        queue = [(0., next(counter), start, [])]
        visited = set()
        while queue:
            distance, _, waypoint, path = heapq.heappop(queue)
            key = (waypoint.road_id, waypoint.section_id, waypoint.lane_id, round(waypoint.s / 1.5))
            if key in visited:
                continue
            visited.add(key)
            p = xyz(waypoint)[:2] - CENTRE
            radius = np.linalg.norm(p)
            if radius > 82 or distance > 240:
                continue
            yaw = math.radians(waypoint.transform.rotation.yaw)
            heading = np.array([math.cos(yaw), math.sin(yaw)])
            path = path + [(waypoint, RoadOption.LANEFOLLOW)]
            if distance > 25 and 58 < radius < 78 and p @ radial / radius > .90 and heading @ radial > .70:
                return path
            for following in waypoint.next(1.5):
                increment = np.linalg.norm(xyz(following) - xyz(waypoint))
                heapq.heappush(queue, (distance + increment, next(counter), following, path))
        return None

    def cleanup_episode(self):
        for actor in reversed(self.actors):
            if actor.is_alive:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                else:
                    actor.set_autopilot(False, self.port)
                actor.destroy()
        self.actors, self.traffic, self.ego = [], [], None
        self.world.tick()

    def start(self, route, seed, speed_kmh=24., traffic_count=12):
        self.cleanup_episode()
        self.tm.set_random_device_seed(seed)
        self.tm.set_global_distance_to_leading_vehicle(3.)
        rng = np.random.default_rng(seed)
        library = self.world.get_blueprint_library()
        bp = library.find("vehicle.mini.cooper_s_2021")
        bp.set_attribute("role_name", "hero")
        bp.set_attribute("color", "48,84,43")
        pose = route["start"].transform
        pose.location.z += .3
        self.ego = self.world.spawn_actor(bp, pose)
        self.actors.append(self.ego)
        self.ego.set_autopilot(False, self.port)
        self.agent = BasicAgent(self.ego, target_speed=speed_kmh, map_inst=self.map, grp_inst=self.planner,
                                opt_dict={"dt": DT, "use_bbs_detection": True, "ignore_traffic_lights": True})
        self.agent.set_global_plan(route["plan"], stop_waypoint_creation=True, clean_queue=True)
        # Include circulating cars as well as approach traffic, not distant scenery.
        nearby = [wp for wp in self.waypoints
                  if 23 < np.linalg.norm(xyz(wp)[:2] - CENTRE) < 80]
        rng.shuffle(nearby)
        occupied = [np.array([pose.location.x, pose.location.y])]
        choices = [library.find(n) for n in ["vehicle.audi.a2", "vehicle.tesla.model3", "vehicle.lincoln.mkz_2020"]]
        for wp in nearby:
            if len(self.traffic) >= traffic_count:
                break
            p = xyz(wp)
            if any(np.linalg.norm(p[:2] - other) < 10 for other in occupied):
                continue
            pose = wp.transform
            pose.location.z += .3
            other = self.world.try_spawn_actor(choices[len(self.traffic) % len(choices)], pose)
            if other is None:
                continue
            self.traffic.append(other)
            self.actors.append(other)
            occupied.append(p[:2])
            other.set_autopilot(True, self.port)
            self.tm.auto_lane_change(other, False)
            self.tm.update_vehicle_lights(other, True)
            self.tm.set_desired_speed(other, float(rng.uniform(17, 30)))
        self.route = route
        self.progress = 0.
        self.nearest_index = 0
        self.start_timestamp = self.world.get_snapshot().timestamp.elapsed_seconds
        for _ in range(10):
            self.tick_route()
        return len(self.traffic)

    def tick_route(self):
        self.ego.apply_control(self.agent.run_step())
        return self.world.tick()

    def observe(self):
        pose = self.ego.get_transform()
        velocity = self.ego.get_velocity()
        p = np.array([pose.location.x, pose.location.y])
        speed = np.linalg.norm([velocity.x, velocity.y])
        neighbours = []
        for actor in self.traffic:
            if not actor.is_alive:
                continue
            op, ov = actor.get_location(), actor.get_velocity()
            delta = np.array([op.x, op.y]) - p
            neighbours.append((float(np.linalg.norm(delta)), delta, [ov.x - velocity.x, ov.y - velocity.y]))
        neighbours.sort(key=lambda n: n[0])
        closest = neighbours[0] if neighbours else (100., [0., 0.], [0., 0.])
        nearby_count = sum(distance < 50 for distance, _, _ in neighbours)
        context = np.array([*p, math.radians(pose.rotation.yaw), velocity.x, velocity.y, speed,
                            *self.route["goal"], *closest[1], *closest[2], nearby_count], dtype=np.float32)
        assert len(context) == len(CONTEXT_FIELDS)
        # Progress is teacher/evaluator-only. It is never supplied to the policy.
        start = max(0, self.nearest_index - 2)
        end = min(len(self.route["positions"]), self.nearest_index + 24)
        distances = np.linalg.norm(self.route["positions"][start:end, :2] - p, axis=1)
        self.nearest_index = start + int(np.argmin(distances))
        if distances.min() < 5:
            self.progress = max(self.progress, float(self.route["distance"][self.nearest_index]))
        annotation = {"progress": self.progress, "teacher_right": self.route["start_s"] <= self.progress <= self.route["end_s"],
                      "nearby_count": nearby_count, "nearest_traffic_m": closest[0],
                      "route_error_m": float(distances.min()),
                      "frame": self.world.get_snapshot().frame,
                      "timestamp": self.world.get_snapshot().timestamp.elapsed_seconds}
        return context, annotation

    def close(self):
        self.cleanup_episode()
        self.tm.set_synchronous_mode(False)
        self.world.apply_settings(self.original)
        self.world.set_weather(self.original_weather)


def route_metadata(route):
    return {k: v for k, v in route.items() if k not in {"plan", "positions", "distance", "goal", "start"}}
