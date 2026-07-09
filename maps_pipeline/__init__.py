"""OSM ingestion pipeline for Quail Maps.

Turns raw Geofabrik .osm.pbf extracts into:
  - a master SQLite database per region (raw WGS84 coordinates, full
    road graph + POIs), built by `osm_import.py`
  - small on-demand city extracts in the exact schema
    `quail_maps_car/geo/{roadnet,search_db}.py` already consume (local flat
    east/north meters, `places` + FTS5), built by `extract.py`

Homelab-only: not imported by the main FastAPI app at module load time, since
it depends on `osmium` (not installed on the Render deploy).
"""
