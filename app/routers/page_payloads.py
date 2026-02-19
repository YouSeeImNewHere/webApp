from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta
from copy import deepcopy
import time
from threading import Lock

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import with_db_cursor, query_db

from app.core.config import CREDIT_UTILIZATION_CAP, MULTI_TENANT_ENABLED
from app.core.home_snapshot_cache import (
    ensure_home_snapshot_cache_pg,
    home_snapshot_version_for_tenant,
    load_page_home_snapshot,
    upsert_page_home_snapshot,
)
from app.core.time import today_local, now_local
from app.core.tenancy import current_tenant_id
from app.core.roundups import (
    ROUNDUP_CATEGORY_DEFAULT,
    get_roundup_settings,
    is_roundup_eligible_tx,
    roundup_amount_from_spend,
)

# Import the underlying route helpers we bundle into page payloads.
from app.routers.transactions import transactions, transactions_all, account_transactions
from app.routers.analytics import category_totals_month, _last_day_of_month, parse_iso
from app.routers.notifications import unread_count
from app.routers.accounts import bank_totals, account_info
from app.routers.category_rules import month_budget_home_cached, unknown_merchant_total_month
from app.routers.budget_groups import _get_budget_groups_for_month, _norm_cat, _norm_name
from app.routers.recurring import recurring_calendar
from app.routers.les import les_paychecks, LESPaychecksRequest, LESProfileModel

router = APIRouter()

WIDGET_SUMMARY_CACHE_TTL_SEC = 90
_WIDGET_SUMMARY_CACHE: Dict[str, Dict[str, Any]] = {}
_WIDGET_REFRESH_READY = False
WIDGET_VERSION_CACHE_TTL_SEC = 15 * 60
_WIDGET_VERSION_CACHE: Dict[str, Dict[str, Any]] = {}
_WIDGET_VERSION_CACHE_LOCK = Lock()
PAGE_PAYLOAD_CACHE_TTL_SEC = 30
_PAGE_PAYLOAD_CACHE: dict[str, dict[str, Any]] = {}
_PAGE_PAYLOAD_CACHE_LOCK = Lock()
DAY_LIMIT_CACHE_TTL_SEC = 20

# =============================================================================
# Page payload endpoints (one request per page)
# =============================================================================

def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


def _widget_tenant_key(tid: Optional[int]) -> int:
    return int(tid) if tid else 0


def _ensure_widget_refresh_tracking_pg() -> None:
    global _WIDGET_REFRESH_READY
    if _WIDGET_REFRESH_READY:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS widget_refresh_state (
              tenant_id INT PRIMARY KEY,
              version BIGINT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE OR REPLACE FUNCTION trg_widget_refresh_transactions()
            RETURNS trigger AS $$
            DECLARE
              tid INT;
            BEGIN
              IF TG_OP = 'DELETE' THEN
                tid := COALESCE(OLD.tenant_id, 0)::int;
              ELSE
                tid := COALESCE(NEW.tenant_id, 0)::int;
              END IF;

              INSERT INTO widget_refresh_state (tenant_id, version, updated_at)
              VALUES (tid, 1, now())
              ON CONFLICT (tenant_id)
              DO UPDATE SET
                version = widget_refresh_state.version + 1,
                updated_at = now();

              IF TG_OP = 'DELETE' THEN
                RETURN OLD;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cur.execute("DROP TRIGGER IF EXISTS widget_refresh_transactions_iud ON transactions")
        cur.execute(
            """
            CREATE TRIGGER widget_refresh_transactions_iud
            AFTER INSERT OR UPDATE OR DELETE ON transactions
            FOR EACH ROW EXECUTE FUNCTION trg_widget_refresh_transactions()
            """
        )
        conn.commit()
    _WIDGET_REFRESH_READY = True


def _widget_version_for_tenant(tid: Optional[int]) -> int:
    _ensure_widget_refresh_tracking_pg()
    tkey = _widget_tenant_key(tid)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "SELECT version FROM widget_refresh_state WHERE tenant_id = %s",
            (tkey,),
        )
        row = cur.fetchone() or {}
        if not row:
            cur.execute(
                """
                INSERT INTO widget_refresh_state (tenant_id, version, updated_at)
                VALUES (%s, 0, now())
                RETURNING version
                """,
                (tkey,),
            )
            row = cur.fetchone() or {}
        conn.commit()
    return int(row.get("version") or 0)


def _widget_version_for_tenant_cached(tid: Optional[int]) -> int:
    tkey = _widget_tenant_key(tid)
    cache_key = f"tenant={int(tkey)}"
    now_ts = time.time()

    with _WIDGET_VERSION_CACHE_LOCK:
        row = _WIDGET_VERSION_CACHE.get(cache_key)
        if row:
            ts = float(row.get("ts") or 0.0)
            if (now_ts - ts) < WIDGET_VERSION_CACHE_TTL_SEC:
                return int(row.get("version") or 0)

    version = _widget_version_for_tenant(tid)
    with _WIDGET_VERSION_CACHE_LOCK:
        _WIDGET_VERSION_CACHE[cache_key] = {"ts": now_ts, "version": int(version)}
    return int(version)

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


def _payload_cache_get(key: str, ttl_sec: int = PAGE_PAYLOAD_CACHE_TTL_SEC):
    now_ts = time.time()
    with _PAGE_PAYLOAD_CACHE_LOCK:
        row = _PAGE_PAYLOAD_CACHE.get(key)
        if not row:
            return None
        ts = float(row.get("ts") or 0.0)
        if now_ts - ts > float(ttl_sec):
            _PAGE_PAYLOAD_CACHE.pop(key, None)
            return None
        return deepcopy(row.get("data"))


def _payload_cache_set(key: str, payload: Dict[str, Any]):
    with _PAGE_PAYLOAD_CACHE_LOCK:
        _PAGE_PAYLOAD_CACHE[key] = {"ts": time.time(), "data": deepcopy(payload)}

@router.get("/page/home")
def page_home(
    tx_limit: int = Query(15, ge=1, le=200),
):
    """
    One-shot payload for home.html/home.js
    Bundle the things home currently fetches separately.
    """
    tid = _require_tenant_id()
    tkey = int(tid or 0)
    v_before = home_snapshot_version_for_tenant(tid)
    cache_key = f"page:home:tenant={tkey}:tx_limit={int(tx_limit)}:v={int(v_before)}"
    cached = _payload_cache_get(cache_key)
    if cached is not None:
        return cached

    snap = load_page_home_snapshot(tkey, int(tx_limit))
    snap_version_raw = snap.get("source_version") if snap else None
    snap_version = int(snap_version_raw) if snap_version_raw is not None else -1
    if snap and snap_version == int(v_before):
        out = snap.get("payload")
        if isinstance(out, dict):
            if "unknown_merchant_total_month" not in out:
                try:
                    out["unknown_merchant_total_month"] = unknown_merchant_total_month()
                    upsert_page_home_snapshot(
                        tid=tkey,
                        tx_limit=int(tx_limit),
                        source_version=int(v_before),
                        payload=out,
                    )
                except Exception:
                    pass
            _payload_cache_set(cache_key, out)
            return out

    now = now_local()
    payload: Dict[str, Any] = {
        "transactions": transactions(limit=tx_limit),
        "category_totals_month": category_totals_month(),
        "unknown_merchant_total_month": unknown_merchant_total_month(),
        "notifications_unread": unread_count(),
        "bank_totals": bank_totals(),
        # add this if you have month_budget() defined in this file:
        "month_budget": month_budget_home_cached(now.year, now.month),
        "day_limit": day_limit(recalc=0),
    }
    v_after = home_snapshot_version_for_tenant(tid)
    if int(v_before) == int(v_after):
        try:
            upsert_page_home_snapshot(
                tid=tkey,
                tx_limit=int(tx_limit),
                source_version=int(v_after),
                payload=payload,
            )
        except Exception:
            pass
    _payload_cache_set(cache_key, payload)
    return payload


@router.get("/debug/page-home-snapshot")
def debug_page_home_snapshot(
    tx_limit: int = Query(15, ge=1, le=200),
):
    tid = _require_tenant_id()
    ensure_home_snapshot_cache_pg()
    tkey = int(tid or 0)
    v = home_snapshot_version_for_tenant(tid)

    rows = query_db(
        """
        SELECT source_version, updated_at
        FROM home_snapshot_page_home
        WHERE tenant_id = %s
          AND tx_limit = %s
        LIMIT 1
        """,
        (tkey, int(tx_limit)),
    )
    row = rows[0] if rows else {}
    source_version_raw = row.get("source_version") if row else None
    source_version = int(source_version_raw) if source_version_raw is not None else -1
    is_fresh = bool(rows) and (source_version == int(v))
    updated_at = row.get("updated_at")

    return {
        "ok": True,
        "tenant_id": tkey,
        "tx_limit": int(tx_limit),
        "current_version": int(v),
        "snapshot_exists": bool(rows),
        "snapshot_source_version": source_version if rows else None,
        "snapshot_is_fresh": bool(is_fresh),
        "snapshot_updated_at": (
            updated_at.isoformat() if hasattr(updated_at, "isoformat") else (str(updated_at) if updated_at else None)
        ),
    }

@router.get("/page/account/{account_id}")
def page_account(
    account_id: int,
    tx_limit: int = Query(200, ge=1, le=2000),
):
    """
    One-shot payload for account.html/account.js
    """
    tid = _require_tenant_id()
    cache_key = f"page:account:tenant={tid or 0}:account_id={int(account_id)}:tx_limit={int(tx_limit)}"
    cached = _payload_cache_get(cache_key)
    if cached is not None:
        return cached

    payload: Dict[str, Any] = {
        "account": account_info(account_id=account_id),                        # existing route fn【turn10file2†app_postgres.py†L1-L12】
        "transactions": account_transactions(account_id=account_id, limit=tx_limit),  # existing route fn【turn10file0†app_postgres.py†L54-L99】
        # Add any account charts/series endpoints your account.js calls:
        # "account_series": account_series(account_id=account_id, start=..., end=...),
    }
    _payload_cache_set(cache_key, payload)
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
    tid = _require_tenant_id()
    cache_key = f"page:all-transactions:tenant={tid or 0}:limit={int(limit)}:offset={int(offset)}"
    cached = _payload_cache_get(cache_key)
    if cached is not None:
        return cached

    payload: Dict[str, Any] = {
        "rows": transactions_all(limit=limit, offset=offset),
        "notifications_unread": unread_count(),
    }
    _payload_cache_set(cache_key, payload)
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
    tid = _require_tenant_id()
    cache_key = f"page:category:tenant={tid or 0}:c={c}"
    cached = _payload_cache_get(cache_key)
    if cached is not None:
        return cached

    payload: Dict[str, Any] = {
        "category": c,
        # "trend": category_trend(c=c),
        # "transactions": category_transactions(c=c, limit=500, offset=0),
        "notifications_unread": unread_count(),
    }
    _payload_cache_set(cache_key, payload)
    return payload

@router.get("/page/recurring")
def page_recurring():
    """
    One-shot payload for recurring.html/recurring_page.js
    Bundle whatever recurring_page.js fetches.
    """
    tid = _require_tenant_id()
    cache_key = f"page:recurring:tenant={tid or 0}"
    cached = _payload_cache_get(cache_key)
    if cached is not None:
        return cached

    payload: Dict[str, Any] = {
        # If you have endpoints like get_recurring() / calendar preview, add them:
        # "recurring": get_recurring_endpoint(...),
        # "ignored_preview": get_ignored_merchants_preview(...),
        "notifications_unread": unread_count(),
    }
    _payload_cache_set(cache_key, payload)
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
    tid = _require_tenant_id()
    tenant_where = "AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""

    # shared normalization: postedDate/purchaseDate are strings like MM/DD/YY or MM/DD/YYYY (or 'unknown')
    base_cte = f"""
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
        {tenant_where}
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
            ((int(tid), int(tid), limit) if tid else (limit,)),
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
        ((int(tid), int(tid), limit) if tid else (limit,)),
    )
    return [dict(r) for r in rows]

@router.get("/widget/summary")
def widget_summary(
    widget_version: Optional[int] = Query(default=None),
):
    tid = _require_tenant_id()
    version = int(widget_version) if widget_version is not None else _widget_version_for_tenant_cached(tid)
    cache_key = f"tenant={_widget_tenant_key(tid)}"
    now_ts = time.time()
    cache_row = _WIDGET_SUMMARY_CACHE.get(cache_key) or {}
    cached_ts = float(cache_row.get("ts") or 0.0)
    cached_data = cache_row.get("data")
    cached_version = int(cache_row.get("version") or -1)
    if (
        cached_data
        and cached_version == version
        and (now_ts - cached_ts) < WIDGET_SUMMARY_CACHE_TTL_SEC
    ):
        return deepcopy(cached_data)

    bt = bank_totals()     # uses your existing logic :contentReference[oaicite:3]{index=3}
    n = now_local()
    mb = month_budget_home_cached(n.year, n.month)
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

    payload = {
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
        "widget_version": version,
        "meta": {"cron": "OK"}
    }
    _WIDGET_SUMMARY_CACHE[cache_key] = {"ts": now_ts, "version": version, "data": payload}
    return deepcopy(payload)


@router.get("/widget/version")
def widget_version():
    tid = _require_tenant_id()
    version = _widget_version_for_tenant_cached(tid)
    return {"ok": True, "widget_version": version}

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


class HomeUpcomingPayloadRequest(BaseModel):
    days_ahead: int = 30
    account_id: Optional[int] = None
    min_occ: int = 3
    include_stale: bool = False
    profile: Optional[LESProfileModel] = None


def _iter_months_between(start_d: date, end_d: date):
    y, m = int(start_d.year), int(start_d.month)
    end_y, end_m = int(end_d.year), int(end_d.month)
    while (y < end_y) or (y == end_y and m <= end_m):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def _dedupe_upcoming_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in events or []:
        key = "|".join(
            [
                str(e.get("date") or ""),
                str(e.get("pay_target") or ""),
                str(e.get("merchant") or ""),
                str(e.get("cadence") or ""),
                str(float(e.get("amount") or 0.0)),
                str(int(e.get("account_id") or 0)),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


@router.post("/page/home/upcoming")
def page_home_upcoming(req: HomeUpcomingPayloadRequest):
    days_ahead = max(1, min(int(req.days_ahead or 30), 120))
    start_d = today_local()
    end_d = start_d + timedelta(days=days_ahead - 1)

    events: list[dict[str, Any]] = []
    for y, m in _iter_months_between(start_d, end_d):
        cal = recurring_calendar(year=int(y), month=int(m), min_occ=int(req.min_occ), include_stale=bool(req.include_stale))
        events.extend(list((cal or {}).get("events") or []))

        if req.profile:
            pay = les_paychecks(LESPaychecksRequest(year=int(y), month=int(m), profile=req.profile))
            events.extend(list((pay or {}).get("events") or []))

    aid_filter = int(req.account_id) if (req.account_id is not None) else None
    filtered: list[dict[str, Any]] = []
    for e in events:
        d_raw = str(e.get("date") or "").strip()
        try:
            d = datetime.strptime(d_raw, "%Y-%m-%d").date()
        except Exception:
            continue
        if d < start_d or d > end_d:
            continue
        if aid_filter is not None and int(e.get("account_id") or -1) != aid_filter:
            continue
        filtered.append(dict(e))

    out = _dedupe_upcoming_events(filtered)
    out.sort(key=lambda e: (str(e.get("date") or ""), str(e.get("merchant") or ""), abs(float(e.get("amount") or 0.0))))
    return {
        "ok": True,
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "days_ahead": days_ahead,
        "events": out,
    }

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
    return FileResponse("static/pages/category/category.html")

def _category_totals_month_display(year: int, month: int):
    tid = _require_tenant_id()
    # month range
    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    base_cte = f"""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
          TRIM(t.category) AS category,
          t.amount::double precision AS amount
        FROM transactions t
        WHERE t.category IS NOT NULL
          AND TRIM(t.category) <> ''
          {"AND t.tenant_id = %s" if tid else ""}
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
        ((int(tid), month_start, month_end) if tid else (month_start, month_end)),
    )
    out = [{"category": r["category"], "spent": float(r["total"] or 0.0)} for r in rows]

    cfg = get_roundup_settings()
    if bool(cfg.get("enabled", False)):
        ru_cat = str(cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT)
        spend_rows = query_db(
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
            SELECT amount, category, accountType
            FROM norm
            WHERE d IS NOT NULL
              AND d >= %s AND d <= %s
            """,
            ((int(tid), int(tid), month_start, month_end) if tid else (month_start, month_end)),
        )
        ru_total = 0.0
        for r in spend_rows:
            amt = float(r.get("amount") or 0.0)
            category = (r.get("category") or "").strip().lower()
            account_type = (r.get("accounttype") or "").strip().lower()
            if is_roundup_eligible_tx(amt, account_type, category):
                ru_total += roundup_amount_from_spend(amt)
        if ru_total > 0:
            out.append({"category": ru_cat, "spent": round(ru_total, 2)})

    out.sort(key=lambda x: float(x.get("spent") or 0.0), reverse=True)
    return out

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
    tid = _require_tenant_id()

    # Pull tx rows for *that day*
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
    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_norm = _norm_cat(str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT))

    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        # Exclusions from DAILY spend (still count in monthly math elsewhere)
        if category in ("card payment", "transfer", "cash withdrawal"):
            continue

        amt = float(r["amount"] or 0.0)
        account_type = (r["accounttype"] or "").lower()
        if account_type in ("checking", "credit") and amt > 0:
            spent_today += amt
            if category:
                cat_spent[category] = cat_spent.get(category, 0.0) + amt
            if roundup_enabled and is_roundup_eligible_tx(amt, account_type, category):
                ru = roundup_amount_from_spend(amt)
                if ru > 0:
                    spent_today += ru
                    cat_spent[roundup_norm] = cat_spent.get(roundup_norm, 0.0) + ru

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

def _compute_extra_saved_rollover(
    tid: int,
    year: int,
    month: int,
    today: date,
    fallback_today_baseline: float = 0.0,
) -> tuple[float, list[dict[str, Any]], int]:
    """
    Rollover rules:
      - Completed days (d < today): move full (baseline - spent_free) into extra-saved.
      - Today:
          * positive leftover is NOT added yet (only at end of day)
          * overspend (negative leftover) reduces extra-saved immediately
      - extra-saved is floored at 0 (never negative)
    """
    month_start = date(year, month, 1)

    rows = query_db(
        """
        SELECT day, baseline, computed_at
        FROM daily_limit_snapshot
        WHERE day >= %s AND day <= %s AND tenant_id = %s
        ORDER BY day ASC
        """,
        (month_start, today, int(tid)),
    )

    by_day: dict[date, dict[str, Any]] = {}
    for r in rows:
        d = r["day"]
        by_day[d] = {
            "baseline": float(r.get("baseline") or 0.0),
            "computed_at": r.get("computed_at"),
        }

    # If today's snapshot does not exist yet, use today's computed baseline.
    if today not in by_day:
        by_day[today] = {
            "baseline": float(fallback_today_baseline or 0.0),
            "computed_at": None,
        }

    balance = 0.0
    days_counted = 0
    out_days: list[dict[str, Any]] = []

    dcur = month_start
    while dcur <= today:
        item = by_day.get(dcur)
        if not item:
            dcur += timedelta(days=1)
            continue

        baseline = float(item.get("baseline") or 0.0)
        spent_today, spent_budgeted, spent_free = _compute_spent_free_for_day(dcur)
        leftover = baseline - spent_free

        # Apply rollover rules.
        if dcur < today:
            applied = leftover
        else:
            applied = leftover if leftover < 0 else 0.0

        balance = max(0.0, balance + applied)
        days_counted += 1

        computed_at = item.get("computed_at")
        out_days.append(
            {
                "day": dcur.isoformat(),
                "baseline": round(baseline, 2),
                "spent_today_total": round(float(spent_today or 0.0), 2),
                "spent_today_budgeted": round(float(spent_budgeted or 0.0), 2),
                "spent_today_free": round(float(spent_free or 0.0), 2),
                "leftover": round(float(leftover or 0.0), 2),
                "applied_to_extra_saved": round(float(applied or 0.0), 2),
                "extra_saved_after_day": round(float(balance or 0.0), 2),
                "computed_at": (
                    computed_at.isoformat()
                    if hasattr(computed_at, "isoformat")
                    else (str(computed_at) if computed_at is not None else None)
                ),
            }
        )
        dcur += timedelta(days=1)

    return balance, out_days, days_counted

@router.get("/day-limit")
def day_limit(recalc: int = 0):
    """
    Daily baseline ($/day) is computed once per day and stored.
    Remaining today updates live as you add purchases:
      remaining_today = baseline - spent_free_today
    Use ?recalc=1 to force a new baseline for today.
    """
    tid = _require_tenant_id()
    _ensure_daily_limit_snapshot_pg(tid)

    today = today_local()
    cache_key = f"day-limit:tenant={int(tid)}:day={today.isoformat()}"
    force_refresh = bool(int(recalc or 0))
    if not force_refresh:
        cached = _payload_cache_get(cache_key, ttl_sec=DAY_LIMIT_CACHE_TTL_SEC)
        if cached is not None:
            return cached

    # Get or compute today's baseline
    row = query_db(
        "SELECT day, baseline, computed_at FROM daily_limit_snapshot WHERE day=%s AND tenant_id=%s",
        (today, int(tid)),
    )
    if force_refresh or not row:
        mb = month_budget_home_cached(today.year, today.month)
        baseline = float(mb.get("daily_limit") or 0.0)

        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO daily_limit_snapshot(day, baseline, computed_at, tenant_id)
                VALUES (%s, %s, now(), %s)
                ON CONFLICT (tenant_id, day)
                DO UPDATE SET baseline=EXCLUDED.baseline, computed_at=now()
                """,
                (today, baseline, int(tid)),
            )
            conn.commit()

        row = query_db(
            "SELECT day, baseline, computed_at FROM daily_limit_snapshot WHERE day=%s AND tenant_id=%s",
            (today, int(tid)),
        )

    baseline = float(row[0]["baseline"])
    computed_at = row[0]["computed_at"]

    spent_today, spent_budgeted, spent_free = _compute_spent_free_for_day(today)
    remaining = baseline - spent_free

    out = {
        "ok": True,
        "day": today.isoformat(),
        "baseline": round(baseline, 2),
        "computed_at": computed_at.isoformat() if hasattr(computed_at, "isoformat") else str(computed_at),

        "spent_today_total": round(spent_today, 2),
        "spent_today_budgeted": round(spent_budgeted, 2),
        "spent_today_free": round(spent_free, 2),

        "remaining_today": round(remaining, 2),
    }
    _payload_cache_set(cache_key, out)
    return out

@router.get("/extra-saved")
def extra_saved():
    """
    Extra-saved rollover bank:
      - Completed days add full leftover (baseline - spent_free)
      - Today's positive leftover is not added yet
      - Today's overspend reduces extra-saved immediately
      - Bank is floored at zero
    """
    tid = _require_tenant_id()
    _ensure_daily_limit_snapshot_pg(tid)

    today = today_local()
    mb = month_budget_home_cached(today.year, today.month)
    fallback_today_baseline = float((mb or {}).get("daily_limit") or 0.0)
    total_extra, _, days_counted = _compute_extra_saved_rollover(
        tid=int(tid),
        year=today.year,
        month=today.month,
        today=today,
        fallback_today_baseline=fallback_today_baseline,
    )

    return {
        "ok": True,
        "extra_saved": round(total_extra, 2),
        "days_counted": days_counted,
    }

@router.get("/extra-saved-detail")
def extra_saved_detail():
    """
    Day-by-day rollover breakdown for extra-saved.
    Includes:
      - leftover (baseline - spent_free)
      - applied_to_extra_saved (what actually changed the bank that day)
      - extra_saved_after_day
    """
    tid = _require_tenant_id()
    _ensure_daily_limit_snapshot_pg(tid)

    today = today_local()
    month_start = date(today.year, today.month, 1)
    mb = month_budget_home_cached(today.year, today.month)
    fallback_today_baseline = float((mb or {}).get("daily_limit") or 0.0)
    total, days, _ = _compute_extra_saved_rollover(
        tid=int(tid),
        year=today.year,
        month=today.month,
        today=today,
        fallback_today_baseline=fallback_today_baseline,
    )

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
    tid = _require_tenant_id()
    today = today_local()
    month_start = date(today.year, today.month, 1)

    start_date = parse_iso(start) if (start or "").strip() else month_start
    end_date = parse_iso(end) if (end or "").strip() else today
    end_excl = end_date + timedelta(days=1)

    cat = (category or "").strip()
    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT).strip() or ROUNDUP_CATEGORY_DEFAULT

    if roundup_enabled and cat.lower() == roundup_cat.lower():
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
                {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
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
            SELECT id, d, amount, merchant, category, bank, card, accountType
            FROM norm
            WHERE d IS NOT NULL
              AND d >= %s AND d < %s
              AND LOWER(COALESCE(category,'')) NOT IN ('card payment','transfer')
            ORDER BY d DESC, id DESC
            LIMIT 500
            """,
            ((int(tid), int(tid), start_date, end_excl) if tid else (start_date, end_excl)),
        )

        out = []
        for r in rows:
            amt = float(r.get("amount") or 0.0)
            account_type = (r.get("accounttype") or "").strip().lower()
            category_lc = (r.get("category") or "").strip().lower()
            if not is_roundup_eligible_tx(amt, account_type, category_lc):
                continue
            ru = roundup_amount_from_spend(amt)
            if ru <= 0:
                continue
            out.append(
                {
                    "id": f"{r.get('id')}_roundup",
                    "date": r["d"].isoformat() if r.get("d") else None,
                    "amount": round(float(ru), 2),
                    "merchant": r.get("merchant"),
                    "category": roundup_cat,
                    "bank": r.get("bank"),
                    "card": r.get("card"),
                }
            )
        return {"ok": True, "transactions": out}

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
            {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
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
        tuple(([int(tid), int(tid)] if tid else []) + params),
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
    tid = _require_tenant_id()
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
    mb = month_budget_home_cached(y, m)

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
        f"""
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
            {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
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
        ((int(tid), int(tid), start_date, end_excl) if tid else (start_date, end_excl)),
    )[0]

    # Totals per explicit category (excluding null/empty). We'll decide included vs excluded in Python.
    cats = query_db(
        f"""
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
            {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
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
        ((int(tid), int(tid), start_date, end_excl) if tid else (start_date, end_excl)),
    )

    roundup_cfg = get_roundup_settings()
    roundup_enabled = bool(roundup_cfg.get("enabled", False))
    roundup_cat = str(roundup_cfg.get("category") or ROUNDUP_CATEGORY_DEFAULT).strip() or ROUNDUP_CATEGORY_DEFAULT
    roundup_total = 0.0
    if roundup_enabled:
        roundup_rows = query_db(
            f"""
            WITH base AS (
              SELECT
                CASE
                  WHEN LOWER(a.accountType) = 'credit' THEN ABS(t.amount::double precision)
                  ELSE t.amount::double precision
                END AS amount,
                LOWER(a.accountType) AS accountType,
                LOWER(TRIM(COALESCE(t.category,''))) AS category_lc,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE LOWER(a.accountType) IN ('checking','credit')
                {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
                AND (
                  (LOWER(a.accountType) = 'checking' AND t.amount::double precision > 0)
                  OR
                  (LOWER(a.accountType) = 'credit' AND t.amount::double precision <> 0)
                )
            ),
            norm AS (
              SELECT
                amount,
                accountType,
                category_lc,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT amount, accountType, category_lc
            FROM norm
            WHERE d IS NOT NULL AND d >= %s AND d < %s
            """,
            ((int(tid), int(tid), start_date, end_excl) if tid else (start_date, end_excl)),
        )
        for rr in roundup_rows:
            amt = float(rr.get("amount") or 0.0)
            account_type = (rr.get("accounttype") or "").strip().lower()
            category_lc = (rr.get("category_lc") or "").strip().lower()
            if is_roundup_eligible_tx(amt, account_type, category_lc):
                roundup_total += roundup_amount_from_spend(amt)

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
    if roundup_enabled and roundup_total > 0:
        roundup_norm = _norm_cat(roundup_cat)
        norm_to_display.setdefault(roundup_norm, roundup_cat)
        norm_to_total[roundup_norm] = norm_to_total.get(roundup_norm, 0.0) + float(roundup_total)

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
        "total_all": float((row.get("total_all") or 0) + roundup_total),
        "roundups_total": float(roundup_total or 0.0),

        "excluded": excluded,
        "included": included,
    }
