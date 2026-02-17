from __future__ import annotations

import json
from typing import Any

from db import query_db, with_db_cursor

_SNAPSHOT_READY = False


def ensure_home_snapshot_cache_pg() -> None:
    global _SNAPSHOT_READY
    if _SNAPSHOT_READY:
        return

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS home_snapshot_state (
              tenant_id BIGINT PRIMARY KEY,
              version BIGINT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS home_snapshot_month_budget (
              tenant_id BIGINT NOT NULL,
              year INT NOT NULL,
              month INT NOT NULL,
              min_occ INT NOT NULL DEFAULT 3,
              include_stale BOOLEAN NOT NULL DEFAULT false,
              source_version BIGINT NOT NULL DEFAULT 0,
              payload_json JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (tenant_id, year, month, min_occ, include_stale)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS home_snapshot_page_home (
              tenant_id BIGINT NOT NULL,
              tx_limit INT NOT NULL DEFAULT 15,
              source_version BIGINT NOT NULL DEFAULT 0,
              payload_json JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (tenant_id, tx_limit)
            )
            """
        )
        cur.execute(
            """
            CREATE OR REPLACE FUNCTION trg_home_snapshot_transactions()
            RETURNS trigger AS $$
            DECLARE
              tid BIGINT;
            BEGIN
              IF TG_OP = 'DELETE' THEN
                tid := COALESCE(OLD.tenant_id, 0)::bigint;
              ELSE
                tid := COALESCE(NEW.tenant_id, 0)::bigint;
              END IF;

              INSERT INTO home_snapshot_state (tenant_id, version, updated_at)
              VALUES (tid, 1, now())
              ON CONFLICT (tenant_id)
              DO UPDATE SET
                version = home_snapshot_state.version + 1,
                updated_at = now();

              IF TG_OP = 'DELETE' THEN
                RETURN OLD;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cur.execute("DROP TRIGGER IF EXISTS home_snapshot_transactions_iud ON transactions")
        cur.execute(
            """
            CREATE TRIGGER home_snapshot_transactions_iud
            AFTER INSERT OR UPDATE OR DELETE ON transactions
            FOR EACH ROW EXECUTE FUNCTION trg_home_snapshot_transactions()
            """
        )
        conn.commit()

    _SNAPSHOT_READY = True


def home_snapshot_version_for_tenant(tid: int | None) -> int:
    ensure_home_snapshot_cache_pg()
    tenant_id = int(tid or 0)
    rows = query_db(
        """
        INSERT INTO home_snapshot_state (tenant_id, version, updated_at)
        VALUES (%s, 0, now())
        ON CONFLICT (tenant_id) DO NOTHING
        RETURNING version
        """,
        (tenant_id,),
    )
    if rows:
        return int(rows[0].get("version") or 0)

    rows = query_db(
        "SELECT version FROM home_snapshot_state WHERE tenant_id=%s LIMIT 1",
        (tenant_id,),
    )
    if not rows:
        return 0
    return int(rows[0].get("version") or 0)


def bump_home_snapshot_version(tid: int | None) -> int:
    ensure_home_snapshot_cache_pg()
    tenant_id = int(tid or 0)
    rows = query_db(
        """
        INSERT INTO home_snapshot_state (tenant_id, version, updated_at)
        VALUES (%s, 1, now())
        ON CONFLICT (tenant_id)
        DO UPDATE SET
          version = home_snapshot_state.version + 1,
          updated_at = now()
        RETURNING version
        """,
        (tenant_id,),
    )
    if not rows:
        return 0
    return int(rows[0].get("version") or 0)


def load_month_budget_snapshot(
    tid: int,
    year: int,
    month: int,
    min_occ: int,
    include_stale: bool,
) -> dict[str, Any] | None:
    ensure_home_snapshot_cache_pg()
    rows = query_db(
        """
        SELECT source_version, payload_json
        FROM home_snapshot_month_budget
        WHERE tenant_id = %s
          AND year = %s
          AND month = %s
          AND min_occ = %s
          AND include_stale = %s
        LIMIT 1
        """,
        (int(tid), int(year), int(month), int(min_occ), bool(include_stale)),
    )
    if not rows:
        return None

    row = rows[0]
    payload = row.get("payload_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None

    if not isinstance(payload, dict):
        return None

    return {
        "source_version": int(row.get("source_version") or 0),
        "payload": payload,
    }


def upsert_month_budget_snapshot(
    tid: int,
    year: int,
    month: int,
    min_occ: int,
    include_stale: bool,
    source_version: int,
    payload: dict[str, Any],
) -> None:
    ensure_home_snapshot_cache_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO home_snapshot_month_budget
              (tenant_id, year, month, min_occ, include_stale, source_version, payload_json, updated_at)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
            ON CONFLICT (tenant_id, year, month, min_occ, include_stale)
            DO UPDATE SET
              source_version = EXCLUDED.source_version,
              payload_json = EXCLUDED.payload_json,
              updated_at = now()
            """,
            (
                int(tid),
                int(year),
                int(month),
                int(min_occ),
                bool(include_stale),
                int(source_version),
                json.dumps(payload),
            ),
        )
        conn.commit()


def load_page_home_snapshot(
    tid: int,
    tx_limit: int,
) -> dict[str, Any] | None:
    ensure_home_snapshot_cache_pg()
    rows = query_db(
        """
        SELECT source_version, payload_json
        FROM home_snapshot_page_home
        WHERE tenant_id = %s
          AND tx_limit = %s
        LIMIT 1
        """,
        (int(tid), int(tx_limit)),
    )
    if not rows:
        return None

    row = rows[0]
    payload = row.get("payload_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None

    if not isinstance(payload, dict):
        return None

    return {
        "source_version": int(row.get("source_version") or 0),
        "payload": payload,
    }


def upsert_page_home_snapshot(
    tid: int,
    tx_limit: int,
    source_version: int,
    payload: dict[str, Any],
) -> None:
    ensure_home_snapshot_cache_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO home_snapshot_page_home
              (tenant_id, tx_limit, source_version, payload_json, updated_at)
            VALUES
              (%s, %s, %s, %s::jsonb, now())
            ON CONFLICT (tenant_id, tx_limit)
            DO UPDATE SET
              source_version = EXCLUDED.source_version,
              payload_json = EXCLUDED.payload_json,
              updated_at = now()
            """,
            (
                int(tid),
                int(tx_limit),
                int(source_version),
                json.dumps(payload, default=str),
            ),
        )
        conn.commit()
