from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.maps_config import (
    MAPS_CAR_DRIVE_STALE_DAYS,
    MAPS_MAX_EXTRACT_RADIUS_KM,
    city_cache_dir,
    maps_enabled,
    master_dir,
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
