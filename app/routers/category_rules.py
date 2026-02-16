from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.core.time import today_local
from app.routers.analytics import _last_day_of_month, parse_iso
from app.routers.budget_groups import _norm_cat, _get_budget_groups_for_month, _norm_name
from app.routers.funds import _list_sinking_funds
from app.routers.les import LESPaychecksRequest, les_paychecks
from app.routers.recurring import recurring_calendar
from app.routers.savings_goal import get_savings_goal
from app.routers.settings import _ensure_app_settings_pg
from db import with_db_cursor, query_db
from app.core.config import CATEGORY_RULES_TABLE, MULTI_TENANT_ENABLED
from app.core.tenant_keys import scoped_key
from app.core.tenancy import current_tenant_id

router = APIRouter()

# =============================================================================
# Category Rules (Postgres) — ported from category_rules.py
# =============================================================================

class RuleCreate(BaseModel):
    category: str
    keywords: List[str] = []
    regex: Optional[str] = None
    apply_now: bool = True

class RuleUpdate(BaseModel):
    category: str
    reapply_existing: bool = False

class RuleActiveUpdate(BaseModel):
    is_active: bool

class RuleTestBody(BaseModel):
    pattern: str
    flags: str = "i"
    limit: int = 50

# -----------------------------
# Helpers
# -----------------------------
_INCOME_CATEGORY_LABELS = {
    "income",
    "paycheck",
    "interest",
    "salary",
    "direct deposit",
    "direct_deposit",
}
_INCOME_MERCHANT_MARKERS = ("salary", "payroll", "dfas", "direct deposit", "mil pay")


def _event_is_income(e: dict, amount: float, etype: str, cadence: str, category: str, merchant: str) -> bool:
    kind = str(e.get("kind") or "").lower().strip()
    if etype == "income" or kind == "paycheck" or cadence in ("paycheck", "interest"):
        return True

    cat_norm = _norm_cat(category or "")
    if cat_norm in _INCOME_CATEGORY_LABELS:
        return True

    merch = str(merchant or "").lower()
    if any(tok in merch for tok in _INCOME_MERCHANT_MARKERS):
        if float(amount or 0.0) <= 0 or cadence in ("weekly", "biweekly", "monthly", "quarterly"):
            return True

    return False

def _ensure_daily_limit_snapshot_pg(tid: int | None = None):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_limit_snapshot (
              tenant_id BIGINT NOT NULL,
              day DATE NOT NULL,
              baseline DOUBLE PRECISION NOT NULL,
              computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute("ALTER TABLE daily_limit_snapshot ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_limit_snapshot_tenant_day ON daily_limit_snapshot(tenant_id, day)"
        )
        if tid:
            cur.execute("UPDATE daily_limit_snapshot SET tenant_id = %s WHERE tenant_id IS NULL", (int(tid),))
        cur.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'daily_limit_snapshot_pkey'
                  AND conrelid = 'daily_limit_snapshot'::regclass
              ) THEN
                ALTER TABLE daily_limit_snapshot DROP CONSTRAINT daily_limit_snapshot_pkey;
              END IF;
            END $$;
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'daily_limit_snapshot_tenant_day_pkey'
                  AND conrelid = 'daily_limit_snapshot'::regclass
              ) THEN
                ALTER TABLE daily_limit_snapshot
                ADD CONSTRAINT daily_limit_snapshot_tenant_day_pkey PRIMARY KEY (tenant_id, day);
              END IF;
            END $$;
            """
        )
        conn.commit()

def _compute_spent_free_for_day(day: date, tid: int | None = None) -> tuple[float, float, float]:
    year = day.year
    month = day.month
    if tid is None:
        tid = _require_tenant_id()

    tx_rows = query_db(
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
        WHERE d = %s
        """,
        ((int(tid), int(tid), day) if tid else (day,)),
    )

    spent_today = 0.0
    cat_spent: dict[str, float] = {}

    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer", "cash withdrawal"):
            continue
        amt = float(r["amount"] or 0.0)
        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            spent_today += amt
            if category:
                cat_spent[category] = cat_spent.get(category, 0.0) + amt

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

def _compute_extra_saved_rollover_for_month(
    tid: int,
    year: int,
    month: int,
    today: date,
    fallback_today_baseline: float = 0.0,
) -> float:
    month_start = date(year, month, 1)

    rows = query_db(
        """
        SELECT day, baseline
        FROM daily_limit_snapshot
        WHERE day >= %s AND day <= %s AND tenant_id = %s
        ORDER BY day ASC
        """,
        (month_start, today, int(tid)),
    )

    by_day: dict[date, float] = {}
    for r in rows:
        by_day[r["day"]] = float(r.get("baseline") or 0.0)

    if today not in by_day:
        by_day[today] = float(fallback_today_baseline or 0.0)

    balance = 0.0
    dcur = month_start
    while dcur <= today:
        baseline = by_day.get(dcur)
        if baseline is None:
            dcur += timedelta(days=1)
            continue

        _, _, spent_free = _compute_spent_free_for_day(dcur, tid=tid)
        leftover = float(baseline) - float(spent_free)

        if dcur < today:
            applied = leftover
        else:
            applied = leftover if leftover < 0 else 0.0

        balance = max(0.0, balance + applied)
        dcur += timedelta(days=1)

    return float(balance)


def _month_budget_home(year: int, month: int, min_occ: int = 3, include_stale: bool = False):
    tid = _require_tenant_id()
    today = today_local()
    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    # 1) Projected recurring events
    cal = recurring_calendar(
        year=year,
        month=month,
        min_occ=min_occ,
        include_stale=include_stale,
    )
    events = (cal or {}).get("events") or []

    bills_debug_event_merchants = sorted({str(e.get("merchant") or "").strip() for e in events if str(e.get("merchant") or "").strip()})

    spendable_account_id = 3

    income_expected = 0.0
    bills_total = 0.0
    bills_remaining = 0.0
    bill_categories: set[str] = set()


    bills_paid_items: list[dict] = []
    bills_future_items: list[dict] = []
    for e in events:
        d = str(e.get("date") or "")
        if not d:
            continue
        try:
            ed = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue

        if ed < month_start or ed > month_end:
            continue

        amt = float(e.get("amount") or 0.0)
        etype = str(e.get("type") or "").lower().strip()
        cadence = str(e.get("cadence") or "").lower().strip()
        category = str(e.get("category") or "").strip()
        merchant = str(e.get("merchant") or "")

        is_income = _event_is_income(
            e,
            amount=amt,
            etype=etype,
            cadence=cadence,
            category=category,
            merchant=merchant,
        )

        if is_income:
            try:
                aid = int(e.get("account_id") or -1)
            except Exception:
                aid = -1
            if aid == spendable_account_id:
                income_expected += abs(amt)
            continue

        # Skip internal transfers in bill projections
        if category.lower() == "transfer" or merchant.lower().startswith("from "):
            continue

        # Total bills for the month (includes past + future)
        bills_total += abs(amt)
        if category:
            bill_categories.add(_norm_cat(category))

        item = {
            "date": ed.isoformat(),
            "merchant": merchant or "",
            "category": category or "",
            "amount": round(abs(amt), 2),
        }
        if ed < today:
            bills_paid_items.append(item)
        else:
            bills_future_items.append(item)

        # Remaining bills: only those scheduled on/after today
        if ed < today:
            continue
        bills_remaining += abs(amt)

    # 2) Actual spending so far + per-category spend map
    tx_rows = query_db(
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
        ((int(tid), int(tid), month_start, today) if tid else (month_start, today)),
    )

    spent_so_far = 0.0
    cat_spent: dict[str, float] = {}

    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer"):
            continue

        amt = float(r["amount"] or 0.0)
        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            spent_so_far += amt
            if category:
                cat_spent[category] = cat_spent.get(category, 0.0) + amt

    # 3) LES + savings goal (Home logic)
    pay_income = _les_pay_income_for_month(year, month) or 0.0
    total_income = income_expected + pay_income
    savings_goal = _compute_monthly_savings_goal(total_income)
    # Base spend goal (before budgeting)
    base_goal = total_income - savings_goal
    spend_goal = base_goal
    # 4) Group budgets (allocations) — reduce free safe-to-spend, but DON'T double-count spend
    groups = _get_budget_groups_for_month(year, month)

    # Synthetic default group: Bills (used for per-group tracking + excluding bills from "spent so far")
    has_bills = any((_norm_name(g.get("name", "")) == "bills") for g in (groups or []))
    if not has_bills:
        groups = list(groups or [])
        groups.append(
            {
                "id": -1,
                "name": "Bills",
                "allocated": float(bills_total or 0.0),   # TOTAL bills for the month
                "cap": None,
                "categories": sorted([c for c in bill_categories if c]) or ["bills"],
            }
        )

    # Allocations include Bills + any other allocated budget groups
    allocations_total = sum(
        float(g.get("allocated") or 0.0)
        for g in (groups or [])
        if float(g.get("allocated") or 0.0) > 0
    )

    # spent inside budgeted categories (INCLUDING Bills, so spent_so_far excludes it)
    budgeted_spent_total = 0.0
    for g in (groups or []):
        g_spent = 0.0
        for c in (g.get("categories") or []):
            cn = _norm_cat(c)
            g_spent += float(cat_spent.get(cn, 0.0))
        budgeted_spent_total += g_spent

    # Free-to-spend excludes allocated money (including Bills)
    free_spend_goal = base_goal - allocations_total

    # spent_so_far includes budgeted categories — remove them so we don't double-count
    spent_free = spent_so_far - budgeted_spent_total
    safe_to_spend = free_spend_goal - spent_free

    # Apply month-to-date rollover:
    # completed-day leftover is moved into extra-saved (not spendable in monthly safe),
    # and overspend pulls from extra-saved first (never below zero).
    extra_saved_applied = 0.0
    if tid and year == today.year and month == today.month:
        _ensure_daily_limit_snapshot_pg(tid)
        # fallback only when today's snapshot is missing
        rough_days_left = max(1, (month_end - today).days + 1)
        fallback_today_baseline = safe_to_spend / rough_days_left
        try:
            extra_saved_applied = _compute_extra_saved_rollover_for_month(
                tid=int(tid),
                year=year,
                month=month,
                today=today,
                fallback_today_baseline=fallback_today_baseline,
            )
        except Exception:
            extra_saved_applied = 0.0

    safe_to_spend = safe_to_spend - extra_saved_applied

    # Daily limits with configurable weekday/weekend point weights.
    # This keeps the same total safe_to_spend, but redistributes it.
    weekday_points, weekend_points = _get_daily_weight_cfg()

    if today < month_start:
        start_day = month_start
    elif today > month_end:
        start_day = None
    else:
        start_day = today

    weekday_days = 0
    weekend_days = 0

    if start_day is None:
        days_left = 0
        total_points = 0
    else:
        dcur = start_day
        while dcur <= month_end:
            if dcur.weekday() >= 5:  # 5=Sat, 6=Sun
                weekend_days += 1
            else:
                weekday_days += 1
            dcur += timedelta(days=1)

        days_left = (month_end - start_day).days + 1
        total_points = (weekday_days * weekday_points) + (weekend_days * weekend_points)

    point_value = (safe_to_spend / total_points) if total_points > 0 else 0.0
    weekday_limit = point_value * weekday_points
    weekend_limit = point_value * weekend_points

    # Keep backward compat: daily_limit becomes "today's limit"
    is_weekend_today = (today.weekday() >= 5)
    today_limit = weekend_limit if is_weekend_today else weekday_limit

    return {
        "ok": True,
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "as_of": today.isoformat(),

        "expected_income": round(total_income, 2),
        "base_income": round(income_expected, 2),
        "les_income": round(pay_income, 2),

        # "Spent so far" should exclude anything in budget groups (including default Bills)
        "spent_so_far": round(spent_free, 2),
        "bills_remaining": round(bills_remaining, 2),

        # Total bills for the month (includes past + future) and paid-to-date
        "bills_total": round(bills_total, 2),
        "bills_paid": round(max(0.0, bills_total - bills_remaining), 2),
        "bills_paid_items": bills_paid_items,
        "bills_future_items": bills_future_items,
        "bill_categories": sorted([c for c in bill_categories if c]),

        "bills_debug_event_merchants": bills_debug_event_merchants,
        "savings_goal": round(savings_goal, 2),
        "spend_goal": round(base_goal, 2),

        # NEW
        "allocations_total": round(allocations_total, 2),
        "budgeted_spent_total": round(budgeted_spent_total, 2),

        # UPDATED meaning: safe-to-spend (FREE spending, after allocations)
# UPDATED meaning: safe-to-spend (FREE spending, after allocations)
        "safe_to_spend": round(safe_to_spend, 2),
        "safe_to_spend_raw": round(free_spend_goal - spent_free, 2),
        "extra_saved_applied": round(extra_saved_applied, 2),

        # Backward compatibility (what widget + UI already expects)
        # This is now TODAY'S allowance
        "daily_limit": round(today_limit, 2),
        "days_left": int(days_left),

        # NEW weekend-weighted budgeting fields
        "daily_weekday_limit": round(weekday_limit, 2),
        "daily_weekend_limit": round(weekend_limit, 2),
        "weekday_days_left": int(weekday_days),
        "weekend_days_left": int(weekend_days),
        "daily_weight_mode": "custom_points",
        "weekday_points": float(weekday_points),
        "weekend_points": float(weekend_points),
        "free_spend_goal": round(free_spend_goal, 2),
        "spent_free": round(spent_free, 2),
        "category_spent": {k: round(v, 2) for k, v in cat_spent.items()},

    }

def _get_savings_goal_cfg():
    """
    Returns (mode, value) where:
      mode: "percent" | "amount"
      value: float
    Matches /settings/savings-goal storage (key='savings_goal', column=value_json).
    """
    _ensure_app_settings_pg()  # table has value_json:contentReference[oaicite:5]{index=5}

    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key=%s LIMIT 1",
        (scoped_key("savings_goal"),),
    )
    if not rows:
        return "percent", 0.0

    try:
        j = json.loads(rows[0].get("value_json") or "{}")
    except Exception:
        j = {}

    mode = (j.get("mode") or "percent").strip().lower()
    try:
        value = float(j.get("value") or 0)
    except Exception:
        value = 0.0

    if mode not in ("percent", "amount"):
        mode = "percent"
    if value < 0:
        value = 0.0
    if mode == "percent" and value > 100:
        value = 100.0

    return mode, value

def _compute_monthly_savings_goal(total_income: float) -> float:
    mode, value = _get_savings_goal_cfg()
    if mode == "percent":
        return max(0.0, total_income * (value / 100.0))
    # mode == "amount"
    return max(0.0, value)


def _get_daily_weight_cfg() -> tuple[float, float]:
    """
    Returns (weekday_points, weekend_points), defaulting to (1.0, 2.0).
    Stored in app_settings key='daily_weights'.
    """
    _ensure_app_settings_pg()
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key=%s LIMIT 1",
        (scoped_key("daily_weights"),),
    )
    if not rows:
        return 1.0, 2.0
    try:
        j = json.loads(rows[0].get("value_json") or "{}")
    except Exception:
        j = {}

    def _safe(v: object, default: float) -> float:
        try:
            x = float(v)
        except Exception:
            return default
        if x <= 0:
            return default
        if x > 10:
            return 10.0
        return x

    return _safe(j.get("weekday_points"), 1.0), _safe(j.get("weekend_points"), 2.0)

def _get_default_les_profile():
    rows = query_db("SELECT profile_json FROM les_profile WHERE key=%s LIMIT 1", (scoped_key("default"),))
    if not rows:
        return None

    v = rows[0].get("profile_json")
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None

def _les_pay_income_for_month(year: int, month: int) -> float:
    profile = _get_default_les_profile()
    if not profile:
        return 0.0

    # Reuse the SAME logic as your /les/paychecks endpoint (including “actual deposit overrides”)
    # If your endpoint code is currently inline, move it into a helper and call it both places.
    req = LESPaychecksRequest(year=year, month=month, profile=profile)
    out = les_paychecks(req)  # calls your existing endpoint function directly

    events = (out or {}).get("events") or []
    return float(sum(max(0.0, float(e.get("amount") or 0)) for e in events))

def build_pattern_from_keywords(keywords: List[str]) -> str:
    kws = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if not kws:
        raise ValueError("Provide at least one keyword or a regex")

    # Escape each keyword then OR them together; allow flexible whitespace/dash matching
    parts = []
    for k in kws:
        esc = re.escape(k)
        esc = esc.replace(r"\ ", r"[\s\-]+")
        parts.append(esc)
    return "(" + "|".join(parts) + ")"

def _compile_rule(pattern: str, flags: str):
    # Only used for /test to show matched boolean in Python too.
    # For actual DB apply/count we use Postgres regex (~ / ~*).
    f = 0
    if flags and "i" in flags.lower():
        f |= re.IGNORECASE
    return re.compile(pattern, f)

def _pg_regex_operator(flags: str) -> str:
    # i => case-insensitive
    if flags and "i" in flags.lower():
        return "~*"
    return "~"

def _recent_merchants(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns merchants with counts from *recent-ish* transactions.
    Uses Postgres date parsing on your string dates (MM/DD/YY or MM/DD/YYYY).
    """
    tid = _require_tenant_id()
    limit = max(1, min(int(limit), 200))
    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            TRIM(COALESCE(merchant,'')) AS merchant,
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date
          FROM transactions
          WHERE merchant IS NOT NULL AND TRIM(merchant) <> ''
            {"AND tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            merchant,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT merchant, COUNT(*)::int AS count
        FROM norm
        WHERE d IS NOT NULL AND d >= (CURRENT_DATE - INTERVAL '120 days')
        GROUP BY merchant
        ORDER BY COUNT(*) DESC
        LIMIT %s
        """,
        ((int(tid), limit) if tid else (limit,)),
    )
    return [dict(r) for r in rows]

def _rule_match_count(pattern: str, flags: str) -> int:
    tid = _require_tenant_id()
    op = _pg_regex_operator(flags)
    rows = query_db(
        f"""
        SELECT COUNT(*)::int AS n
        FROM transactions
        WHERE merchant IS NOT NULL
          AND TRIM(merchant) <> ''
          {"AND tenant_id = %s" if tid else ""}
          AND merchant {op} %s
        """,
        ((int(tid), pattern) if tid else (pattern,)),
    )
    return int(rows[0]["n"]) if rows else 0

def apply_rule_to_existing(category: str, pattern: str, flags: str) -> int:
    """
    Apply rule only to transactions with empty/NULL category.
    Returns rows updated.
    """
    tid = _require_tenant_id()
    op = _pg_regex_operator(flags)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            UPDATE transactions
            SET category = %s
            WHERE (category IS NULL OR TRIM(category) = '')
              AND merchant IS NOT NULL
              AND TRIM(merchant) <> ''
              {"AND tenant_id = %s" if tid else ""}
              AND merchant {op} %s
            """,
            ((category, int(tid), pattern) if tid else (category, pattern)),
        )
        updated = int(cur.rowcount or 0)
        conn.commit()
        return updated

def _apply_rule_override(category: str, pattern: str, flags: str) -> int:
    """
    Force override category for all matching transactions.
    Returns rows updated.
    """
    tid = _require_tenant_id()
    op = _pg_regex_operator(flags)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            UPDATE transactions
            SET category = %s
            WHERE merchant IS NOT NULL
              AND TRIM(merchant) <> ''
              {"AND tenant_id = %s" if tid else ""}
              AND merchant {op} %s
            """,
            ((category, int(tid), pattern) if tid else (category, pattern)),
        )
        updated = int(cur.rowcount or 0)
        conn.commit()
        return updated

# -----------------------------
# Endpoints
# -----------------------------
@router.post("/category-rules")
def create_category_rule(payload: RuleCreate):
    category = (payload.category or "").strip()
    if not category:
        return {"ok": False, "error": "Category is required"}

    if payload.regex and payload.regex.strip():
        pattern = payload.regex.strip()
    else:
        try:
            pattern = build_pattern_from_keywords(payload.keywords)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    flags = "i"  # default

    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                f"""
                INSERT INTO {CATEGORY_RULES_TABLE} (category, pattern, flags, is_active)
                VALUES (%s, %s, %s, TRUE)
                """,
                (category, pattern, flags),
            )
            applied = 0
            if payload.apply_now:
                conn.commit()  # commit rule insert before large update
                applied = apply_rule_to_existing(category, pattern, flags)
            else:
                conn.commit()
            return {"ok": True, "pattern": pattern, "applied": int(applied)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/category-rules/list")
def list_category_rules(
    include_inactive: int = 0,
    with_counts: int = 0,
    limit: int = 0,
    offset: int = 0,
    rule_id: str = "",
    keyword: str = "",
    category: str = "",
):
    clauses: list[str] = []
    params: list[Any] = []

    if not include_inactive:
        clauses.append("COALESCE(is_active, TRUE) = TRUE")

    rid = (rule_id or "").strip()
    if rid:
        try:
            clauses.append("id = %s")
            params.append(int(rid))
        except Exception:
            return {"rows": [], "limit": 0, "offset": 0, "has_more": False, "total": 0}

    kw = (keyword or "").strip()
    if kw:
        clauses.append("(pattern ILIKE %s)")
        params.append(f"%{kw}%")

    cat = (category or "").strip()
    if cat:
        clauses.append("category ILIKE %s")
        params.append(f"%{cat}%")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    use_paging = bool(limit) or bool(offset) or bool(rid) or bool(kw) or bool(cat)
    if use_paging:
        lim = max(1, min(int(limit or 50), 200))
        off = max(0, int(offset or 0))
        page_params = params + [lim + 1, off]

        rows = query_db(
            f"""
            SELECT id, pattern, flags, category, COALESCE(is_active, TRUE) AS is_active
            FROM {CATEGORY_RULES_TABLE}
            {where}
            ORDER BY COALESCE(is_active, TRUE) DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(page_params),
        )

        rules = [dict(r) for r in rows]
        has_more = len(rules) > lim
        if has_more:
            rules = rules[:lim]

        if with_counts:
            for r in rules:
                try:
                    r["match_count"] = _rule_match_count(r["pattern"], r.get("flags") or "i")
                except Exception:
                    r["match_count"] = 0
                    r["regex_error"] = "Invalid regex"

        total_rows = query_db(
            f"SELECT COUNT(*)::int AS n FROM {CATEGORY_RULES_TABLE} {where}",
            tuple(params),
        )
        total = int(total_rows[0]["n"] or 0) if total_rows else 0

        return {"rows": rules, "limit": lim, "offset": off, "has_more": has_more, "total": total}

    rows = query_db(
        f"""
        SELECT id, pattern, flags, category, COALESCE(is_active, TRUE) AS is_active
        FROM {CATEGORY_RULES_TABLE}
        {where}
        ORDER BY COALESCE(is_active, TRUE) DESC, id DESC
        """
    )

    rules = [dict(r) for r in rows]

    if with_counts:
        # Use Postgres regex for fast counts
        for r in rules:
            try:
                r["match_count"] = _rule_match_count(r["pattern"], r.get("flags") or "i")
            except Exception:
                r["match_count"] = 0
                r["regex_error"] = "Invalid regex"

    return rules

@router.post("/category-rules/{rule_id}")
def update_category_rule(rule_id: int, payload: RuleUpdate):
    category = (payload.category or "").strip()
    if not category:
        return {"ok": False, "error": "Category is required"}

    rows = query_db(
        f"""
        SELECT id, pattern, flags
        FROM {CATEGORY_RULES_TABLE}
        WHERE id = %s
        LIMIT 1
        """,
        (int(rule_id),),
    )
    if not rows:
        return {"ok": False, "error": "Rule not found"}

    pattern = rows[0]["pattern"]
    flags = rows[0].get("flags") or "i"

    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                f"UPDATE {CATEGORY_RULES_TABLE} SET category = %s WHERE id = %s",
                (category, int(rule_id)),
            )

            applied = 0
            if payload.reapply_existing:
                # override category on ALL matches
                conn.commit()  # commit rule edit first
                applied = _apply_rule_override(category, pattern, flags)
            else:
                conn.commit()

            # refresh match count (nice UX)
            try:
                match_count = _rule_match_count(pattern, flags)
            except Exception:
                match_count = 0

            return {"ok": True, "applied": int(applied), "match_count": int(match_count)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/category-rules/{rule_id}/active")
def set_rule_active(rule_id: int, payload: RuleActiveUpdate):
    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                f"UPDATE {CATEGORY_RULES_TABLE} SET is_active = %s WHERE id = %s",
                (bool(payload.is_active), int(rule_id)),
            )
            conn.commit()
            return {"ok": True, "id": int(rule_id), "is_active": bool(payload.is_active)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@router.delete("/category-rules/{rule_id}")
def delete_rule(rule_id: int):
    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(f"DELETE FROM {CATEGORY_RULES_TABLE} WHERE id = %s", (int(rule_id),))
            conn.commit()
            return {"ok": True, "deleted": int(rule_id)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/category-rules/test")
def test_rule(body: RuleTestBody):
    pattern = (body.pattern or "").strip()
    if not pattern:
        return {"ok": False, "error": "Pattern is required"}

    flags = (body.flags or "i").strip()

    # validate regex early (same behavior)
    try:
        rx = _compile_rule(pattern, flags)
    except Exception as e:
        return {"ok": False, "error": f"Invalid regex: {e}"}

    recent = _recent_merchants(limit=body.limit)

    tested = []
    for r in recent:
        merchant = r["merchant"]
        tested.append(
            {
                "merchant": merchant,
                "count": int(r["count"]),
                "matched": bool(rx.search(merchant or "")),
            }
        )

    return {"ok": True, "tested": tested}

# -----------------------------------------------------------------------------
# /unknown-merchant-total-month
# -----------------------------------------------------------------------------
@router.get("/unknown-merchant-total-month")
def unknown_merchant_total_month():
    tid = _require_tenant_id()
    today = today_local()
    first = today.replace(day=1)
    next_month = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)

    row = query_db(
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
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            amount, merchant, category, accountType,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          COALESCE(SUM(amount), 0)::double precision AS total,
          COALESCE(COUNT(*), 0)::int AS tx_count
        FROM norm
        WHERE d IS NOT NULL
          AND d >= %s AND d < %s
          AND amount > 0
          AND accountType IN ('checking','credit')
          AND merchant = 'unknown'
          AND category NOT IN ('card payment','transfer')
        """,
        ((int(tid), int(tid), first, next_month) if tid else (first, next_month)),
    )[0]

    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}

# -----------------------------------------------------------------------------
# /unknown-merchant-total-range
# -----------------------------------------------------------------------------
@router.get("/unknown-merchant-total-range")
def unknown_merchant_total_range(start: str, end: str):
    tid = _require_tenant_id()
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    row = query_db(
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
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            amount, merchant, category, accountType,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          COALESCE(SUM(amount), 0)::double precision AS total,
          COALESCE(COUNT(*), 0)::int AS tx_count
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
          AND amount > 0
          AND accountType IN ('checking','credit')
          AND merchant = 'unknown'
          AND category NOT IN ('card payment','transfer')
        """,
        ((int(tid), int(tid), start_date, end_date) if tid else (start_date, end_date)),
    )[0]

    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}

# -----------------------------------------------------------------------------
# /month-budget
# NOTE: assumes recurring_calendar(...) exists in your app_postgres.py (same as sqlite version)
# -----------------------------------------------------------------------------

@router.get("/month-budget")
def month_budget(
    year: int | None = None,
    month: int | None = None,
    min_occ: int = 3,
    include_stale: bool = False,
):
    now = datetime.now()
    y = int(year or now.year)
    m = int(month or now.month)
    return _month_budget_home(y, m, min_occ=min_occ, include_stale=include_stale)

@router.get("/page/budget")
def page_budget(year: int | None = None, month: int | None = None, min_occ: int = 3, include_stale: bool = False):
    tid = _require_tenant_id()
    now = datetime.now()
    y = int(year or now.year)
    m = int(month or now.month)

    mb = _month_budget_home(y, m, min_occ=min_occ, include_stale=include_stale)

    groups = _get_budget_groups_for_month(y, m)

    # ------------------------------------------------------------
    # Default budget group: Bills (auto-allocated to TOTAL bills)
    # - Synthetic unless the user already created a real "Bills" group.
    # - Uses projected recurring bill categories for the month.
    # ------------------------------------------------------------
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
                "id": -1,  # synthetic
                "name": "Bills",
                "allocated": bills_alloc,
                "cap": None,
                "categories": bill_cats or ["bills"],
            }
        )

    # decorate groups with spent/remaining using mb.category_spent
    cat_spent = (mb.get("category_spent") or {}) if isinstance(mb, dict) else {}
    out_groups = []
    for g in groups:
        g_spent = 0.0
        for c in (g.get("categories") or []):
            g_spent += float(cat_spent.get(_norm_cat(c), 0.0))
        allocated = float(g.get("allocated") or 0.0)
        cap = g.get("cap", None)
        remaining = allocated - g_spent
        out_groups.append(
            {
                **g,
                "spent": round(g_spent, 2),
                "remaining": round(remaining, 2),
                "over_cap": bool(cap is not None and float(g_spent) > float(cap)),
            }
        )

    # categories spent list (sorted desc), for the read-only section
    # cat_spent keys are normalized (lowercased). Map them back to canonical display names.
    canon_rows = query_db(
        f"""
        SELECT category FROM (
          SELECT DISTINCT TRIM(category) AS category
          FROM transactions
          WHERE category IS NOT NULL AND TRIM(category) <> ''
            {"AND tenant_id = %s" if tid else ""}

          UNION

          SELECT DISTINCT TRIM(category) AS category
          FROM "categoryrules"
          WHERE category IS NOT NULL AND TRIM(category) <> ''
            {"AND tenant_id = %s" if tid else ""}
        ) u
        ORDER BY LOWER(category) ASC
        """,
        ((int(tid), int(tid)) if tid else ()),
    )

    norm_to_display = {}
    for r in canon_rows:
        c = (r.get("category") or "").strip()
        if not c:
            continue
        n = _norm_cat(c)
        # first one wins (stable enough, and matches how your app already thinks about categories)
        norm_to_display.setdefault(n, c)

    spent_items = [
        {"category": norm_to_display.get(k, k), "spent": float(v)}
        for k, v in (cat_spent or {}).items()
    ]
    spent_items.sort(key=lambda x: x["spent"], reverse=True)

    return {
        "ok": True,
        "month": mb,
        "groups": out_groups,
        "funds": _list_sinking_funds(include_inactive=False),
        "spent_categories": spent_items,
        "savings_goal_cfg": get_savings_goal(),  # re-use existing endpoint logic
    }
def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)
