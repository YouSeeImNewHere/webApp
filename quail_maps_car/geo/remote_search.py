"""Server-backed destination search, for anything the local extract can't
answer.

search_db.py only ever searches whatever's in the currently-downloaded
extract.sqlite3 - a POI/city "seed" scoped to one small download radius
(see data_source.py). Real user reports: searching "Dallas" from Seattle
returned nothing (Dallas was never in any downloaded extract), and
searching "walmart" only ever surfaced the 1-3 already inside that small
radius, not every Walmart within a reasonable driving distance. This talks
to homelab's nationwide master database instead - same auth pattern as
data_source.py's extract download (QUAIL_API_TOKEN bearer token, since
these live behind the app's normal RequireLoginMiddleware, unlike Valhalla
which has none)."""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from .data_source import DEFAULT_BASE_URL

# Server caps radius_km at 50 (see app/routers/maps.py's search_places) -
# already a lot further than any locally-downloaded extract's own radius
# (data_source.py's default is 40km), which is the whole point.
POI_SEARCH_RADIUS_KM = 50.0


@dataclass(frozen=True)
class RemotePlace:
    name: str
    lat: float
    lon: float
    address: str = ""
    icon: str = "\U0001f4cd"
    category: str = ""
    distance_mi: float = 0.0


def _token() -> str:
    return os.environ.get("QUAIL_API_TOKEN", "")


def fetch_remote_places(
    query: str, lat: float, lon: float, base_url: str = DEFAULT_BASE_URL,
) -> list[RemotePlace]:
    """Named POIs (e.g. "walmart") within POI_SEARCH_RADIUS_KM of (lat,
    lon) - homelab's /api/maps/places, backed by every imported region,
    not just whatever's locally downloaded."""
    token = _token()
    if not token or not query.strip():
        return []
    try:
        resp = requests.get(
            f"{base_url}/api/maps/places",
            params={"lat": lat, "lon": lon, "radius_km": POI_SEARCH_RADIUS_KM, "q": query, "limit": 50},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []
    return [
        RemotePlace(
            name=p["name"] or query,
            lat=p["lat"],
            lon=p["lon"],
            address=p.get("address") or "",
            icon=p.get("icon") or "\U0001f4cd",
            category=p.get("category") or "",
            distance_mi=float(p.get("distance_km", 0.0)) * 0.621371,
        )
        for p in data.get("places", [])
    ]


def fetch_remote_cities(query: str, base_url: str = DEFAULT_BASE_URL) -> list[RemotePlace]:
    """Free-text city/town search with no location bound at all (e.g.
    "Dallas" while in Seattle) - homelab's /api/maps/geocode."""
    token = _token()
    if not token or not query.strip():
        return []
    try:
        resp = requests.get(
            f"{base_url}/api/maps/geocode",
            params={"q": query, "limit": 20},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []
    return [
        RemotePlace(
            # State appended right into the name (not a separate field) so
            # every place this flows through - search row, detail sheet,
            # long-route screen title - shows it without each of them
            # needing their own plumbing. Real need: 3+ same-named cities
            # ("Dallas" in TX/OR/GA) are ambiguous without it.
            name=f"{c['name']}, {c['state']}" if c.get("state") else c["name"],
            lat=c["lat"],
            lon=c["lon"],
            address=(c.get("place_type") or "").replace("_", " ").title(),
            icon="\U0001f3d9️",
            category="city",
        )
        for c in data.get("results", [])
    ]
