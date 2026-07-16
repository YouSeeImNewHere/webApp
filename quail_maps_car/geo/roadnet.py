from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field

from .data_source import EXTRACT_PATH

# Coordinates are meters in a local flat (east, north) frame with an
# arbitrary origin — the same representation a real OSM extract is already
# projected into (see maps_pipeline/schema.py EXTRACT_SCHEMA). If
# geo/data_source.py has downloaded a real extract, it's loaded below
# instead of the small synthetic network that otherwise ships as a
# fallback so the app still runs standalone before that first pull.


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


def distance_m(a: Node, b: Node) -> float:
    return math.hypot(a.east - b.east, a.north - b.north)


def _synthetic_nodes_edges() -> tuple[dict[str, Node], list[Edge]]:
    nodes = {
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
    raw_edges: list[tuple[str, str, str, str, float]] = [
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
    edges = [Edge(a, b, street, cls, speed) for a, b, street, cls, speed in raw_edges]
    return nodes, edges


# A real extract can be requested at up to a 40km RADIUS (see
# data_source.py) — that's the right size for a one-time download so the
# car doesn't need repeat trips home for every new road. But loading it all
# into memory as Python dataclasses at every app *startup* is a different
# cost entirely, and a real extract around a populated area (confirmed:
# 331MB for one real download) is dense enough that even a 10-mile bound
# left too much to hold in memory and route across on the mini PC's weak
# CPU with no hardware acceleration — unlike the Pixel 7a, which has a real
# GPU and hardware-composited rendering for comparison. 3 miles covers
# nearly all local daily driving; widen this if you're routing somewhere
# past its edge and see "no route found."
_LOAD_RADIUS_M = 4828.03  # 3 miles


def _ensure_spatial_indices(conn: sqlite3.Connection) -> None:
    # EXTRACT_SCHEMA (maps_pipeline/schema.py) ships with no index on
    # nodes(east, north) or edges(a)/edges(b) — only primary keys. Against
    # a 331MB real file, the bounding-box queries below were still doing a
    # full table scan every load without these. One-time cost (persists to
    # the file — IF NOT EXISTS makes every later call a cheap no-op), then
    # every future load is fast.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_east_north ON nodes(east, north)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_a ON edges(a)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_b ON edges(b)")
    conn.commit()


def _load_real_nodes_edges(path) -> tuple[dict[str, Node], list[Edge]]:
    conn = sqlite3.connect(path)
    try:
        _ensure_spatial_indices(conn)
        r = _LOAD_RADIUS_M
        # The extract's local coordinate frame is centered on (0, 0) — the
        # lat/lon the download was requested for (see the START-snapping
        # logic below) — so a box around the origin is the bounded region.
        node_rows = conn.execute(
            "SELECT id, east, north, label FROM nodes WHERE east BETWEEN ? AND ? AND north BETWEEN ? AND ?",
            (-r, r, -r, r),
        ).fetchall()
        # UNION of two indexed IN (SELECT ...) lookups — an OR across two
        # JOINs (what this used to be) defeats SQLite's ability to use the
        # indices at all: it falls back to a full scan of every edge, and
        # an added DISTINCT forces a full temp-B-tree sort on top of that.
        # Confirmed via EXPLAIN QUERY PLAN: the OR/JOIN/DISTINCT version
        # took 1.06s against 400K edges (a real full SCAN); this version
        # takes 0.03s (real indexed SEARCHes) — a ~33x difference on
        # exactly the kind of large real extract that prompted this fix.
        # An edge is kept if either endpoint falls inside the loaded
        # region; edges entirely outside get dropped, which is intended.
        edge_rows = conn.execute(
            """
            SELECT e.a, e.b, e.street, e.road_class, e.speed_kph
            FROM edges e
            WHERE e.a IN (SELECT id FROM nodes WHERE east BETWEEN ? AND ? AND north BETWEEN ? AND ?)
            UNION
            SELECT e.a, e.b, e.street, e.road_class, e.speed_kph
            FROM edges e
            WHERE e.b IN (SELECT id FROM nodes WHERE east BETWEEN ? AND ? AND north BETWEEN ? AND ?)
            """,
            (-r, r, -r, r, -r, r, -r, r),
        ).fetchall()
    finally:
        conn.close()

    nodes: dict[str, Node] = {
        str(nid): Node(str(nid), east, north, label or "") for nid, east, north, label in node_rows
    }
    edges = [
        Edge(str(a), str(b), street or "", road_class or "local", float(speed_kph or 40.0))
        for a, b, street, road_class, speed_kph in edge_rows
    ]

    # A real extract has no notion of "current location" — it's OSM data
    # centered on wherever the download was requested from, with no origin
    # node at all. Snap a synthetic START onto whichever real node is
    # closest to the extract's center so routing/search (both of which
    # assume a "START" node exists) keep working unchanged.
    if nodes:
        nearest_id = min(nodes, key=lambda nid: math.hypot(nodes[nid].east, nodes[nid].north))
        nodes["START"] = Node("START", 0.0, 0.0, "Current Location")
        edges.append(Edge("START", nearest_id, "", "local", 30))

    return nodes, edges


def _load_nodes_edges() -> tuple[dict[str, Node], list[Edge]]:
    if EXTRACT_PATH.exists():
        try:
            nodes, edges = _load_real_nodes_edges(EXTRACT_PATH)
            if nodes and edges:
                return nodes, edges
        except sqlite3.Error:
            pass  # corrupt/partial download — fall through to synthetic
    return _synthetic_nodes_edges()


NODES, EDGES = _load_nodes_edges()


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
        # A real extract is cut off at a radius boundary — an edge just
        # inside that boundary can reference a node just outside it that
        # never made it into the returned node set. Skip those rather than
        # KeyError on a graph that's otherwise perfectly valid.
        if edge.a not in adjacency or edge.b not in adjacency:
            continue
        adjacency[edge.a].append(edge)
        adjacency[edge.b].append(Edge(edge.b, edge.a, edge.street, edge.road_class, edge.speed_kph))
    return Graph(nodes=NODES, edges=EDGES, adjacency=adjacency)


GRAPH = build_graph()
