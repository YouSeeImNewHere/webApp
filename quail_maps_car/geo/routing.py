from __future__ import annotations

import heapq
import math
import sqlite3
from dataclasses import dataclass

from .data_source import EXTRACT_PATH
from .roadnet import GRAPH, Edge, Graph, Node

# Ported from maps_pipeline/routing.py (the same engine Android's server
# calls actually use) instead of staying a separately-invented Dijkstra —
# same algorithm and process, the only real difference being that this one
# queries the already-downloaded local extract.sqlite3 file instead of a
# live master database over HTTP. The key behavior worth porting: adaptive
# bounding-box widening per routing request. A destination a few tenths of
# a mile away as the crow flies can genuinely need a much longer drivable
# path around water or terrain — this server region includes the Kitsap
# Peninsula, where that's routine, not an edge case — so a route request
# that only ever looks at a fixed small box around the start point (what
# this file used to do, and what roadnet.py's GRAPH still does for
# rendering/POI-listing purposes) can fail to find a route that's actually
# right there, just not reachable without briefly leaving that box.

Strategy = str  # "fastest" | "shortest" | "avoid_highways"

STRATEGIES: list[tuple[str, Strategy]] = [
    ("Fastest", "fastest"),
    ("Shortest", "shortest"),
    ("Avoid highways", "avoid_highways"),
]

# Fixed increasing steps, not a straight-line-distance multiplier (what
# this used to be, mirroring the server) — for a short trip (most real
# destinations here are well under a mile), a multiplier of even 3x a tiny
# straight-line distance still lands under a several-km floor, so every
# "widened" attempt ended up using the exact same box. Verified: a synthetic
# 500m-straight-line trip needing a 6km detour around an obstacle failed to
# route at all under the multiplier version, and succeeds under this one.
_BBOX_PAD_STEPS_M = (3000.0, 8000.0, 20_000.0)


def _edge_weight(edge: Edge, length_m: float, strategy: Strategy) -> float:
    if strategy == "shortest":
        return length_m
    time_h = (length_m / 1000.0) / edge.speed_kph
    if strategy == "avoid_highways" and edge.road_class == "highway":
        return time_h * 25.0
    return time_h


@dataclass
class PathResult:
    node_path: list[str]
    edge_path: list[Edge]
    distance_m: float
    time_h: float
    graph: Graph  # the (possibly leg-scoped) graph the path was found in


def _dijkstra(graph: Graph, start: str, goal: str, strategy: Strategy) -> PathResult | None:
    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, Edge]] = {}
    visited: set[str] = set()
    heap: list[tuple[float, str]] = [(0.0, start)]

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == goal:
            break
        for edge in graph.neighbors(node):
            length_m = graph.edge_length(edge)
            weight = _edge_weight(edge, length_m, strategy)
            nd = d + weight
            if edge.b not in dist or nd < dist[edge.b]:
                dist[edge.b] = nd
                prev[edge.b] = (node, edge)
                heapq.heappush(heap, (nd, edge.b))

    if goal not in dist:
        return None

    node_path = [goal]
    edge_path: list[Edge] = []
    cur = goal
    while cur != start:
        parent, edge = prev[cur]
        edge_path.append(edge)
        node_path.append(parent)
        cur = parent
    node_path.reverse()
    edge_path.reverse()

    distance_m = sum(graph.edge_length(e) for e in edge_path)
    time_h = sum((graph.edge_length(e) / 1000.0) / e.speed_kph for e in edge_path)
    return PathResult(node_path=node_path, edge_path=edge_path, distance_m=distance_m, time_h=time_h, graph=graph)


def _resolve_node_coords(node_id: str) -> tuple[float, float] | None:
    node = GRAPH.nodes.get(node_id)
    if node is not None:
        return node.east, node.north
    if not EXTRACT_PATH.exists():
        return None
    # Not in the (3mi-bounded, render/listing-focused) global GRAPH — the
    # full downloaded extract on disk covers a much wider radius, so look
    # the single node up there directly instead of giving up.
    conn = sqlite3.connect(EXTRACT_PATH)
    try:
        row = conn.execute("SELECT east, north FROM nodes WHERE id = ?", (node_id,)).fetchone()
    finally:
        conn.close()
    return (row[0], row[1]) if row else None


def _load_leg_graph(start_id: str, goal_id: str) -> Graph | None:
    """Loads a graph big enough to connect start and goal, widening the
    search area if the first (tight) attempt can't. Runs once per routing
    request — every strategy's Dijkstra below reuses this same graph, since
    strategy only changes edge weights, not which edges exist."""
    if not EXTRACT_PATH.exists():
        # Synthetic/offline fallback — GRAPH already holds the whole
        # (small) network, no widening needed or possible.
        return GRAPH

    start_coords = _resolve_node_coords(start_id)
    goal_coords = _resolve_node_coords(goal_id)
    if start_coords is None or goal_coords is None:
        return None

    conn = sqlite3.connect(EXTRACT_PATH)
    try:
        for pad in _BBOX_PAD_STEPS_M:
            min_e = min(start_coords[0], goal_coords[0]) - pad
            max_e = max(start_coords[0], goal_coords[0]) + pad
            min_n = min(start_coords[1], goal_coords[1]) - pad
            max_n = max(start_coords[1], goal_coords[1]) + pad

            node_rows = conn.execute(
                "SELECT id, east, north, label FROM nodes WHERE east BETWEEN ? AND ? AND north BETWEEN ? AND ?",
                (min_e, max_e, min_n, max_n),
            ).fetchall()
            if not node_rows:
                continue
            nodes = {
                str(nid): Node(str(nid), east, north, label or "") for nid, east, north, label in node_rows
            }
            if start_id not in nodes:
                nodes[start_id] = Node(start_id, *start_coords)
            if goal_id not in nodes:
                nodes[goal_id] = Node(goal_id, *goal_coords)

            # Same UNION-of-two-indexed-lookups shape as roadnet.py's
            # bounded load (see that file for why: an OR-across-JOINs
            # version defeats SQLite's ability to use its indices at all).
            edge_rows = conn.execute(
                """
                SELECT a, b, street, road_class, speed_kph FROM edges
                WHERE a IN (SELECT id FROM nodes WHERE east BETWEEN ? AND ? AND north BETWEEN ? AND ?)
                UNION
                SELECT a, b, street, road_class, speed_kph FROM edges
                WHERE b IN (SELECT id FROM nodes WHERE east BETWEEN ? AND ? AND north BETWEEN ? AND ?)
                """,
                (min_e, max_e, min_n, max_n, min_e, max_e, min_n, max_n),
            ).fetchall()

            adjacency: dict[str, list[Edge]] = {node_id: [] for node_id in nodes}
            edges: list[Edge] = []
            for a, b, street, road_class, speed_kph in edge_rows:
                a, b = str(a), str(b)
                if a not in nodes or b not in nodes:
                    continue
                edge = Edge(a, b, street or "", road_class or "local", float(speed_kph or 40.0))
                edges.append(edge)
                adjacency[a].append(edge)
                adjacency[b].append(Edge(b, a, edge.street, edge.road_class, edge.speed_kph))

            leg_graph = Graph(nodes=nodes, edges=edges, adjacency=adjacency)
            # "fastest" doubles as the connectivity check — if even the
            # cheapest-to-traverse weighting can't connect start and goal
            # in this subgraph, no other strategy will either, so it's not
            # worth trying them before widening further.
            if _dijkstra(leg_graph, start_id, goal_id, "fastest") is not None:
                return leg_graph
    finally:
        conn.close()

    return None


@dataclass
class TurnStep:
    instruction: str
    distance_m: float
    maneuver: str


_COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def _bearing(a: Node, b: Node) -> float:
    return math.degrees(math.atan2(b.east - a.east, b.north - a.north)) % 360


def _compass(bearing: float) -> str:
    return _COMPASS[round(bearing / 45) % 8]


def _turn_glyph(delta: float) -> str:
    if delta > 150 or delta < -150:
        return "⤴"
    if delta > 45:
        return "↱"
    if delta > 15:
        return "⇗"
    if delta < -45:
        return "↰"
    if delta < -15:
        return "⇖"
    return "↑"


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


def build_turn_by_turn(path: PathResult) -> list[TurnStep]:
    graph = path.graph
    edges = path.edge_path
    if not edges:
        return [TurnStep("You have arrived", 0.0, "▪")]

    legs: list[list[Edge]] = []
    for edge in edges:
        if legs and legs[-1][-1].street == edge.street:
            legs[-1].append(edge)
        else:
            legs.append([edge])

    steps: list[TurnStep] = []
    prev_bearing: float | None = None
    for i, leg in enumerate(legs):
        leg_distance = sum(graph.edge_length(e) for e in leg)
        start_node = graph.nodes[leg[0].a]
        end_node = graph.nodes[leg[-1].b]
        bearing = _bearing(start_node, end_node)

        if i == 0:
            instruction = f"Head {_compass(bearing)} on {leg[0].street}"
            maneuver = "↑"
        else:
            delta = ((bearing - prev_bearing) + 180) % 360 - 180
            instruction = f"{_turn_word(delta)} {leg[0].street}"
            maneuver = _turn_glyph(delta)
        steps.append(TurnStep(instruction, leg_distance, maneuver))
        prev_bearing = bearing

    steps.append(TurnStep("Arrive at destination", 0.0, "▪"))
    return steps


@dataclass
class RouteOption:
    label: str
    path: PathResult
    steps: list[TurnStep]

    @property
    def distance_mi(self) -> float:
        return self.path.distance_m / 1609.34

    @property
    def minutes(self) -> int:
        return max(1, round(self.path.time_h * 60))

    @property
    def via(self) -> str:
        streets = []
        for edge in self.path.edge_path:
            if not streets or streets[-1] != edge.street:
                streets.append(edge.street)
        return streets[1] if len(streets) > 1 else (streets[0] if streets else "")


def path_points(path: PathResult) -> list[tuple[float, float]]:
    return [(path.graph.nodes[n].east, path.graph.nodes[n].north) for n in path.node_path]


def point_at_fraction(points: list[tuple[float, float]], fraction: float) -> tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    if len(points) == 1:
        return points[0]
    seg_lengths = [
        math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    ]
    total = sum(seg_lengths)
    target = max(0.0, min(1.0, fraction)) * total
    acc = 0.0
    for i, seg_len in enumerate(seg_lengths):
        if acc + seg_len >= target or i == len(seg_lengths) - 1:
            t = 0.0 if seg_len == 0 else (target - acc) / seg_len
            x = points[i][0] + (points[i + 1][0] - points[i][0]) * t
            y = points[i][1] + (points[i + 1][1] - points[i][1]) * t
            return (x, y)
        acc += seg_len
    return points[-1]


def shortest_path(start: str, goal: str, strategy: Strategy) -> PathResult | None:
    graph = _load_leg_graph(start, goal)
    if graph is None:
        return None
    return _dijkstra(graph, start, goal, strategy)


def compute_routes(start: str, goal: str) -> list[RouteOption]:
    graph = _load_leg_graph(start, goal)
    if graph is None:
        return []

    results: list[RouteOption] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for label, strategy in STRATEGIES:
        path = _dijkstra(graph, start, goal, strategy)
        if path is None:
            continue
        signature = tuple(e.street for e in path.edge_path)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        results.append(RouteOption(label=label, path=path, steps=build_turn_by_turn(path)))
    return results
