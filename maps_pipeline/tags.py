from __future__ import annotations

# highway=* -> (road_class, default speed_kph). road_class is one of
# "highway" (freeways), "local" (drivable streets), "foot" (walk-only ways) —
# quail_maps_car's Edge.road_class currently only distinguishes
# "local"/"highway"; "foot" is a superset added so phone extracts can carry
# real pedestrian routes for the walk-without-the-car use case, without
# forcing the car client to change anything (it can simply ignore edges it
# doesn't recognize).
HIGHWAY_CLASS_SPEED: dict[str, tuple[str, float]] = {
    "motorway": ("highway", 110.0),
    "motorway_link": ("highway", 60.0),
    "trunk": ("highway", 100.0),
    "trunk_link": ("highway", 55.0),
    "primary": ("local", 65.0),
    "primary_link": ("local", 45.0),
    "secondary": ("local", 55.0),
    "secondary_link": ("local", 40.0),
    "tertiary": ("local", 45.0),
    "tertiary_link": ("local", 35.0),
    "unclassified": ("local", 40.0),
    "residential": ("local", 40.0),
    "living_street": ("local", 20.0),
    "service": ("local", 25.0),
    "footway": ("foot", 5.0),
    "path": ("foot", 5.0),
    "pedestrian": ("foot", 5.0),
    "steps": ("foot", 3.0),
    "track": ("foot", 15.0),
}

# Ways with any of these tags are never routable (parking aisle geometry,
# proposed/construction, etc.) even if `highway` looks routable.
EXCLUDE_IF_TRUTHY = {"area", "proposed", "construction"}


def classify_highway(highway_value: str, maxspeed_kph: float | None) -> tuple[str, float] | None:
    entry = HIGHWAY_CLASS_SPEED.get(highway_value)
    if entry is None:
        return None
    road_class, default_speed = entry
    speed = maxspeed_kph if maxspeed_kph and maxspeed_kph > 0 else default_speed
    return road_class, speed


def parse_maxspeed(raw: str | None) -> float | None:
    """Best-effort parse of OSM's maxspeed tag ('35', '35 mph', '56 km/h')."""
    if not raw:
        return None
    raw = raw.strip().lower()
    try:
        if "mph" in raw:
            return float(raw.replace("mph", "").strip()) * 1.60934
        if "km/h" in raw or "kph" in raw:
            return float(raw.replace("km/h", "").replace("kph", "").strip())
        return float(raw)
    except ValueError:
        return None


# (osm tag key, osm tag value) -> (category, icon) — mirrors and extends
# quail_maps_car/geo/search_db.py's DISCOVER_CATEGORIES so a real extract
# drops into that schema unchanged. Extended beyond the original
# errand-running set (gas/food/coffee/parking/grocery/pharmacy) to cover
# tourism/leisure/historic/natural tags, for "discover nearby places" and
# "points of attraction" rather than just fuel-and-groceries.
POI_TAG_CATEGORY: dict[tuple[str, str], tuple[str, str]] = {
    ("amenity", "fuel"): ("gas", "⛽"),
    ("amenity", "charging_station"): ("ev", "\U0001f50c"),
    ("amenity", "restaurant"): ("food", "\U0001f354"),
    ("amenity", "fast_food"): ("food", "\U0001f354"),
    ("amenity", "cafe"): ("coffee", "☕"),
    ("shop", "coffee"): ("coffee", "☕"),
    ("amenity", "parking"): ("parking", "\U0001f17f️"),
    ("shop", "supermarket"): ("grocery", "\U0001f6d2"),
    ("shop", "grocery"): ("grocery", "\U0001f6d2"),
    ("shop", "convenience"): ("store", "\U0001f3ea"),
    ("amenity", "pharmacy"): ("pharmacy", "\U0001f48a"),
    # Tourism / points of attraction
    ("tourism", "attraction"): ("attraction", "\U0001f3a1"),
    ("tourism", "museum"): ("museum", "\U0001f3db️"),
    ("tourism", "gallery"): ("museum", "\U0001f5bc️"),
    ("tourism", "viewpoint"): ("viewpoint", "\U0001f306"),
    ("tourism", "artwork"): ("attraction", "\U0001f3a8"),
    ("tourism", "zoo"): ("attraction", "\U0001f981"),
    ("tourism", "aquarium"): ("attraction", "\U0001f420"),
    ("tourism", "theme_park"): ("attraction", "\U0001f3a2"),
    ("tourism", "hotel"): ("lodging", "\U0001f3e8"),
    ("tourism", "motel"): ("lodging", "\U0001f3e8"),
    ("tourism", "guest_house"): ("lodging", "\U0001f3e8"),
    ("tourism", "hostel"): ("lodging", "\U0001f3e8"),
    ("tourism", "camp_site"): ("lodging", "⛺"),
    # Leisure / outdoors
    ("leisure", "park"): ("park", "\U0001f333"),
    ("leisure", "garden"): ("park", "\U0001f33c"),
    ("leisure", "playground"): ("park", "\U0001fa81"),
    ("leisure", "nature_reserve"): ("park", "\U0001f332"),
    ("leisure", "golf_course"): ("recreation", "⛳"),
    ("leisure", "stadium"): ("recreation", "\U0001f3df️"),
    # Historic / landmarks
    ("historic", "monument"): ("historic", "\U0001f5ff"),
    ("historic", "memorial"): ("historic", "\U0001f5ff"),
    ("historic", "castle"): ("historic", "\U0001f3f0"),
    ("historic", "ruins"): ("historic", "\U0001f3db️"),
    ("historic", "fort"): ("historic", "\U0001f3f0"),
    ("historic", "archaeological_site"): ("historic", "\U0001f3fa"),
    # Natural landmarks
    ("natural", "beach"): ("beach", "\U0001f3d6️"),
    ("natural", "peak"): ("viewpoint", "⛰️"),
    ("natural", "waterfall"): ("viewpoint", "\U0001f4a7"),
    # Entertainment
    ("amenity", "theatre"): ("entertainment", "\U0001f3ad"),
    ("amenity", "cinema"): ("entertainment", "\U0001f3ac"),
}

# OSM tag keys checked, in order, when classifying a node's POI category.
_POI_TAG_KEYS = ("amenity", "shop", "tourism", "leisure", "historic", "natural")


def classify_poi(tags: dict[str, str]) -> tuple[str, str] | None:
    for key in _POI_TAG_KEYS:
        value = tags.get(key)
        if value and (key, value) in POI_TAG_CATEGORY:
            return POI_TAG_CATEGORY[(key, value)]
    return None
