from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Callable

import osmium

from .schema import open_master_db
from .tags import (
    CITY_PLACE_TYPES,
    EXCLUDE_IF_TRUTHY,
    classify_area,
    classify_highway,
    classify_node_control,
    classify_poi,
    is_motor_vehicle_routable,
    is_roundabout,
    parse_layer,
    parse_lanes,
    parse_maxspeed,
    parse_meters,
    parse_oneway,
)

_FLUSH_EVERY = 20_000
_PROGRESS_INTERVAL_SEC = 5.0


class _MasterImportHandler(osmium.SimpleHandler):
    """Streams a .osm.pbf once, writing routable ways (+ the nodes they
    reference) and tagged POI nodes straight into the master SQLite db.

    Deliberately a single streaming pass over the whole region: with
    `locations=True` pyosmium resolves each way node's lat/lon inline, so we
    never need a second pass or an in-memory node index of our own — only
    nodes actually used by a kept way (or that are POIs) ever touch SQLite,
    which is what keeps this tractable for a multi-GB regional extract.
    """

    def __init__(self, conn: sqlite3.Connection, on_progress: Callable[[int, int], None] | None = None):
        super().__init__()
        self.conn = conn
        self.cur = conn.cursor()
        self._node_rows: list[tuple] = []
        self._way_rows: list[tuple] = []
        self._way_node_rows: list[tuple] = []
        self._place_rows: list[tuple] = []
        self._city_rows: list[tuple] = []
        self._area_rows: list[tuple] = []
        self._control_rows: list[tuple] = []
        self.way_count = 0
        self.node_count = 0
        self.place_count = 0
        self.city_count = 0
        self.area_count = 0
        self._on_progress = on_progress
        self._last_report = time.monotonic()

    def _maybe_report(self):
        if not self._on_progress:
            return
        now = time.monotonic()
        if now - self._last_report >= _PROGRESS_INTERVAL_SEC:
            self._on_progress(self.way_count, self.place_count)
            self._last_report = now

    def _flush(self):
        if self._node_rows:
            self.cur.executemany(
                "INSERT OR IGNORE INTO nodes (id, lat, lon) VALUES (?,?,?)", self._node_rows
            )
            self._node_rows.clear()
        if self._way_rows:
            self.cur.executemany(
                "INSERT OR REPLACE INTO ways "
                "(id, street, road_class, speed_kph, lanes, turn_lanes, oneway, roundabout, "
                "surface, bridge, tunnel, layer, toll, maxheight, maxweight) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                self._way_rows,
            )
            self._way_rows.clear()
        if self._control_rows:
            self.cur.executemany(
                "INSERT OR REPLACE INTO node_controls (node_id, control) VALUES (?,?)",
                self._control_rows,
            )
            self._control_rows.clear()
        if self._way_node_rows:
            self.cur.executemany(
                "INSERT INTO way_nodes (way_id, seq, node_id) VALUES (?,?,?)", self._way_node_rows
            )
            self._way_node_rows.clear()
        if self._place_rows:
            self.cur.executemany(
                """INSERT OR REPLACE INTO places
                   (osm_id, node_id, lat, lon, name, address, city, postcode, icon, category,
                    opening_hours, phone, website)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                self._place_rows,
            )
            self._place_rows.clear()
        if self._city_rows:
            self.cur.executemany(
                "INSERT OR REPLACE INTO cities (osm_id, lat, lon, name, place_type, population) VALUES (?,?,?,?,?,?)",
                self._city_rows,
            )
            self._city_rows.clear()
        if self._area_rows:
            self.cur.executemany(
                "INSERT OR REPLACE INTO areas (osm_id, kind, ring_json, lat_min, lat_max, lon_min, lon_max) "
                "VALUES (?,?,?,?,?,?,?)",
                self._area_rows,
            )
            self._area_rows.clear()
        self.conn.commit()

    def way(self, w):
        if any(w.tags.get(k) for k in EXCLUDE_IF_TRUTHY):
            return

        tags = {t.k: t.v for t in w.tags}

        highway = tags.get("highway")
        # A private driveway or no-entry service road otherwise classifies
        # and routes exactly like a public street — real bug this closes:
        # nothing here ever checked access/motor_vehicle/vehicle before.
        if highway and is_motor_vehicle_routable(tags):
            classified = classify_highway(highway, parse_maxspeed(tags.get("maxspeed")))
            if classified is not None:
                road_class, speed_kph = classified
                # Falls back to ref (e.g. "I-90", "US-101") before the
                # generic label — a lot of interstate/US-route segments
                # carry no name tag at all, only ref, so without this
                # fallback they'd render/route as a bare "Motorway".
                street = tags.get("name") or tags.get("ref") or highway.replace("_", " ").title()
                # Direction-specific lane tags (dual carriageways) beat the
                # plain `lanes` total, which counts both directions —
                # rendering wants "lanes going my way," not the sum.
                lanes = parse_lanes(tags.get("lanes:forward") or tags.get("lanes")) or 0
                turn_lanes = tags.get("turn:lanes:forward") or tags.get("turn:lanes") or ""
                oneway = parse_oneway(tags)
                roundabout = 1 if is_roundabout(tags) else 0
                surface = tags.get("surface", "")
                bridge = 1 if tags.get("bridge") not in (None, "no") else 0
                tunnel = 1 if tags.get("tunnel") not in (None, "no") else 0
                layer = parse_layer(tags)
                toll = 1 if tags.get("toll") == "yes" else 0
                maxheight = parse_meters(tags.get("maxheight")) or 0
                maxweight = parse_meters(tags.get("maxweight")) or 0

                seq_nodes: list[int] = []
                for seq, n in enumerate(w.nodes):
                    if not n.location.valid():
                        continue
                    self._node_rows.append((n.ref, n.location.lat, n.location.lon))
                    self._way_node_rows.append((w.id, seq, n.ref))
                    seq_nodes.append(n.ref)
                    self.node_count += 1
                if len(seq_nodes) >= 2:
                    self._way_rows.append((
                        w.id, street, road_class, speed_kph, lanes, turn_lanes,
                        oneway, roundabout, surface, bridge, tunnel, layer, toll,
                        maxheight, maxweight,
                    ))
                    self.way_count += 1

        # Buildings mapped as an outline (way) rather than a single point
        # node — the norm for anything with a real footprint (big-box
        # stores, standalone restaurants, malls). Verified against live OSM
        # data: a real Dairy Queen near a test coordinate was exactly this
        # shape (amenity=fast_food + name on a closed way, no separate
        # node), and was silently dropped before this branch existed since
        # only node() checked classify_poi(). The ring's node-average is a
        # good-enough marker position without needing real polygon-centroid
        # math for typically-rectangular building footprints.
        name = tags.get("name")
        poi_classified = classify_poi(tags)
        housenumber = tags.get("addr:housenumber", "")
        street_addr = tags.get("addr:street", "")
        address = f"{housenumber} {street_addr}".strip()
        city = tags.get("addr:city", "")
        postcode = tags.get("addr:postcode", "")

        if (poi_classified is not None and name) or (housenumber and street_addr):
            lats: list[float] = []
            lons: list[float] = []
            for n in w.nodes:
                if n.location.valid():
                    lats.append(n.location.lat)
                    lons.append(n.location.lon)
            if lats:
                if poi_classified is not None and name:
                    category, icon = poi_classified
                    display_name = name
                else:
                    # A pure address building — no business/POI tag at all,
                    # just addr:housenumber/addr:street on the footprint.
                    # This is the common shape for an ordinary house: real
                    # bug this closes is "route to a home address" being
                    # completely unsupported, since every capture path in
                    # this importer required a `name` tag before this.
                    category, icon = "address", "🏠"
                    display_name = address
                opening_hours = tags.get("opening_hours", "")
                phone = tags.get("phone", "") or tags.get("contact:phone", "")
                website = tags.get("website", "") or tags.get("contact:website", "")
                self._place_rows.append(
                    (f"w{w.id}", None, sum(lats) / len(lats), sum(lons) / len(lons), display_name, address,
                     city, postcode, icon, category, opening_hours, phone, website)
                )
                self.place_count += 1

        # Fillable area geometry (water/parks/landuse/buildings) for a
        # future terrain/land-use basemap renderer — see classify_area()'s
        # docstring for why this is captured now despite nothing drawing it
        # yet. Only a CLOSED way (first and last referenced node match) is
        # a simple polygon; OSM also represents complex/large areas as
        # `relation` (multipolygon) features, which osmium.SimpleHandler
        # gives no callback for here — deliberately deferred, a real but
        # smaller residual gap than capturing no area data at all.
        area_kind = classify_area(tags)
        if area_kind is not None and len(w.nodes) >= 4 and w.nodes[0].ref == w.nodes[-1].ref:
            ring: list[list[float]] = []
            area_lats: list[float] = []
            area_lons: list[float] = []
            for n in w.nodes:
                if not n.location.valid():
                    continue
                ring.append([n.location.lat, n.location.lon])
                area_lats.append(n.location.lat)
                area_lons.append(n.location.lon)
            if len(ring) >= 4:
                self._area_rows.append((
                    f"w{w.id}", area_kind, json.dumps(ring),
                    min(area_lats), max(area_lats), min(area_lons), max(area_lons),
                ))
                self.area_count += 1

        if (self.way_count and self.way_count % _FLUSH_EVERY == 0) or (
            self.place_count and self.place_count % _FLUSH_EVERY == 0
        ) or (self.area_count and self.area_count % _FLUSH_EVERY == 0):
            self._flush()
        self._maybe_report()

    def node(self, n):
        if not n.location.valid() or len(n.tags) == 0:
            return
        tags = {t.k: t.v for t in n.tags}
        name = tags.get("name")

        control = classify_node_control(tags)
        if control is not None:
            self._control_rows.append((n.id, control))
            if len(self._control_rows) % _FLUSH_EVERY == 0:
                self._flush()

        place = tags.get("place")
        if place in CITY_PLACE_TYPES and name:
            try:
                population = int(tags.get("population", "0") or 0)
            except ValueError:
                population = 0
            self._city_rows.append((f"n{n.id}", n.location.lat, n.location.lon, name, place, population))
            self.city_count += 1
            if self.city_count % _FLUSH_EVERY == 0:
                self._flush()

        classified = classify_poi(tags)
        housenumber = tags.get("addr:housenumber", "")
        street = tags.get("addr:street", "")
        address = f"{housenumber} {street}".strip()
        city = tags.get("addr:city", "")
        postcode = tags.get("addr:postcode", "")

        if classified is not None and name:
            category, icon = classified
            display_name = name
        elif housenumber and street:
            # Pure address node — no business/POI tag at all, the common
            # shape for standalone residential address points (often
            # bulk-imported from county GIS/TIGER address data). Same fix
            # as the way() branch above: without this, "route to a home
            # address" was unsupported everywhere in this importer.
            category, icon = "address", "🏠"
            display_name = address
        else:
            return

        opening_hours = tags.get("opening_hours", "")
        phone = tags.get("phone", "") or tags.get("contact:phone", "")
        website = tags.get("website", "") or tags.get("contact:website", "")
        self._place_rows.append(
            (f"n{n.id}", n.id, n.location.lat, n.location.lon, display_name, address, city, postcode,
             icon, category, opening_hours, phone, website)
        )
        self.place_count += 1
        if self.place_count % _FLUSH_EVERY == 0:
            self._flush()

    def finish(self):
        self._flush()


def import_region(
    pbf_path: Path,
    master_db_path: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Rebuilds `master_db_path` from scratch out of `pbf_path`.

    Rebuilding (rather than diffing) keeps this importer simple and correct;
    a weekly full re-import of a state-sized extract is a few minutes of
    work, which is cheap relative to how rarely road networks actually
    change.

    `on_progress(way_count, place_count)` is called periodically during the
    pass — osmium doesn't expose bytes-read progress through SimpleHandler,
    so running feature counts are the best available "still working" signal.
    """
    started = time.time()
    if master_db_path.exists():
        master_db_path.unlink()

    conn = open_master_db(master_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    handler = _MasterImportHandler(conn, on_progress=on_progress)
    handler.apply_file(str(pbf_path), locations=True, idx="sparse_mem_array")
    handler.finish()

    conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_latlon ON nodes(lat, lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_places_latlon ON places(lat, lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cities_latlon ON cities(lat, lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_areas_bbox ON areas(lat_min, lat_max, lon_min, lon_max)")
    conn.commit()

    way_count = conn.execute("SELECT COUNT(*) FROM ways").fetchone()[0]
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    place_count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    city_count = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    area_count = conn.execute("SELECT COUNT(*) FROM areas").fetchone()[0]
    conn.close()

    elapsed = round(time.time() - started, 1)
    return {
        "way_count": way_count,
        "node_count": node_count,
        "place_count": place_count,
        "city_count": city_count,
        "area_count": area_count,
        "elapsed_sec": elapsed,
        "size_bytes": master_db_path.stat().st_size,
    }
