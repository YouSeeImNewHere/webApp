from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable

from fastapi import APIRouter, HTTPException, Query

from app.core.analytics_helpers import apply_transaction
from app.core.date_parse import parse_iso, parse_posted_date
from app.routers.transactions_feeds import attach_transfer_peers_pg
from db import with_db_cursor, query_db
from app.core.time import today_local
from datetime import date as _date, timedelta as _timedelta
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from app.core.transactions_ignore import ensure_transactions_ignore_column
from app.core.roundups import (
    get_roundup_settings,
    is_roundup_eligible_tx,
    roundup_amount_from_spend,
    roundup_cents_from_spend,
)

router = APIRouter()

# =============================================================================
# Balance / Series Helpers (Postgres)
# Ported from balances.py
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
            str(r.get("account_type") or r.get("accounttype") or r.get("accountType") or fallback_account_type)
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


def latest_rates_map_pg() -> Dict[int, float]:
    """
    Returns {account_id: apr} for the most recent effective_date per account.
    Postgres equivalent of latest_rates_map(). :contentReference[oaicite:5]{index=5}
    """
    tid = _require_tenant_id()
    rows = query_db(
        f"""
        SELECT r.account_id::int AS account_id, r.apr::double precision AS apr
        FROM interest_rates r
        JOIN accounts a ON a.id = r.account_id
        JOIN (
          SELECT account_id, MAX(effective_date) AS max_eff
          FROM interest_rates
          GROUP BY account_id
        ) last
          ON last.account_id = r.account_id
         AND last.max_eff = r.effective_date
        {"WHERE a.tenant_id = %s" if tid else ""}
        """,
        ((int(tid),) if tid else ()),
    )

    out: Dict[int, float] = {}
    for r in rows:
        try:
            out[int(r["account_id"])] = float(r["apr"])
        except Exception:
            pass
    return out

@router.get("/transactions")
def transactions(limit: int = Query(15, ge=1, le=1000)):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
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
            COALESCE(t.is_ignored, false) AS is_ignored,
            t.account_id,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accounttype) AS account_type,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
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
          is_ignored,
          bank,
          card,
          account_type,
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
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.merchant,
            t.amount::double precision AS amount,
            COALESCE(t.is_ignored, false) AS is_ignored,
            TRIM(t.category) AS category
          FROM transactions t
          WHERE t.account_id = %s
            {"AND t.tenant_id = %s" if tid else ""}
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
          is_ignored,
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

from fastapi import Query

@router.get("/transactions-all")
def transactions_all(
    limit: int = Query(50, ge=1, le=50000),
    offset: int = Query(0, ge=0),

    merchant: str = "",
    card: str = "",
    category: str = "",

    q: str = "",
    start: str = "",
    end: str = "",
    amt_mode: str = "any",
    amt_min: float | None = None,
    amt_max: float | None = None,
    amt_abs: int = 1,
):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()

    """
    Paginated feed with server-side filtering for All Transactions page.
    """
    merchant = (merchant or "").strip()
    card = (card or "").strip()
    category = (category or "").strip()
    q = (q or "").strip()
    start = (start or "").strip()
    end = (end or "").strip()
    amt_mode = (amt_mode or "any").strip().lower()
    use_abs = bool(int(amt_abs or 0))

    where = []
    params = []
    if merchant:
        where.append("COALESCE(merchant,'') ILIKE %s")
        params.append(f"%{merchant}%")

    if card:
        where.append("COALESCE(card,'') ILIKE %s")
        params.append(f"%{card}%")

    if category:
        where.append("COALESCE(category,'') ILIKE %s")
        params.append(f"%{category}%")

    # text search across merchant/bank/card/category
    if q:
        where.append("""
          (
            COALESCE(merchant,'') ILIKE %s OR
            COALESCE(bank,'') ILIKE %s OR
            COALESCE(card,'') ILIKE %s OR
            COALESCE(category,'') ILIKE %s
          )
        """)
        like = f"%{q}%"
        params.extend([like, like, like, like])

    # date window (ISO yyyy-mm-dd)
    if start:
        sd = parse_iso(start)
        where.append("d >= %s")
        params.append(sd)

    if end:
        ed = parse_iso(end)
        where.append("d <= %s")
        params.append(ed)

    # amount filter (note: outer query sees "amount", not "t.amount")
    amt_expr = "ABS(amount::double precision)" if use_abs else "amount::double precision"

    if amt_min is not None:
        where.append(f"{amt_expr} >= %s")
        params.append(float(amt_min))
    if amt_max is not None:
        where.append(f"{amt_expr} <= %s")
        params.append(float(amt_max))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

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
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            base.*,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          *,
          d AS "dateISO"
        FROM norm
        {where_sql}
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(([int(tid), int(tid)] if tid else []) + params + [int(limit), int(offset)]),
    )

    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    _annotate_roundups(rows)
    return rows


# -----------------------------------------------------------------------------
# /account-series (single account balance series)
# -----------------------------------------------------------------------------
@router.get("/account-series")
def account_series(account_id: int, start: str, end: str):
    """
    Postgres port of your sqlite /account-series.

    Rules preserved:
      - Use postedDate if present, else purchaseDate.
      - Skip rows with no usable date or non-numeric amount.
      - Roll forward transactions before start, then emit daily values.
      - investment: bal += amount
        else:        bal -= amount
      - credit display value is (-bal)
    """

    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    with with_db_cursor() as (conn, cur):
        # starting balance for this account
        cur.execute(
            f"""
            SELECT COALESCE(SUM(start), 0)::double precision AS s
            FROM startingbalance
            WHERE account_id = %s
              {"AND tenant_id = %s" if tid else ""}
            """,
            ((int(account_id), int(tid)) if tid else (int(account_id),)),
        )
        bal = float((cur.fetchone() or {}).get("s") or 0.0)

        # account type
        cur.execute(
            f"SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s {'AND tenant_id = %s' if tid else ''}",
            ((int(account_id), int(tid)) if tid else (int(account_id),)),
        )
        row = cur.fetchone()
        acc_type = (row["t"] if row else "other") or "other"

        # pull both postedDate and purchaseDate (stored as strings in your schema)
        cur.execute(
            f"""
            SELECT posteddate, purchasedate, amount
            FROM transactions
            WHERE account_id = %s
              {"AND tenant_id = %s" if tid else ""}
            """,
            ((int(account_id), int(tid)) if tid else (int(account_id),)),
        )
        rows = cur.fetchall() or []

    # psycopg2 DictCursor rows support both dict-style and key access; be defensive
    tx: List[Dict[str, Any]] = []
    for r in rows:
        posted_raw = (r.get("postedDate") or r.get("posteddate")) if hasattr(r, "get") else r["posteddate"]
        purchase_raw = (r.get("purchaseDate") or r.get("purchasedate")) if hasattr(r, "get") else r["purchasedate"]

        posted = parse_posted_date(posted_raw)
        purchase = parse_posted_date(purchase_raw)

        tx_date = posted if posted is not None else purchase
        if tx_date is None:
            continue

        amt_raw = r.get("amount") if hasattr(r, "get") else r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            continue

        tx.append({"date": tx_date, "amount": amt})

    tx.sort(key=lambda x: x["date"])

    i = 0

    # A) roll forward transactions BEFORE the start date
    while i < len(tx) and tx[i]["date"] < start_date:
        amt = tx[i]["amount"]
        if acc_type == "investment":
            bal += amt
        else:
            bal -= amt
        i += 1

    # B) day-by-day series
    results = []
    day = start_date
    while day <= end_date:
        while i < len(tx) and tx[i]["date"] == day:
            amt = tx[i]["amount"]
            if acc_type == "investment":
                bal += amt
            else:
                bal -= amt
            i += 1

        display_val = (-bal) if acc_type == "credit" else bal
        results.append({"date": day.isoformat(), "value": float(display_val)})
        day += timedelta(days=1)

    return results

# -----------------------------------------------------------------------------
# /account-transactions-range (Postgres)
# -----------------------------------------------------------------------------
@router.get("/account-transactions-range")
def account_transactions_range(
    account_id: int,
    start: str,
    end: str,
    limit: int = Query(500, ge=1, le=5000),
):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    start_d = parse_iso(start)   # python date
    end_d = parse_iso(end)       # python date

    # For SQL comparisons
    start_date = start_d.isoformat()  # 'YYYY-MM-DD'
    end_date = end_d.isoformat()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'transactions'
              AND lower(column_name) = 'time'
            LIMIT 1
            """
        )
        has_time_col = bool(cur.fetchone())

        # account type
        cur.execute(
            f"SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s {'AND tenant_id = %s' if tid else ''}",
            ((int(account_id), int(tid)) if tid else (int(account_id),)),
        )
        row = cur.fetchone()
        acc_type = (row["t"] if row else "other") or "other"

        # sign rule consistent with your series logic:
        # investment: balance += amount
        # others:     balance -= amount
        sign = 1 if acc_type == "investment" else -1

        # starting balance from table
        cur.execute(
            f"""
            SELECT COALESCE(SUM(start), 0)::double precision AS s
            FROM startingbalance
            WHERE account_id = %s
              {"AND tenant_id = %s" if tid else ""}
            """,
            ((int(account_id), int(tid)) if tid else (int(account_id),)),
        )
        row = cur.fetchone()
        start_bal = float((row["s"] if row else 0.0) or 0.0)

        # roll forward all transactions BEFORE start_date (effective date = posted else purchase)
        cur.execute(
            f"""
            WITH base AS (
              SELECT
                COALESCE(
                  NULLIF(TRIM(postedDate), 'unknown'),
                  NULLIF(TRIM(purchaseDate), 'unknown')
                ) AS raw_date,
                amount::double precision AS amount
              FROM transactions
              WHERE account_id = %s
                {"AND tenant_id = %s" if tid else ""}
            ),
            norm AS (
              SELECT
                amount,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT COALESCE(SUM(amount), 0)::double precision AS s
            FROM norm
            WHERE d IS NOT NULL AND d < %s::date
            """,
            ((int(account_id), int(tid), start_date) if tid else (int(account_id), start_date)),
        )
        row = cur.fetchone()
        before_sum = float((row["s"] if row else 0.0) or 0.0)

        starting_balance_at_range = start_bal + (sign * before_sum)

        # now fetch range tx and compute running balance inside range
        time_raw_sql = "TRIM(COALESCE(\"time\"::text, '')) AS time_raw," if has_time_col else "''::text AS time_raw,"
        tenant_filter_sql = "AND tenant_id = %s" if tid else ""
        cur.execute(
            f"""
            WITH base AS (
              SELECT
                id,
                %s::int AS account_id,
                merchant,
                amount::double precision AS amount,
                COALESCE(is_ignored, false) AS is_ignored,
                TRIM(category) AS category,
                COALESCE(NULLIF(TRIM(status), ''), 'posted') AS status,
                TRIM(postedDate) AS "postedDate_raw",
                TRIM(purchaseDate) AS "purchaseDate_raw",
                {time_raw_sql}
                COALESCE(
                  NULLIF(TRIM(postedDate), 'unknown'),
                  NULLIF(TRIM(purchaseDate), 'unknown')
                ) AS raw_date
              FROM transactions
              WHERE account_id = %s
                {tenant_filter_sql}
            ),
            norm AS (
              SELECT
                id,
                account_id,
                merchant,
                amount,
                is_ignored,
                category,
                status,
                "postedDate_raw",
                "purchaseDate_raw",
                time_raw,
                raw_date,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            ),
            in_range AS (
              SELECT *
              FROM norm
              WHERE d IS NOT NULL
                AND d BETWEEN %s::date AND %s::date
              ORDER BY d ASC, id ASC
              LIMIT %s
            ),
            with_running AS (
              SELECT
                id,
                account_id,
                merchant,
                amount,
                is_ignored,
                category,
                status,
                "postedDate_raw",
                "purchaseDate_raw",
                time_raw,
                raw_date AS "effectiveDate",
                d AS "dateISO",
                SUM(amount) OVER (ORDER BY d, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_sum
              FROM in_range
            )
            SELECT
              id,
              account_id,
              "effectiveDate",
              "dateISO",
              merchant,
              amount,
              is_ignored,
              category,
              status,
              "postedDate_raw" AS "postedDate",
              "purchaseDate_raw" AS "purchaseDate",
              time_raw AS "time",
              (%s::double precision + (%s::double precision * running_sum))::double precision AS balance_after
            FROM with_running
            ORDER BY "dateISO" DESC, id DESC
            """,
            (
                int(account_id),
                int(account_id),
                *(([int(tid)] if tid else [])),
                start_date,
                end_date,
                int(limit),
                float(starting_balance_at_range),
                float(sign),
            ),
        )
        rows = cur.fetchall() or []

        tx = [dict(r) for r in rows]

        # Peer detection: you already have this helper in app_postgres.py.
        # It adds transfer_peer + transfer_peer_id for transfer/card payment rows.
        # (It expects: id, account_id, amount, category, dateISO)
        attach_transfer_peers_pg(tx)

    # direction relative to THIS account (matches your prior behavior)
    transfer_cats = {"transfer", "card payment"}
    for r in tx:
        cat = (r.get("category") or "").strip().lower()
        if cat in transfer_cats:
            try:
                a = float(r.get("amount") or 0.0)
            except Exception:
                a = 0.0
            r["transfer_dir"] = "from" if a < 0 else "to"
    _annotate_roundups(tx, fallback_account_type=acc_type)

    ending_balance = float(tx[0]["balance_after"]) if tx else float(starting_balance_at_range)

    # ---- DISPLAY NORMALIZATION (credit shows positive debt) ----
    if acc_type == "credit":
        starting_balance_at_range = -float(starting_balance_at_range)
        ending_balance = -float(ending_balance)
        for r in tx:
            r["balance_after"] = -float(r["balance_after"])

    return {
        "account_id": int(account_id),
        "start": start_date,
        "end": end_date,
        # Pending rows are displayed in a separate section on the account page.
        # This multiplier keeps pending running-balance math consistent with
        # posted display math (including credit normalization).
        "pending_balance_multiplier": 1 if acc_type in {"investment", "credit"} else -1,
        "starting_balance": float(starting_balance_at_range),
        "ending_balance": float(ending_balance),
        "transactions": tx,
    }
