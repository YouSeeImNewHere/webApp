from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.routers.transactions_feeds import attach_transfer_peers_pg
from db import with_db_cursor, query_db
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from app.core.roundups import (
    get_roundup_settings,
    is_roundup_eligible_tx,
    roundup_amount_from_spend,
    roundup_cents_from_spend,
)

router = APIRouter()

# =============================================================================
# Transactions (Postgres) — ported from transactions.py
# Tables used (per your screenshot): transactions, accounts
# =============================================================================


def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


def _annotate_roundups(rows: list[dict[str, Any]], fallback_account_type: str = "") -> None:
    cfg = get_roundup_settings()
    enabled = bool(cfg.get("enabled", False))
    for r in rows:
        amt = float(r.get("amount") or 0.0)
        category = (r.get("category") or "").strip().lower()
        account_type = (
            str(r.get("accountType") or r.get("accounttype") or r.get("account_type") or fallback_account_type)
            .strip()
            .lower()
        )
        if enabled and is_roundup_eligible_tx(amt, account_type, category):
            ru = roundup_amount_from_spend(amt)
            r["roundup_amount"] = round(ru, 2)
            r["roundup_cents"] = roundup_cents_from_spend(amt)
        else:
            r["roundup_amount"] = 0.0
            r["roundup_cents"] = 0

@router.get("/transactions")
def transactions(limit: int = Query(15, ge=1, le=1000)):
    tid = _require_tenant_id()
    tenant_where = "WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""
    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            t.postedDate,
            t.purchaseDate,
            t.merchant,
            t.amount::double precision AS amount,
            t.status,
            t.account_id,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {tenant_where}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          id,
          account_id,
          raw_date AS postedDate,
          merchant,
          amount,
          status,
          bank,
          card,
          accountType,
          category,
          d AS "dateISO"
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        ((int(tid), int(tid), int(limit)) if tid else (int(limit),)),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    _annotate_roundups(rows)
    return rows

@router.get("/account-transactions")
def account_transactions(account_id: int, limit: int = Query(200, ge=1, le=5000)):
    tid = _require_tenant_id()
    tenant_where = "AND t.tenant_id = %s" if tid else ""
    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.merchant,
            t.amount::double precision AS amount,
            TRIM(t.category) AS category
          FROM transactions t
          WHERE t.account_id = %s
          {tenant_where}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          id,
          raw_date AS postedDate,
          merchant,
          amount,
          category,
          d AS "dateISO",
          %s::int AS account_id
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        ((int(account_id), int(tid), int(account_id), int(limit)) if tid else (int(account_id), int(account_id), int(limit))),
    )
    rows = [dict(r) for r in rows]
    account_type = ""
    try:
        at = query_db(
            f"SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s {'AND tenant_id = %s' if tid else ''} LIMIT 1",
            ((int(account_id), int(tid)) if tid else (int(account_id),)),
        )
        account_type = str((at[0].get("t") if at else "") or "")
    except Exception:
        account_type = ""
    attach_transfer_peers_pg(rows)
    _annotate_roundups(rows, fallback_account_type=account_type)
    return rows

@router.get("/transactions-all")
def transactions_all(limit: int = Query(10000, ge=1, le=50000), offset: int = Query(0, ge=0)):
    tid = _require_tenant_id()
    tenant_where = "WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""
    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.*,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {tenant_where}
        ),
        norm AS (
          SELECT
            base.*,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT *, d AS "dateISO"
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s OFFSET %s
        """,
        ((int(tid), int(tid), int(limit), int(offset)) if tid else (int(limit), int(offset))),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    _annotate_roundups(rows)
    return rows
