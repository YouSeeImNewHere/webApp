from __future__ import annotations

import hashlib
import math
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.maps_config import (
    MAPS_CAR_DRIVE_STALE_DAYS,
    MAPS_MAX_EXTRACT_RADIUS_KM,
    city_cache_dir,
    maps_enabled,
    master_dir,
    tile_cache_dir,
)
from app.core.maps_state import car_drive_staleness, get_car_drive_state, get_master_state
from app.core.tenancy import current_tenant_id

router = APIRouter(prefix="/api/maps", tags=["maps"])


def _require_maps_enabled():
    if not maps_enabled():
        raise HTTPException(
            status_code=501,
            detail="Quail Maps isn't configured on this server (MAPS_DATA_DIR unset) — "
            "this endpoint only runs on the homelab, not the hosted web app.",
        )


def _master_db_paths() -> list[Path]:
    return sorted(master_dir().glob("*.sqlite3"))


@router.get("/status")
def maps_status():
    tid = current_tenant_id() or 0
    regions = get_master_state(tid)
    drive = get_car_drive_state(tid)
    staleness = car_drive_staleness(tid, MAPS_CAR_DRIVE_STALE_DAYS)
    return {
        "enabled": maps_enabled(),
        "regions": regions,
        "car_drive": drive,
        "car_drive_staleness": staleness,
    }


@router.get("/extract")
def get_city_extract(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10.0, gt=0),
    refresh: bool = Query(False),
):
    _require_maps_enabled()
    if radius_km > MAPS_MAX_EXTRACT_RADIUS_KM:
        raise HTTPException(
            status_code=400,
            detail=f"radius_km must be <= {MAPS_MAX_EXTRACT_RADIUS_KM}",
        )

    master_db_paths = _master_db_paths()
    if not master_db_paths:
        raise HTTPException(status_code=404, detail="No map regions have been built yet")

    # Lazy import: extract.py is pure sqlite (no osmium), but keep the
    # pipeline package's import out of the hot module-load path anyway.
    from maps_pipeline.extract import build_city_extract

    cache_key = hashlib.sha1(f"{lat:.3f}:{lon:.3f}:{radius_km:.1f}".encode()).hexdigest()[:16]
    out_path = city_cache_dir() / f"{cache_key}.sqlite3"

    if refresh or not out_path.exists():
        build_city_extract(master_db_paths, out_path, lat, lon, radius_km)

    return FileResponse(
        out_path,
        media_type="application/x-sqlite3",
        filename=f"quail-maps-{cache_key}.sqlite3",
    )


@router.get("/tile/{z}/{x}/{y}.png")
def get_tile(z: int, x: int, y: int):
    """Standard slippy-map raster tile — the client only ever fetches the
    handful of tiles actually on screen, instead of downloading/rendering
    an entire metro area's worth of roads at once (see /extract's docstring
    history for why that doesn't scale on a phone)."""
    _require_maps_enabled()
    if not (0 <= z <= 19):
        raise HTTPException(status_code=400, detail="z must be between 0 and 19")
    n = 2**z
    if not (0 <= x < n and 0 <= y < n):
        raise HTTPException(status_code=400, detail="x/y out of range for this z")

    cache_path = tile_cache_dir() / str(z) / str(x) / f"{y}.png"
    if not cache_path.exists():
        master_db_paths = _master_db_paths()
        if not master_db_paths:
            raise HTTPException(status_code=404, detail="No map regions have been built yet")

        from maps_pipeline.tile_render import render_tile

        png_bytes = render_tile(master_db_paths, z, x, y)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(png_bytes)

    return FileResponse(cache_path, media_type="image/png")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.get("/places")
def search_places(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(5.0, gt=0, le=50),
    category: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, gt=0, le=200),
):
    """Nearby POIs — gas/food/coffee/parking/grocery plus the tourism/
    leisure/historic/natural categories maps_pipeline/tags.py classifies
    (attractions, museums, viewpoints, parks, historic sites, etc.)."""
    _require_maps_enabled()
    master_db_paths = _master_db_paths()
    if not master_db_paths:
        raise HTTPException(status_code=404, detail="No map regions have been built yet")

    meters_per_deg_lat = 110_540.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    dlat = (radius_km * 1000.0) / meters_per_deg_lat
    dlon = (radius_km * 1000.0) / meters_per_deg_lon
    lat_min, lat_max = lat - dlat, lat + dlat
    lon_min, lon_max = lon - dlon, lon + dlon

    results = []
    for db_path in master_db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            sql = (
                "SELECT osm_id, lat, lon, name, address, icon, category, opening_hours, phone, website FROM places "
                "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
            )
            params: list = [lat_min, lat_max, lon_min, lon_max]
            if category:
                # Comma-separated list supported (e.g. "attraction,museum,park")
                # so the Android "Things to do near me" discovery row can pull
                # several categories in one request instead of one per chip.
                categories = [c.strip() for c in category.split(",") if c.strip()]
                if categories:
                    placeholders = ",".join("?" for _ in categories)
                    sql += f" AND category IN ({placeholders})"
                    params.extend(categories)
            if q:
                sql += " AND name LIKE ?"
                params.append(f"%{q}%")
            for r in conn.execute(sql, params).fetchall():
                dist = _haversine_km(lat, lon, r["lat"], r["lon"])
                if dist <= radius_km:
                    results.append(
                        {
                            "id": r["osm_id"],
                            "name": r["name"],
                            "address": r["address"],
                            "icon": r["icon"],
                            "category": r["category"],
                            "lat": r["lat"],
                            "lon": r["lon"],
                            "distance_km": round(dist, 2),
                            "opening_hours": r["opening_hours"],
                            "phone": r["phone"],
                            "website": r["website"],
                        }
                    )
        finally:
            conn.close()

    results.sort(key=lambda p: p["distance_km"])
    return {"places": results[:limit]}


@router.get("/cities")
def nearby_cities(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(60.0, gt=0, le=300),
    limit: int = Query(8, gt=0, le=30),
):
    """Nearest city/town/village (best-effort "what city am I in" via
    nearest-node distance, NOT true administrative-boundary containment —
    no boundary polygons are imported, just place=city/town/village point
    nodes) plus other nearby ones, for the discovery panel's "Nearby
    Cities" section."""
    _require_maps_enabled()
    master_db_paths = _master_db_paths()
    if not master_db_paths:
        raise HTTPException(status_code=404, detail="No map regions have been built yet")

    meters_per_deg_lat = 110_540.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    dlat = (radius_km * 1000.0) / meters_per_deg_lat
    dlon = (radius_km * 1000.0) / meters_per_deg_lon
    lat_min, lat_max = lat - dlat, lat + dlat
    lon_min, lon_max = lon - dlon, lon + dlon

    results = []
    for db_path in master_db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute(
                "SELECT osm_id, lat, lon, name, place_type, population FROM cities "
                "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                (lat_min, lat_max, lon_min, lon_max),
            ).fetchall():
                dist = _haversine_km(lat, lon, r["lat"], r["lon"])
                if dist <= radius_km:
                    results.append(
                        {
                            "id": r["osm_id"],
                            "name": r["name"],
                            "place_type": r["place_type"],
                            "population": r["population"],
                            "lat": r["lat"],
                            "lon": r["lon"],
                            "distance_km": round(dist, 2),
                        }
                    )
        finally:
            conn.close()

    results.sort(key=lambda c: c["distance_km"])
    current = results[0] if results else None
    nearby = results[1 : limit + 1] if results else []
    return {"current": current, "nearby": nearby}


class RoutePointIn(BaseModel):
    lat: float
    lon: float


class RouteRequestIn(BaseModel):
    points: list[RoutePointIn]
    mode: str = "drive"


@router.post("/route")
def get_route(request: RouteRequestIn = Body(...)):
    """Real Dijkstra routing + turn-by-turn over the master road graph, with
    up to 3 labeled alternatives (fastest/shortest/avoid-highways for
    driving, fastest/shortest for walking) and multi-stop support (2+
    ordered points) — see maps_pipeline/routing.py. No transit mode: this
    engine has no real transit schedule data (GTFS) to route over."""
    _require_maps_enabled()
    if request.mode not in ("drive", "walk"):
        raise HTTPException(status_code=400, detail="mode must be 'drive' or 'walk'")
    if len(request.points) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 points (start and destination)")

    master_db_paths = _master_db_paths()
    if not master_db_paths:
        raise HTTPException(status_code=404, detail="No map regions have been built yet")

    points = [(p.lat, p.lon) for p in request.points]
    for i in range(len(points) - 1):
        (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
        if _haversine_km(lat1, lon1, lat2, lon2) > 80:
            raise HTTPException(status_code=400, detail="Two consecutive stops are too far apart (max ~80km)")

    from maps_pipeline.routing import RouteNotFoundError, compute_routes

    try:
        return {"routes": compute_routes(master_db_paths, points, mode=request.mode)}
    except RouteNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
