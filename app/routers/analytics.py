from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.time import today_local
from app.core.analytics_helpers import (
    load_starting_balances_pg,
    load_transactions_pg,
    load_account_type_map_pg,
    apply_transaction,
    build_series,
)
from app.core.date_parse import parse_iso, parse_posted_date

from db import with_db_cursor, query_db
from app.core.config import ISO_DATE_RE, MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id

router = APIRouter()

# =============================================================================
# Analytics endpoints (Postgres) — ported from analytics.py
# =============================================================================

# --- Date helpers (safe, small, self-contained) ---
def parse_iso(s: str) -> date:
    # expects "YYYY-MM-DD"
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Bad ISO date: {s!r}")

def parse_posted_date(raw: Optional[object]) -> Optional[date]:
    if raw is None:
        return None

    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()

    x = str(raw).strip()
    if not x or x.lower() == "unknown":
        return None

    # ISO: YYYY-MM-DD
    if ISO_DATE_RE.match(x):
        try:
            return datetime.fromisoformat(x).date()
        except Exception:
            return None

    try:
        if len(x) == 8:
            return datetime.strptime(x, "%m/%d/%y").date()
        if len(x) == 10:
            return datetime.strptime(x, "%m/%d/%Y").date()
    except Exception:
        return None

    return None

def _last_day_of_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]

# -----------------------------------------------------------------------------
# /net-worth
# -----------------------------------------------------------------------------
@router.get("/net-worth")
def net_worth(start: str, end: str):
    _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances_pg()
    transactions = load_transactions_pg()
    acct_types = load_account_type_map_pg()

    current_totals = dict(starting)
    results = []
    tx_index = 0

    # A) roll forward before start_date
    while tx_index < len(transactions) and transactions[tx_index]["date"] < start_date:
        t = transactions[tx_index]
        apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
        tx_index += 1

    # B) day-by-day
    day = start_date
    while day <= end_date:
        while tx_index < len(transactions) and transactions[tx_index]["date"] == day:
            t = transactions[tx_index]
            apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
            tx_index += 1

        banks = 0.0
        savings_total = 0.0
        cards_balance = 0.0  # signed: negative = owe, positive = surplus

        for aid, bal in current_totals.items():
            t = (acct_types.get(aid) or "other").lower()
            if t == "savings":
                savings_total += bal
            elif t == "credit":
                cards_balance += bal
            else:
                banks += bal

        cards_owed = max(0.0, -cards_balance)
        net = banks + savings_total + cards_balance

        results.append(
            {
                "date": day.isoformat(),
                "value": float(net),
                "banks": float(banks),
                "savings": float(savings_total),
                "cards": float(cards_owed),
                "cards_balance": float(cards_balance),
            }
        )

        day += timedelta(days=1)

    return results

# -----------------------------------------------------------------------------
# /savings
# -----------------------------------------------------------------------------
@router.get("/savings")
def savings(start: str, end: str):
    _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances_pg()
    transactions = load_transactions_pg()
    acct_types = load_account_type_map_pg()

    def savings_only(totals: Dict[int, float]) -> float:
        return sum(bal for aid, bal in totals.items() if (acct_types.get(aid) or "").lower() == "savings")

    return build_series(start_date, end_date, starting, transactions, value_fn=savings_only)

# -----------------------------------------------------------------------------
# /investments
# -----------------------------------------------------------------------------
@router.get("/investments")
def investments(start: str, end: str):
    _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances_pg()
    transactions = load_transactions_pg()
    acct_types = load_account_type_map_pg()

    def investments_only(totals: Dict[int, float]) -> float:
        return sum(bal for aid, bal in totals.items() if (acct_types.get(aid) or "").lower() == "investment")

    return build_series(start_date, end_date, starting, transactions, value_fn=investments_only)

# -----------------------------------------------------------------------------
# /spending
# -----------------------------------------------------------------------------
@router.get("/spending")
def spending(start: str, end: str):
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT d, amount, category, accountType
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        """,
        ((int(tid), int(tid), start_date, end_date) if tid else (start_date, end_date)),
    )

    daily: Dict[date, float] = {}
    for r in rows:
        d = r["d"]
        if not d:
            continue
        try:
            amt = float(r["amount"])
        except Exception:
            continue

        category = (r["category"] or "").strip().lower()

        # exclusions
        if category in ("card payment", "transfer"):
            continue

        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            daily[d] = daily.get(d, 0.0) + amt

    results = []
    day = start_date
    while day <= end_date:
        results.append({"date": day.isoformat(), "value": float(daily.get(day, 0.0))})
        day += timedelta(days=1)

    return results

# -----------------------------------------------------------------------------
# /spending-debug
# -----------------------------------------------------------------------------
@router.get("/spending-debug")
def spending_debug(start: str, end: str):
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            t.merchant,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType,
            a.institution AS bank,
            a.name AS account
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT id, d, amount, merchant, category, accountType, bank, account
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        ORDER BY d DESC, id DESC
        """,
        ((int(tid), int(tid), start_date, end_date) if tid else (start_date, end_date)),
    )

    out = []
    for r in rows:
        try:
            amt = float(r["amount"])
        except Exception:
            continue

        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer"):
            continue

        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            out.append(
                {
                    "date": r["d"].isoformat(),
                    "amount": amt,
                    "merchant": r["merchant"],
                    "category": r["category"],
                    "bank": r["bank"],
                    "account": r["account"],
                }
            )

    return out

# -----------------------------------------------------------------------------
# /category-totals-month
# -----------------------------------------------------------------------------
@router.get("/category-totals-month")
def category_totals_month():
    tid = _require_tenant_id()
    today = today_local()
    first = today.replace(day=1)
    next_month = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)

    # Keep this count aligned with /unassigned so the badge and modal agree.
    unassigned = query_db(
        f"""
        SELECT COUNT(*)::int AS c
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE (t.category IS NULL OR TRIM(t.category) = '')
          AND t.merchant IS NOT NULL
          AND TRIM(t.merchant) <> ''
          AND LOWER(TRIM(t.merchant)) <> 'unknown'
          {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        """,
        ((int(tid), int(tid)) if tid else ()),
    )[0]["c"]

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            TRIM(category) AS category,
            t.amount::double precision AS amount,
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE t.amount::double precision > 0
            AND t.category IS NOT NULL
            AND TRIM(t.category) <> ''
            {"AND t.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            category,
            amount,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT category, SUM(amount) AS total, COUNT(*)::int AS tx_count
        FROM norm
        WHERE d IS NOT NULL AND d >= %s AND d < %s
        GROUP BY category
        ORDER BY total DESC
        """,
        ((int(tid), first, next_month) if tid else (first, next_month)),
    )

    return {
        "unassigned_all_time": int(unassigned or 0),
        "categories": [
            {"category": r["category"], "total": float(r["total"] or 0), "tx_count": int(r["tx_count"] or 0)}
            for r in rows
        ],
    }

# -----------------------------------------------------------------------------
# /category-trend
# -----------------------------------------------------------------------------
@router.get("/category-trend")
def category_trend(category: str, period: str = "1m"):
    tid = _require_tenant_id()
    cat = (category or "").strip().lower()

    if cat in ("unknown merchant", "unknown merchants"):
        rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.merchant,''))) AS merchant,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                LOWER(a.accountType) AS accountType,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE t.amount::double precision > 0
                AND LOWER(a.accountType) IN ('checking','credit')
                {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
            ),
            norm AS (
              SELECT
                amount,
                merchant,
                category,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT d, SUM(amount) AS total
            FROM norm
            WHERE d IS NOT NULL
              AND merchant = 'unknown'
              AND category NOT IN ('card payment','transfer')
            GROUP BY d
            ORDER BY d ASC
            """,
            ((int(tid), int(tid)) if tid else ()),
        )
    else:
        rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              WHERE LOWER(TRIM(COALESCE(t.category,''))) = LOWER(TRIM(%s))
                {"AND t.tenant_id = %s" if tid else ""}
            ),
            norm AS (
              SELECT
                amount,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT d, SUM(amount) AS total
            FROM norm
            WHERE d IS NOT NULL
            GROUP BY d
            ORDER BY d ASC
            """,
            ((category, int(tid)) if tid else (category,)),
        )

    daily = [{"date": r["d"].isoformat(), "amount": float(r["total"] or 0)} for r in rows if r.get("d")]
    return {"category": category, "period": period, "series": daily}

# -----------------------------------------------------------------------------
# /category-transactions
# -----------------------------------------------------------------------------
@router.get("/category-transactions")
def category_transactions(category: str, start: str, end: str, limit: int = 500):
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)
    cat_norm = (category or "").strip().lower()

    if cat_norm in ("unknown merchant", "unknown merchants"):
        rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.id,
                t.postedDate AS postedDate_raw,
                t.purchaseDate AS purchaseDate_raw,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS postedDate,
                t.merchant,
                t.amount::double precision AS amount,
                TRIM(t.category) AS category,
                LOWER(TRIM(COALESCE(t.category,''))) AS category_lc,
                a.institution AS bank,
                a.name AS card,
                LOWER(a.accountType) AS accountType,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE LOWER(TRIM(COALESCE(t.merchant,''))) = 'unknown'
                {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
            ),
            norm AS (
              SELECT
                *,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT DISTINCT
              id,
              postedDate,
              merchant,
              amount,
              category,
              bank,
              card,
              d AS "dateISO",
              postedDate_raw,
              purchaseDate_raw
            FROM norm
            WHERE d IS NOT NULL
              AND d BETWEEN %s AND %s
              AND amount > 0
              AND accountType IN ('checking','credit')
              AND category_lc NOT IN ('card payment','transfer')
            ORDER BY d DESC, id DESC
            LIMIT %s
            """,
            ((int(tid), int(tid), start_date, end_date, int(limit)) if tid else (start_date, end_date, int(limit))),
        )
        return [dict(r) for r in rows]

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            t.postedDate AS postedDate_raw,
            t.purchaseDate AS purchaseDate_raw,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS postedDate,
            t.merchant,
            t.amount::double precision AS amount,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          WHERE TRIM(t.category) = TRIM(%s)
            {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT DISTINCT
          id,
          postedDate,
          merchant,
          amount,
          category,
          bank,
          card,
          d AS "dateISO",
          postedDate_raw,
          purchaseDate_raw
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        ORDER BY d DESC, id DESC
        LIMIT %s
        """,
        ((category, int(tid), int(tid), start_date, end_date, int(limit)) if tid else (category, start_date, end_date, int(limit))),
    )
    return [dict(r) for r in rows]

# -----------------------------------------------------------------------------
# /category-totals-lifetime
# -----------------------------------------------------------------------------
@router.get("/category-totals-lifetime")
def category_totals_lifetime():
    tid = _require_tenant_id()
    rows = query_db(
        f"""
        SELECT
          TRIM(category) AS category,
          SUM(amount::double precision) AS total
        FROM transactions
        WHERE category IS NOT NULL
          AND TRIM(category) <> ''
          AND amount::double precision > 0
          {"AND tenant_id = %s" if tid else ""}
        GROUP BY TRIM(category)
        ORDER BY total DESC
        """,
        ((int(tid),) if tid else ()),
    )
    return [{"category": r["category"], "total": float(r["total"] or 0)} for r in rows]

# -----------------------------------------------------------------------------
# /category-totals-range
# -----------------------------------------------------------------------------
@router.get("/category-totals-range")
def category_totals_range(start: str, end: str):
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            TRIM(t.category) AS category,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS cat_lc,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE t.amount::double precision > 0
            AND t.category IS NOT NULL
            AND TRIM(t.category) <> ''
            AND LOWER(TRIM(t.category)) NOT IN ('card payment','transfer')
            {"AND t.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            category,
            amount,
            cat_lc,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT category, SUM(amount) AS total
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN %s AND %s
        GROUP BY category
        ORDER BY total DESC
        """,
        ((int(tid), start_date, end_date) if tid else (start_date, end_date)),
    )

    return [{"category": r["category"], "total": float(r["total"] or 0)} for r in rows]
def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)
