from __future__ import annotations

import math
import sqlite3
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

# Standard slippy-map (Web Mercator) tile scheme — the same z/x/y addressing
# every OSM-based map client speaks. This is a deliberate architecture
# change from maps_pipeline/extract.py's local-flat-meter city extracts:
# rendering the *entire* downloaded area as vectors on the phone (the
# earlier approach) doesn't scale — a real metro-area extract is enough
# edges to trip Android's ANR watchdog just parsing/drawing it once. Tiles
# mean the client only ever asks for and draws the handful of small images
# actually on screen, regardless of how big the underlying region is.
TILE_SIZE = 256

BG_COLOR = (10, 13, 19)
HIGHWAY_COLOR = (58, 67, 86)
LOCAL_COLOR = (36, 44, 58)
FOOT_COLOR = (26, 32, 48)
PLACE_FILL = (23, 28, 38)
PLACE_BORDER = (244, 246, 250)
ROAD_WIDTH = {"highway": 3, "local": 2, "foot": 1}
# Places only render at street-level zoom — no point paying the query cost
# for POI markers nobody can usefully tap on a city-wide view.
PLACE_MIN_ZOOM = 15


def _lonlat_to_tilef(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _tile_to_lonlat(x: float, y: float, zoom: int) -> tuple[float, float]:
    n = 2.0**zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return lon, math.degrees(lat_rad)


def tile_bbox(z: int, x: int, y: int, pad: float = 0.15) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) for this tile, padded so roads
    that cross into a neighboring tile don't visibly cut off mid-line."""
    lon_nw, lat_nw = _tile_to_lonlat(x, y, z)
    lon_se, lat_se = _tile_to_lonlat(x + 1, y + 1, z)
    dlat = (lat_nw - lat_se) * pad
    dlon = (lon_se - lon_nw) * pad
    return lat_se - dlat, lat_nw + dlat, lon_nw - dlon, lon_se + dlon


def _pixel(lon: float, lat: float, z: int, x: int, y: int) -> tuple[float, float]:
    tx, ty = _lonlat_to_tilef(lon, lat, z)
    return (tx - x) * TILE_SIZE, (ty - y) * TILE_SIZE


def render_tile(master_db_paths: list[Path], z: int, x: int, y: int) -> bytes:
    lat_min, lat_max, lon_min, lon_max = tile_bbox(z, x, y)

    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)

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
                SELECT wn.way_id, wn.seq, n.lat, n.lon, w.road_class
                FROM way_nodes wn
                JOIN nodes n ON n.id = wn.node_id
                JOIN ways w ON w.id = wn.way_id
                WHERE wn.way_id IN (SELECT DISTINCT way_id FROM way_nodes WHERE node_id IN (SELECT id FROM temp.bbox_nodes))
                ORDER BY wn.way_id, wn.seq
                """
            ).fetchall()

            ways: dict[int, list[tuple[int, float, float]]] = {}
            way_class: dict[int, str] = {}
            for r in way_rows:
                ways.setdefault(r["way_id"], []).append((r["seq"], r["lat"], r["lon"]))
                way_class[r["way_id"]] = r["road_class"]

            # Draw minor roads first so major roads render on top of them.
            for road_class in ("foot", "local", "highway"):
                color = {"highway": HIGHWAY_COLOR, "local": LOCAL_COLOR, "foot": FOOT_COLOR}[road_class]
                width = ROAD_WIDTH[road_class]
                for way_id, points in ways.items():
                    if way_class.get(way_id) != road_class:
                        continue
                    points.sort(key=lambda p: p[0])
                    pixels = [_pixel(lon, lat, z, x, y) for _, lat, lon in points]
                    if len(pixels) >= 2:
                        draw.line(pixels, fill=color, width=width, joint="curve")

            if z >= PLACE_MIN_ZOOM:
                place_rows = conn.execute(
                    "SELECT lat, lon FROM places WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                    (lat_min, lat_max, lon_min, lon_max),
                ).fetchall()
                for r in place_rows:
                    px, py = _pixel(r["lon"], r["lat"], z, x, y)
                    if -10 <= px <= TILE_SIZE + 10 and -10 <= py <= TILE_SIZE + 10:
                        draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=PLACE_FILL, outline=PLACE_BORDER)
        finally:
            conn.close()

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
