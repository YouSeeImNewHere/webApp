from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Callable

import osmium

from .schema import open_master_db
from .tags import EXCLUDE_IF_TRUTHY, classify_highway, classify_poi, parse_maxspeed

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
        self.way_count = 0
        self.node_count = 0
        self.place_count = 0
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
                "INSERT OR REPLACE INTO ways (id, street, road_class, speed_kph) VALUES (?,?,?,?)",
                self._way_rows,
            )
            self._way_rows.clear()
        if self._way_node_rows:
            self.cur.executemany(
                "INSERT INTO way_nodes (way_id, seq, node_id) VALUES (?,?,?)", self._way_node_rows
            )
            self._way_node_rows.clear()
        if self._place_rows:
            self.cur.executemany(
                """INSERT OR REPLACE INTO places
                   (osm_id, node_id, lat, lon, name, address, icon, category, opening_hours, phone, website)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                self._place_rows,
            )
            self._place_rows.clear()
        self.conn.commit()

    def way(self, w):
        if any(w.tags.get(k) for k in EXCLUDE_IF_TRUTHY):
            return
        highway = w.tags.get("highway")
        if not highway:
            return
        classified = classify_highway(highway, parse_maxspeed(w.tags.get("maxspeed")))
        if classified is None:
            return
        road_class, speed_kph = classified
        street = w.tags.get("name") or highway.replace("_", " ").title()

        seq_nodes: list[int] = []
        for seq, n in enumerate(w.nodes):
            if not n.location.valid():
                continue
            self._node_rows.append((n.ref, n.location.lat, n.location.lon))
            self._way_node_rows.append((w.id, seq, n.ref))
            seq_nodes.append(n.ref)
            self.node_count += 1
        if len(seq_nodes) < 2:
            return

        self._way_rows.append((w.id, street, road_class, speed_kph))
        self.way_count += 1
        if self.way_count % _FLUSH_EVERY == 0:
            self._flush()
        self._maybe_report()

    def node(self, n):
        if not n.location.valid() or len(n.tags) == 0:
            return
        tags = {t.k: t.v for t in n.tags}
        classified = classify_poi(tags)
        if classified is None:
            return
        name = tags.get("name")
        if not name:
            return
        category, icon = classified
        housenumber = tags.get("addr:housenumber", "")
        street = tags.get("addr:street", "")
        address = f"{housenumber} {street}".strip()
        opening_hours = tags.get("opening_hours", "")
        phone = tags.get("phone", "") or tags.get("contact:phone", "")
        website = tags.get("website", "") or tags.get("contact:website", "")
        self._place_rows.append(
            (f"n{n.id}", n.id, n.location.lat, n.location.lon, name, address, icon, category,
             opening_hours, phone, website)
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
    conn.commit()

    way_count = conn.execute("SELECT COUNT(*) FROM ways").fetchone()[0]
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    place_count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    conn.close()

    elapsed = round(time.time() - started, 1)
    return {
        "way_count": way_count,
        "node_count": node_count,
        "place_count": place_count,
        "elapsed_sec": elapsed,
        "size_bytes": master_db_path.stat().st_size,
    }
