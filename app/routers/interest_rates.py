from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.settings import RateUpsert, _ensure_interest_rates_table_pg
from db import with_db_cursor

router = APIRouter()

# =============================================================================
# Interest Rates (interest_rates)
# =============================================================================

@router.post("/interest-rate")
def set_interest_rate(payload: RateUpsert):
    try:
        rate_percent = float(payload.rate_percent)
    except Exception:
        return {"ok": False, "error": "rate_percent must be a number"}

    if rate_percent < 0 or rate_percent > 100:
        return {"ok": False, "error": "rate_percent must be between 0 and 100"}

    eff = (payload.effective_date or "").strip() or datetime.now().strftime("%Y-%m-%d")
    rate_decimal = rate_percent / 100.0

    _ensure_interest_rates_table_pg()

    with with_db_cursor() as (conn, cur):
        # Upsert on (account_id, effective_date)
        cur.execute(
            """
            INSERT INTO interest_rates (account_id, apr, effective_date, note, created_at)
            VALUES (%s, %s, %s::date, %s, now())
            ON CONFLICT (account_id, effective_date)
            DO UPDATE SET apr = EXCLUDED.apr,
                          note = EXCLUDED.note
            """,
            (
                int(payload.account_id),
                float(rate_decimal),
                eff,
                (payload.note or "").strip() or None,
            ),
        )
        conn.commit()

    return {
        "ok": True,
        "account_id": int(payload.account_id),
        "effective_date": eff,
        "rate_percent": rate_percent,
    }

