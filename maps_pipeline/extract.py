from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from .schema import build_extract_db

METERS_PER_DEG_LAT = 110_540.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def _project(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    east = (lon - origin_lon) * _meters_per_deg_lon(origin_lat)
    north = (lat - origin_lat) * METERS_PER_DEG_LAT
    return east, north


def _bbox(center_lat: float, center_lon: float, radius_km: float, pad: float = 1.15):
    padded_m = radius_km * 1000.0 * pad
    dlat = padded_m / METERS_PER_DEG_LAT
    dlon = padded_m / _meters_per_deg_lon(center_lat)
    return (center_lat - dlat, center_lat + dlat, center_lon - dlon, center_lon + dlon)


def _collect_from_region(master_db_path: Path, bbox) -> tuple[dict, list, list]:
    """Pulls the bbox-clipped node positions / edges / places out of a
    single region's master db. OSM node/way ids are globally unique, so
    results from multiple regions merge safely by id — needed since a city
    near a state border can straddle two Geofabrik region extracts.
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    master = sqlite3.connect(str(master_db_path))
    master.row_factory = sqlite3.Row
    try:
        master.execute("CREATE TEMP TABLE bbox_nodes (id INTEGER PRIMARY KEY)")
        master.execute(
            "INSERT INTO temp.bbox_nodes SELECT id FROM nodes WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
            (lat_min, lat_max, lon_min, lon_max),
        )

        way_rows = master.execute(
            """
            SELECT wn.way_id, wn.seq, wn.node_id, n.lat, n.lon, w.street, w.road_class, w.speed_kph
            FROM way_nodes wn
            JOIN nodes n ON n.id = wn.node_id
            JOIN ways w ON w.id = wn.way_id
            WHERE wn.way_id IN (SELECT DISTINCT way_id FROM way_nodes WHERE node_id IN (SELECT id FROM temp.bbox_nodes))
            ORDER BY wn.way_id, wn.seq
            """
        ).fetchall()

        place_rows = master.execute(
            "SELECT osm_id, node_id, lat, lon, name, address, icon, category FROM places "
            "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
            (lat_min, lat_max, lon_min, lon_max),
        ).fetchall()
        in_bbox_node_ids = {r[0] for r in master.execute("SELECT id FROM temp.bbox_nodes")}
    finally:
        master.close()

    node_positions: dict[int, tuple[float, float]] = {}
    edges: list[tuple[int, int, str, str, float]] = []
    ways: dict[int, list[tuple[int, int, float, float]]] = {}
    for row in way_rows:
        ways.setdefault(row["way_id"], []).append(
            (row["seq"], row["node_id"], row["lat"], row["lon"])
        )
    way_meta = {r["way_id"]: (r["street"], r["road_class"], r["speed_kph"]) for r in way_rows}

    for way_id, points in ways.items():
        points.sort(key=lambda p: p[0])
        street, road_class, speed_kph = way_meta[way_id]
        for (_, na, lata, lona), (_, nb, latb, lonb) in zip(points, points[1:]):
            if na not in in_bbox_node_ids and nb not in in_bbox_node_ids:
                continue
            node_positions[na] = (lata, lona)
            node_positions[nb] = (latb, lonb)
            edges.append((na, nb, street, road_class, speed_kph))

    return node_positions, edges, list(place_rows)


def build_city_extract(
    master_db_paths: list[Path],
    out_path: Path,
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> dict:
    """Clips a radius_km-around-(center_lat, center_lon) slice out of one or
    more master regional databases and writes it as a standalone SQLite file
    in quail_maps_car's local flat-meter schema — small enough for a phone
    to pull over wifi and drive fully offline nav from.
    """
    bbox = _bbox(center_lat, center_lon, radius_km)

    node_positions: dict[int, tuple[float, float]] = {}
    edges: list[tuple[int, int, str, str, float]] = []
    place_rows: list = []
    for master_db_path in master_db_paths:
        np, ed, pr = _collect_from_region(master_db_path, bbox)
        node_positions.update(np)
        edges.extend(ed)
        place_rows.extend(pr)

    if out_path.exists():
        out_path.unlink()
    extract = build_extract_db(out_path)
    cur = extract.cursor()

    node_id_map = {osm_id: f"n{osm_id}" for osm_id in node_positions}
    node_insert_rows = []
    for osm_id, (lat, lon) in node_positions.items():
        east, north = _project(lat, lon, center_lat, center_lon)
        node_insert_rows.append((node_id_map[osm_id], east, north, ""))
    cur.executemany("INSERT INTO nodes (id, east, north, label) VALUES (?,?,?,?)", node_insert_rows)

    edge_insert_rows = [
        (node_id_map[a], node_id_map[b], street, road_class, speed_kph)
        for a, b, street, road_class, speed_kph in edges
        if a in node_id_map and b in node_id_map
    ]
    cur.executemany(
        "INSERT INTO edges (a, b, street, road_class, speed_kph) VALUES (?,?,?,?,?)", edge_insert_rows
    )

    place_insert_rows = []
    seen_place_ids: set[str] = set()
    for r in place_rows:
        if r["osm_id"] in seen_place_ids:
            continue
        seen_place_ids.add(r["osm_id"])
        node_id = node_id_map.get(r["node_id"])
        if node_id is None:
            # POI's own node fell outside the drivable-node set (e.g. a shop
            # set back from any routable way we kept) — anchor it to itself
            # as a standalone node so it still shows up and is reachable.
            node_id = f"poi{r['osm_id']}"
            east, north = _project(r["lat"], r["lon"], center_lat, center_lon)
            cur.execute(
                "INSERT OR IGNORE INTO nodes (id, east, north, label) VALUES (?,?,?,?)",
                (node_id, east, north, r["name"]),
            )
        place_insert_rows.append((r["osm_id"], node_id, r["name"], r["address"], r["icon"], r["category"]))
    cur.executemany(
        "INSERT INTO places (id, node_id, name, address, icon, category) VALUES (?,?,?,?,?,?)",
        place_insert_rows,
    )

    cur.executemany(
        "INSERT INTO meta (key, value) VALUES (?,?)",
        [
            ("origin_lat", str(center_lat)),
            ("origin_lon", str(center_lon)),
            ("radius_km", str(radius_km)),
        ],
    )
    extract.commit()
    extract.close()

    return {
        "node_count": len(node_insert_rows),
        "edge_count": len(edge_insert_rows),
        "place_count": len(place_insert_rows),
        "size_bytes": out_path.stat().st_size,
    }
