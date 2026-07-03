from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from .roadnet import GRAPH, Edge, Node

Strategy = str  # "fastest" | "shortest" | "avoid_highways"

STRATEGIES: list[tuple[str, Strategy]] = [
    ("Fastest", "fastest"),
    ("Shortest", "shortest"),
    ("Avoid highways", "avoid_highways"),
]


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


def shortest_path(start: str, goal: str, strategy: Strategy) -> PathResult | None:
    graph = GRAPH
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
    return PathResult(node_path=node_path, edge_path=edge_path, distance_m=distance_m, time_h=time_h)


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
    graph = GRAPH
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
    return [(GRAPH.nodes[n].east, GRAPH.nodes[n].north) for n in path.node_path]


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


def compute_routes(start: str, goal: str) -> list[RouteOption]:
    results: list[RouteOption] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for label, strategy in STRATEGIES:
        path = shortest_path(start, goal, strategy)
        if path is None:
            continue
        signature = tuple(e.street for e in path.edge_path)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        results.append(RouteOption(label=label, path=path, steps=build_turn_by_turn(path)))
    return results
