from __future__ import annotations

import json
from pathlib import Path

# Deliberately separate from quail_maps_car's search_db (which has its own
# hardcoded "home"/"work" synthetic seed rows) — that data gets wholesale
# replaced every time a real extract is re-downloaded (see
# quail_maps_car/geo/data_source.py), so anything meant to persist across
# extract updates needs to live outside that schema entirely.
SAVED_LOCATIONS_PATH = Path.home() / ".local" / "share" / "quail_car" / "saved_locations.json"


def load_locations() -> dict[str, dict]:
    """name -> {"lat": float, "lon": float}, insertion order preserved."""
    try:
        data = json.loads(SAVED_LOCATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_location(name: str, lat: float, lon: float) -> None:
    locations = load_locations()
    locations[name] = {"lat": lat, "lon": lon}
    SAVED_LOCATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAVED_LOCATIONS_PATH.write_text(json.dumps(locations, indent=2), encoding="utf-8")


def delete_location(name: str) -> None:
    locations = load_locations()
    if name in locations:
        del locations[name]
        SAVED_LOCATIONS_PATH.write_text(json.dumps(locations, indent=2), encoding="utf-8")


def get_location(name: str) -> tuple[float, float] | None:
    entry = load_locations().get(name)
    if entry is None:
        return None
    return entry["lat"], entry["lon"]
