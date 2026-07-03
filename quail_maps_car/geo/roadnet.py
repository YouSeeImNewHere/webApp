from __future__ import annotations

import math
from dataclasses import dataclass, field

# Coordinates are meters in a local flat (east, north) frame with an
# arbitrary origin — the same representation a real OSM extract would be
# projected into before routing/rendering. This network is synthetic (no
# internet access to pull real OpenStreetMap data in this environment), but
# every node is a real point in the frame and every edge a real, weighted
# graph edge — nothing here is faked at the algorithm level.


@dataclass(frozen=True)
class Node:
    id: str
    east: float
    north: float
    label: str = ""


@dataclass(frozen=True)
class Edge:
    a: str
    b: str
    street: str
    road_class: str  # "local" or "highway"
    speed_kph: float


NODES: dict[str, Node] = {
    n.id: n
    for n in [
        Node("START", 0, 0, "Current Location"),
        Node("OAK", 0, 600),
        Node("UNIONSQ", 250, 1000, "Union Sq"),
        Node("DINER", -1300, 150, "Market St"),
        Node("HWY_JCT", 100, -800),
        Node("SHELL", 350, -950, "Route 9 & Main St"),
        Node("SERVICE_RD_MID", 1600, -2200),
        Node("HWY_MID", 2000, -2600),
        Node("COSTCO", 3200, -3400, "Retail Pkwy"),
        Node("HWY_SOUTH", 2800, -4400),
        Node("CHARGE", 3600, -5200, "Innovation Dr"),
        Node("RIVERRD_JCT", 900, 400),
        Node("PARKING", 2350, -300, "River Rd"),
        Node("WILLOW_JCT", -800, 1700),
        Node("HOME", -3800, 3200, "Willow Creek Ln"),
        Node("HWY101_JCT", 500, 3200),
        Node("WORK", 9500, 8800, "5th Ave"),
    ]
}

_RAW_EDGES: list[tuple[str, str, str, str, float]] = [
    ("START", "OAK", "Main St", "local", 40),
    ("OAK", "UNIONSQ", "Union Sq", "local", 25),
    ("START", "DINER", "Market St", "local", 30),
    ("START", "HWY_JCT", "Main St", "local", 40),
    ("HWY_JCT", "SHELL", "Main St", "local", 30),
    ("HWY_JCT", "HWY_MID", "Route 9", "highway", 100),
    ("HWY_JCT", "SERVICE_RD_MID", "Retail Pkwy", "local", 45),
    ("SERVICE_RD_MID", "HWY_MID", "Retail Pkwy", "local", 45),
    ("HWY_MID", "COSTCO", "Retail Pkwy", "local", 35),
    ("HWY_MID", "HWY_SOUTH", "Route 9", "highway", 100),
    ("SERVICE_RD_MID", "HWY_SOUTH", "Retail Pkwy", "local", 45),
    ("HWY_SOUTH", "CHARGE", "Innovation Dr", "local", 35),
    ("OAK", "RIVERRD_JCT", "Oak Ave", "local", 35),
    ("RIVERRD_JCT", "PARKING", "River Rd", "local", 30),
    ("OAK", "WILLOW_JCT", "Main St", "local", 40),
    ("WILLOW_JCT", "HOME", "Willow Creek Ln", "local", 25),
    ("OAK", "HWY101_JCT", "Oak Ave", "local", 35),
    ("HWY101_JCT", "WORK", "Hwy 101", "highway", 100),
]

EDGES: list[Edge] = [Edge(a, b, street, cls, speed) for a, b, street, cls, speed in _RAW_EDGES]


def distance_m(a: Node, b: Node) -> float:
    return math.hypot(a.east - b.east, a.north - b.north)


@dataclass
class Graph:
    nodes: dict[str, Node]
    edges: list[Edge]
    adjacency: dict[str, list[Edge]] = field(default_factory=dict)

    def neighbors(self, node_id: str) -> list[Edge]:
        return self.adjacency.get(node_id, [])

    def edge_length(self, edge: Edge) -> float:
        return distance_m(self.nodes[edge.a], self.nodes[edge.b])


def build_graph() -> Graph:
    adjacency: dict[str, list[Edge]] = {node_id: [] for node_id in NODES}
    for edge in EDGES:
        adjacency[edge.a].append(edge)
        adjacency[edge.b].append(Edge(edge.b, edge.a, edge.street, edge.road_class, edge.speed_kph))
    return Graph(nodes=NODES, edges=EDGES, adjacency=adjacency)


GRAPH = build_graph()
