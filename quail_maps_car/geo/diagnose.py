"""One-off diagnostic — run with: python3 -m quail_maps_car.geo.diagnose"""
from __future__ import annotations

import datetime
import os

from . import data_source, roadnet, search_db

print("extract path:", data_source.EXTRACT_PATH)
print("extract exists:", data_source.EXTRACT_PATH.exists())
if data_source.EXTRACT_PATH.exists():
    st = os.stat(data_source.EXTRACT_PATH)
    print("size MB:", round(st.st_size / 1024 / 1024, 1))
    print("last modified:", datetime.datetime.fromtimestamp(st.st_mtime))

print()
print("loaded node count (bounded to 3mi):", len(roadnet.GRAPH.nodes))
print("loaded edge count (bounded to 3mi):", len(roadnet.GRAPH.edges))

print()
places = search_db.fetch_places()
print(f"places found near you: {len(places)}")
for p in places[:20]:
    node = roadnet.GRAPH.nodes.get(p.node_id)
    neighbors = roadnet.GRAPH.neighbors(p.node_id) if node else []
    print(f"  {p.name}: dist={p.distance_mi:.2f}mi  node_loaded={node is not None}  edges_from_node={len(neighbors)}")
