from __future__ import annotations

import heapq
import math
import sqlite3
from pathlib import Path

# Real Dijkstra over a bbox-bounded slice of the master db(s), plus
# turn-by-turn instructions generated from bearing changes between
# consecutive same-street legs — the same approach
# quail_maps_car/geo/routing.py already uses over its synthetic local graph,
# ported here for real lat/lon data server-side, and extended to: multiple
# strategy-based route alternatives (fastest/shortest/avoid-highways, same
# three quail_maps_car already defines) and multi-stop routing (an ordered
# list of waypoints, each consecutive pair routed as its own leg and
# concatenated). Doesn't model oneway restrictions (roads are treated as
# bidirectional), matching the client's existing simplification.

_COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]

DRIVE_STRATEGIES: list[tuple[str, str]] = [
    ("Fastest", "fastest"),
    ("Shortest", "shortest"),
    ("Avoid highways", "avoid_highways"),
]
# Walking has no meaningful "avoid highways" strategy — highways are already
# strongly penalized for every walking strategy (see _CLASS_PENALTY), not
# just one of them, since pedestrians can't legally/physically use most of
# them regardless of preference.
WALK_STRATEGIES: list[tuple[str, str]] = [
    ("Fastest", "fastest"),
    ("Shortest", "shortest"),
]
# Backwards-compat alias — existing callers that don't pass a mode keep
# getting the driving strategy set.
STRATEGIES = DRIVE_STRATEGIES

WALK_SPEED_KPH = 4.8


class RouteNotFoundError(Exception):
    pass


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bbox_around(lat1: float, lon1: float, lat2: float, lon2: float, pad_km: float) -> tuple[float, float, float, float]:
    lat_min, lat_max = min(lat1, lat2), max(lat1, lat2)
    lon_min, lon_max = min(lon1, lon2), max(lon1, lon2)
    mid_lat = (lat1 + lat2) / 2
    meters_per_deg_lat = 110_540.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(mid_lat))
    dlat = (pad_km * 1000.0) / meters_per_deg_lat
    dlon = (pad_km * 1000.0) / meters_per_deg_lon
    return lat_min - dlat, lat_max + dlat, lon_min - dlon, lon_max + dlon


# adjacency value tuple: (neighbor_id, distance_m, speed_kph, street, road_class)
_Edge = tuple[int, float, float, str, str]


def _load_graph(
    master_db_paths: list[Path], bbox: tuple[float, float, float, float]
) -> tuple[dict[int, tuple[float, float]], dict[int, list[_Edge]]]:
    lat_min, lat_max, lon_min, lon_max = bbox
    nodes: dict[int, tuple[float, float]] = {}
    adjacency: dict[int, list[_Edge]] = {}

    for db_path in master_db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TEMP TABLE bbox_nodes (id INTEGER PRIMARY KEY)")
            conn.execute(
                "INSERT INTO temp.bbox_nodes SELECT id FROM nodes WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                (lat_min, lat_max, lon_min, lon_max),
            )
            way_rows = conn.execute(
                """
                SELECT wn.way_id, wn.seq, wn.node_id, n.lat, n.lon, w.street, w.speed_kph, w.road_class
                FROM way_nodes wn
                JOIN nodes n ON n.id = wn.node_id
                JOIN ways w ON w.id = wn.way_id
                WHERE wn.way_id IN (SELECT DISTINCT way_id FROM way_nodes WHERE node_id IN (SELECT id FROM temp.bbox_nodes))
                ORDER BY wn.way_id, wn.seq
                """
            ).fetchall()
        finally:
            conn.close()

        ways: dict[int, list[sqlite3.Row]] = {}
        for r in way_rows:
            ways.setdefault(r["way_id"], []).append(r)

        for rows in ways.values():
            rows.sort(key=lambda r: r["seq"])
            for a, b in zip(rows, rows[1:]):
                na, nb = a["node_id"], b["node_id"]
                nodes[na] = (a["lat"], a["lon"])
                nodes[nb] = (b["lat"], b["lon"])
                dist_m = _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                street = a["street"]
                speed = a["speed_kph"]
                road_class = a["road_class"]
                adjacency.setdefault(na, []).append((nb, dist_m, speed, street, road_class))
                adjacency.setdefault(nb, []).append((na, dist_m, speed, street, road_class))

    return nodes, adjacency


def _nearest_node(nodes: dict[int, tuple[float, float]], lat: float, lon: float) -> int | None:
    best_id, best_dist = None, float("inf")
    for node_id, (nlat, nlon) in nodes.items():
        d = _haversine_m(lat, lon, nlat, nlon)
        if d < best_dist:
            best_dist, best_id = d, node_id
    return best_id


def _class_penalty(mode: str, road_class: str) -> float:
    """Multiplicative cost penalty for road classes that are the wrong mode
    for the trip — not a hard exclusion (a pedestrian bridge alongside a
    motorway is technically "on" the same way in sparse OSM data
    occasionally), just heavily discouraged so Dijkstra only picks it when
    there's truly no other path."""
    if mode == "walk" and road_class == "highway":
        return 50.0
    if mode == "drive" and road_class == "foot":
        return 50.0
    return 1.0


def _edge_weight_h(dist_m: float, speed_kph: float, road_class: str, strategy: str, mode: str = "drive") -> float:
    penalty = _class_penalty(mode, road_class)
    effective_speed = WALK_SPEED_KPH if mode == "walk" else speed_kph
    if strategy == "shortest":
        # Not really "hours", just a monotonic cost in meters — fine since
        # Dijkstra only cares about relative ordering, and the caller always
        # recomputes real distance/time from the resulting path afterward.
        return dist_m * penalty
    time_h = (dist_m / 1000.0) / max(effective_speed, 1.0)
    if strategy == "avoid_highways" and road_class == "highway":
        time_h *= 25.0
    return time_h * penalty


# path edge tuple: (street, road_class, distance_m, speed_kph)
_PathEdge = tuple[str, str, float, float]


def _dijkstra(
    adjacency: dict[int, list[_Edge]], start_id: int, goal_id: int, strategy: str, mode: str = "drive"
) -> tuple[list[int], list[_PathEdge]] | None:
    dist: dict[int, float] = {start_id: 0.0}
    prev: dict[int, tuple[int, _PathEdge]] = {}
    visited: set[int] = set()
    heap: list[tuple[float, int]] = [(0.0, start_id)]

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == goal_id:
            break
        for neighbor, dist_m, speed_kph, street, road_class in adjacency.get(node, []):
            weight = _edge_weight_h(dist_m, speed_kph, road_class, strategy, mode)
            nd = d + weight
            if neighbor not in dist or nd < dist[neighbor]:
                dist[neighbor] = nd
                prev[neighbor] = (node, (street, road_class, dist_m, speed_kph))
                heapq.heappush(heap, (nd, neighbor))

    if goal_id not in dist:
        return None

    path_nodes = [goal_id]
    path_edges: list[_PathEdge] = []
    cur = goal_id
    while cur != start_id:
        parent, edge = prev[cur]
        path_edges.append(edge)
        path_nodes.append(parent)
        cur = parent
    path_nodes.reverse()
    path_edges.reverse()

    return path_nodes, path_edges


def _route_leg(
    master_db_paths: list[Path], from_lat: float, from_lon: float, to_lat: float, to_lon: float,
    strategy: str, mode: str = "drive",
) -> tuple[list[int], list[_PathEdge], dict[int, tuple[float, float]]]:
    straight_km = _haversine_m(from_lat, from_lon, to_lat, to_lon) / 1000.0
    bbox = _bbox_around(from_lat, from_lon, to_lat, to_lon, pad_km=max(1.0, straight_km * 0.15))
    nodes, adjacency = _load_graph(master_db_paths, bbox)
    if not nodes:
        raise RouteNotFoundError("No road data near these points")

    start_id = _nearest_node(nodes, from_lat, from_lon)
    goal_id = _nearest_node(nodes, to_lat, to_lon)
    if start_id is None or goal_id is None:
        raise RouteNotFoundError("No road data near these points")

    result = _dijkstra(adjacency, start_id, goal_id, strategy, mode)
    if result is None:
        raise RouteNotFoundError("No route found between these points")
    path_nodes, path_edges = result
    return path_nodes, path_edges, nodes


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return math.degrees(math.atan2(y, x)) % 360


def _compass(bearing: float) -> str:
    return _COMPASS[round(bearing / 45) % 8]


def _turn_word(delta: float) -> str:
    if delta > 45:
        return "Turn right onto"
    if delta > 15:
        return "Bear right onto"
    if delta < -45:
        return "Turn left onto"
    if delta < -15:
        return "Bear left onto"
    return "Continue onto"


def _build_turns(
    path_nodes: list[int],
    path_edges: list[_PathEdge],
    nodes: dict[int, tuple[float, float]],
    stop_markers: set[int],
) -> list[dict]:
    """[stop_markers] is the set of path_nodes indices where a waypoint
    (an intermediate stop, not the final destination) was reached — used to
    insert an "Arrive at stop" instruction mid-route for multi-stop trips."""
    if not path_edges:
        return [{"instruction": "You have arrived", "street": "", "distance_m": 0.0, "point_index": 0}]

    legs: list[list] = []  # [street, total_dist_m, start_i, end_i]
    for i, (street, _road_class, dist_m, _speed) in enumerate(path_edges):
        breaks_leg = (i in stop_markers) if legs else False
        if legs and legs[-1][0] == street and not breaks_leg:
            legs[-1][1] += dist_m
            legs[-1][3] = i + 1
        else:
            legs.append([street, dist_m, i, i + 1])

    steps = []
    prev_bearing: float | None = None
    for i, (street, leg_dist, start_i, end_i) in enumerate(legs):
        slat, slon = nodes[path_nodes[start_i]]
        elat, elon = nodes[path_nodes[end_i]]
        bearing = _bearing(slat, slon, elat, elon)
        if i == 0:
            instruction = f"Head {_compass(bearing)} on {street}"
        else:
            delta = ((bearing - prev_bearing) + 180) % 360 - 180
            instruction = f"{_turn_word(delta)} {street}"
        steps.append({"instruction": instruction, "street": street, "distance_m": round(leg_dist, 1), "point_index": start_i})
        prev_bearing = bearing
        if end_i in stop_markers:
            steps.append({"instruction": "Arrive at stop", "street": "", "distance_m": 0.0, "point_index": end_i})

    steps.append({"instruction": "Arrive at destination", "street": "", "distance_m": 0.0, "point_index": len(path_nodes) - 1})
    return steps


def _route_for_strategy(
    master_db_paths: list[Path], points: list[tuple[float, float]], strategy: str, mode: str = "drive",
) -> dict:
    all_path_nodes: list[int] = []
    all_path_edges: list[_PathEdge] = []
    all_nodes: dict[int, tuple[float, float]] = {}
    stop_markers: set[int] = set()

    for i in range(len(points) - 1):
        from_lat, from_lon = points[i]
        to_lat, to_lon = points[i + 1]
        leg_nodes, leg_edges, leg_node_coords = _route_leg(
            master_db_paths, from_lat, from_lon, to_lat, to_lon, strategy, mode,
        )
        all_nodes.update(leg_node_coords)

        if all_path_nodes and all_path_nodes[-1] == leg_nodes[0]:
            all_path_nodes.extend(leg_nodes[1:])
        else:
            all_path_nodes.extend(leg_nodes)
        all_path_edges.extend(leg_edges)

        if i < len(points) - 2:
            stop_markers.add(len(all_path_nodes) - 1)

    total_dist_m = sum(e[2] for e in all_path_edges)
    effective_speed = (lambda speed: WALK_SPEED_KPH if mode == "walk" else speed)
    total_time_h = sum((e[2] / 1000.0) / max(effective_speed(e[3]), 1.0) for e in all_path_edges)
    steps = _build_turns(all_path_nodes, all_path_edges, all_nodes, stop_markers)

    return {
        "points": [{"lat": all_nodes[n][0], "lon": all_nodes[n][1]} for n in all_path_nodes],
        "steps": steps,
        "distance_m": round(total_dist_m, 1),
        "duration_sec": round(total_time_h * 3600, 1),
    }


def compute_routes(
    master_db_paths: list[Path], points: list[tuple[float, float]], mode: str = "drive", max_options: int = 3,
) -> list[dict]:
    """[points] is an ordered list of (lat, lon) — 2 for a simple A-to-B
    trip, more for multi-stop. [mode] is "drive" or "walk" — walking uses a
    fixed ~4.8kph pace instead of each road's tagged driving speed, and
    strongly discourages (not hard-excludes) motorway/trunk-class ways,
    while driving does the same for footway/path/pedestrian/steps-class
    ways (present in the graph for the walking use case, but not something a
    car should be routed down). Returns up to [max_options] labeled route
    alternatives, deduped when two strategies land on the identical street
    sequence. No transit mode: this routing engine is Dijkstra over the OSM
    road/path graph, not backed by any real transit schedule data (GTFS) —
    there's nothing to route "transit" over yet."""
    if len(points) < 2:
        raise RouteNotFoundError("Need at least two points to route between")

    strategies = WALK_STRATEGIES if mode == "walk" else DRIVE_STRATEGIES
    options: list[dict] = []
    seen_signatures: set[tuple[str, ...]] = set()
    last_error: RouteNotFoundError | None = None

    for label, strategy in strategies:
        try:
            route = _route_for_strategy(master_db_paths, points, strategy, mode)
        except RouteNotFoundError as e:
            last_error = e
            continue
        signature = tuple(step["street"] for step in route["steps"])
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        options.append({"label": label, **route})
        if len(options) >= max_options:
            break

    if not options:
        raise last_error or RouteNotFoundError("No route found")
    return options
