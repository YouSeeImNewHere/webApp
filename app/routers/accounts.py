from __future__ import annotations

from datetime import datetime, time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.routers.balances import latest_rates_map_pg
from db import with_db_cursor, query_db, run_db_retry
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from app.core.home_snapshot_cache import bump_home_snapshot_version

router = APIRouter()

# =============================================================================
# Accounts / Bank endpoints (Postgres) — ported from accounts.py
# =============================================================================

def _pg_column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    )
    return cur.fetchone() is not None

def _pg_table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = %s
        LIMIT 1
        """,
        (table,),
    )
    return cur.fetchone() is not None

def _to_float_or_zero(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)

def _tenant_scope_key(tid: int | None) -> int:
    return int(tid or 0)

def _ensure_account_balance_audit_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS account_balance_audit (
              tenant_id BIGINT NOT NULL DEFAULT 0,
              account_id BIGINT NOT NULL,
              last_csv_upload_at TIMESTAMPTZ NULL,
              last_manual_verified_at TIMESTAMPTZ NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (tenant_id, account_id),
              FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_balance_audit_tenant_updated
            ON account_balance_audit(tenant_id, updated_at DESC)
            """
        )
        conn.commit()

def mark_account_csv_upload(account_id: int, tenant_id: int | None) -> None:
    _ensure_account_balance_audit_pg()
    scope_tid = _tenant_scope_key(tenant_id)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO account_balance_audit(tenant_id, account_id, last_csv_upload_at, updated_at)
            VALUES (%s, %s, now(), now())
            ON CONFLICT (tenant_id, account_id)
            DO UPDATE SET
              last_csv_upload_at = now(),
              updated_at = now()
            """,
            (int(scope_tid), int(account_id)),
        )
        conn.commit()
    bump_home_snapshot_version(tenant_id)

def _parse_verified_date_to_timestamp(v: Any) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=422, detail="invalid_verified_date")
    # Record as end-of-day for the selected date.
    return datetime.combine(d, time(23, 59, 59))


def _mark_account_manual_verified(
    account_id: int,
    tenant_id: int | None,
    *,
    verified_at: datetime | None = None,
) -> dict[str, Any]:
    _ensure_account_balance_audit_pg()
    scope_tid = _tenant_scope_key(tenant_id)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO account_balance_audit(tenant_id, account_id, last_manual_verified_at, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (tenant_id, account_id)
            DO UPDATE SET
              last_manual_verified_at = %s,
              updated_at = now()
            RETURNING last_csv_upload_at, last_manual_verified_at, updated_at
            """,
            (int(scope_tid), int(account_id), verified_at, verified_at),
        )
        row = dict(cur.fetchone() or {})
        conn.commit()
    bump_home_snapshot_version(tenant_id)
    return row

def _to_iso_or_none(v: Any) -> str | None:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if v is None:
        return None
    s = str(v).strip()
    return s or None

@router.get("/account/{account_id}")
def account_info(account_id: int):
    tid = _require_tenant_id()
    sql = """
      SELECT id, institution, name, LOWER(accountType) AS accounttype
      FROM accounts
      WHERE id = %s
    """
    params: tuple = (int(account_id),)
    if tid:
        sql += " AND tenant_id = %s"
        params = (int(account_id), int(tid))
    rows = query_db(sql, params)
    if not rows:
        return {"error": "Account not found"}

    out = dict(rows[0] or {})
    try:
        _ensure_account_balance_audit_pg()
        scope_tid = _tenant_scope_key(tid)
        audit_rows = query_db(
            """
            SELECT last_csv_upload_at, last_manual_verified_at, updated_at
            FROM account_balance_audit
            WHERE tenant_id = %s AND account_id = %s
            LIMIT 1
            """,
            (int(scope_tid), int(account_id)),
        )
        if audit_rows:
            ar = dict(audit_rows[0] or {})
            out["last_csv_upload_at"] = _to_iso_or_none(ar.get("last_csv_upload_at"))
            out["last_manual_verified_at"] = _to_iso_or_none(ar.get("last_manual_verified_at"))
            out["audit_updated_at"] = _to_iso_or_none(ar.get("updated_at"))
        else:
            out["last_csv_upload_at"] = None
            out["last_manual_verified_at"] = None
            out["audit_updated_at"] = None
    except Exception:
        out["last_csv_upload_at"] = None
        out["last_manual_verified_at"] = None
        out["audit_updated_at"] = None

    return out

class BalanceVerifiedIn(BaseModel):
    verified_date: str | None = None


@router.post("/account/{account_id}/balance-verified")
def mark_balance_verified(account_id: int, body: BalanceVerifiedIn | None = None):
    tid = _require_tenant_id()
    rows = query_db(
        "SELECT 1 FROM accounts WHERE id = %s " + ("AND tenant_id = %s " if tid else "") + "LIMIT 1",
        ((int(account_id), int(tid)) if tid else (int(account_id),)),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="account_not_found")

    verified_at = _parse_verified_date_to_timestamp((body.verified_date if body else None)) or datetime.now()
    row = _mark_account_manual_verified(int(account_id), tid, verified_at=verified_at)
    return {
        "ok": True,
        "account_id": int(account_id),
        "last_csv_upload_at": _to_iso_or_none(row.get("last_csv_upload_at")),
        "last_manual_verified_at": _to_iso_or_none(row.get("last_manual_verified_at")),
        "updated_at": _to_iso_or_none(row.get("updated_at")),
    }

@router.get("/bank-info")
def bank_info():
    tid = _require_tenant_id()

    def _run():
        with with_db_cursor() as (conn, cur):
            # Current rate (decimal) from interest_rates: 0.0425 means 4.25%
            # Your app_postgres.py already defines latest_rates_map_pg()
            rate_now = latest_rates_map_pg()

            # Be robust to schema (no hard requirement for optional columns/tables)
            has_credit_limit = _pg_column_exists(cur, "accounts", "credit_limit")
            has_notes = _pg_column_exists(cur, "accounts", "notes")  # only if you added it
            has_card_benefits = _pg_table_exists(cur, "card_benefits")

            # Build SELECT lists without requiring non-existent columns
            account_select = """
              SELECT id AS account_id,
                     institution AS bank,
                     name,
                     LOWER(accountType) AS type
            """
            if has_notes:
                account_select += ", notes"
            account_select += """
              FROM accounts
              WHERE LOWER(accountType) != 'credit'
              ORDER BY institution, name
            """
            if tid:
                account_select = account_select.replace("ORDER BY institution, name", "AND tenant_id = %s ORDER BY institution, name")

            card_select = """
              SELECT id AS card_id,
                     institution AS bank,
                     name
            """
            if has_credit_limit:
                card_select += ", credit_limit"
            card_select += """
              FROM accounts
              WHERE LOWER(accountType) = 'credit'
              ORDER BY institution, name
            """
            if tid:
                card_select = card_select.replace("ORDER BY institution, name", "AND tenant_id = %s ORDER BY institution, name")

            cur.execute(account_select, (int(tid),) if tid else ())
            accounts = cur.fetchall()

            cur.execute(card_select, (int(tid),) if tid else ())
            cards = cur.fetchall()

            benefits_rows = []
            if has_card_benefits:
                cur.execute(
                    """
                    SELECT
                        card_id AS account_id,
                        benefit_type AS category,
                        rate AS cashback_percent
                    FROM card_benefits
                    ORDER BY card_id, benefit_type, start_date NULLS FIRST, end_date NULLS LAST
                    """
                )
                benefits_rows = cur.fetchall()

        return rate_now, has_notes, has_credit_limit, accounts, cards, benefits_rows

    rate_now, has_notes, has_credit_limit, accounts, cards, benefits_rows = run_db_retry(_run, retries=1)

    # Attach benefits by card
    by_card: Dict[int, List[Dict[str, Any]]] = {}
    for b in benefits_rows:
        aid = int(b["account_id"])
        by_card.setdefault(aid, []).append(
            {
                "categories": [b["category"]] if b.get("category") else [],
                "cashback_percent": float(b.get("cashback_percent") or 0.0),
            }
        )

    def as_percent(rate_decimal):
        if rate_decimal is None:
            return None
        try:
            return float(rate_decimal) * 100.0
        except Exception:
            return None

    accounts_out = []
    for r in accounts:
        aid = int(r["account_id"])
        item = {
            "account_id": aid,
            "bank": r["bank"],
            "name": r["name"],
            "type": r["type"],
            "apy": as_percent(rate_now.get(aid)),
        }
        if has_notes:
            item["notes"] = r.get("notes")
        accounts_out.append(item)

    cards_out = []
    for r in cards:
        cid = int(r["card_id"])
        item = {
            "card_id": cid,
            "bank": r["bank"],
            "name": r["name"],
            "apr": as_percent(rate_now.get(cid)),
            "benefits": by_card.get(cid, []),
        }
        if has_credit_limit:
            item["credit_limit"] = r.get("credit_limit")
        cards_out.append(item)

    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "accounts": accounts_out,
        "credit_cards": cards_out,
    }

@router.post("/bank-info/refresh")
def bank_info_refresh():
    # placeholder for now
    return {"ok": True}

@router.get("/bank-totals")
def bank_totals():
    tid = _require_tenant_id()

    def _run():
        with with_db_cursor() as (conn, cur):
            has_credit_limit = _pg_column_exists(cur, "accounts", "credit_limit")
            _ensure_account_balance_audit_pg()

            accounts_sql = """
              SELECT id, institution, name, LOWER(accountType) AS accounttype
            """
            if has_credit_limit:
                accounts_sql += ", credit_limit"
            accounts_sql += """
              FROM accounts
            """
            if tid:
                accounts_sql += " WHERE tenant_id = %s"

            cur.execute(accounts_sql, (int(tid),) if tid else ())
            accounts = cur.fetchall()

            acct_ids = [int(r.get("id") or 0) for r in accounts if int(r.get("id") or 0) > 0]
            audit_rows: list[dict[str, Any]] = []
            if acct_ids:
                cur.execute(
                    """
                    SELECT account_id, last_csv_upload_at, last_manual_verified_at
                    FROM account_balance_audit
                    WHERE tenant_id = %s
                      AND account_id = ANY(%s)
                    """,
                    (int(_tenant_scope_key(tid)), acct_ids),
                )
                audit_rows = cur.fetchall() or []
            audit_map: Dict[int, Dict[str, Any]] = {
                int(r.get("account_id") or 0): dict(r) for r in (audit_rows or [])
            }

            if tid:
                cur.execute(
                    """
                    SELECT account_id, SUM(start) AS start_total
                    FROM "startingbalance"
                    WHERE tenant_id = %s
                    GROUP BY account_id
                    """,
                    (int(tid),),
                )
            else:
                cur.execute(
                    """
                    SELECT account_id, SUM(start) AS start_total
                    FROM "startingbalance"
                    GROUP BY account_id
                    """
                )
            starting_rows = cur.fetchall() or []

            if tid:
                cur.execute(
                    """
                    WITH base AS (
                      SELECT
                        account_id,
                        amount::double precision AS amount,
                        COALESCE(
                          NULLIF(TRIM(postedDate), 'unknown'),
                          NULLIF(TRIM(purchaseDate), 'unknown')
                        ) AS raw_date
                      FROM transactions
                      WHERE tenant_id = %s
                    ),
                    norm AS (
                      SELECT
                        account_id,
                        amount,
                        CASE
                          WHEN raw_date IS NULL THEN NULL
                          WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
                          WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
                          ELSE NULL
                        END AS d
                      FROM base
                    )
                    SELECT account_id, COALESCE(SUM(amount), 0)::double precision AS trans_total
                    FROM norm
                    WHERE d IS NOT NULL
                    GROUP BY account_id
                    """,
                    (int(tid),),
                )
            else:
                cur.execute(
                    """
                    WITH base AS (
                      SELECT
                        account_id,
                        amount::double precision AS amount,
                        COALESCE(
                          NULLIF(TRIM(postedDate), 'unknown'),
                          NULLIF(TRIM(purchaseDate), 'unknown')
                        ) AS raw_date
                      FROM transactions
                    ),
                    norm AS (
                      SELECT
                        account_id,
                        amount,
                        CASE
                          WHEN raw_date IS NULL THEN NULL
                          WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
                          WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
                          ELSE NULL
                        END AS d
                      FROM base
                    )
                    SELECT account_id, COALESCE(SUM(amount), 0)::double precision AS trans_total
                    FROM norm
                    WHERE d IS NOT NULL
                    GROUP BY account_id
                    """
                )
            tx_rows = cur.fetchall() or []
            totals_map: Dict[int, Dict[str, float | int]] = {
                int(r["account_id"]): {
                    "account_id": int(r["account_id"]),
                    "start_total": 0.0,
                    "trans_total": float(r["trans_total"] or 0.0),
                }
                for r in tx_rows
            }
            for r in starting_rows:
                aid = int(r["account_id"])
                row = totals_map.get(aid)
                if row is None:
                    totals_map[aid] = {
                        "account_id": aid,
                        "start_total": float(r["start_total"] or 0.0),
                        "trans_total": 0.0,
                    }
                else:
                    row["start_total"] = float(r["start_total"] or 0.0)
            totals_rows = list(totals_map.values())

        return has_credit_limit, accounts, totals_rows, audit_map

    has_credit_limit, accounts, totals_rows, audit_map = run_db_retry(_run, retries=1)
    starting = {int(r["account_id"]): float(r.get("start_total") or 0) for r in totals_rows}
    tx_totals = {int(r["account_id"]): float(r.get("trans_total") or 0) for r in totals_rows}

    by_type = {"checking": [], "savings": [], "investment": [], "credit": [], "other": []}

    for a in accounts:
        aid = int(a["id"])
        acc_type = (a.get("accounttype") or "other").lower()

        start = starting.get(aid, 0.0)
        trans = tx_totals.get(aid, 0.0)

        # Keep balance math consistent with account-series/account-transactions-range:
        # - investment: raw = start + trans
        # - others:     raw = start - trans
        # - credit display value is sign-flipped from raw
        if acc_type == "investment":
            raw_balance = start + trans
        else:
            raw_balance = start - trans
        balance = (-raw_balance) if acc_type == "credit" else raw_balance

        bucket = acc_type if acc_type in by_type else "other"
        display_name = f'{a["institution"]} — {a["name"]}'
        item = {"id": aid, "name": display_name, "total": balance}
        audit = audit_map.get(aid) or {}
        item["last_csv_upload_at"] = _to_iso_or_none(audit.get("last_csv_upload_at"))
        item["last_manual_verified_at"] = _to_iso_or_none(audit.get("last_manual_verified_at"))

        if bucket == "credit" and has_credit_limit:
            item["credit_limit"] = _to_float_or_zero(a.get("credit_limit"))

        by_type[bucket].append(item)

    for k in by_type:
        by_type[k].sort(key=lambda x: x["total"], reverse=True)

    return {k: {"total": sum(x["total"] for x in lst), "accounts": lst} for k, lst in by_type.items()}
