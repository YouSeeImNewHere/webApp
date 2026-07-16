from __future__ import annotations

import math
import sqlite3

from .data_source import EXTRACT_PATH
from .roadnet import GRAPH, Node

# Same constants/formula maps_pipeline/extract.py used to build the local
# flat frame in the first place — this runs the same projection on the
# client side, using the extract's own recorded origin (meta table) rather
# than re-deriving it.
_METERS_PER_DEG_LAT = 110_540.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


_origin_cache: tuple[float, float] | None = None


def _origin_latlon() -> tuple[float, float] | None:
    global _origin_cache
    if _origin_cache is not None:
        return _origin_cache
    if not EXTRACT_PATH.exists():
        return None
    conn = sqlite3.connect(EXTRACT_PATH)
    try:
        rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    try:
        _origin_cache = (float(rows["origin_lat"]), float(rows["origin_lon"]))
    except (KeyError, ValueError):
        return None
    return _origin_cache


def latlon_to_local(lat: float, lon: float) -> tuple[float, float] | None:
    """WGS84 -> the loaded extract's local flat (east, north) meter frame.
    None if there's no real extract loaded (synthetic fallback network has
    no real-world origin to project against)."""
    origin = _origin_latlon()
    if origin is None:
        return None
    origin_lat, origin_lon = origin
    east = (lon - origin_lon) * _meters_per_deg_lon(origin_lat)
    north = (lat - origin_lat) * _METERS_PER_DEG_LAT
    return east, north


def local_to_latlon(east: float, north: float) -> tuple[float, float] | None:
    origin = _origin_latlon()
    if origin is None:
        return None
    origin_lat, origin_lon = origin
    lat = origin_lat + north / _METERS_PER_DEG_LAT
    lon = origin_lon + east / _meters_per_deg_lon(origin_lat)
    return lat, lon


def nearest_routable_node(lat: float, lon: float) -> Node | None:
    """Snaps a real-world GPS coordinate (from the phone) to the closest
    node in the car's own loaded road graph — a linear scan, but this only
    runs once per remote destination request, not per frame, and the
    loaded graph is bounded to a few miles' radius."""
    local = latlon_to_local(lat, lon)
    if local is None or not GRAPH.nodes:
        return None
    east, north = local
    return min(GRAPH.nodes.values(), key=lambda n: (n.east - east) ** 2 + (n.north - north) ** 2)
