from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import with_db_cursor, query_db

from app.core.config import WIDGET_SECRET, CREDIT_UTILIZATION_CAP
from app.core.time import today_local, now_local

# Import the underlying route helpers we bundle into page payloads.
from app.routers.transactions import transactions, transactions_all, account_transactions
from app.routers.analytics import category_totals_month, _last_day_of_month, parse_iso
from app.routers.notifications import unread_count
from app.routers.accounts import bank_totals, account_info
from app.routers.category_rules import _month_budget_home
from app.routers.budget_groups import _get_budget_groups_for_month, _norm_cat, _norm_name

router = APIRouter()

# =============================================================================
# Page payload endpoints (one request per page)
# =============================================================================

def _call_optional(fn, *args, **kwargs):
    """
    Call fn if it exists, otherwise return None.
    Lets you add bundles without hard-breaking if a feature isn't present.
    """
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None

@router.get("/page/home")
def page_home(
    tx_limit: int = Query(15, ge=1, le=200),
):
    """
    One-shot payload for home.html/home.js
    Bundle the things home currently fetches separately.
    """
    payload: Dict[str, Any] = {
        "transactions": transactions(limit=tx_limit),
        "category_totals_month": category_totals_month(),
        "notifications_unread": unread_count(),
        "bank_totals": bank_totals(),
        # add this if you have month_budget() defined in this file:
        "month_budget": _call_optional(globals().get("month_budget")),
    }
    return payload

@router.get("/page/account/{account_id}")
def page_account(
    account_id: int,
    tx_limit: int = Query(200, ge=1, le=2000),
):
    """
    One-shot payload for account.html/account.js
    """
    payload: Dict[str, Any] = {
        "account": account_info(account_id=account_id),                        # existing route fn【turn10file2†app_postgres.py†L1-L12】
        "transactions": account_transactions(account_id=account_id, limit=tx_limit),  # existing route fn【turn10file0†app_postgres.py†L54-L99】
        # Add any account charts/series endpoints your account.js calls:
        # "account_series": account_series(account_id=account_id, start=..., end=...),
    }
    return payload

@router.get("/page/all-transactions")
def page_all_transactions(
    limit: int = Query(2000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
):
    """
    One-shot payload for all-transactions.html/all-transactions.js
    Uses your existing 'transactions-all' endpoint function.
    """
    # transactions_all() exists right after transactions() in your file【turn10file0†app_postgres.py†L100-L103】
    payload: Dict[str, Any] = {
        "rows": transactions_all(limit=limit, offset=offset),
        "notifications_unread": unread_count(),
    }
    return payload

@router.get("/page/category")
def page_category(
    c: str,
    # add date window params here if your category page needs them
):
    """
    One-shot payload for category.html/category.js
    Fill in with the existing category endpoints your category.js currently calls.
    """
    # These function names are placeholders — wire to whatever your app_postgres.py already has.
    # Example:
    #   category_trend(c=...)
    #   category_transactions(c=..., limit=..., offset=...)
    payload: Dict[str, Any] = {
        "category": c,
        # "trend": category_trend(c=c),
        # "transactions": category_transactions(c=c, limit=500, offset=0),
        "notifications_unread": unread_count(),
    }
    return payload

@router.get("/page/recurring")
def page_recurring():
    """
    One-shot payload for recurring.html/recurring_page.js
    Bundle whatever recurring_page.js fetches.
    """
    payload: Dict[str, Any] = {
        # If you have endpoints like get_recurring() / calendar preview, add them:
        # "recurring": get_recurring_endpoint(...),
        # "ignored_preview": get_ignored_merchants_preview(...),
        "notifications_unread": unread_count(),
    }
    return payload

# -----------------------------------------------------------------------------
# /unassigned  (Postgres)
# -----------------------------------------------------------------------------
@router.get("/unassigned")
def get_unassigned(limit: int = 25, mode: str = "freq"):
    """
    mode:
      - "freq"   => most frequent unassigned merchants
      - "recent" => most recent unassigned transactions
    """
    limit = max(1, min(int(limit or 25), 500))
    mode = (mode or "freq").strip().lower()

    # shared normalization: postedDate/purchaseDate are strings like MM/DD/YY or MM/DD/YYYY (or 'unknown')
    base_cte = """
      WITH base AS (
        SELECT
          t.id,
          COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
          TRIM(t.merchant) AS merchant,
          t.amount::double precision AS amount,
          a.institution AS bank,
          a.name        AS card
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE (t.category IS NULL OR TRIM(t.category) = '')
          AND t.merchant IS NOT NULL
          AND TRIM(t.merchant) <> ''
          AND LOWER(TRIM(t.merchant)) <> 'unknown'
      ),
      norm AS (
        SELECT
          *,
          CASE
            WHEN raw_date IS NULL THEN NULL
            WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
            WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
            ELSE NULL
          END AS d
        FROM base
      )
    """

    if mode == "recent":
        rows = query_db(
            base_cte
            + """
            SELECT
              id,
              raw_date AS "postedDate",
              merchant,
              amount,
              bank,
              card
            FROM norm
            ORDER BY d DESC NULLS LAST, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in rows]

    # default: freq
    rows = query_db(
        base_cte
        + """
        SELECT
          id,
          raw_date AS "postedDate",
          merchant,
          amount,
          bank,
          card,
          COUNT(*) OVER (PARTITION BY merchant) AS usage_count
        FROM norm
        ORDER BY usage_count DESC, d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in rows]

@router.get("/widget/summary")
def widget_summary(x_widget_secret: str = Header(default="")):
    #Simple protection so the widget can fetch data without a login session/cookies
    if WIDGET_SECRET and x_widget_secret != WIDGET_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    bt = bank_totals()     # uses your existing logic :contentReference[oaicite:3]{index=3}
    n = now_local()
    mb = _month_budget_home(n.year, n.month)
    dl = day_limit(recalc=0)
    credit_accounts = ((bt.get("credit") or {}).get("accounts") or [])

    limit_sum = 0.0
    used_sum = 0.0

    for a in credit_accounts:
        lim = float(a.get("credit_limit") or 0)
        if lim > 0:
            limit_sum += lim

        bal = float(a.get("total") or 0)
        used_sum += max(0.0, -bal)  # only debt counts

    cap_limit = limit_sum * CREDIT_UTILIZATION_CAP
    available = max(0.0, cap_limit - used_sum)
    pct_used = int(round((used_sum / cap_limit) * 100)) if cap_limit > 0 else 0

    return {
        "ok": True,

        "credit": {
            "used": round(used_sum, 2),
            "cap": round(cap_limit, 2),
            "pct": pct_used,
            "available": round(available, 2),
            "limit_sum": round(limit_sum, 2),
        },

        # existing (keep)
        "safe_to_spend": mb["safe_to_spend"],
        "month": mb,

        # ✅ NEW: same as Home "$/day"
        "cost_per_day": dl.get("baseline", 0.0),
        "days_left": mb.get("days_left", 0),
        "as_of": mb.get("as_of"),
        "totals": {
            "checking": round(float((bt.get("checking") or {}).get("total") or 0), 2),
            "savings": round(float((bt.get("savings") or {}).get("total") or 0), 2),
        },
        "today": {
            "baseline": dl.get("baseline", 0.0),
            "remaining_today": dl.get("remaining_today", 0.0),
            "spent_today_free": dl.get("spent_today_free", 0.0),
            "day": dl.get("day"),
        },
        "meta": {"cron": "OK"}
    }

def _ensure_budget_tables_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS budget_category_month (
          year INT NOT NULL,
          month INT NOT NULL,
          category TEXT NOT NULL,
          allocated DOUBLE PRECISION NOT NULL DEFAULT 0,
          cap DOUBLE PRECISION NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (year, month, category)
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_budget_category_month_ym ON budget_category_month(year, month)")
        conn.commit()

class BudgetCatUpsert(BaseModel):
    year: int
    month: int
    category: str
    allocated: float = 0.0
    cap: float | None = None

@router.get("/budget/categories")
def budget_categories(year: int, month: int):
    _ensure_budget_tables_pg()
    rows = query_db(
        """
        SELECT category, allocated, cap, updated_at
        FROM budget_category_month
        WHERE year=%s AND month=%s
        ORDER BY LOWER(category)
        """,
        (int(year), int(month)),
    )
    return {"items": rows}

@router.post("/budget/categories")
def upsert_budget_category(b: BudgetCatUpsert):
    _ensure_budget_tables_pg()
    cat = (b.category or "").strip()
    if not cat:
        raise HTTPException(status_code=400, detail="category required")

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO budget_category_month(year, month, category, allocated, cap)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (year, month, category)
            DO UPDATE SET allocated=EXCLUDED.allocated, cap=EXCLUDED.cap, updated_at=now()
            """,
            (int(b.year), int(b.month), cat, float(b.allocated or 0.0), (None if b.cap is None else float(b.cap))),
        )
        conn.commit()
    return {"ok": True}

@router.delete("/budget/categories")
def delete_budget_category(year: int, month: int, category: str):
    _ensure_budget_tables_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM budget_category_month WHERE year=%s AND month=%s AND category=%s",
            (int(year), int(month), (category or "").strip()),
        )
        conn.commit()
    return {"ok": True}

@router.get("/budget")
def budget_page():
    return FileResponse("static/pages/budget/budget.html")

class BudgetGroupUpsert(BaseModel):
    year: int
    month: int
    name: str
    allocated: float = 0.0
    cap: float | None = None
    categories: list[str] = []

def _ensure_budget_group_tables_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS budget_group_month (
          id BIGSERIAL PRIMARY KEY,
          year INT NOT NULL,
          month INT NOT NULL,
          name TEXT NOT NULL,
          allocated DOUBLE PRECISION NOT NULL DEFAULT 0,
          cap DOUBLE PRECISION NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(year, month, name)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS budget_group_member (
          group_id BIGINT NOT NULL REFERENCES budget_group_month(id) ON DELETE CASCADE,
          category TEXT NOT NULL,
          PRIMARY KEY (group_id, category)
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_budget_group_month_ym ON budget_group_month(year, month)")
        conn.commit()

@router.get("/category")
def category_page():
    """Category detail page (reads category from ?c=...)."""
    return FileResponse("static/category.html")

def _category_totals_month_display(year: int, month: int):
    # month range
    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    base_cte = """
      WITH base AS (
        SELECT
          COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
          TRIM(t.category) AS category,
          t.amount::double precision AS amount
        FROM transactions t
        WHERE t.category IS NOT NULL
          AND TRIM(t.category) <> ''
      ),
      norm AS (
        SELECT
          *,
          CASE
            WHEN raw_date IS NULL THEN NULL
            WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
            WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
            ELSE NULL
          END AS d
        FROM base
      )
    """

    rows = query_db(
        base_cte + """
        SELECT
          category,
          COALESCE(SUM(amount),0)::double precision AS total
        FROM norm
        WHERE d IS NOT NULL
          AND d >= %s AND d <= %s
          AND amount > 0
          AND LOWER(category) NOT IN ('transfer','card payment')
        GROUP BY category
        ORDER BY total DESC
        """,
        (month_start, month_end),
    )
    return [{"category": r["category"], "spent": float(r["total"] or 0.0)} for r in rows]

def _ensure_daily_limit_snapshot_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_limit_snapshot (
          day DATE PRIMARY KEY,
          baseline DOUBLE PRECISION NOT NULL,
          computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """)
        conn.commit()

def _compute_spent_free_for_day(day: date) -> tuple[float, float, float]:
    """
    Returns (spent_today_total, spent_today_budgeted, spent_today_free)
    using the same rules as _month_budget_home:
      - exclude category in ('card payment','transfer')
      - only count amt > 0 for checking/credit
      - budgeted = categories inside budget groups for this month
      - free = total - budgeted
    """
    year = day.year
    month = day.month

    # Pull tx rows for *that day*
    tx_rows = query_db(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
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
        WHERE d = %s
        """,
        (day,),
    )

    spent_today = 0.0
    cat_spent: dict[str, float] = {}

    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        # Exclusions from DAILY spend (still count in monthly math elsewhere)
        if category in ("card payment", "transfer", "cash withdrawal"):
            continue

        amt = float(r["amount"] or 0.0)
        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            spent_today += amt
            if category:
                cat_spent[category] = cat_spent.get(category, 0.0) + amt

    # Budgeted categories for this month
    groups = _get_budget_groups_for_month(year, month)
    budgeted_cats = set()
    for g in (groups or []):
        for c in (g.get("categories") or []):
            budgeted_cats.add(_norm_cat(c))

    spent_budgeted = 0.0
    for cn, amt in cat_spent.items():
        if _norm_cat(cn) in budgeted_cats:
            spent_budgeted += float(amt)

    spent_free = spent_today - spent_budgeted
    return spent_today, spent_budgeted, spent_free

@router.get("/day-limit")
def day_limit(recalc: int = 0):
    """
    Daily baseline ($/day) is computed once per day and stored.
    Remaining today updates live as you add purchases:
      remaining_today = baseline - spent_free_today
    Use ?recalc=1 to force a new baseline for today.
    """
    _ensure_daily_limit_snapshot_pg()

    today = today_local()

    # Get or compute today's baseline
    row = query_db("SELECT day, baseline, computed_at FROM daily_limit_snapshot WHERE day=%s", (today,))
    if recalc or not row:
        mb = _month_budget_home(today.year, today.month)
        baseline = float(mb.get("daily_limit") or 0.0)

        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO daily_limit_snapshot(day, baseline, computed_at)
                VALUES (%s, %s, now())
                ON CONFLICT (day)
                DO UPDATE SET baseline=EXCLUDED.baseline, computed_at=now()
                """,
                (today, baseline),
            )
            conn.commit()

        row = query_db("SELECT day, baseline, computed_at FROM daily_limit_snapshot WHERE day=%s", (today,))

    baseline = float(row[0]["baseline"])
    computed_at = row[0]["computed_at"]

    spent_today, spent_budgeted, spent_free = _compute_spent_free_for_day(today)
    remaining = baseline - spent_free

    return {
        "ok": True,
        "day": today.isoformat(),
        "baseline": round(baseline, 2),
        "computed_at": computed_at.isoformat() if hasattr(computed_at, "isoformat") else str(computed_at),

        "spent_today_total": round(spent_today, 2),
        "spent_today_budgeted": round(spent_budgeted, 2),
        "spent_today_free": round(spent_free, 2),

        "remaining_today": round(remaining, 2),
    }

@router.get("/extra-saved")
def extra_saved():
    """
    Sum of leftover free spending (baseline - spent_free)
    from the 1st of the month through today.
    Only positive leftover days count.
    """
    _ensure_daily_limit_snapshot_pg()

    today = today_local()
    month_start = date(today.year, today.month, 1)

    # Pull all stored baselines this month
    rows = query_db(
        """
        SELECT day, baseline
        FROM daily_limit_snapshot
        WHERE day >= %s AND day <= %s
        ORDER BY day ASC
        """,
        (month_start, today),
    )

    total_extra = 0.0
    days_counted = 0

    for r in rows:
        d = r["day"]
        baseline = float(r["baseline"] or 0.0)

        _, _, spent_free = _compute_spent_free_for_day(d)
        leftover = baseline - spent_free

        total_extra += leftover

        days_counted += 1

    return {
        "ok": True,
        "extra_saved": round(total_extra, 2),
        "days_counted": days_counted,
    }

@router.get("/extra-saved-detail")
def extra_saved_detail():
    """
    Day-by-day breakdown of:
      leftover = baseline - spent_free
    from the 1st of the month through today.

    IMPORTANT: includes negative days (overspent days reduce the total).
    """
    _ensure_daily_limit_snapshot_pg()

    today = today_local()
    month_start = date(today.year, today.month, 1)

    rows = query_db(
        """
        SELECT day, baseline, computed_at
        FROM daily_limit_snapshot
        WHERE day >= %s AND day <= %s
        ORDER BY day ASC
        """,
        (month_start, today),
    )

    days = []
    total = 0.0

    for r in rows:
        d = r["day"]
        baseline = float(r["baseline"] or 0.0)

        spent_today, spent_budgeted, spent_free = _compute_spent_free_for_day(d)
        leftover = baseline - spent_free

        total += leftover

        days.append({
            "day": d.isoformat(),
            "baseline": round(baseline, 2),
            "spent_today_total": round(float(spent_today or 0.0), 2),
            "spent_today_budgeted": round(float(spent_budgeted or 0.0), 2),
            "spent_today_free": round(float(spent_free or 0.0), 2),
            "leftover": round(float(leftover or 0.0), 2),
            "computed_at": (
                r["computed_at"].isoformat()
                if hasattr(r["computed_at"], "isoformat")
                else str(r["computed_at"])
            ),
        })

    return {
        "ok": True,
        "month_start": month_start.isoformat(),
        "today": today.isoformat(),
        "total_extra_saved": round(total, 2),
        "days": days,
    }

# -----------------------------------------------------------------------------
# /spent-so-far-breakdown  (for the modal summary)
# -----------------------------------------------------------------------------
@router.get("/spent-so-far-transactions")
def spent_so_far_transactions(category: str, start: str = "", end: str = ""):
    today = today_local()
    month_start = date(today.year, today.month, 1)

    start_date = parse_iso(start) if (start or "").strip() else month_start
    end_date = parse_iso(end) if (end or "").strip() else today
    end_excl = end_date + timedelta(days=1)

    cat = (category or "").strip()

    params = [start_date, end_excl]

    # IMPORTANT: filter using the CTE output column name (no "t.")
    if cat.lower() == "unassigned":
        cat_where = "AND (category IS NULL OR category = '')"
    else:
        # case-insensitive match (also against CTE column)
        cat_where = "AND LOWER(COALESCE(category,'')) = LOWER(%s)"
        params.append(cat)

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            CASE
              WHEN LOWER(a.accountType) = 'credit' THEN ABS(t.amount::double precision)
              ELSE t.amount::double precision
            END AS amount,
            t.merchant,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'),
                     NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          WHERE LOWER(a.accountType) IN ('checking','credit')
            AND (
              (LOWER(a.accountType) = 'checking' AND t.amount::double precision > 0)
              OR
              (LOWER(a.accountType) = 'credit' AND t.amount::double precision <> 0)
            )
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
        SELECT id, d, amount, merchant, category, bank, card
        FROM norm
        WHERE d IS NOT NULL
          AND d >= %s AND d < %s
          AND LOWER(COALESCE(category,'')) NOT IN ('card payment','transfer')
          {cat_where}
        ORDER BY d DESC, id DESC
        LIMIT 500
        """,
        tuple(params),
    )

    out = []
    for r in rows:
        out.append(
            {
                # FIX: your id isn't always numeric (e.g. '3_020226_591.67_0')
                "id": str(r.get("id")),
                "date": r["d"].isoformat() if r.get("d") else None,
                "amount": float(r.get("amount") or 0),
                "merchant": r.get("merchant"),
                "category": r.get("category"),
                "bank": r.get("bank"),
                "card": r.get("card"),
            }
        )

    return {"ok": True, "transactions": out}

# -----------------------------------------------------------------------------
# /spent-so-far-transactions (lazy-load tx list for accordion)
# category="Unassigned" returns NULL/blank category tx
# -----------------------------------------------------------------------------
@router.get("/spent-so-far-breakdown")
def spent_so_far_breakdown(start: str = "", end: str = ""):
    """
    Returns a breakdown of *free* spending (what counts toward "Spent so far"),
    plus everything excluded (card payment/transfer + any categories inside budget
    groups that have an allocation).

    UI contract:
      - total   => FREE spending total (included categories sum)
      - excluded => list of excluded categories + totals
      - included => list of included categories + totals
      - total_all => (debug) total spend across all categories (incl. excluded)
    """
    today = today_local()
    month_start = date(today.year, today.month, 1)

    start_date = parse_iso(start) if (start or "").strip() else month_start
    end_date = parse_iso(end) if (end or "").strip() else today

    # inclusive end in UI, but SQL easiest as < (end+1)
    end_excl = end_date + timedelta(days=1)

    # Determine budgets month (use start_date's month)
    y = int(start_date.year)
    m = int(start_date.month)

    # Month budget gives us projected bill categories + totals, and ensures consistency with home math
    mb = _month_budget_home(y, m)

    # Build budget groups for this month, including synthetic Bills group if missing
    groups = _get_budget_groups_for_month(y, m)

    try:
        bills_alloc = float((mb or {}).get("bills_total") or 0.0)
    except Exception:
        bills_alloc = 0.0

    try:
        bill_cats = list((mb or {}).get("bill_categories") or [])
    except Exception:
        bill_cats = []

    has_bills = any((_norm_name(g.get("name", "")) == "bills") for g in (groups or []))
    if not has_bills:
        groups = list(groups or [])
        groups.append(
            {
                "id": -1,
                "name": "Bills",
                "allocated": bills_alloc,
                "cap": None,
                "categories": bill_cats or ["bills"],
            }
        )

    # Categories to exclude from "spent so far" = any category in an allocated group
    excluded_norm: set[str] = set(["card payment", "transfer"])
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
                excluded_norm.add(cn)

    # --- Pull totals ---
    row = query_db(
        """
        WITH base AS (
          SELECT
            -- keep the original signed amount for transfer/card-payment math
            t.amount::double precision AS signed_amount,

            -- normalized amount for "spend" math (credit may be stored negative)
            CASE
              WHEN LOWER(a.accountType) = 'credit' THEN ABS(t.amount::double precision)
              ELSE t.amount::double precision
            END AS amount,

            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            LOWER(a.accountType) AS accountType,
            TRIM(t.category) AS category_trim
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          WHERE LOWER(a.accountType) IN ('checking','credit')
            AND (
              (LOWER(a.accountType) = 'checking' AND t.amount::double precision > 0)
              OR
              (LOWER(a.accountType) = 'credit' AND t.amount::double precision <> 0)
            )
        ),
        norm AS (
          SELECT
            amount,
            signed_amount,
            accountType,
            category_trim,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        ),
        scoped AS (
          SELECT *
          FROM norm
          WHERE d IS NOT NULL AND d >= %s AND d < %s
        )
        SELECT
          COALESCE(SUM(amount),0)::double precision AS total_all,

          -- only count the positive side for card payment / transfer
          COALESCE(SUM(
            CASE
              WHEN LOWER(COALESCE(category_trim,'')) = 'card payment' AND signed_amount > 0
                THEN signed_amount
              ELSE 0
            END
          ),0)::double precision AS total_card_payment,

          COALESCE(SUM(
            CASE
              WHEN LOWER(COALESCE(category_trim,'')) = 'transfer' AND signed_amount > 0
                THEN signed_amount
              ELSE 0
            END
          ),0)::double precision AS total_transfer,

          COALESCE(SUM(CASE
            WHEN category_trim IS NULL OR category_trim = '' THEN amount
            ELSE 0
          END),0)::double precision AS total_unassigned
        FROM scoped
        """,
        (start_date, end_excl),
    )[0]

    # Totals per explicit category (excluding null/empty). We'll decide included vs excluded in Python.
    cats = query_db(
        """
        WITH base AS (
          SELECT
            CASE
              WHEN LOWER(a.accountType) = 'credit' THEN ABS(t.amount::double precision)
              ELSE t.amount::double precision
            END AS amount,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            TRIM(t.category) AS category_trim
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          WHERE LOWER(a.accountType) IN ('checking','credit')
            AND (
              (LOWER(a.accountType) = 'checking' AND t.amount::double precision > 0)
              OR
              (LOWER(a.accountType) = 'credit' AND t.amount::double precision <> 0)
            )
        ),
        norm AS (
          SELECT
            amount,
            category_trim,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          category_trim AS category,
          SUM(amount)::double precision AS total
        FROM norm
        WHERE d IS NOT NULL AND d >= %s AND d < %s
          AND category_trim IS NOT NULL AND category_trim <> ''
        GROUP BY category_trim
        ORDER BY total DESC
        """,
        (start_date, end_excl),
    )

    # Build norm->display map from actual transaction categories (stable + matches UI)
    norm_to_display: dict[str, str] = {}
    norm_to_total: dict[str, float] = {}

    for r in cats:
        cat_disp = (r.get("category") or "").strip()
        if not cat_disp:
            continue
        cn = _norm_cat(cat_disp)
        if not cn:
            continue
        # Skip card payment/transfer here; we use the special totals from 'row' (signed>0)
        if cn in ("card payment", "transfer"):
            continue
        norm_to_display.setdefault(cn, cat_disp)
        norm_to_total[cn] = norm_to_total.get(cn, 0.0) + float(r.get("total") or 0.0)

    # Inject special categories with correct totals
    norm_to_display.setdefault("card payment", "Card Payment")
    norm_to_display.setdefault("transfer", "Transfer")
    norm_to_total["card payment"] = float(row.get("total_card_payment") or 0.0)
    norm_to_total["transfer"] = float(row.get("total_transfer") or 0.0)

    # Unassigned is treated as its own included "category"
    unassigned_total = float(row.get("total_unassigned") or 0.0)

    excluded = []
    included = []

    # Excluded: show EVERY excluded category (even if $0) so user can see what's being removed
    # (except we don't add "unassigned" here)
    for cn in sorted(excluded_norm):
        total = float(norm_to_total.get(cn, 0.0) or 0.0)
        excluded.append({"category": norm_to_display.get(cn, cn), "total": total})

    # Included: everything else
    for cn, total in norm_to_total.items():
        if cn in excluded_norm:
            continue
        if total == 0:
            continue
        included.append({"category": norm_to_display.get(cn, cn), "total": float(total)})

    if unassigned_total > 0:
        included.append({"category": "Unassigned", "total": float(unassigned_total)})

    included.sort(key=lambda x: float(x.get("total") or 0.0), reverse=True)

    total_free = sum(float(x.get("total") or 0.0) for x in included)

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),

        # FREE spending (what counts toward your "Spent so far" metric)
        "total": float(total_free or 0.0),

        # Debug / transparency
        "total_all": float(row.get("total_all") or 0),

        "excluded": excluded,
        "included": included,
    }
