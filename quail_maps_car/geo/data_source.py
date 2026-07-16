"""Pulls a real OSM-derived map extract from the homelab server and installs
it where roadnet.py / search_db.py already know to look for one.

The car computer is usually offline once installed, but while it does have
network (home WiFi, testing, etc.) run this once:

    export QUAIL_API_TOKEN=<token minted via the browser mobile-auth flow>
    python -m quail_maps_car.geo.data_source --lat 47.6062 --lon -122.3321

That downloads a real road network + POIs centered on the given point and
saves it to geo/extract.sqlite3. roadnet.py and search_db.py both check for
that file on import and use it instead of the small synthetic dataset if
present — no restart-time flag needed, just re-launch the app.

The homelab's /api/maps/extract endpoint already returns data in exactly
the schema this app's own loaders expect (local flat east/north meters,
same nodes/edges/places/places_fts table names) — see maps_pipeline/schema.py
EXTRACT_SCHEMA — so this is a straight download-and-save, no conversion.

Auth: the whole backend sits behind RequireLoginMiddleware (Google OAuth +
a signed "mq1." bearer token, app/core/auth.py) — there's no fixed API key
for scripts. Mint a personal token the same way the Android app does, by
visiting (in a browser):

    <base-url>/mobile/auth/start?callback=http://localhost/token

Log in with Google if prompted; the final redirect (to a URL that won't
actually load) will have ?token=...&email=...&tenant_id=... in the address
bar — copy the token value into QUAIL_API_TOKEN. It's valid 30 days.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

EXTRACT_PATH = Path(__file__).resolve().parent / "extract.sqlite3"

# Matches QuailAndroid's BASE_URL_LOCAL_LAN (AppConfig.kt) — the car
# computer and the homelab are typically on the same home LAN when this
# runs, which is simpler/faster than going out over Tailscale for a
# same-room download.
DEFAULT_BASE_URL = "http://192.168.0.31:8000"
DEFAULT_RADIUS_KM = 40.0  # server's MAPS_MAX_EXTRACT_RADIUS_KM default cap


def fetch_extract(
    lat: float,
    lon: float,
    radius_km: float = DEFAULT_RADIUS_KM,
    base_url: str = DEFAULT_BASE_URL,
    token: str | None = None,
) -> Path:
    token = token if token is not None else os.environ.get("QUAIL_API_TOKEN", "")
    if not token:
        raise RuntimeError(
            "No auth token — set QUAIL_API_TOKEN (see this module's docstring "
            "for how to mint one via the browser mobile-auth flow)"
        )
    resp = requests.get(
        f"{base_url}/api/maps/extract",
        # refresh=true: the endpoint caches its output by a hash of
        # lat/lon/radius (app/routers/maps.py) — without this, re-running
        # this script after a server-side extract-building fix just gets
        # the same stale cached file back, silently. This tool exists
        # specifically to (re-)pull fresh data, so there's no case where a
        # stale cache is actually what's wanted here.
        params={"lat": lat, "lon": lon, "radius_km": radius_km, "refresh": "true"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    )
    resp.raise_for_status()
    EXTRACT_PATH.write_bytes(resp.content)
    return EXTRACT_PATH


def has_real_extract() -> bool:
    return EXTRACT_PATH.exists()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True, help="Latitude to center the extract on")
    parser.add_argument("--lon", type=float, required=True, help="Longitude to center the extract on")
    parser.add_argument("--radius-km", type=float, default=DEFAULT_RADIUS_KM)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    print(f"Fetching extract centered on ({args.lat}, {args.lon}), radius {args.radius_km}km …")
    try:
        path = fetch_extract(args.lat, args.lon, args.radius_km, args.base_url)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"error: fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"Saved {size_mb:.1f}MB to {path}")
    print("Restart the app (or just re-run qtest) to pick up the real data.")


if __name__ == "__main__":
    main()
