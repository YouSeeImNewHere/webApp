from __future__ import annotations

import json
from datetime import datetime, timezone

from db import with_db_cursor

_tables_ready = False


def ensure_maps_tables():
    global _tables_ready
    if _tables_ready:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS maps_master_state (
                tenant_id INTEGER NOT NULL DEFAULT 0,
                region VARCHAR(200) NOT NULL,
                source_md5 VARCHAR(64) DEFAULT '',
                node_count BIGINT DEFAULT 0,
                way_count BIGINT DEFAULT 0,
                place_count BIGINT DEFAULT 0,
                size_bytes BIGINT DEFAULT 0,
                built_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (tenant_id, region)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS maps_car_drive_state (
                tenant_id INTEGER PRIMARY KEY DEFAULT 0,
                drive_label VARCHAR(200) DEFAULT '',
                synced_regions JSONB DEFAULT '[]'::jsonb,
                synced_at TIMESTAMPTZ
            )
            """
        )
        conn.commit()
    _tables_ready = True


def record_region_build(tenant_id: int, region: str, stats: dict, source_md5: str) -> None:
    ensure_maps_tables()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO maps_master_state
                (tenant_id, region, source_md5, node_count, way_count, place_count, size_bytes, built_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (tenant_id, region) DO UPDATE SET
                source_md5 = EXCLUDED.source_md5,
                node_count = EXCLUDED.node_count,
                way_count = EXCLUDED.way_count,
                place_count = EXCLUDED.place_count,
                size_bytes = EXCLUDED.size_bytes,
                built_at = NOW()
            """,
            (
                tenant_id or 0,
                region,
                source_md5,
                stats.get("node_count", 0),
                stats.get("way_count", 0),
                stats.get("place_count", 0),
                stats.get("size_bytes", 0),
            ),
        )
        conn.commit()


def get_master_state(tenant_id: int) -> list[dict]:
    ensure_maps_tables()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "SELECT * FROM maps_master_state WHERE tenant_id = %s ORDER BY region",
            (tenant_id or 0,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if r.get("built_at") and not isinstance(r["built_at"], str):
            r["built_at"] = r["built_at"].isoformat()
    return rows


def record_car_drive_sync(tenant_id: int, drive_label: str, synced_regions: list[dict]) -> None:
    ensure_maps_tables()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO maps_car_drive_state (tenant_id, drive_label, synced_regions, synced_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET
                drive_label = EXCLUDED.drive_label,
                synced_regions = EXCLUDED.synced_regions,
                synced_at = NOW()
            """,
            (tenant_id or 0, drive_label, json.dumps(synced_regions)),
        )
        conn.commit()


def get_car_drive_state(tenant_id: int) -> dict | None:
    ensure_maps_tables()
    with with_db_cursor() as (conn, cur):
        cur.execute("SELECT * FROM maps_car_drive_state WHERE tenant_id = %s", (tenant_id or 0,))
        row = cur.fetchone()
    if not row:
        return None
    row = dict(row)
    if row.get("synced_at") and not isinstance(row["synced_at"], str):
        row["synced_at"] = row["synced_at"].isoformat()
    return row


def car_drive_staleness(tenant_id: int, stale_days: int) -> dict:
    """Compares the car drive's last-synced region versions against the
    current master state. Stale if it's simply been too long, or if any
    region on the drive is behind what the master db was last rebuilt from.
    """
    master = {r["region"]: r for r in get_master_state(tenant_id)}
    drive = get_car_drive_state(tenant_id)

    if drive is None or not drive.get("synced_at"):
        return {
            "stale": bool(master),
            "reason": "never_synced" if master else "no_master_data",
            "days_since_sync": None,
            "behind_regions": list(master.keys()),
        }

    synced_at = drive["synced_at"]
    if isinstance(synced_at, str):
        synced_at = datetime.fromisoformat(synced_at)
    days_since_sync = (datetime.now(timezone.utc) - synced_at).days

    synced_versions = {r["region"]: r.get("source_md5") for r in (drive.get("synced_regions") or [])}
    behind_regions = [
        region
        for region, state in master.items()
        if synced_versions.get(region) != state.get("source_md5")
    ]

    stale = days_since_sync >= stale_days or bool(behind_regions)
    reason = "behind_regions" if behind_regions else ("time_elapsed" if stale else "up_to_date")
    return {
        "stale": stale,
        "reason": reason,
        "days_since_sync": days_since_sync,
        "behind_regions": behind_regions,
    }
