"""Checks the RAW extract file directly, with no client-side bounding at
all, to isolate whether missing edges are a server-side (extract-building)
problem or a client-side (roadnet.py's 3-mile bound) problem.

Run with: python3 -m quail_maps_car.geo.diagnose2
"""
from __future__ import annotations

import sqlite3

from . import data_source

conn = sqlite3.connect(data_source.EXTRACT_PATH)

total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
total_places = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
print(f"RAW FILE (no bounding at all): {total_nodes} nodes, {total_edges} edges, {total_places} places")
print()

places = conn.execute(
    "SELECT id, node_id, name FROM places ORDER BY name LIMIT 10"
).fetchall()
for pid, node_id, name in places:
    edge_count = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE a = ? OR b = ?", (node_id, node_id)
    ).fetchone()[0]
    node_row = conn.execute("SELECT east, north FROM nodes WHERE id = ?", (node_id,)).fetchone()
    print(f"  {name}: node_id={node_id}  node_exists={node_row is not None}  "
          f"edges_in_RAW_FILE={edge_count}")

conn.close()
