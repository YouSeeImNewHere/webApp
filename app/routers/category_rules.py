from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from threading import Lock, Thread
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request

from app.core.time import today_local
from app.core.roundups import (
    ROUNDUP_CATEGORY_DEFAULT,
    ROUNDUP_CATEGORY_NORM,
    get_roundup_settings,
    is_roundup_eligible_tx,
    roundup_amount_from_spend,
)
from app.routers.analytics import _last_day_of_month, parse_iso
from app.routers.budget_groups import _norm_cat, _get_budget_groups_for_month, _norm_name
from app.routers.funds import _list_sinking_funds
from app.routers.recurring import recurring_calendar
from app.routers.savings_goal import get_savings_goal
from app.routers.settings import _ensure_app_settings_pg
from app.routers.notifications import create_notification
from db import with_db_cursor, query_db
from app.core.config import CATEGORY_RULES_TABLE, MULTI_TENANT_ENABLED
from app.core.home_snapshot_cache import (
    ensure_home_snapshot_cache_pg,
    home_snapshot_version_for_tenant,
    load_month_budget_snapshot,
    upsert_month_budget_snapshot,
)
from app.core.tenant_keys import scoped_key
from app.core.tenancy import current_tenant_id, get_user_pushover_key_by_email
from app.core.pushover import send_pushover
from app.core.transactions_ignore import ensure_transactions_ignore_column

router = APIRouter()

MONTH_BUDGET_CACHE_TTL_SEC = int(os.getenv("MONTH_BUDGET_CACHE_TTL_SEC", "45"))
UNKNOWN_MERCHANT_CACHE_TTL_SEC = int(os.getenv("UNKNOWN_MERCHANT_CACHE_TTL_SEC", "60"))
_MONTH_BUDGET_CACHE: dict[str, dict[str, Any]] = {}
_UNKNOWN_MERCHANT_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = Lock()
_RULE_APPLY_JOBS_READY = False
_RULE_APPLY_JOBS_LOCK = Lock()
_RULE_APPLY_WORKERS: set[int] = set()
MONTH_BUDGET_CALC_VERSION = 2
_CATEGORY_RULES_HAS_TENANT_ID: bool | None = None

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


def _cache_get(cache: dict[str, dict[str, Any]], key: str, ttl_sec: int):
    now_ts = time.time()
    with _CACHE_LOCK:
        row = cache.get(key)
        if not row:
            return None
        ts = float(row.get("ts") or 0.0)
        if now_ts - ts > float(ttl_sec):
            cache.pop(key, None)
            return None
        return deepcopy(row.get("data"))


def _cache_set(cache: dict[str, dict[str, Any]], key: str, value: Any):
    with _CACHE_LOCK:
        cache[key] = {"ts": time.time(), "data": deepcopy(value)}


def _budgeted_covered_spend_total(groups: list[dict[str, Any]], cat_totals: dict[str, float]) -> float:
    """
    Compute budget-covered spend with per-group allocation caps.
    Category spend is consumed once across groups to avoid double-counting
    when categories overlap between groups.
    """
    remaining = {str(k): max(0.0, float(v or 0.0)) for k, v in (cat_totals or {}).items()}
    covered = 0.0

    for g in (groups or []):
        alloc = max(0.0, float(g.get("allocated") or 0.0))
        if alloc <= 0:
            continue
        cats: list[str] = []
        for c in (g.get("categories") or []):
            cn = _norm_cat(c)
            if cn and cn not in cats:
                cats.append(cn)
        if not cats:
            continue

        eligible = sum(float(remaining.get(cn, 0.0)) for cn in cats)
        take_total = min(alloc, max(0.0, eligible))
        if take_total <= 0:
            continue
        covered += take_total

        to_take = take_total
        for cn in cats:
            if to_take <= 0:
                break
            avail = float(remaining.get(cn, 0.0))
            if avail <= 0:
                continue
            used = min(avail, to_take)
            remaining[cn] = avail - used
            to_take -= used

    return max(0.0, float(covered))

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
    ensure_transactions_ignore_column()
    year = day.year
    month = day.month
    if tid is None:
        tid = _require_tenant_id()
    month_start = date(year, month, 1)

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
          {"WHERE COALESCE(t.is_ignored, false) = false" if not tid else ""}
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else ""}
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
        WHERE d BETWEEN %s AND %s
        """,
        ((int(tid), int(tid), month_start, day) if tid else (month_start, day)),
    )

    spent_by_day: dict[date, float] = {}
    cat_spent_by_day: dict[date, dict[str, float]] = {}
    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_norm = _norm_cat(str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT))

    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer", "cash withdrawal"):
            continue
        amt = float(r["amount"] or 0.0)
        account_type = (r["accounttype"] or "").lower()
        is_spend_direction = (
            (account_type == "checking" and amt > 0)
            or (account_type == "credit" and amt != 0)
        )
        if is_spend_direction:
            dtx = r["d"]
            spent_by_day[dtx] = spent_by_day.get(dtx, 0.0) + amt
            day_cat = cat_spent_by_day.setdefault(dtx, {})
            if category:
                day_cat[category] = day_cat.get(category, 0.0) + amt
            if roundup_enabled and is_roundup_eligible_tx(amt, account_type, category):
                ru = roundup_amount_from_spend(amt)
                if ru > 0:
                    spent_by_day[dtx] = spent_by_day.get(dtx, 0.0) + ru
                    day_cat[roundup_norm] = day_cat.get(roundup_norm, 0.0) + ru

    groups = _get_budget_groups_for_month(year, month)
    cumulative_cat_spent: dict[str, float] = {}
    covered_prev = 0.0
    spent_budgeted = 0.0

    dcur = month_start
    while dcur <= day:
        day_cat = cat_spent_by_day.get(dcur) or {}
        for cn, amt in day_cat.items():
            k = _norm_cat(cn)
            if not k:
                continue
            cumulative_cat_spent[k] = cumulative_cat_spent.get(k, 0.0) + float(amt)
        covered_now = _budgeted_covered_spend_total(groups, cumulative_cat_spent)
        if dcur == day:
            spent_budgeted = max(0.0, covered_now - covered_prev)
        covered_prev = covered_now
        dcur += timedelta(days=1)

    spent_today = float(spent_by_day.get(day, 0.0))
    spent_budgeted = min(spent_today, spent_budgeted)
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


def _emit_over_budget_alerts(
    *,
    tid: int | None,
    year: int,
    month: int,
    today: date,
    groups: list[dict[str, Any]],
    cat_spent: dict[str, float],
    pushover_user_key: str | None = None,
) -> None:
    if not tid:
        return
    # Only alert for the current active month.
    if year != today.year or month != today.month:
        return

    for g in (groups or []):
        name = str(g.get("name") or "").strip()
        if not name:
            continue
        if _norm_name(name) == "bills":
            continue
        try:
            allocated = float(g.get("allocated") or 0.0)
        except Exception:
            allocated = 0.0
        if allocated <= 0:
            continue

        g_spent = 0.0
        for c in (g.get("categories") or []):
            g_spent += float(cat_spent.get(_norm_cat(c), 0.0))

        over = float(g_spent - allocated)
        if over <= 0:
            continue

        dedupe_key = f"budget-over:{year:04d}-{month:02d}:{_norm_name(name)}"
        subject = f'Budget over: "{name}" exceeded by ${over:.2f}'
        body = (
            f'{name} is over budget.\n'
            f"Allocated: ${allocated:.2f}\n"
            f"Spent: ${g_spent:.2f}\n"
            f"Over by: ${over:.2f}"
        )

        try:
            created = create_notification(
                kind="budget_over",
                dedupe_key=dedupe_key,
                subject=subject,
                sender="Budget",
                body=body,
                tenant_id=int(tid),
            )
            if created:
                send_pushover(f'Budget Over: {name}', body, user_key=pushover_user_key)
        except Exception:
            # Never break budget response due to notification errors.
            continue


def _usd(value: float) -> str:
    return f"${float(value or 0.0):,.2f}"


def _push_smart_budget_notification(
    *,
    tid: int | None,
    kind: str,
    dedupe_key: str,
    subject: str,
    body: str,
    sender: str = "Budget Coach",
    pushover_user_key: str | None = None,
) -> None:
    if not tid:
        return
    try:
        created = create_notification(
            kind=kind,
            dedupe_key=dedupe_key,
            subject=subject,
            sender=sender,
            body=body,
            tenant_id=int(tid),
        )
        if created:
            send_pushover(subject, body, user_key=pushover_user_key)
    except Exception:
        return


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month <= 1:
        return int(year) - 1, 12
    return int(year), int(month) - 1


def _non_income_recurring_total(events: list[dict[str, Any]]) -> float:
    total = 0.0
    for e in (events or []):
        amt = float(e.get("amount") or 0.0)
        etype = str(e.get("type") or "").lower().strip()
        cadence = str(e.get("cadence") or "").lower().strip()
        category = str(e.get("category") or "").strip()
        merchant = str(e.get("merchant") or "")
        if _event_is_income(e, amount=amt, etype=etype, cadence=cadence, category=category, merchant=merchant):
            continue
        total += abs(amt)
    return float(total)


def _free_spend_streak_days(tid: int, today: date, max_days: int = 21) -> int:
    streak = 0
    for delta in range(0, max(1, int(max_days))):
        day = today - timedelta(days=delta)
        _, _, spent_free = _compute_spent_free_for_day(day, tid=tid)
        if float(spent_free) <= 0.0:
            streak += 1
            continue
        break
    return int(streak)


def _weekly_free_spend_vs_plan(
    *,
    tid: int,
    today: date,
    fallback_baseline: float,
) -> tuple[float, float, int]:
    week_start = today - timedelta(days=today.weekday())
    rows = query_db(
        """
        SELECT day, baseline
        FROM daily_limit_snapshot
        WHERE tenant_id = %s AND day >= %s AND day <= %s
        """,
        (int(tid), week_start, today),
    )
    by_day = {r["day"]: float(r.get("baseline") or 0.0) for r in (rows or [])}

    week_spent = 0.0
    week_budget = 0.0
    days = 0
    cur = week_start
    while cur <= today:
        _, _, spent_free = _compute_spent_free_for_day(cur, tid=tid)
        week_spent += float(spent_free)
        week_budget += float(by_day.get(cur, fallback_baseline))
        days += 1
        cur += timedelta(days=1)
    return float(week_spent), float(week_budget), int(days)


def _emit_smart_budget_notifications(
    *,
    tid: int | None,
    year: int,
    month: int,
    today: date,
    groups: list[dict[str, Any]],
    cat_spent: dict[str, float],
    safe_to_spend: float,
    days_left: int,
    today_limit: float,
    spent_free: float,
    events: list[dict[str, Any]],
    min_occ: int,
    include_stale: bool,
    pushover_user_key: str | None = None,
) -> None:
    if not tid:
        return
    if int(year) != int(today.year) or int(month) != int(today.month):
        return

    today_key = today.isoformat()

    _push_smart_budget_notification(
        tid=tid,
        kind="safe_to_spend_daily",
        dedupe_key=f"safe-to-spend:{today_key}",
        subject=f"Today's safe-to-spend is {_usd(safe_to_spend)}",
        body=(
            f"Free spending available after goals and allocations: {_usd(safe_to_spend)}.\n"
            f"Days left this month: {int(days_left)}\n"
            f"Today's free-spend limit: {_usd(today_limit)}"
        ),
        sender="Spending Power",
        pushover_user_key=pushover_user_key,
    )

    for g in (groups or []):
        name = str(g.get("name") or "").strip()
        if not name or _norm_name(name) == "bills":
            continue
        allocated = float(g.get("allocated") or 0.0)
        if allocated <= 0:
            continue
        g_spent = 0.0
        for c in (g.get("categories") or []):
            g_spent += float(cat_spent.get(_norm_cat(c), 0.0))
        pct = (g_spent / allocated) * 100.0
        if pct < 75.0:
            continue
        bucket = int(pct // 10) * 10
        _push_smart_budget_notification(
            tid=tid,
            kind="category_drift",
            dedupe_key=f"category-drift:{year:04d}-{month:02d}:{_norm_name(name)}:{bucket}",
            subject=f"Category drift: {name} at {pct:.0f}%",
            body=(
                f"{name} has used {_usd(g_spent)} of {_usd(allocated)} ({pct:.1f}%).\n"
                f"Days left this month: {int(days_left)}."
            ),
            sender="Budget Guardrails",
            pushover_user_key=pushover_user_key,
        )

    elapsed_days = max(1, (today - date(year, month, 1)).days + 1)
    avg_daily_free_spend = max(0.0, float(spent_free)) / float(elapsed_days)
    if safe_to_spend <= 0:
        _push_smart_budget_notification(
            tid=tid,
            kind="runway_warning",
            dedupe_key=f"runway-warning:{today_key}:empty",
            subject="Runway warning: free budget is depleted",
            body="Your free spending runway is at or below zero. Consider pausing discretionary spending.",
            sender="Spending Power",
            pushover_user_key=pushover_user_key,
        )
    elif avg_daily_free_spend > 0 and days_left > 0:
        days_to_zero = safe_to_spend / avg_daily_free_spend
        if days_to_zero < float(days_left):
            runout_date = today + timedelta(days=max(0, int(days_to_zero)))
            _push_smart_budget_notification(
                tid=tid,
                kind="runway_warning",
                dedupe_key=f"runway-warning:{today_key}:{runout_date.isoformat()}",
                subject=f"Runway warning: pace points to {runout_date.strftime('%A')}",
                body=(
                    f"At your current free-spend pace ({_usd(avg_daily_free_spend)}/day), "
                    f"your free budget may run out by {runout_date.isoformat()}."
                ),
                sender="Spending Power",
                pushover_user_key=pushover_user_key,
            )

    streak = _free_spend_streak_days(int(tid), today, max_days=21)
    if streak >= 3:
        monthly_projection = max(0.0, avg_daily_free_spend * 30.0)
        _push_smart_budget_notification(
            tid=tid,
            kind="savings_streak",
            dedupe_key=f"savings-streak:{today_key}:{streak}",
            subject=f"Savings streak: {streak} low-spend days",
            body=(
                f"You're on a {streak}-day free-spend streak.\n"
                f"If this pace holds, you preserve about {_usd(monthly_projection)} per month."
            ),
            sender="Savings Momentum",
            pushover_user_key=pushover_user_key,
        )

    py, pm = _prev_month(year, month)
    try:
        prev_cal = recurring_calendar(
            year=int(py),
            month=int(pm),
            min_occ=int(min_occ),
            include_stale=bool(include_stale),
        )
        prev_events = list((prev_cal or {}).get("events") or [])
    except Exception:
        prev_events = []
    current_recurring = _non_income_recurring_total(list(events or []))
    prev_recurring = _non_income_recurring_total(prev_events)
    recurring_delta = float(current_recurring - prev_recurring)
    if recurring_delta >= 20.0:
        _push_smart_budget_notification(
            tid=tid,
            kind="subscription_creep",
            dedupe_key=f"subscription-creep:{year:04d}-{month:02d}:{int(recurring_delta)}",
            subject=f"Subscription creep: +{_usd(recurring_delta)}/month",
            body=(
                f"Projected recurring spend this month: {_usd(current_recurring)}.\n"
                f"Last month: {_usd(prev_recurring)}."
            ),
            sender="Subscription Watch",
            pushover_user_key=pushover_user_key,
        )

    _, _, spent_today_free = _compute_spent_free_for_day(today, tid=int(tid))
    if today_limit > 0 and spent_today_free >= max(20.0, float(today_limit) * 2.0):
        ratio = float(spent_today_free) / float(today_limit)
        _push_smart_budget_notification(
            tid=tid,
            kind="high_spend_cooldown",
            dedupe_key=f"high-spend-cooldown:{today_key}",
            subject="High-spend day: cooldown recommended",
            body=(
                f"Today's free spending is {_usd(spent_today_free)} "
                f"({ratio:.1f}x your {_usd(today_limit)} daily limit). "
                "Consider a 24-hour pause on non-essentials."
            ),
            sender="Budget Guardrails",
            pushover_user_key=pushover_user_key,
        )

    _ensure_daily_limit_snapshot_pg(int(tid))
    week_spent, week_budget, week_days = _weekly_free_spend_vs_plan(
        tid=int(tid),
        today=today,
        fallback_baseline=max(0.0, float(today_limit)),
    )
    if week_days >= 3 and week_budget > 0 and week_spent <= week_budget * 0.9:
        week_win = max(0.0, week_budget - week_spent)
        suggestion = min(max(5.0, week_win * 0.3), max(5.0, safe_to_spend), 50.0)
        iso = today.isocalendar()
        _push_smart_budget_notification(
            tid=tid,
            kind="small_win_reinforcement",
            dedupe_key=f"small-win:{int(iso.year)}-W{int(iso.week)}",
            subject="Small win: you're under plan this week",
            body=(
                f"Week-to-date free spend {_usd(week_spent)} vs planned {_usd(week_budget)}.\n"
                f"Consider moving {_usd(suggestion)} to savings."
            ),
            sender="Savings Momentum",
            pushover_user_key=pushover_user_key,
        )


def _month_budget_home(
    year: int,
    month: int,
    min_occ: int = 3,
    include_stale: bool = False,
    pushover_user_key: str | None = None,
    allow_notifications: bool = False,
):
    ensure_transactions_ignore_column()
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
        ((int(tid), int(tid), month_start, today) if tid else (month_start, today)),
    )

    spent_so_far = 0.0
    cat_spent: dict[str, float] = {}
    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_norm = _norm_cat(str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT))

    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer"):
            continue

        amt = float(r["amount"] or 0.0)
        account_type = (r["accounttype"] or "").lower()
        is_spend_direction = (
            (account_type == "checking" and amt > 0)
            or (account_type == "credit" and amt != 0)
        )
        if is_spend_direction:
            spent_so_far += amt
            if category:
                cat_spent[category] = cat_spent.get(category, 0.0) + amt
            if roundup_enabled and is_roundup_eligible_tx(amt, account_type, category):
                ru = roundup_amount_from_spend(amt)
                if ru > 0:
                    spent_so_far += ru
                    cat_spent[roundup_norm] = cat_spent.get(roundup_norm, 0.0) + ru

    # 3) Income basis for this month: previous month's ACTUAL paychecks
    basis_year, basis_month = _prev_month(year, month)
    pay_income, pay_income_rows = _actual_paycheck_income_detail_for_month(
        basis_year,
        basis_month,
        spendable_account_id=3,
    )
    total_income = income_expected + pay_income
    savings_goal = _compute_monthly_savings_goal(total_income)
    # Base spend goal (before budgeting)
    base_goal = total_income - savings_goal
    spend_goal = base_goal

    # Deduct active financing installments from spendable budget
    if tid:
        try:
            from app.routers.financing import get_active_monthly_financing_total
            financing_deduction = get_active_monthly_financing_total(int(tid), year, month)
            base_goal = base_goal - financing_deduction
        except Exception:
            pass

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

    # Covered budget spend excludes only what fits inside each group's allocation.
    # Overspend in budget groups is treated as free spend.
    budgeted_spent_total = _budgeted_covered_spend_total(list(groups or []), dict(cat_spent or {}))

    # Free-to-spend excludes allocated money (including Bills)
    free_spend_goal = base_goal - allocations_total

    # spent_so_far includes budgeted categories — remove them so we don't double-count
    spent_free = spent_so_far - budgeted_spent_total
    safe_to_spend = free_spend_goal - spent_free

    _emit_over_budget_alerts(
        tid=tid,
        year=year,
        month=month,
        today=today,
        groups=list(groups or []),
        cat_spent=cat_spent,
        pushover_user_key=pushover_user_key,
    )

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

    if allow_notifications:
        _emit_smart_budget_notifications(
            tid=tid,
            year=year,
            month=month,
            today=today,
            groups=list(groups or []),
            cat_spent=dict(cat_spent or {}),
            safe_to_spend=float(safe_to_spend),
            days_left=int(days_left),
            today_limit=float(today_limit),
            spent_free=float(spent_free),
            events=list(events or []),
            min_occ=int(min_occ),
            include_stale=bool(include_stale),
            pushover_user_key=pushover_user_key,
        )

    return {
        "_calc_version": int(MONTH_BUDGET_CALC_VERSION),
        "ok": True,
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "as_of": today.isoformat(),

        "expected_income": round(total_income, 2),
        "base_income": round(income_expected, 2),
        "les_income": round(pay_income, 2),
        "income_basis_mode": "last_month_actual_paychecks",
        "income_basis_month": {
            "year": int(basis_year),
            "month": int(basis_month),
            "label": f"{int(basis_year)}-{int(basis_month):02d}",
        },
        "income_basis_paychecks": list(pay_income_rows or []),
        "income_basis_total": round(pay_income, 2),

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
        # UI-facing daily limit is floored at 0.
        "daily_limit": round(max(0.0, today_limit), 2),
        # Raw signed value for analytics/overspend logic.
        "daily_limit_raw": round(today_limit, 2),
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


def month_budget_home_cached(
    year: int,
    month: int,
    min_occ: int = 3,
    include_stale: bool = False,
    pushover_user_key: str | None = None,
    force_refresh: bool = False,
    allow_notifications: bool = False,
):
    tid = _require_tenant_id()
    today = today_local()
    is_current_month = (int(year) == int(today.year) and int(month) == int(today.month))

    def _is_fresh_for_today(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        if int(payload.get("_calc_version") or 0) != int(MONTH_BUDGET_CALC_VERSION):
            return False
        if not is_current_month:
            return True
        return str(payload.get("as_of") or "") == today.isoformat()

    month_cache_key = (
        int(tid),
        int(year),
        int(month),
        int(min_occ),
        bool(include_stale),
    )
    version_before: int | None = None

    if not force_refresh:
        version_before = home_snapshot_version_for_tenant(tid)
        snap = load_month_budget_snapshot(*month_cache_key)
        snap_version_raw = snap.get("source_version") if snap else None
        snap_version = int(snap_version_raw) if snap_version_raw is not None else -1
        if snap and snap_version == version_before:
            out = snap.get("payload")
            if _is_fresh_for_today(out):
                return out

    key = (
        f"month-budget:tenant={tid or 0}:year={int(year)}:month={int(month)}:"
        f"min_occ={int(min_occ)}:include_stale={int(bool(include_stale))}:"
        f"calc_v={int(MONTH_BUDGET_CALC_VERSION)}:user_key={(pushover_user_key or '')}"
    )
    if not force_refresh:
        cached = _cache_get(_MONTH_BUDGET_CACHE, key, MONTH_BUDGET_CACHE_TTL_SEC)
        if _is_fresh_for_today(cached):
            return cached

    out = _month_budget_home(
        year=int(year),
        month=int(month),
        min_occ=int(min_occ),
        include_stale=bool(include_stale),
        pushover_user_key=pushover_user_key,
        allow_notifications=bool(allow_notifications),
    )

    version_after = home_snapshot_version_for_tenant(tid)
    if (version_before is not None) and (version_before == version_after):
        try:
            upsert_month_budget_snapshot(
                tid=int(tid),
                year=int(year),
                month=int(month),
                min_occ=int(min_occ),
                include_stale=bool(include_stale),
                source_version=version_after,
                payload=out,
            )
        except Exception:
            pass

    _cache_set(_MONTH_BUDGET_CACHE, key, out)
    return out

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


DEFAULT_PAYCHECK_MATCH_KEYWORDS: list[str] = [
    "dfas",
    "payroll",
    "salary",
    "direct deposit",
    "mil pay",
]


def _normalize_paycheck_keywords(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_PAYCHECK_MATCH_KEYWORDS)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = str(item or "").strip().lower()
        if not s:
            continue
        if len(s) > 64:
            s = s[:64]
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 20:
            break
    return out or list(DEFAULT_PAYCHECK_MATCH_KEYWORDS)


def _get_paycheck_match_keywords() -> list[str]:
    _ensure_app_settings_pg()
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (scoped_key("paycheck_matchers"),),
    )
    raw: object = {}
    if rows:
        try:
            raw = json.loads(rows[0].get("value_json") or "{}")
        except Exception:
            raw = {}
    return _normalize_paycheck_keywords((raw or {}).get("keywords"))


def _prev_month(year: int, month: int) -> tuple[int, int]:
    y = int(year)
    m = int(month)
    if m <= 1:
        return (y - 1, 12)
    return (y, m - 1)


def _actual_paycheck_income_for_month(year: int, month: int, spendable_account_id: int = 3) -> float:
    """
    Sum ACTUAL paycheck deposits posted in the given month.
    Deposits are stored as negative amounts in this app, so we sum ABS(amount).
    """
    tid = _require_tenant_id()
    month_start = date(int(year), int(month), 1)
    month_end = date(int(year), int(month), _last_day_of_month(int(year), int(month)))

    markers = tuple(_get_paycheck_match_keywords())
    marker_sql = " OR ".join(["LOWER(TRIM(COALESCE(t.merchant,''))) LIKE %s"] * len(markers))
    marker_vals = tuple(f"%{m}%" for m in markers)

    def _sum(require_account_3: bool) -> float:
        params: list[Any] = []
        tenant_pred = ""
        if tid:
            tenant_pred = "AND t.tenant_id = %s AND a.tenant_id = %s"
            params.extend([int(tid), int(tid)])

        acct_pred = ""
        if require_account_3:
            acct_pred = "AND t.account_id = %s"
            params.append(int(spendable_account_id))

        params.extend(marker_vals)
        params.extend([month_start, month_end])

        rows = query_db(
            f"""
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE 1=1
                {tenant_pred}
                {acct_pred}
                AND t.amount < 0
                AND ABS(t.amount) >= 100
                AND ({marker_sql})
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
            SELECT COALESCE(SUM(ABS(amount)), 0)::double precision AS total
            FROM norm
            WHERE d IS NOT NULL
              AND d BETWEEN %s AND %s
            """,
            tuple(params),
        )
        return float((rows[0] or {}).get("total") or 0.0) if rows else 0.0

    primary = _sum(require_account_3=True)
    if primary > 0:
        return primary
    return _sum(require_account_3=False)


def _actual_paycheck_income_detail_for_month(
    year: int,
    month: int,
    spendable_account_id: int = 3,
) -> tuple[float, list[dict[str, Any]]]:
    """
    Returns (total, rows) for actual paycheck deposits posted in the given month.
    """
    tid = _require_tenant_id()
    month_start = date(int(year), int(month), 1)
    month_end = date(int(year), int(month), _last_day_of_month(int(year), int(month)))

    markers = tuple(_get_paycheck_match_keywords())
    marker_sql = " OR ".join(["LOWER(TRIM(COALESCE(t.merchant,''))) LIKE %s"] * len(markers))
    marker_vals = tuple(f"%{m}%" for m in markers)

    def _rows(require_account_3: bool) -> list[dict[str, Any]]:
        params: list[Any] = []
        tenant_pred = ""
        if tid:
            tenant_pred = "AND t.tenant_id = %s AND a.tenant_id = %s"
            params.extend([int(tid), int(tid)])

        acct_pred = ""
        if require_account_3:
            acct_pred = "AND t.account_id = %s"
            params.append(int(spendable_account_id))

        params.extend(marker_vals)
        params.extend([month_start, month_end])

        return query_db(
            f"""
            WITH base AS (
              SELECT
                t.account_id::bigint AS account_id,
                t.merchant AS merchant,
                ABS(t.amount::double precision) AS amount_abs,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE 1=1
                {tenant_pred}
                {acct_pred}
                AND t.amount < 0
                AND ABS(t.amount) >= 100
                AND ({marker_sql})
            ),
            norm AS (
              SELECT
                account_id,
                merchant,
                amount_abs,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT
              d::date AS d,
              account_id::bigint AS account_id,
              merchant,
              amount_abs::double precision AS amount
            FROM norm
            WHERE d IS NOT NULL
              AND d BETWEEN %s AND %s
            ORDER BY d ASC, amount_abs DESC
            """,
            tuple(params),
        )

    rows = _rows(require_account_3=True)
    if not rows:
        rows = _rows(require_account_3=False)

    out_rows: list[dict[str, Any]] = []
    total = 0.0
    for r in (rows or []):
        amt = float(r.get("amount") or 0.0)
        if amt <= 0:
            continue
        dt = r.get("d")
        date_iso = dt.isoformat() if hasattr(dt, "isoformat") else str(dt or "")
        out_rows.append(
            {
                "date": date_iso,
                "amount": round(amt, 2),
                "merchant": str(r.get("merchant") or ""),
                "account_id": int(r.get("account_id") or 0),
            }
        )
        total += amt
    return round(total, 2), out_rows

def _les_pay_income_for_month(year: int, month: int) -> float:
    py, pm = _prev_month(int(year), int(month))
    total, _rows = _actual_paycheck_income_detail_for_month(py, pm, spendable_account_id=3)
    return float(total)

    # Reuse the SAME logic as your /les/paychecks endpoint (including “actual deposit overrides”)
    # If your endpoint code is currently inline, move it into a helper and call it both places.

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


def _refresh_widget_cache_for_tenant(tid: int | None) -> None:
    try:
        from app.routers.page_payloads import touch_widget_cache_for_tenant

        touch_widget_cache_for_tenant(tid)
    except Exception:
        pass

def _apply_rule_to_existing_for_tenant(category: str, pattern: str, flags: str, tid: int | None) -> int:
    """
    Apply rule only to transactions with empty/NULL category.
    Returns rows updated.
    """
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
        if updated > 0:
            _refresh_widget_cache_for_tenant(tid)
        return updated

def _apply_rule_override_for_tenant(category: str, pattern: str, flags: str, tid: int | None) -> int:
    """
    Force override category for all matching transactions.
    Returns rows updated.
    """
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
        if updated > 0:
            _refresh_widget_cache_for_tenant(tid)
        return updated


def apply_rule_to_existing(category: str, pattern: str, flags: str) -> int:
    tid = _require_tenant_id()
    return _apply_rule_to_existing_for_tenant(category, pattern, flags, tid)


def _apply_rule_override(category: str, pattern: str, flags: str) -> int:
    tid = _require_tenant_id()
    return _apply_rule_override_for_tenant(category, pattern, flags, tid)


def _ensure_category_rule_apply_jobs_pg() -> None:
    global _RULE_APPLY_JOBS_READY
    if _RULE_APPLY_JOBS_READY:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS category_rule_apply_jobs (
              id BIGSERIAL PRIMARY KEY,
              tenant_id BIGINT NOT NULL DEFAULT 0,
              rule_id BIGINT NULL,
              mode TEXT NOT NULL,
              category TEXT NOT NULL,
              pattern TEXT NOT NULL,
              flags TEXT NOT NULL DEFAULT 'i',
              status TEXT NOT NULL DEFAULT 'queued',
              total_applied INT NOT NULL DEFAULT 0,
              error TEXT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              started_at TIMESTAMPTZ NULL,
              finished_at TIMESTAMPTZ NULL
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_category_rule_apply_jobs_tenant_created
            ON category_rule_apply_jobs(tenant_id, created_at DESC)
            """
        )
        conn.commit()
    _RULE_APPLY_JOBS_READY = True


def _category_rules_has_tenant_id(cur) -> bool:
    global _CATEGORY_RULES_HAS_TENANT_ID
    if _CATEGORY_RULES_HAS_TENANT_ID is not None:
        return bool(_CATEGORY_RULES_HAS_TENANT_ID)
    try:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = 'tenant_id'
            LIMIT 1
            """,
            (str(CATEGORY_RULES_TABLE),),
        )
        _CATEGORY_RULES_HAS_TENANT_ID = bool(cur.fetchone())
    except Exception:
        _CATEGORY_RULES_HAS_TENANT_ID = False
    return bool(_CATEGORY_RULES_HAS_TENANT_ID)


def _rule_apply_job_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)

    return {
        "id": int(row.get("id") or 0),
        "tenant_id": int(row.get("tenant_id") or 0),
        "rule_id": int(row.get("rule_id") or 0) if row.get("rule_id") is not None else None,
        "mode": str(row.get("mode") or ""),
        "status": str(row.get("status") or ""),
        "total_applied": int(row.get("total_applied") or 0),
        "error": (str(row.get("error") or "").strip() or None),
        "created_at": _iso(row.get("created_at")),
        "started_at": _iso(row.get("started_at")),
        "finished_at": _iso(row.get("finished_at")),
    }


def _spawn_rule_apply_worker(job_id: int) -> None:
    jid = int(job_id)
    with _RULE_APPLY_JOBS_LOCK:
        if jid in _RULE_APPLY_WORKERS:
            return
        _RULE_APPLY_WORKERS.add(jid)
    t = Thread(target=_run_rule_apply_job, args=(jid,), daemon=True, name=f"category-rule-apply-{jid}")
    t.start()


def _run_rule_apply_job(job_id: int) -> None:
    try:
        _ensure_category_rule_apply_jobs_pg()
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE category_rule_apply_jobs
                SET status = 'in_progress',
                    started_at = now(),
                    error = NULL
                WHERE id = %s
                  AND status IN ('queued', 'in_progress')
                RETURNING id, tenant_id, mode, category, pattern, flags
                """,
                (int(job_id),),
            )
            row = cur.fetchone()
            conn.commit()
        if not row:
            return

        tid_raw = row.get("tenant_id")
        tid = int(tid_raw) if tid_raw not in (None, "") else None
        if tid == 0:
            tid = None
        mode = str(row.get("mode") or "").strip().lower()
        category = str(row.get("category") or "")
        pattern = str(row.get("pattern") or "")
        flags = str(row.get("flags") or "i")

        if mode == "override":
            total_applied = _apply_rule_override_for_tenant(category, pattern, flags, tid)
        else:
            total_applied = _apply_rule_to_existing_for_tenant(category, pattern, flags, tid)

        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE category_rule_apply_jobs
                SET status = 'completed',
                    total_applied = %s,
                    finished_at = now(),
                    error = NULL
                WHERE id = %s
                """,
                (int(total_applied), int(job_id)),
            )
            conn.commit()
    except Exception as e:
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE category_rule_apply_jobs
                SET status = 'failed',
                    error = %s,
                    finished_at = now()
                WHERE id = %s
                """,
                (f"{type(e).__name__}: {e}", int(job_id)),
            )
            conn.commit()
    finally:
        with _RULE_APPLY_JOBS_LOCK:
            _RULE_APPLY_WORKERS.discard(int(job_id))


def _queue_rule_apply_job(
    *,
    tenant_id: int | None,
    mode: str,
    category: str,
    pattern: str,
    flags: str,
    rule_id: int | None = None,
) -> dict[str, Any]:
    _ensure_category_rule_apply_jobs_pg()
    scope_tid = _tenant_scope_key(tenant_id)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO category_rule_apply_jobs (
              tenant_id, rule_id, mode, category, pattern, flags, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'queued')
            RETURNING id, tenant_id, rule_id, mode, status, total_applied, error, created_at, started_at, finished_at
            """,
            (
                int(scope_tid),
                (int(rule_id) if rule_id is not None else None),
                str(mode or "uncategorized").strip().lower(),
                str(category or ""),
                str(pattern or ""),
                str(flags or "i"),
            ),
        )
        row = cur.fetchone() or {}
        conn.commit()

    job = _rule_apply_job_row_to_api(row)
    _spawn_rule_apply_worker(int(job.get("id") or 0))
    return job

# -----------------------------
# Endpoints
# -----------------------------
@router.post("/category-rules")
def create_category_rule(payload: RuleCreate):
    tid = _require_tenant_id()
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
            if _category_rules_has_tenant_id(cur):
                cur.execute(
                    f"""
                    INSERT INTO {CATEGORY_RULES_TABLE} (tenant_id, category, pattern, flags, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (int(_tenant_scope_key(tid)), category, pattern, flags),
                )
            else:
                cur.execute(
                    f"""
                    INSERT INTO {CATEGORY_RULES_TABLE} (category, pattern, flags, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (category, pattern, flags),
                )
            rule_row = cur.fetchone() or {}
            rule_id = int(rule_row.get("id") or 0) or None
            conn.commit()  # commit rule insert before background apply
            job = _queue_rule_apply_job(
                tenant_id=tid,
                mode="uncategorized",
                category=category,
                pattern=pattern,
                flags=flags,
                rule_id=rule_id,
            )
            return {"ok": True, "pattern": pattern, "applied": 0, "apply_job": job}
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


@router.get("/category-rules/check-all")
def check_all_category_rules(
    include_inactive: int = 0,
    uncategorized_only: int = 0,
    sample_limit: int = 3,
    apply_now: int = 0,
):
    """
    Run a full regex rule check and return match counts per rule.
    Useful for auditing rule coverage after imports.
    """
    tid = _require_tenant_id()
    only_uncat = bool(int(uncategorized_only or 0))
    do_apply = bool(int(apply_now or 0))
    sample_limit_i = max(0, min(int(sample_limit or 0), 10))

    where_rules = "" if include_inactive else "WHERE COALESCE(is_active, TRUE) = TRUE"
    rules = query_db(
        f"""
        SELECT id, category, pattern, COALESCE(flags, 'i') AS flags, COALESCE(is_active, TRUE) AS is_active
        FROM {CATEGORY_RULES_TABLE}
        {where_rules}
        ORDER BY COALESCE(is_active, TRUE) DESC, id DESC
        """
    )

    out_rows: list[dict[str, Any]] = []
    total_matches = 0
    total_uncategorized_matches = 0
    total_applied = 0

    with with_db_cursor() as (_conn, cur):
        for r in (rules or []):
            rid = int(r["id"])
            category = str(r.get("category") or "")
            pattern = str(r.get("pattern") or "")
            flags = str(r.get("flags") or "i")
            op = _pg_regex_operator(flags)

            base_where = [
                "merchant IS NOT NULL",
                "TRIM(merchant) <> ''",
                f"merchant {op} %s",
            ]
            params: list[Any] = [pattern]
            if tid:
                base_where.append("tenant_id = %s")
                params.append(int(tid))

            try:
                cur.execute(
                    f"""
                    SELECT COUNT(*)::int AS n
                    FROM transactions
                    WHERE {' AND '.join(base_where)}
                    """,
                    tuple(params),
                )
                total_n = int((cur.fetchone() or {}).get("n") or 0)

                cur.execute(
                    f"""
                    SELECT COUNT(*)::int AS n
                    FROM transactions
                    WHERE {' AND '.join(base_where)}
                      AND (category IS NULL OR TRIM(category) = '')
                    """,
                    tuple(params),
                )
                uncat_n = int((cur.fetchone() or {}).get("n") or 0)
                matched_n = uncat_n if only_uncat else total_n
                applied_n = 0
                if do_apply and uncat_n > 0:
                    apply_where = list(base_where)
                    apply_where.append("(category IS NULL OR TRIM(category) = '')")
                    cur.execute(
                        f"""
                        UPDATE transactions
                        SET category = %s
                        WHERE {' AND '.join(apply_where)}
                        """,
                        tuple([category] + params),
                    )
                    applied_n = int(cur.rowcount or 0)
                    total_applied += applied_n

                samples: list[dict[str, Any]] = []
                if sample_limit_i > 0 and matched_n > 0:
                    sample_where = list(base_where)
                    sample_params = list(params)
                    if only_uncat:
                        sample_where.append("(category IS NULL OR TRIM(category) = '')")
                    cur.execute(
                        f"""
                        SELECT id, merchant, COALESCE(NULLIF(TRIM(category), ''), '(blank)') AS category
                        FROM transactions
                        WHERE {' AND '.join(sample_where)}
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        tuple(sample_params + [sample_limit_i]),
                    )
                    samples = [dict(x) for x in (cur.fetchall() or [])]

                out_rows.append(
                    {
                        "id": rid,
                        "category": category,
                        "pattern": pattern,
                        "flags": flags,
                        "is_active": bool(r.get("is_active")),
                        "matches": int(matched_n),
                        "total_matches": int(total_n),
                        "uncategorized_matches": int(uncat_n),
                        "applied": int(applied_n),
                        "samples": samples,
                    }
                )
                total_matches += int(total_n)
                total_uncategorized_matches += int(uncat_n)
            except Exception as e:
                out_rows.append(
                    {
                        "id": rid,
                        "category": category,
                        "pattern": pattern,
                        "flags": flags,
                        "is_active": bool(r.get("is_active")),
                        "matches": 0,
                        "total_matches": 0,
                        "uncategorized_matches": 0,
                        "applied": 0,
                        "samples": [],
                        "regex_error": str(e),
                    }
                )
        if do_apply and total_applied > 0:
            _conn.commit()
            _refresh_widget_cache_for_tenant(tid)

    return {
        "ok": True,
        "checked_at": datetime.now().isoformat(),
        "include_inactive": bool(int(include_inactive or 0)),
        "uncategorized_only": only_uncat,
        "apply_now": do_apply,
        "rule_count": len(out_rows),
        "total_matches_all_rules": int(total_matches),
        "total_uncategorized_matches_all_rules": int(total_uncategorized_matches),
        "total_applied": int(total_applied),
        "rows": out_rows,
    }


@router.post("/category-rules/{rule_id}")
def update_category_rule(rule_id: int, payload: RuleUpdate):
    tid = _require_tenant_id()
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

            # Always override category on all matching transactions in background.
            conn.commit()  # commit rule edit first
            job = _queue_rule_apply_job(
                tenant_id=tid,
                mode="override",
                category=category,
                pattern=pattern,
                flags=flags,
                rule_id=int(rule_id),
            )
            return {"ok": True, "applied": 0, "match_count": 0, "apply_job": job}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/category-rules/jobs/{job_id}")
def get_category_rule_apply_job(job_id: int):
    tid = _require_tenant_id()
    _ensure_category_rule_apply_jobs_pg()
    rows = query_db(
        """
        SELECT id, tenant_id, rule_id, mode, status, total_applied, error, created_at, started_at, finished_at
        FROM category_rule_apply_jobs
        WHERE id = %s
          AND tenant_id = %s
        LIMIT 1
        """,
        (int(job_id), int(_tenant_scope_key(tid))),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="job_not_found")
    row = dict(rows[0] or {})
    job = _rule_apply_job_row_to_api(row)
    if job.get("status") in ("queued", "in_progress"):
        _spawn_rule_apply_worker(int(job.get("id") or 0))
    return {"ok": True, "job": job}

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
    cache_key = f"unknown-merchant-month:tenant={tid or 0}:first={first.isoformat()}"
    cached = _cache_get(_UNKNOWN_MERCHANT_CACHE, cache_key, UNKNOWN_MERCHANT_CACHE_TTL_SEC)
    if cached is not None:
        return cached

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

    out = {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}
    _cache_set(_UNKNOWN_MERCHANT_CACHE, cache_key, out)
    return out

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
    request: Request,
    year: int | None = None,
    month: int | None = None,
    min_occ: int = 3,
    include_stale: bool = False,
    recalc: int = 0,
):
    now = datetime.now()
    y = int(year or now.year)
    m = int(month or now.month)
    session_email = (request.session.get("google_email") or "").strip().lower()
    user_key = get_user_pushover_key_by_email(session_email)
    return month_budget_home_cached(
        y,
        m,
        min_occ=min_occ,
        include_stale=include_stale,
        pushover_user_key=user_key,
        force_refresh=bool(int(recalc or 0)),
    )


@router.get("/debug/home-snapshot")
def debug_home_snapshot(
    year: int | None = None,
    month: int | None = None,
    min_occ: int = 3,
    include_stale: bool = False,
):
    tid = _require_tenant_id()
    ensure_home_snapshot_cache_pg()

    now = today_local()
    y = int(year or now.year)
    m = int(month or now.month)
    v = home_snapshot_version_for_tenant(tid)

    rows = query_db(
        """
        SELECT source_version, updated_at
        FROM home_snapshot_month_budget
        WHERE tenant_id = %s
          AND year = %s
          AND month = %s
          AND min_occ = %s
          AND include_stale = %s
        LIMIT 1
        """,
        (int(tid), y, m, int(min_occ), bool(include_stale)),
    )
    row = rows[0] if rows else {}
    source_version_raw = row.get("source_version") if row else None
    source_version = int(source_version_raw) if source_version_raw is not None else -1
    is_fresh = bool(rows) and (source_version == int(v))
    updated_at = row.get("updated_at")

    return {
        "ok": True,
        "tenant_id": int(tid),
        "year": y,
        "month": m,
        "min_occ": int(min_occ),
        "include_stale": bool(include_stale),
        "current_version": int(v),
        "snapshot_exists": bool(rows),
        "snapshot_source_version": source_version if rows else None,
        "snapshot_is_fresh": bool(is_fresh),
        "snapshot_updated_at": (
            updated_at.isoformat() if hasattr(updated_at, "isoformat") else (str(updated_at) if updated_at else None)
        ),
    }

@router.get("/page/budget")
def page_budget(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    min_occ: int = 3,
    include_stale: bool = False,
    recalc: int = 0,
):
    tid = _require_tenant_id()
    now = datetime.now()
    y = int(year or now.year)
    m = int(month or now.month)
    session_email = (request.session.get("google_email") or "").strip().lower()
    user_key = get_user_pushover_key_by_email(session_email)

    mb = month_budget_home_cached(
        y,
        m,
        min_occ=min_occ,
        include_stale=include_stale,
        pushover_user_key=user_key,
        force_refresh=bool(int(recalc or 0)),
    )

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

    # ------------------------------------------------------------
    # Synthetic budget group: Savings goal
    # - Allocated equals computed monthly savings goal
    # - No categories
    # - "Spent" tracks only free-spend overspend (safe_to_spend < 0)
    # ------------------------------------------------------------
    try:
        savings_goal_alloc = float((mb or {}).get("savings_goal") or 0.0)
    except Exception:
        savings_goal_alloc = 0.0
    try:
        safe_to_spend_now = float((mb or {}).get("safe_to_spend") or 0.0)
    except Exception:
        safe_to_spend_now = 0.0
    savings_goal_spent = max(0.0, -safe_to_spend_now)

    has_savings_goal_group = any((_norm_name(g.get("name", "")) == "savings goal") for g in (groups or []))
    if not has_savings_goal_group:
        groups = list(groups or [])
        groups.append(
            {
                "id": -2,  # synthetic
                "name": "Savings goal",
                "allocated": savings_goal_alloc,
                "cap": None,
                "categories": [],
                "synthetic_kind": "savings_goal",
                "synthetic_spent": savings_goal_spent,
            }
        )

    # decorate groups with spent/remaining using mb.category_spent
    cat_spent = (mb.get("category_spent") or {}) if isinstance(mb, dict) else {}
    out_groups = []
    for g in groups:
        if str(g.get("synthetic_kind") or "") == "savings_goal":
            g_spent = float(g.get("synthetic_spent") or 0.0)
        else:
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
                "read_only": bool(str(g.get("synthetic_kind") or "") == "savings_goal"),
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
        ) u
        ORDER BY LOWER(category) ASC
        """,
        ((int(tid),) if tid else ()),
    )

    norm_to_display = {}
    for r in canon_rows:
        c = (r.get("category") or "").strip()
        if not c:
            continue
        n = _norm_cat(c)
        # first one wins (stable enough, and matches how your app already thinks about categories)
        norm_to_display.setdefault(n, c)
    norm_to_display.setdefault(ROUNDUP_CATEGORY_NORM, ROUNDUP_CATEGORY_DEFAULT)

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


def _tenant_scope_key(tid: int | None) -> int:
    return int(tid or 0)
