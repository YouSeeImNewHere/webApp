from __future__ import annotations

import os
from pathlib import Path

# Root directory for all Quail Maps data (raw OSM downloads, the master
# regional database, and the on-demand city-extract cache). Left unset on
# Render — the maps pipeline only runs on the homelab, which has the disk
# space for a country's worth of map data; the main web app must keep working
# with this entirely absent.
MAPS_DATA_DIR = (os.getenv("MAPS_DATA_DIR", "") or "").strip()


def maps_enabled() -> bool:
    return bool(MAPS_DATA_DIR)


def _subdir(name: str) -> Path:
    root = Path(MAPS_DATA_DIR) if MAPS_DATA_DIR else Path("data") / "maps"
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_dir() -> Path:
    """Downloaded .osm.pbf region files, one per configured region."""
    return _subdir("raw")


def master_dir() -> Path:
    """The built master SQLite database(s), one per region."""
    return _subdir("master")


def city_cache_dir() -> Path:
    """On-demand city extracts served to phones, cached by bbox key."""
    return _subdir("city_cache")


# Comma-separated list of Geofabrik relative paths, e.g.
#   "north-america/us/california,north-america/us/nevada"
# Each becomes https://download.geofabrik.de/<path>-latest.osm.pbf
# Intentionally empty by default — the user picks which regions they
# actually need (state-level extracts keep each import pass small and fast;
# add more states as the car's coverage area grows).
MAPS_REGION_SOURCES = [
    r.strip() for r in (os.getenv("MAPS_REGION_SOURCES", "") or "").split(",") if r.strip()
]

# How many days the removable car drive can go without being synced before
# we start pestering about it via Pushover.
MAPS_CAR_DRIVE_STALE_DAYS = max(1, int(os.getenv("MAPS_CAR_DRIVE_STALE_DAYS", "21")))

# Max radius a phone can request for a single on-demand city extract, to
# keep any one generated file (and the query behind it) bounded.
MAPS_MAX_EXTRACT_RADIUS_KM = max(1, int(os.getenv("MAPS_MAX_EXTRACT_RADIUS_KM", "40")))


def geofabrik_url(region: str) -> str:
    return f"https://download.geofabrik.de/{region}-latest.osm.pbf"


def geofabrik_state_url(region: str) -> str:
    """geofabrik publishes a small .osm.pbf.md5 alongside each extract —
    cheap way to detect an upstream update without downloading the whole file."""
    return f"https://download.geofabrik.de/{region}-latest.osm.pbf.md5"
