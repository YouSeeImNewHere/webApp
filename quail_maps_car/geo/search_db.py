from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .roadnet import GRAPH, distance_m

DB_PATH = Path(__file__).resolve().parent / "places.sqlite3"

# (id, node_id, name, address, icon, category) — stands in for a real
# offline POI export (e.g. built from an OSM extract) seeded into the same
# schema. The search mechanism (FTS5 full-text index + distance sort) is
# fully real; only this seed data is synthetic.
_SEED: list[tuple[str, str, str, str, str, str]] = [
    ("home", "HOME", "Home", "212 Willow Creek Ln", "⌂", "saved"),
    ("work", "WORK", "Work", "900 5th Ave, Suite 220", "\U0001f4bc", "saved"),
    ("gas1", "SHELL", "Shell", "Route 9 & Main St", "⛽", "gas"),
    ("gas2", "COSTCO", "Costco Gas", "455 Retail Pkwy", "⛽", "gas"),
    ("food1", "DINER", "Blue Owl Diner", "18 Market St", "\U0001f354", "food"),
    ("coffee1", "UNIONSQ", "Fenwick Coffee Co.", "77 Union Sq", "☕", "coffee"),
    ("park1", "PARKING", "Riverside Parking Deck", "40 River Rd", "\U0001f17f️", "parking"),
    ("ev1", "CHARGE", "Quail Charge Station", "1200 Innovation Dr", "\U0001f50c", "ev"),
]

DISCOVER_CATEGORIES: list[tuple[str, str, str]] = [
    ("gas", "⛽", "Gas"),
    ("food", "\U0001f354", "Food"),
    ("coffee", "☕", "Coffee"),
    ("parking", "\U0001f17f️", "Parking"),
    ("ev", "\U0001f50c", "EV Charging"),
]


@dataclass(frozen=True)
class Place:
    id: str
    node_id: str
    name: str
    address: str
    icon: str
    category: str
    distance_mi: float = 0.0


def _build_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE places (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            icon TEXT NOT NULL,
            category TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE places_fts USING fts5(
            name, address, category, content='places', content_rowid='rowid'
        );
        CREATE TRIGGER places_ai AFTER INSERT ON places BEGIN
            INSERT INTO places_fts(rowid, name, address, category)
            VALUES (new.rowid, new.name, new.address, new.category);
        END;
        """
    )
    conn.executemany(
        "INSERT INTO places (id, node_id, name, address, icon, category) VALUES (?, ?, ?, ?, ?, ?)",
        _SEED,
    )
    conn.commit()


def _connect() -> sqlite3.Connection:
    is_new = not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    if is_new:
        _build_schema(conn)
    return conn


def _fts_query(raw: str) -> str:
    tokens = [t for t in raw.strip().split() if t]
    return " ".join(f'"{t}"*' for t in tokens)


def fetch_places(query: str = "", category: str | None = None, from_node: str = "START") -> list[Place]:
    conn = _connect()
    try:
        cur = conn.cursor()
        q = (query or "").strip()
        if q:
            rows = cur.execute(
                """
                SELECT p.id, p.node_id, p.name, p.address, p.icon, p.category
                FROM places_fts f
                JOIN places p ON p.rowid = f.rowid
                WHERE places_fts MATCH ?
                ORDER BY rank
                """,
                (_fts_query(q),),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT id, node_id, name, address, icon, category FROM places"
            ).fetchall()
    finally:
        conn.close()

    origin = GRAPH.nodes[from_node]
    places: list[Place] = []
    for pid, node_id, name, address, icon, cat in rows:
        if category and cat != category:
            continue
        node = GRAPH.nodes[node_id]
        dist_mi = distance_m(origin, node) / 1609.34
        places.append(Place(pid, node_id, name, address, icon, cat, dist_mi))
    places.sort(key=lambda p: p.distance_mi)
    return places


def get_place(place_id: str) -> Place | None:
    for place in fetch_places(from_node="START"):
        if place.id == place_id:
            return place
    return None
