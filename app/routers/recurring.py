from __future__ import annotations

import re
import json
import calendar
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.routers.analytics import _last_day_of_month
from app.routers.categories import get_category_from_db_pg
from db import with_db_cursor, query_db
from recurring import get_recurring, _norm_merchant, _amount_bucket, get_ignored_merchants_preview
from app.core.time import today_local

router = APIRouter()

# =============================================================================
# Recurring (Postgres) — ported from recurring.py
# =============================================================================

# -----------------------------
# Transfer peer helpers (Postgres)
# -----------------------------
def _account_label_pg(account_id: int) -> str:
    rows = query_db(
        "SELECT institution, name FROM accounts WHERE id = %s LIMIT 1",
        (int(account_id),),
    )
    if not rows:
        return f"Account {account_id}"
    r = rows[0]
    return f'{r["institution"]} {r["name"]}'.strip()

def _find_transfer_peer_account_pg(tx_id: int, window_days: int = 10) -> int | None:
    """
    Given a transfer tx_id, find the 'other side' transfer account within +/- window_days
    matching opposite sign and same abs(amount) cents, different account_id.
    """
    # 1) load the anchor tx (normalized date)
    anchor = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.account_id::int AS account_id,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE t.id = %s
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
        SELECT id, account_id, amount, category, d
        FROM norm
        LIMIT 1
        """,
        (int(tx_id),),
    )
    if not anchor:
        return None

    a = anchor[0]
    if not a.get("d"):
        return None

    try:
        amt = float(a["amount"] or 0.0)
    except Exception:
        return None
    if amt == 0:
        return None

    aid = int(a["account_id"])
    d0: date = a["d"]
    cents = int(round(abs(amt) * 100))
    sign = 1 if amt > 0 else -1

    d_min = d0 - timedelta(days=int(window_days))
    d_max = d0 + timedelta(days=int(window_days))

    # 2) find the best opposite-sign peer in window
    peer = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.account_id::int AS account_id,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE LOWER(TRIM(COALESCE(t.category,''))) IN ('transfer','card payment')
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
        SELECT account_id, d, amount
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
          AND account_id <> %s
          AND (round(abs(amount) * 100))::int = %s
          AND (
            (%s =  1 AND amount < 0) OR
            (%s = -1 AND amount > 0)
          )
        ORDER BY ABS(d - %s) ASC, id DESC
        LIMIT 1
        """,
        (d_min, d_max, aid, cents, sign, sign, d0),
    )
    if not peer:
        return None
    return int(peer[0]["account_id"])

# =============================================================================
# Recurring + category + interest helpers (Postgres ports)
# =============================================================================

# =============================================================================
# Interest rate helpers (Postgres)
# =============================================================================

def _get_rate_rows(cur, account_id: int) -> List[Tuple[date, float]]:
    """
    Postgres version:
      - reads effective-dated APR rows from interest_rates
      - returns sorted list[(effective_date: date, apr: float)]
    """
    cur.execute(
        """
        SELECT effective_date, apr
        FROM interest_rates
        WHERE account_id = %s
        ORDER BY effective_date ASC
        """,
        (int(account_id),),
    )
    rows = cur.fetchall() or []

    out: List[Tuple[date, float]] = []
    for r in rows:
        try:
            eff = r["effective_date"]
            # psycopg2 typically returns date for DATE columns
            if isinstance(eff, date):
                eff_d = eff
            else:
                eff_d = datetime.strptime(str(eff), "%Y-%m-%d").date()
            out.append((eff_d, float(r["apr"])))
        except Exception:
            pass
    return out

def _interest_cycle_window(year: int, month: int, post_day: int | None):
    """
    Postgres version (DB-agnostic logic).

    Returns (start_date, end_date_exclusive, post_date) for the interest accrual period
    that pays on post_day in (year, month).

    Example: post_day=18 in Jan => cycle is Dec 19 .. Jan 18 (inclusive)
    """
    # Use your Postgres version if you added it; otherwise keep your old name.
    try:
        post_date = _interest_post_date(year, month, post_day)
    except NameError:
        post_date = _interest_post_date(year, month, post_day)

    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1

    try:
        prev_post = _interest_post_date(py, pm, post_day)
    except NameError:
        prev_post = _interest_post_date(py, pm, post_day)

    start = prev_post + timedelta(days=1)
    end_excl = post_date + timedelta(days=1)
    return start, end_excl, post_date

def _apr_for_day(rate_rows: List[Tuple[date, float]], d: date) -> float:
    """
    rate_rows sorted asc by effective_date; returns the latest apr whose eff<=d.
    """
    apr = 0.0
    for eff, r in rate_rows:
        if eff <= d:
            apr = float(r)
        else:
            break
    return float(apr)

def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _last_day_of_month(y, m))
    return date(y, m, day)

def _project_occurrences_for_month(last_seen: date, cadence: str, anchor_day: int, month_start: date, month_end: date):
    """
    Returns list[date] of projected occurrences within [month_start, month_end]
    using cadence + anchor_day (day-of-month from last_seen for month-based cadences).

    IMPORTANT:
    - We include `last_seen` itself if it falls inside the target month window.
      This makes month projections include charges that already happened this month
      (e.g., Verizon/ChatGPT on the 1st), so they contribute to bills_total and
      appear under "Paid bills".
    """
    out: list[date] = []
    cadence = (cadence or "").lower().strip()

    # Always include last_seen if it falls within the requested month window.
    if month_start <= last_seen <= month_end:
        out.append(last_seen)

    if cadence in ("weekly", "biweekly"):
        step = 7 if cadence == "weekly" else 14

        d = last_seen + timedelta(days=step)
        while d < month_start:
            d += timedelta(days=step)

        while d <= month_end:
            out.append(d)
            d += timedelta(days=step)

        # de-dupe + sort
        return sorted(set(out))

    if cadence in ("monthly", "quarterly", "yearly"):
        step_months = {"monthly": 1, "quarterly": 3, "yearly": 12}[cadence]

        base_anchor = last_seen.replace(day=min(anchor_day, _last_day_of_month(last_seen.year, last_seen.month)))

        # Include the anchored occurrence too (in case last_seen was adjusted by day clamp)
        if month_start <= base_anchor <= month_end:
            out.append(base_anchor)

        cursor = _add_months(base_anchor, step_months)
        while cursor < month_start:
            cursor = _add_months(cursor, step_months)

        while cursor <= month_end:
            out.append(cursor)
            cursor = _add_months(cursor, step_months)

        return sorted(set(out))

    return sorted(set(out))

def get_category_from_db(tx_ids):
    """
    Postgres replacement for sqlite get_category_from_db(tx_ids).
    Returns the first non-empty category among those tx ids (or None).
    """
    if not tx_ids:
        return None

    rows = query_db(
        """
        SELECT category
        FROM transactions
        WHERE id = ANY(%s)
          AND category IS NOT NULL
          AND TRIM(category) <> ''
        LIMIT 1
        """,
        (list(map(int, tx_ids)),),
    )
    return rows[0]["category"] if rows else None

def _estimate_interest_for_account_month(cur, account_id: int, year: int, month: int) -> float:
    """
    Postgres port of your sqlite _estimate_interest_for_account_month.

    End-of-day balance convention:
      - apply that day's transactions to balance
      - then accrue interest for that day on resulting balance

    Depends on your existing helpers (same as sqlite version):
      - _interest_cycle_window(year, month, post_day) -> (month_start, month_end, post_date)
      - _get_rate_rows(cur, account_id)
      - _apr_for_day(rate_rows, d)
    """
    # interest_post_day
    cur.execute("SELECT interest_post_day FROM accounts WHERE id = %s", (int(account_id),))
    row = cur.fetchone()
    post_day = row["interest_post_day"] if row else None

    month_start, month_end, _post_date = _interest_cycle_window(year, month, post_day)

    # only checking/savings
    cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s", (int(account_id),))
    row = cur.fetchone()
    acc_type = (row["t"] if row else "other") or "other"
    if acc_type not in ("checking", "savings"):
        return 0.0

    rate_rows = _get_rate_rows(cur, account_id)
    if not rate_rows:
        return 0.0

    # starting balance (Postgres table name: startingbalance)
    # Column name might be start or start depending on how pgloader created it.
    # If you get a column error here, change start -> start.
    cur.execute(
        """
        SELECT COALESCE(SUM(start), 0)::double precision AS s
        FROM startingbalance
        WHERE account_id = %s
        """,
        (int(account_id),),
    )
    row = cur.fetchone()
    start_bal = float((row["s"] if row else 0.0) or 0.0)

    # Sum of amounts BEFORE month_start using effective date logic (posted else purchase)
    cur.execute(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
            amount::double precision AS amount
          FROM transactions
          WHERE account_id = %s
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
        SELECT COALESCE(SUM(amount), 0)::double precision AS s
        FROM norm
        WHERE d IS NOT NULL AND d < %s
        """,
        (int(account_id), month_start),
    )
    row = cur.fetchone()
    before_sum = float((row["s"] if row else 0.0) or 0.0)

    # balance convention: bal -= amount
    bal = start_bal - before_sum

    # daily net within [month_start, month_end) (same half-open as your sqlite loop)
    cur.execute(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
            amount::double precision AS amount
          FROM transactions
          WHERE account_id = %s
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
        SELECT d, COALESCE(SUM(amount), 0)::double precision AS net
        FROM norm
        WHERE d IS NOT NULL
          AND d >= %s
          AND d < %s
        GROUP BY d
        ORDER BY d ASC
        """,
        (int(account_id), month_start, month_end),
    )
    rows = cur.fetchall() or []
    net_by_day = {r["d"]: float(r["net"] or 0.0) for r in rows if r.get("d") is not None}

    total_interest = 0.0
    d = month_start
    while d < month_end:
        net = net_by_day.get(d, 0.0)
        bal = bal - net

        apr = _apr_for_day(rate_rows, d)
        daily_rate = apr / 365.0
        total_interest += (bal * daily_rate)

        d += timedelta(days=1)

    return float(total_interest)

def _interest_post_date(year: int, month: int, post_day: int | None) -> date:
    """
    Same logic as sqlite version, DB-agnostic.
    """
    last_day = calendar.monthrange(year, month)[1]
    if post_day is None:
        return date(year, month, last_day)
    day = min(int(post_day), last_day)
    return date(year, month, day)

# -----------------------------
# Endpoints
# -----------------------------
@router.get("/recurring")
def recurring(min_occ: int = 3, include_stale: bool = False):
    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    # decorate transfer patterns with "From A to B"
    for g in (groups or []):
        for p in (g.get("patterns") or []):
            tx = p.get("tx") or []
            if not tx:
                continue

            cats = {(t.get("category") or "").strip().lower() for t in tx}
            if cats != {"transfer"}:
                continue

            # representative tx
            try:
                rep = tx[-1]
                tx_id = int(rep.get("id"))
            except Exception:
                continue

            peer_aid = _find_transfer_peer_account_pg(tx_id, window_days=10)
            if not peer_aid:
                continue

            try:
                amt = float(rep.get("amount") or 0.0)
            except Exception:
                amt = 0.0

            a_from = _account_label_pg(int(rep.get("account_id") or 0))
            a_to = _account_label_pg(int(peer_aid))

            label = f"From {a_from} to {a_to}" if amt > 0 else f"From {a_to} to {a_from}"
            p["merchant_display"] = label

        labels = [pp.get("merchant_display") for pp in (g.get("patterns") or []) if pp.get("merchant_display")]
        if labels and len(labels) == len(g.get("patterns") or []):
            g["merchant_display"] = labels[0]

    return groups

@router.get("/recurring/ignore")
def get_recurring_ignores():
    merchants_rows = query_db("SELECT merchant FROM recurring_ignore_merchants ORDER BY merchant ASC")
    categories_rows = query_db("SELECT category FROM recurring_ignore_categories ORDER BY category ASC")
    merchants = [r["merchant"] for r in merchants_rows]
    categories = [r["category"] for r in categories_rows]
    return {"merchants": merchants, "categories": categories}

@router.post("/recurring/ignore/merchant")
def ignore_merchant(name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_ignore_merchants (merchant)
            VALUES (%s)
            ON CONFLICT DO NOTHING
            """,
            (name.upper(),),
        )
        conn.commit()
    return {"ok": True}

@router.post("/recurring/ignore/category")
def ignore_category(name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_ignore_categories (category)
            VALUES (%s)
            ON CONFLICT DO NOTHING
            """,
            (name.upper(),),
        )
        conn.commit()
    return {"ok": True}

@router.post("/recurring/ignore/pattern")
def ignore_pattern(merchant: str, amount: float, account_id: int = -1):
    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_ignore_patterns (merchant_norm, amount_bucket, sign, account_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (m_norm, bucket, sign, int(account_id)),
        )
        conn.commit()
    return {"ok": True}

@router.post("/recurring/override-cadence")
def override_cadence(merchant: str, amount: float, cadence: str, account_id: int = -1):
    cadence = (cadence or "").strip().lower()
    allowed = {"weekly", "biweekly", "monthly", "quarterly", "yearly", "irregular"}
    if cadence not in allowed:
        return {"ok": False, "error": f"cadence must be one of {sorted(allowed)}"}

    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_cadence_overrides
              (merchant_norm, amount_bucket, sign, account_id, cadence)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (merchant_norm, amount_bucket, sign, account_id)
            DO UPDATE SET cadence = EXCLUDED.cadence
            """,
            (m_norm, bucket, sign, int(account_id), cadence),
        )
        conn.commit()
    return {"ok": True}

@router.post("/recurring/merchant-alias")
def set_merchant_alias(alias: str, canonical: str):
    a = _norm_merchant(alias).upper()
    c = _norm_merchant(canonical).upper()
    if not a or not c:
        return {"ok": False, "error": "alias and canonical required"}

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO merchant_aliases (alias, canonical)
            VALUES (%s, %s)
            ON CONFLICT (alias) DO UPDATE SET canonical = EXCLUDED.canonical
            """,
            (a, c),
        )
        conn.commit()
    return {"ok": True}

@router.post("/recurring/merchant-alias/delete")
def delete_merchant_alias(alias: str):
    a = _norm_merchant(alias).upper()
    with with_db_cursor() as (conn, cur):
        cur.execute("DELETE FROM merchant_aliases WHERE alias = %s", (a,))
        conn.commit()
    return {"ok": True}

@router.post("/recurring/unignore/merchant")
def unignore_merchant(name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute("DELETE FROM recurring_ignore_merchants WHERE merchant = %s", (name.upper(),))
        conn.commit()
    return {"ok": True}

@router.get("/recurring/ignored-preview")
def recurring_ignored_preview(min_occ: int = 3, include_stale: bool = False):
    return get_ignored_merchants_preview(min_occ=min_occ, include_stale=include_stale)

@router.get("/recurring/calendar")
def recurring_calendar(year: int, month: int, min_occ: int = 3, include_stale: bool = False):
    """
    Returns projected recurring WITHDRAWALS for a given month.
    - uses get_recurring() output
    - excludes kind == "paycheck"
    """
    if month < 1 or month > 12:
        return {"ok": False, "error": "month must be 1..12"}

    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    events = []
    for g in (groups or []):
        # Skip paycheck-like groups
        if any((p.get("kind") or "").lower() == "paycheck" for p in (g.get("patterns") or [])):
            continue

        merchant = g.get("merchant") or ""

        for p in (g.get("patterns") or []):
            if (p.get("kind") or "").lower() == "paycheck":
                continue

            cadence = (p.get("cadence") or "").lower().strip()
            if cadence in ("unknown", "irregular", ""):
                continue

            last_seen_iso = p.get("last_seen")
            if not last_seen_iso:
                continue

            try:
                last_seen_d = datetime.strptime(last_seen_iso, "%Y-%m-%d").date()
            except Exception:
                continue

            anchor_day = last_seen_d.day

            occs = _project_occurrences_for_month(
                last_seen=last_seen_d,
                cadence=cadence,
                anchor_day=anchor_day,
                month_start=month_start,
                month_end=month_end,
            )

            merch_label = merchant
            tx_list = p.get("tx") or []

            def to_int_id(v):
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.isdigit():
                    return int(v)
                return None

            tx_ids = [t["id"] for t in tx_list if isinstance(t.get("id"), str)]

            # use your PG version if present; fall back to existing name if you kept it
            try:
                cat_label = get_category_from_db_pg(tx_ids)  # preferred in app_postgres
            except NameError:
                cat_label = get_category_from_db(tx_ids)     # if you kept old helper name

            amt = float(p.get("amount") or 0.0)
            aid = int(p.get("account_id") or -1)
            for d in occs:
                events.append({
                    "date": d.isoformat(),
                    "merchant": merch_label,
                    "merchant_display": merch_label,
                    "category": cat_label,
                    "amount": amt,
                    "cadence": cadence,
                    "account_id": aid,
                })

    # ---- INTEREST EVENTS (estimated) ----
    # Uses your existing helpers: _estimate_interest_for_account_month, _interest_post_date
    acct_rows = query_db(
        """
        SELECT id, institution, name, LOWER(accountType) AS accounttype, interest_post_day
        FROM accounts
        WHERE LOWER(accountType) IN ('checking', 'savings')
        """
    )

    with with_db_cursor() as (conn, cur):
        for a in acct_rows:
            aid = int(a["id"])
            est = _estimate_interest_for_account_month(cur, aid, year, month)

            if abs(est) < 0.01:
                continue

            post_date = _interest_post_date(year, month, a["interest_post_day"])

            events.append({
                "date": post_date.isoformat(),
                "merchant": f'INTEREST — {a["institution"]} {a["name"]}',
                "amount": round(est, 2),
                "cadence": "interest",
                "type": "Interest",
                "account_id": aid,
            })

    events.sort(key=lambda e: (e["date"], e["merchant"], abs(e["amount"])))
    return {
        "ok": True,
        "year": year,
        "month": month,
        "start": month_start.isoformat(),
        "end": month_end.isoformat(),
        "events": events,
    }

