from __future__ import annotations

import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.settings import _ensure_app_settings_pg, SavingsGoalIn
from app.core.tenant_keys import scoped_key
from app.core.home_snapshot_cache import bump_home_snapshot_version
from app.core.tenancy import current_tenant_id
from db import with_db_cursor, query_db

router = APIRouter()

# =============================================================================
# Savings Goal (app_settings)
# =============================================================================
@router.get("/settings/savings-goal")
def get_savings_goal():
    _ensure_app_settings_pg()

    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (scoped_key("savings_goal"),),
    )
    if not rows:
        return {"mode": "percent", "value": 0}

    try:
        j = json.loads(rows[0]["value_json"] or "{}")
    except Exception:
        j = {}

    mode = j.get("mode", "percent")
    value = float(j.get("value", 0) or 0)

    if mode not in ("percent", "amount"):
        mode = "percent"
    if value < 0:
        value = 0
    if mode == "percent" and value > 100:
        value = 100

    return {"mode": mode, "value": value}

@router.post("/settings/savings-goal")
def set_savings_goal(body: SavingsGoalIn):
    mode = body.mode if body.mode in ("percent", "amount") else None
    if mode is None:
        raise HTTPException(status_code=422, detail="mode must be 'percent' or 'amount'")

    value = float(body.value)
    if value < 0:
        raise HTTPException(status_code=422, detail="value must be >= 0")
    if mode == "percent" and value > 100:
        raise HTTPException(status_code=422, detail="percent must be <= 100")

    payload = json.dumps({"mode": mode, "value": value})

    _ensure_app_settings_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO app_settings(key, value_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET value_json = EXCLUDED.value_json,
                          updated_at = now()
            """,
            (scoped_key("savings_goal"), payload),
        )
        conn.commit()
    bump_home_snapshot_version(current_tenant_id())

    return {"ok": True}
