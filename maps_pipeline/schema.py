from __future__ import annotations

import sqlite3

# Master regional database: raw WGS84 coordinates, every node referenced by
# a routable way (not just intersections — keeps the importer a single
# streaming pass with no second pass to find junctions), plus POIs.
MASTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ways (
    id INTEGER PRIMARY KEY,
    street TEXT NOT NULL,
    road_class TEXT NOT NULL,
    speed_kph REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS way_nodes (
    way_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    node_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_way_nodes_way ON way_nodes(way_id, seq);
CREATE INDEX IF NOT EXISTS idx_way_nodes_node ON way_nodes(node_id);
CREATE TABLE IF NOT EXISTS places (
    osm_id TEXT PRIMARY KEY,
    node_id INTEGER,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL,
    category TEXT NOT NULL,
    opening_hours TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_nodes_latlon ON nodes(lat, lon);
CREATE INDEX IF NOT EXISTS idx_places_latlon ON places(lat, lon);
CREATE TABLE IF NOT EXISTS cities (
    osm_id TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    name TEXT NOT NULL,
    place_type TEXT NOT NULL,
    population INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cities_latlon ON cities(lat, lon);
CREATE TABLE IF NOT EXISTS areas (
    osm_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ring_json TEXT NOT NULL,
    lat_min REAL NOT NULL,
    lat_max REAL NOT NULL,
    lon_min REAL NOT NULL,
    lon_max REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_areas_bbox ON areas(lat_min, lat_max, lon_min, lon_max);
CREATE TABLE IF NOT EXISTS region_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# On-demand city extract: local flat east/north meter frame, exact schema
# quail_maps_car/geo/{roadnet,search_db}.py already expect (places + FTS5),
# plus nodes/edges tables a future loader can read straight into
# roadnet.Node/Edge without changing routing.py or the renderer.
EXTRACT_SCHEMA = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    east REAL NOT NULL,
    north REAL NOT NULL,
    label TEXT NOT NULL DEFAULT ''
);
CREATE TABLE edges (
    a TEXT NOT NULL,
    b TEXT NOT NULL,
    street TEXT NOT NULL,
    road_class TEXT NOT NULL,
    speed_kph REAL NOT NULL
);
CREATE TABLE places (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    icon TEXT NOT NULL,
    category TEXT NOT NULL,
    opening_hours TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT ''
);
CREATE VIRTUAL TABLE places_fts USING fts5(
    name, address, category, content='places', content_rowid='rowid'
);
CREATE TRIGGER places_ai AFTER INSERT ON places BEGIN
    INSERT INTO places_fts(rowid, name, address, category)
    VALUES (new.rowid, new.name, new.address, new.category);
END;
"""


def open_master_db(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(MASTER_SCHEMA)
    return conn


def build_extract_db(path) -> sqlite3.Connection:
    """Creates a fresh extract file at `path` (overwriting any existing one)."""
    import os

    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(str(path))
    conn.executescript(EXTRACT_SCHEMA)
    return conn
