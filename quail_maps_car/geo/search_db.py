from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .data_source import EXTRACT_PATH
from .roadnet import GRAPH, distance_m

# Synthetic fallback DB — only used when no real extract has been
# downloaded (see data_source.py). A real extract already has places +
# places_fts tables in this exact schema, so it's used directly with no
# rebuild/reseed step.
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
    opening_hours: str = ""
    phone: str = ""
    website: str = ""


def _build_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE places (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            icon TEXT NOT NULL,
            category TEXT NOT NULL,
            opening_hours TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            website TEXT NOT NULL DEFAULT ''
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
    if EXTRACT_PATH.exists():
        return sqlite3.connect(EXTRACT_PATH)
    is_new = not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    if is_new:
        _build_schema(conn)
    return conn


def _fts_query(raw: str) -> str:
    tokens = [t for t in raw.strip().split() if t]
    return " ".join(f'"{t}"*' for t in tokens)


# An already-downloaded extract (e.g. the 331MB one pulled before this
# field was added server-side) has the old 6-column places table with no
# opening_hours/phone/website — re-downloading gets the richer columns,
# but the app shouldn't break against an existing file in the meantime.
_RICH_COLUMNS_AVAILABLE: bool | None = None


def _has_rich_columns(conn: sqlite3.Connection) -> bool:
    global _RICH_COLUMNS_AVAILABLE
    if _RICH_COLUMNS_AVAILABLE is None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(places)")}
        _RICH_COLUMNS_AVAILABLE = {"opening_hours", "phone", "website"} <= cols
    return _RICH_COLUMNS_AVAILABLE


def fetch_places(
    query: str = "",
    category: str | None = None,
    from_node: str = "START",
    max_distance_mi: float | None = None,
) -> list[Place]:
    conn = _connect()
    try:
        cur = conn.cursor()
        rich = _has_rich_columns(conn)
        extra_cols = ", p.opening_hours, p.phone, p.website" if rich else ""
        extra_cols_plain = ", opening_hours, phone, website" if rich else ""
        q = (query or "").strip()
        if q:
            rows = cur.execute(
                f"""
                SELECT p.id, p.node_id, p.name, p.address, p.icon, p.category{extra_cols}
                FROM places_fts f
                JOIN places p ON p.rowid = f.rowid
                WHERE places_fts MATCH ?
                ORDER BY rank
                """,
                (_fts_query(q),),
            ).fetchall()
        else:
            rows = cur.execute(
                f"SELECT id, node_id, name, address, icon, category{extra_cols_plain} FROM places"
            ).fetchall()
    finally:
        conn.close()

    origin = GRAPH.nodes[from_node]
    places: list[Place] = []
    for row in rows:
        pid, node_id, name, address, icon, cat = row[:6]
        hours, phone, website = row[6:9] if rich else ("", "", "")
        if category and cat != category:
            continue
        # A real extract's places table can reference a node just outside
        # the returned node set at the extract's radius boundary — same
        # dangling-reference situation roadnet.py already guards against.
        node = GRAPH.nodes.get(node_id)
        if node is None:
            continue
        dist_mi = distance_m(origin, node) / 1609.34
        if max_distance_mi is not None and dist_mi > max_distance_mi:
            continue
        places.append(Place(pid, node_id, name, address, icon, cat, dist_mi, hours or "", phone or "", website or ""))

    if q:
        # rows already arrived in FTS5 relevance-rank order (ORDER BY rank
        # above) — that ordering used to get thrown away here by an
        # unconditional distance sort, so a weak substring match nearby
        # would always beat a strong name match slightly farther off. A
        # typed search should rank by how well it matches what you typed;
        # distance only matters when you're just browsing nearby.
        return places
    places.sort(key=lambda p: p.distance_mi)
    return places


def get_place(place_id: str) -> Place | None:
    for place in fetch_places(from_node="START"):
        if place.id == place_id:
            return place
    return None
