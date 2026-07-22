"""Long-distance routing via the homelab's Valhalla instance, for trips well
outside anything the car's own downloaded extract could ever cover.

routing.py's Dijkstra only ever searches the one small extract.sqlite3 file
downloaded around a point (see data_source.py) - a real road network graph,
but bounded to roughly a --radius-km download, padded out to a max of 20km
by _BBOX_PAD_STEPS_M. That's the right tool for "find me a route across
town" and deliberately doesn't touch the network per-frame. It cannot route
Seattle -> Texas: the destination simply isn't in the loaded graph's nodes
at all, so no amount of bbox widening finds it.

Valhalla, by contrast, already has all 50 states' tiles built from the full
nationwide OSM extract (see maps_pipeline/) and free-roams the whole
country per request. This client is only ever used for the long-haul case;
short local trips keep using routing.py's own graph, which is faster and
works offline.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from .routing import TurnStep

# Matches quail_maps_car's homelab LAN address (see data_source.py) - the
# car computer and homelab are typically on the same home network. Valhalla
# listens on 8002 (see maps_pipeline/ + docker-compose on homelab), separate
# from the main webapp's 8000.
DEFAULT_VALHALLA_URL = "http://192.168.0.14:8002"

# Beyond this straight-line distance there's no realistic extract download
# radius that would ever cover both ends (data_source.py's own default
# extract radius caps at 40km/25mi) - past this, go straight to Valhalla
# instead of snapping to the nearest (wrong) locally-loaded node.
LONG_ROUTE_THRESHOLD_MI = 50.0

def _glyph_for_instruction(instruction: str) -> str:
    """Valhalla's numeric maneuver `type` doesn't line up with any glyph
    scheme worth hardcoding (verified against real output - e.g. type 10 is
    a right turn, type 15 is a left turn, not the sequential/directional
    enum you'd guess). The instruction text itself is far more reliable."""
    text = instruction.lower()
    if "arrive" in text:
        return "▪"
    if "left" in text:
        return "↰"
    if "right" in text:
        return "↱"
    if "keep" in text or "continue" in text or "stay" in text:
        return "↑"
    return "↑"


@dataclass
class LongRoute:
    distance_mi: float
    minutes: int
    steps: list[TurnStep]
    shape: list[tuple[float, float]]  # decoded (lat, lon) polyline, for reference/future map use


def _decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    """Standard Valhalla/OSRM polyline decode at 1e6 precision (Valhalla's
    default 'shape' encoding, precision 6 - not the more common Google
    precision-5 polyline)."""
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if is_lat:
                lat += delta
            else:
                lon += delta
        coords.append((lat / 1e6, lon / 1e6))
    return coords


def fetch_long_route(
    start_lat: float, start_lon: float, goal_lat: float, goal_lon: float,
    base_url: str = DEFAULT_VALHALLA_URL,
) -> LongRoute | None:
    body = {
        "locations": [
            {"lat": start_lat, "lon": start_lon},
            {"lat": goal_lat, "lon": goal_lon},
        ],
        "costing": "auto",
        "units": "miles",
    }
    try:
        resp = requests.post(f"{base_url}/route", json=body, timeout=30)
        resp.raise_for_status()
        trip = resp.json()["trip"]
    except (requests.RequestException, KeyError, ValueError):
        return None
    if trip.get("status") != 0:
        return None

    steps: list[TurnStep] = []
    shape: list[tuple[float, float]] = []
    for leg in trip.get("legs", []):
        shape.extend(_decode_polyline6(leg.get("shape", "")))
        for maneuver in leg.get("maneuvers", []):
            instruction = maneuver.get("instruction") or " ".join(maneuver.get("street_names", [])) or "Continue"
            length_m = float(maneuver.get("length", 0.0)) * 1609.34
            steps.append(TurnStep(instruction, length_m, _glyph_for_instruction(instruction)))

    summary = trip.get("summary", {})
    return LongRoute(
        distance_mi=float(summary.get("length", 0.0)),
        minutes=max(1, round(float(summary.get("time", 0.0)) / 60.0)),
        steps=steps or [TurnStep("Arrive at destination", 0.0, "▪")],
        shape=shape,
    )
