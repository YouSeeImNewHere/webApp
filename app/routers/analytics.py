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
from app.core.roundups import (
    ROUNDUP_CATEGORY_DEFAULT,
    get_roundup_settings,
    is_roundup_eligible_tx,
    roundup_amount_from_spend,
)
from app.core.transactions_ignore import ensure_transactions_ignore_column
from app.routers.budget_groups import _get_budget_groups_for_month, _norm_cat

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


def _roundup_totals_for_rows(rows: list[dict[str, Any]]) -> tuple[float, int]:
    total = 0.0
    count = 0
    for r in rows:
        amt = float(r.get("amount") or 0.0)
        category = (r.get("category") or "").strip().lower()
        account_type = (r.get("accounttype") or r.get("accountType") or "").strip().lower()
        if is_roundup_eligible_tx(amt, account_type, category):
            ru = roundup_amount_from_spend(amt)
            if ru > 0:
                total += ru
                count += 1
    return round(total, 2), int(count)

# -----------------------------------------------------------------------------
# /net-worth
# -----------------------------------------------------------------------------
@router.get("/net-worth")
def net_worth(start: str, end: str):
    ensure_transactions_ignore_column()
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
    ensure_transactions_ignore_column()
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
    ensure_transactions_ignore_column()
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
    ensure_transactions_ignore_column()
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
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
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
    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
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
            day_total = amt
            if roundup_enabled and is_roundup_eligible_tx(amt, r.get("accounttype"), category):
                day_total += roundup_amount_from_spend(amt)
            daily[d] = daily.get(d, 0.0) + day_total

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
    ensure_transactions_ignore_column()
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
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
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
# /spending-unbudgeted-safe-range
# -----------------------------------------------------------------------------
@router.get("/spending-unbudgeted-safe-range")
def spending_unbudgeted_safe_range(start: str, end: str):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_must_be_on_or_before_end")

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
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
        ),
        norm AS (
          SELECT
            amount, category, accountType,
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

    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_norm = _norm_cat(str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT))

    excluded_by_month: dict[tuple[int, int], set[str]] = {}

    def excluded_for_month(y: int, m: int) -> set[str]:
        key = (int(y), int(m))
        cached = excluded_by_month.get(key)
        if cached is not None:
            return cached
        excluded: set[str] = set(["card payment", "transfer", "cash withdrawal"])
        try:
            groups = _get_budget_groups_for_month(int(y), int(m))
            for g in (groups or []):
                try:
                    alloc = float(g.get("allocated") or 0.0)
                except Exception:
                    alloc = 0.0
                if alloc <= 0:
                    continue
                for c in (g.get("categories") or []):
                    cn = _norm_cat(c)
                    if cn:
                        excluded.add(cn)
        except Exception:
            pass
        excluded_by_month[key] = excluded
        return excluded

    unbudgeted_by_day: dict[date, float] = {}
    for r in rows:
        d = r.get("d")
        if not d:
            continue
        try:
            amt = float(r.get("amount") or 0.0)
        except Exception:
            amt = 0.0
        account_type = (r.get("accounttype") or "").strip().lower()
        category = (r.get("category") or "").strip().lower()
        if account_type not in ("checking", "credit") or amt <= 0:
            continue

        excluded = excluded_for_month(d.year, d.month)
        if category in excluded:
            continue

        unbudgeted_by_day[d] = unbudgeted_by_day.get(d, 0.0) + amt
        if roundup_enabled and is_roundup_eligible_tx(amt, account_type, category):
            ru = roundup_amount_from_spend(amt)
            if ru > 0 and roundup_norm not in excluded:
                unbudgeted_by_day[d] = unbudgeted_by_day.get(d, 0.0) + ru

    try:
        baseline_rows = query_db(
            "SELECT day, baseline FROM daily_limit_snapshot WHERE day BETWEEN %s AND %s AND tenant_id = %s",
            (start_date, end_date, int(tid)),
        )
    except Exception:
        baseline_rows = []
    baseline_by_day = {r["day"]: float(r.get("baseline") or 0.0) for r in baseline_rows if r.get("day")}
    baseline_fallback_by_month: dict[tuple[int, int], float] = {}

    def fallback_baseline(y: int, m: int) -> float:
        key = (int(y), int(m))
        if key in baseline_fallback_by_month:
            return baseline_fallback_by_month[key]
        try:
            from app.routers.category_rules import month_budget_home_cached
            mb = month_budget_home_cached(int(y), int(m))
            val = float((mb or {}).get("daily_limit") or 0.0)
        except Exception:
            val = 0.0
        baseline_fallback_by_month[key] = val
        return val

    series: list[dict[str, float | str]] = []
    dcur = start_date
    while dcur <= end_date:
        safe = baseline_by_day.get(dcur)
        if safe is None:
            safe = fallback_baseline(dcur.year, dcur.month)
        series.append(
            {
                "date": dcur.isoformat(),
                "unbudgeted_spend": round(float(unbudgeted_by_day.get(dcur, 0.0) or 0.0), 2),
                "daily_safe_to_spend": round(float(safe or 0.0), 2),
            }
        )
        dcur += timedelta(days=1)

    return {"start": start_date.isoformat(), "end": end_date.isoformat(), "series": series}


# -----------------------------------------------------------------------------
# /spending-unbudgeted-day
# -----------------------------------------------------------------------------
@router.get("/spending-unbudgeted-day")
def spending_unbudgeted_day(day: str):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    d = parse_iso(day)

    def excluded_for_month(y: int, m: int) -> set[str]:
        excluded: set[str] = set(["card payment", "transfer", "cash withdrawal"])
        try:
            groups = _get_budget_groups_for_month(int(y), int(m))
            for g in (groups or []):
                try:
                    alloc = float(g.get("allocated") or 0.0)
                except Exception:
                    alloc = 0.0
                if alloc <= 0:
                    continue
                for c in (g.get("categories") or []):
                    cn = _norm_cat(c)
                    if cn:
                        excluded.add(cn)
        except Exception:
            pass
        return excluded

    excluded = excluded_for_month(d.year, d.month)
    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            TRIM(COALESCE(t.category,'')) AS category_raw,
            LOWER(TRIM(COALESCE(t.category,''))) AS category_lc,
            TRIM(COALESCE(t.merchant,'')) AS merchant,
            LOWER(a.accountType) AS accountType,
            COALESCE(a.institution, '') AS bank,
            COALESCE(a.name, '') AS account
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
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
        SELECT id, d, amount, category_raw, category_lc, merchant, accountType, bank, account
        FROM norm
        WHERE d = %s
        ORDER BY id DESC
        """,
        ((int(tid), int(tid), d) if tid else (d,)),
    )

    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT).strip() or ROUNDUP_CATEGORY_DEFAULT
    roundup_norm = _norm_cat(roundup_cat)

    purchases: list[dict[str, Any]] = []
    unbudgeted_total = 0.0
    for r in rows:
        try:
            amt = float(r.get("amount") or 0.0)
        except Exception:
            amt = 0.0
        category_lc = (r.get("category_lc") or "").strip().lower()
        account_type = (r.get("accounttype") or "").strip().lower()
        if account_type not in ("checking", "credit") or amt <= 0:
            continue
        if category_lc in excluded:
            continue

        category_disp = (r.get("category_raw") or "").strip() or "Unassigned"
        merchant_disp = (r.get("merchant") or "").strip() or "(no merchant)"
        purchases.append(
            {
                "id": str(r.get("id") or ""),
                "kind": "purchase",
                "merchant": merchant_disp,
                "category": category_disp,
                "amount": round(amt, 2),
                "bank": str(r.get("bank") or ""),
                "account": str(r.get("account") or ""),
            }
        )
        unbudgeted_total += amt

        if roundup_enabled and roundup_norm not in excluded and is_roundup_eligible_tx(amt, account_type, category_lc):
            ru = roundup_amount_from_spend(amt)
            if ru > 0:
                purchases.append(
                    {
                        "id": f"{r.get('id')}_roundup",
                        "kind": "roundup",
                        "merchant": f"Round-up • {merchant_disp}",
                        "category": roundup_cat,
                        "amount": round(float(ru), 2),
                        "bank": str(r.get("bank") or ""),
                        "account": str(r.get("account") or ""),
                    }
                )
                unbudgeted_total += ru

    try:
        baseline_rows = query_db(
            "SELECT baseline FROM daily_limit_snapshot WHERE day = %s AND tenant_id = %s LIMIT 1",
            (d, int(tid)),
        )
    except Exception:
        baseline_rows = []
    if baseline_rows:
        daily_safe = float(baseline_rows[0].get("baseline") or 0.0)
    else:
        try:
            from app.routers.category_rules import month_budget_home_cached
            mb = month_budget_home_cached(int(d.year), int(d.month))
            daily_safe = float((mb or {}).get("daily_limit") or 0.0)
        except Exception:
            daily_safe = 0.0

    return {
        "day": d.isoformat(),
        "totals": {
            "unbudgeted_spend": round(float(unbudgeted_total), 2),
            "daily_safe_to_spend": round(float(daily_safe), 2),
        },
        "purchases": purchases,
    }

# -----------------------------------------------------------------------------
# /category-totals-month
# -----------------------------------------------------------------------------
@router.get("/category-totals-month")
def category_totals_month():
    ensure_transactions_ignore_column()
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
          AND COALESCE(t.is_ignored, false) = false
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
            AND COALESCE(t.is_ignored, false) = false
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
    budgeted_norm: set[str] = set()
    try:
        groups = _get_budget_groups_for_month(int(first.year), int(first.month))
        for g in (groups or []):
            try:
                alloc = float(g.get("allocated") or 0.0)
            except Exception:
                alloc = 0.0
            if alloc <= 0:
                continue
            for c in (g.get("categories") or []):
                cn = _norm_cat(c)
                if cn:
                    budgeted_norm.add(cn)
    except Exception:
        budgeted_norm = set()

    out_categories = [
        {"category": r["category"], "total": float(r["total"] or 0), "tx_count": int(r["tx_count"] or 0)}
        for r in rows
        if _norm_cat(r.get("category")) not in budgeted_norm
    ]

    roundup_cfg = get_roundup_settings()
    if bool(roundup_cfg.get("enabled", False)):
        ru_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT)
        spend_rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                LOWER(a.accountType) AS accountType,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
            ),
            norm AS (
              SELECT
                amount,
                category,
                accountType,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT amount, category, accountType
            FROM norm
            WHERE d IS NOT NULL AND d >= %s AND d < %s
            """,
            ((int(tid), int(tid), first, next_month) if tid else (first, next_month)),
        )
        ru_total, ru_count = _roundup_totals_for_rows([dict(r) for r in spend_rows])
        if ru_total > 0:
            if _norm_cat(ru_cat) not in budgeted_norm:
                out_categories.append({"category": ru_cat, "total": ru_total, "tx_count": ru_count})

    out_categories.sort(key=lambda x: float(x.get("total") or 0.0), reverse=True)
    return {
        "unassigned_all_time": int(unassigned or 0),
        "categories": out_categories,
    }

# -----------------------------------------------------------------------------
# /category-trend
# -----------------------------------------------------------------------------
@router.get("/category-trend")
def category_trend(category: str, period: str = "1m"):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    cat = (category or "").strip().lower()
    roundup_cfg = get_roundup_settings()
    roundup_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT)
    roundup_enabled = bool(roundup_cfg.get("enabled", False))

    if roundup_enabled and cat == roundup_cat.strip().lower():
        rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                LOWER(a.accountType) AS accountType,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
            ),
            norm AS (
              SELECT
                amount,
                category,
                accountType,
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
            ORDER BY d ASC
            """,
            ((int(tid), int(tid)) if tid else ()),
        )
        by_day: dict[date, float] = {}
        for r in rows:
            amt = float(r.get("amount") or 0.0)
            category_lc = (r.get("category") or "").strip().lower()
            account_type = (r.get("accounttype") or "").strip().lower()
            if not is_roundup_eligible_tx(amt, account_type, category_lc):
                continue
            ru = roundup_amount_from_spend(amt)
            if ru <= 0:
                continue
            d = r.get("d")
            if d:
                by_day[d] = by_day.get(d, 0.0) + ru
        daily = [{"date": d.isoformat(), "amount": round(v, 2)} for d, v in sorted(by_day.items(), key=lambda x: x[0])]
        return {"category": roundup_cat, "period": period, "series": daily}

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
                AND COALESCE(t.is_ignored, false) = false
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
                AND COALESCE(t.is_ignored, false) = false
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
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)
    cat_norm = (category or "").strip().lower()
    roundup_cfg = get_roundup_settings()
    roundup_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT)
    roundup_enabled = bool(roundup_cfg.get("enabled", False))

    if roundup_enabled and cat_norm == roundup_cat.strip().lower():
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
              {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
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
            SELECT
              id,
              postedDate,
              merchant,
              amount,
              category,
              category_lc,
              bank,
              card,
              accountType,
              d AS "dateISO",
              postedDate_raw,
              purchaseDate_raw
            FROM norm
            WHERE d IS NOT NULL
              AND d BETWEEN %s AND %s
            ORDER BY d DESC, id DESC
            LIMIT %s
            """,
            ((int(tid), int(tid), start_date, end_date, int(limit)) if tid else (start_date, end_date, int(limit))),
        )

        out = []
        for r in rows:
            rr = dict(r)
            amt = float(rr.get("amount") or 0.0)
            category_lc = (rr.get("category_lc") or "").strip().lower()
            account_type = (rr.get("accounttype") or "").strip().lower()
            if not is_roundup_eligible_tx(amt, account_type, category_lc):
                continue
            ru = roundup_amount_from_spend(amt)
            if ru <= 0:
                continue
            rr["amount"] = round(ru, 2)
            rr["category"] = roundup_cat
            rr["roundup_cents"] = int(round(ru * 100))
            rr["roundup_amount"] = round(ru, 2)
            out.append(rr)
        return out

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
                AND COALESCE(t.is_ignored, false) = false
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
        out = [dict(r) for r in rows]
        roundup_cfg = get_roundup_settings()
        roundup_enabled = bool(roundup_cfg.get("enabled", False))
        for rr in out:
            amt = float(rr.get("amount") or 0.0)
            category_lc = (rr.get("category") or "").strip().lower()
            account_type = (rr.get("accounttype") or "").strip().lower()
            if roundup_enabled and is_roundup_eligible_tx(amt, account_type, category_lc):
                ru = roundup_amount_from_spend(amt)
                rr["roundup_amount"] = round(ru, 2)
                rr["roundup_cents"] = int(round(ru * 100))
            else:
                rr["roundup_amount"] = 0.0
                rr["roundup_cents"] = 0
        return out

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
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          WHERE TRIM(t.category) = TRIM(%s)
            {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
            AND COALESCE(t.is_ignored, false) = false
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
          accountType,
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
    out = [dict(r) for r in rows]
    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    for rr in out:
        amt = float(rr.get("amount") or 0.0)
        category_lc = (rr.get("category") or "").strip().lower()
        account_type = (rr.get("accounttype") or "").strip().lower()
        if roundup_enabled and is_roundup_eligible_tx(amt, account_type, category_lc):
            ru = roundup_amount_from_spend(amt)
            rr["roundup_amount"] = round(ru, 2)
            rr["roundup_cents"] = int(round(ru * 100))
        else:
            rr["roundup_amount"] = 0.0
            rr["roundup_cents"] = 0
    return out

# -----------------------------------------------------------------------------
# /category-totals-lifetime
# -----------------------------------------------------------------------------
@router.get("/category-totals-lifetime")
def category_totals_lifetime():
    ensure_transactions_ignore_column()
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
          AND COALESCE(is_ignored, false) = false
          {"AND tenant_id = %s" if tid else ""}
        GROUP BY TRIM(category)
        ORDER BY total DESC
        """,
        ((int(tid),) if tid else ()),
    )
    out = [{"category": r["category"], "total": float(r["total"] or 0)} for r in rows]

    roundup_cfg = get_roundup_settings()
    if bool(roundup_cfg.get("enabled", False)):
        ru_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT)
        spend_rows = query_db(
            f"""
            SELECT
              t.amount::double precision AS amount,
              LOWER(TRIM(COALESCE(t.category,''))) AS category,
              LOWER(a.accountType) AS accountType
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
            """,
            ((int(tid), int(tid)) if tid else ()),
        )
        ru_total, _ = _roundup_totals_for_rows([dict(r) for r in spend_rows])
        if ru_total > 0:
            out.append({"category": ru_cat, "total": ru_total})

    out.sort(key=lambda x: float(x.get("total") or 0.0), reverse=True)
    return out

# -----------------------------------------------------------------------------
# /category-totals-range
# -----------------------------------------------------------------------------
@router.get("/category-totals-range")
def category_totals_range(start: str, end: str):
    ensure_transactions_ignore_column()
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
            AND COALESCE(t.is_ignored, false) = false
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
    out = [{"category": r["category"], "total": float(r["total"] or 0)} for r in rows]

    roundup_cfg = get_roundup_settings()
    if bool(roundup_cfg.get("enabled", False)):
        ru_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT)
        spend_rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                LOWER(a.accountType) AS accountType,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
            ),
            norm AS (
              SELECT
                amount,
                category,
                accountType,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT amount, category, accountType
            FROM norm
            WHERE d IS NOT NULL AND d BETWEEN %s AND %s
            """,
            ((int(tid), int(tid), start_date, end_date) if tid else (start_date, end_date)),
        )
        ru_total, _ = _roundup_totals_for_rows([dict(r) for r in spend_rows])
        if ru_total > 0:
            out.append({"category": ru_cat, "total": ru_total})

    out.sort(key=lambda x: float(x.get("total") or 0.0), reverse=True)
    return out
def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)
