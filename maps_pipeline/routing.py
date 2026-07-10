from __future__ import annotations

import heapq
import math
import sqlite3
from pathlib import Path

# Real Dijkstra over a bbox-bounded slice of the master db(s), plus
# turn-by-turn instructions generated from bearing changes between
# consecutive same-street legs — the same approach
# quail_maps_car/geo/routing.py already uses over its synthetic local graph,
# ported here for real lat/lon data server-side. Doesn't model oneway
# restrictions (roads are treated as bidirectional), matching the client's
# existing simplification.

_COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


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


def _load_graph(
    master_db_paths: list[Path], bbox: tuple[float, float, float, float]
) -> tuple[dict[int, tuple[float, float]], dict[int, list[tuple[int, float, float, str]]]]:
    lat_min, lat_max, lon_min, lon_max = bbox
    nodes: dict[int, tuple[float, float]] = {}
    # node -> [(neighbor_id, distance_m, speed_kph, street)]
    adjacency: dict[int, list[tuple[int, float, float, str]]] = {}

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
                SELECT wn.way_id, wn.seq, wn.node_id, n.lat, n.lon, w.street, w.speed_kph
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
                adjacency.setdefault(na, []).append((nb, dist_m, speed, street))
                adjacency.setdefault(nb, []).append((na, dist_m, speed, street))

    return nodes, adjacency


def _nearest_node(nodes: dict[int, tuple[float, float]], lat: float, lon: float) -> int | None:
    best_id, best_dist = None, float("inf")
    for node_id, (nlat, nlon) in nodes.items():
        d = _haversine_m(lat, lon, nlat, nlon)
        if d < best_dist:
            best_dist, best_id = d, node_id
    return best_id


def _dijkstra(
    adjacency: dict[int, list[tuple[int, float, float, str]]], start_id: int, goal_id: int
) -> tuple[list[int], list[tuple[str, float]], float] | None:
    dist: dict[int, float] = {start_id: 0.0}
    prev: dict[int, tuple[int, str, float]] = {}
    visited: set[int] = set()
    heap: list[tuple[float, int]] = [(0.0, start_id)]

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == goal_id:
            break
        for neighbor, dist_m, speed_kph, street in adjacency.get(node, []):
            weight_h = (dist_m / 1000.0) / max(speed_kph, 1.0)
            nd = d + weight_h
            if neighbor not in dist or nd < dist[neighbor]:
                dist[neighbor] = nd
                prev[neighbor] = (node, street, dist_m)
                heapq.heappush(heap, (nd, neighbor))

    if goal_id not in dist:
        return None

    path_nodes = [goal_id]
    path_edges: list[tuple[str, float]] = []
    cur = goal_id
    while cur != start_id:
        parent, street, dist_m = prev[cur]
        path_edges.append((street, dist_m))
        path_nodes.append(parent)
        cur = parent
    path_nodes.reverse()
    path_edges.reverse()

    return path_nodes, path_edges, dist[goal_id]


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


def _build_turns(path_nodes: list[int], path_edges: list[tuple[str, float]], nodes: dict[int, tuple[float, float]]) -> list[dict]:
    if not path_edges:
        return [{"instruction": "You have arrived", "street": "", "distance_m": 0.0, "point_index": 0}]

    # Merge consecutive edges that share a street name into one leg.
    legs: list[list] = []  # [street, total_dist_m, start_node_idx, end_node_idx]
    for i, (street, dist_m) in enumerate(path_edges):
        if legs and legs[-1][0] == street:
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
        # point_index: where in the returned `points` list this leg starts —
        # lets the client find "which step am I on" from a live GPS fix by
        # matching it to the nearest point, without recomputing anything
        # route-shaped on-device.
        steps.append({"instruction": instruction, "street": street, "distance_m": round(leg_dist, 1), "point_index": start_i})
        prev_bearing = bearing

    steps.append({"instruction": "Arrive at destination", "street": "", "distance_m": 0.0, "point_index": len(path_nodes) - 1})
    return steps


def compute_route(master_db_paths: list[Path], from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    straight_km = _haversine_m(from_lat, from_lon, to_lat, to_lon) / 1000.0
    bbox = _bbox_around(from_lat, from_lon, to_lat, to_lon, pad_km=max(1.0, straight_km * 0.15))
    nodes, adjacency = _load_graph(master_db_paths, bbox)
    if not nodes:
        raise RouteNotFoundError("No road data near these points")

    start_id = _nearest_node(nodes, from_lat, from_lon)
    goal_id = _nearest_node(nodes, to_lat, to_lon)
    if start_id is None or goal_id is None:
        raise RouteNotFoundError("No road data near these points")

    result = _dijkstra(adjacency, start_id, goal_id)
    if result is None:
        raise RouteNotFoundError("No route found between these points")
    path_nodes, path_edges, total_time_h = result

    points = [{"lat": nodes[n][0], "lon": nodes[n][1]} for n in path_nodes]
    steps = _build_turns(path_nodes, path_edges, nodes)
    total_dist_m = sum(d for _, d in path_edges)

    return {
        "points": points,
        "steps": steps,
        "distance_m": round(total_dist_m, 1),
        "duration_sec": round(total_time_h * 3600, 1),
    }
