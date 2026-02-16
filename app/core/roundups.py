from __future__ import annotations

import json
import math
from typing import Any

from db import with_db_cursor, query_db
from app.core.tenant_keys import scoped_key

ROUNDUP_SETTINGS_KEY = "round_up_transactions"
ROUNDUP_CATEGORY_DEFAULT = "Round-ups"
ROUNDUP_CATEGORY_NORM = "round-ups"


def _ensure_app_settings_table() -> None:
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_settings_tenant_id ON app_settings(tenant_id)")
        conn.commit()


def get_roundup_settings() -> dict[str, Any]:
    _ensure_app_settings_table()
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (scoped_key(ROUNDUP_SETTINGS_KEY),),
    )
    if not rows:
        return {"enabled": False, "category": ROUNDUP_CATEGORY_DEFAULT}

    try:
        obj = json.loads(rows[0].get("value_json") or "{}")
    except Exception:
        obj = {}

    enabled = bool(obj.get("enabled", False))
    category = str(obj.get("category") or ROUNDUP_CATEGORY_DEFAULT).strip() or ROUNDUP_CATEGORY_DEFAULT
    return {"enabled": enabled, "category": category}


def set_roundup_settings(enabled: bool, category: str = ROUNDUP_CATEGORY_DEFAULT) -> dict[str, Any]:
    _ensure_app_settings_table()
    payload = json.dumps(
        {
            "enabled": bool(enabled),
            "category": (str(category).strip() or ROUNDUP_CATEGORY_DEFAULT),
        }
    )
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO app_settings(key, value_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET value_json = EXCLUDED.value_json,
                          updated_at = now()
            """,
            (scoped_key(ROUNDUP_SETTINGS_KEY), payload),
        )
        conn.commit()
    return get_roundup_settings()


def roundup_amount_from_spend(amount: float) -> float:
    """
    For an outgoing spend amount (positive), returns the dollars needed to reach next whole dollar.
    Example: 7.56 -> 0.44; 7.00 -> 0.00.
    """
    try:
        a = float(amount)
    except Exception:
        return 0.0
    if a <= 0:
        return 0.0

    frac = a - math.floor(a)
    if frac <= 1e-9:
        return 0.0
    return round(1.0 - frac, 2)


def roundup_cents_from_spend(amount: float) -> int:
    return int(round(roundup_amount_from_spend(amount) * 100))


def is_roundup_eligible_tx(amount: float, account_type: str, category: str) -> bool:
    ct = (str(account_type or "")).strip().lower()
    if ct not in ("checking", "credit"):
        return False
    if float(amount or 0.0) <= 0:
        return False
    cat = (str(category or "")).strip().lower()
    if cat in ("card payment", "transfer", "cash withdrawal"):
        return False
    return True

