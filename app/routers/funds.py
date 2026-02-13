from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import with_db_cursor, query_db

router = APIRouter()

# =============================================================================
# Sinking Funds (Postgres)
# =============================================================================

def _ensure_sinking_funds_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sinking_fund (
              id BIGSERIAL PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              target_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
              target_date DATE NULL,
              cadence TEXT NOT NULL DEFAULT 'monthly',
              contrib_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
              reserved_balance DOUBLE PRECISION NOT NULL DEFAULT 0,
              is_active BOOLEAN NOT NULL DEFAULT TRUE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sinking_fund_ledger (
              id BIGSERIAL PRIMARY KEY,
              fund_id BIGINT NOT NULL REFERENCES sinking_fund(id) ON DELETE CASCADE,
              ts TIMESTAMPTZ NOT NULL DEFAULT now(),
              amount DOUBLE PRECISION NOT NULL,
              note TEXT
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sinking_fund_ledger_fund_ts ON sinking_fund_ledger(fund_id, ts DESC)")
        conn.commit()

class SinkingFundCreate(BaseModel):
    name: str
    target_amount: float = 0.0
    target_date: str | None = None  # YYYY-MM-DD or None/blank
    cadence: str = "monthly"         # monthly|weekly|paycheck|custom
    contrib_amount: float = 0.0

class SinkingFundUpdate(BaseModel):
    name: str | None = None
    target_amount: float | None = None
    target_date: str | None = None
    cadence: str | None = None
    contrib_amount: float | None = None
    is_active: bool | None = None

class SinkingFundAdjust(BaseModel):
    amount: float
    note: str = ""

def _parse_date_yyyy_mm_dd(s: str | None):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=422, detail="target_date must be YYYY-MM-DD")

def _list_sinking_funds(include_inactive: bool = False):
    _ensure_sinking_funds_pg()
    where = "" if include_inactive else "WHERE is_active = TRUE"
    rows = query_db(
        f"""
        SELECT id, name, target_amount, target_date, cadence, contrib_amount, reserved_balance, is_active
        FROM sinking_fund
        {where}
        ORDER BY LOWER(name) ASC
        """
    )

    out = []
    today = date.today()
    for r in rows:
        tgt = float(r.get("target_amount") or 0.0)
        bal = float(r.get("reserved_balance") or 0.0)
        td = r.get("target_date")
        td_str = td.isoformat() if hasattr(td, "isoformat") else (str(td) if td else "")
        needed_per_day = None
        if td and tgt > bal:
            days = max(1, (td - today).days)
            needed_per_day = round((tgt - bal) / float(days), 2)
        out.append(
            {
                "id": int(r["id"]),
                "name": r.get("name") or "",
                "target_amount": round(tgt, 2),
                "target_date": td_str,
                "cadence": r.get("cadence") or "monthly",
                "contrib_amount": round(float(r.get("contrib_amount") or 0.0), 2),
                "reserved_balance": round(bal, 2),
                "needed_per_day": needed_per_day,
                "is_active": bool(r.get("is_active", True)),
            }
        )
    return out

@router.get("/funds")
def list_sinking_funds(include_inactive: int = 0):
    return {"ok": True, "funds": _list_sinking_funds(include_inactive=bool(int(include_inactive or 0)))}

@router.post("/funds")
def create_sinking_fund(f: SinkingFundCreate):
    _ensure_sinking_funds_pg()
    nm = (f.name or "").strip()
    if not nm:
        raise HTTPException(status_code=422, detail="name is required")

    tgt = float(f.target_amount or 0.0)
    td = _parse_date_yyyy_mm_dd(f.target_date)
    cadence = (f.cadence or "monthly").strip().lower()
    contrib = float(f.contrib_amount or 0.0)

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO sinking_fund(name, target_amount, target_date, cadence, contrib_amount)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (nm, tgt, td, cadence, contrib),
        )
        row = cur.fetchone()
        # Depending on cursor_factory, fetchone() can return tuple/list OR dict-like row.
        if row is None:
            raise HTTPException(status_code=500, detail="Failed to create fund (no id returned)")
        new_id = int(row["id"] if isinstance(row, dict) else row[0])
        conn.commit()

    return {"ok": True, "id": new_id}

@router.patch("/funds/{fund_id}")
def update_sinking_fund(fund_id: int, f: SinkingFundUpdate):
    _ensure_sinking_funds_pg()

    rows = query_db("SELECT id FROM sinking_fund WHERE id=%s LIMIT 1", (int(fund_id),))
    if not rows:
        raise HTTPException(status_code=404, detail="Fund not found")

    sets = []
    params = []

    if f.name is not None:
        nm = (f.name or "").strip()
        if not nm:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        sets.append("name=%s")
        params.append(nm)

    if f.target_amount is not None:
        sets.append("target_amount=%s")
        params.append(float(f.target_amount or 0.0))

    if f.target_date is not None:
        td = _parse_date_yyyy_mm_dd(f.target_date)
        sets.append("target_date=%s")
        params.append(td)

    if f.cadence is not None:
        sets.append("cadence=%s")
        params.append((f.cadence or "monthly").strip().lower())

    if f.contrib_amount is not None:
        sets.append("contrib_amount=%s")
        params.append(float(f.contrib_amount or 0.0))

    if f.is_active is not None:
        sets.append("is_active=%s")
        params.append(bool(f.is_active))

    if not sets:
        return {"ok": True, "updated": False}

    params.append(int(fund_id))

    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"UPDATE sinking_fund SET {', '.join(sets)}, updated_at=now() WHERE id=%s",
            tuple(params),
        )
        conn.commit()

    return {"ok": True, "updated": True}

@router.post("/funds/{fund_id}/adjust")
def adjust_sinking_fund(fund_id: int, a: SinkingFundAdjust):
    _ensure_sinking_funds_pg()
    amt = float(a.amount or 0.0)
    if not amt:
        raise HTTPException(status_code=422, detail="amount is required")
    note = (a.note or "").strip()

    with with_db_cursor() as (conn, cur):
        cur.execute("SELECT reserved_balance FROM sinking_fund WHERE id=%s AND is_active=TRUE LIMIT 1", (int(fund_id),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Fund not found")

        bal_val = row.get("reserved_balance") if isinstance(row, dict) else row[0]
        bal = float(bal_val or 0.0)
        new_bal = round(bal + amt, 2)

        cur.execute(
            "INSERT INTO sinking_fund_ledger(fund_id, amount, note) VALUES (%s, %s, %s)",
            (int(fund_id), amt, note),
        )
        cur.execute(
            "UPDATE sinking_fund SET reserved_balance=%s, updated_at=now() WHERE id=%s",
            (new_bal, int(fund_id)),
        )
        conn.commit()

    return {"ok": True, "reserved_balance": new_bal}

@router.delete("/funds/{fund_id}")
def delete_sinking_fund(fund_id: int):
    _ensure_sinking_funds_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE sinking_fund SET is_active=FALSE, updated_at=now() WHERE id=%s", (int(fund_id),))
        conn.commit()
    return {"ok": True}


