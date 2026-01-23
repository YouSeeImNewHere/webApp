from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import sqlite3
from datetime import datetime, timedelta
import re
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import calendar
import datetime as dt

from emails.transactionHandler import DB_PATH
from recurring import get_ignored_merchants_preview
import inspect  # add near your imports

from fastapi import HTTPException
import os
from Receipts.receipts import router as receipts_router

app = FastAPI()
app.include_router(receipts_router)  # ✅ THIS is what makes /receipts/* exist


def get_category_from_db(tx_ids):
    if not tx_ids:
        return None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in tx_ids)
    cur.execute(
        f"""
        SELECT category
        FROM transactions
        WHERE id IN ({placeholders})
          AND category IS NOT NULL
          AND category != ''
        LIMIT 1
        """,
        tx_ids,
    )

    row = cur.fetchone()
    conn.close()

    return row[0] if row else None


def _last_day_of_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    # weekday: Mon=0..Sun=6
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    d = date(year, month, _last_day_of_month(year, month))
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed(d: date) -> date:
    # Federal holiday observed rules: if Sat -> Fri, if Sun -> Mon
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _us_federal_holidays_observed(year: int) -> set[date]:
    # Core federal holidays (observed)
    holidays = set()

    # Fixed-date holidays
    holidays.add(_observed(date(year, 1, 1)))  # New Year's Day
    holidays.add(_observed(date(year, 6, 19)))  # Juneteenth
    holidays.add(_observed(date(year, 7, 4)))  # Independence Day
    holidays.add(_observed(date(year, 11, 11)))  # Veterans Day
    holidays.add(_observed(date(year, 12, 25)))  # Christmas Day

    # Weekday-based holidays
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))  # MLK Day: 3rd Mon Jan
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))  # Presidents Day: 3rd Mon Feb
    holidays.add(_last_weekday_of_month(year, 5, 0))  # Memorial Day: last Mon May
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))  # Labor Day: 1st Mon Sep
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))  # Columbus Day: 2nd Mon Oct
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving: 4th Thu Nov

    return holidays


def _previous_workday(d: date, holiday_set: set[date]) -> date:
    while _is_weekend(d) or d in holiday_set:
        d -= timedelta(days=1)
    return d


def _paycheck_dates_for_month(year: int, month: int) -> list[date]:
    """
    Paydays are 1st and 15th, but deposit is day before.
    If that day-before is weekend/holiday -> previous workday.

    IMPORTANT:
    - The deposit for NEXT month’s 1st can land in THIS month
      (ex: Feb 1 payday -> Jan 31 deposit).
    """
    hol_this = _us_federal_holidays_observed(year)

    def deposit_for_target(target: date) -> date:
        # use holidays for the target's year (can differ when target is next year)
        hol = hol_this if target.year == year else _us_federal_holidays_observed(target.year)
        d = target - timedelta(days=1)
        return _previous_workday(d, hol)

    paydays = []

    # 1st and 15th of this month
    paydays.append(deposit_for_target(date(year, month, 1)))
    paydays.append(deposit_for_target(date(year, month, 15)))

    # ALSO: 1st of next month (deposit can fall in this month)
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1

    next_month_deposit = deposit_for_target(date(ny, nm, 1))
    # only include if it lands in the requested month
    if next_month_deposit.year == year and next_month_deposit.month == month:
        paydays.append(next_month_deposit)

    return sorted(set(paydays))


def _account_label(conn, account_id: int) -> str:
    r = conn.execute("SELECT institution, name FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not r:
        return f"Account {account_id}"
    return f"{r[0]} — {r[1]}"


def _dateiso_expr(raw: str) -> str:
    # returns a SQL expression that converts mm/dd/yy or mm/dd/yyyy to YYYY-MM-DD
    return f"""
    CASE
      WHEN length({raw}) = 8 THEN
        date('20' || substr({raw}, 7, 2) || '-' ||
                   substr({raw}, 1, 2) || '-' ||
                   substr({raw}, 4, 2))
      WHEN length({raw}) = 10 THEN
        date(substr({raw}, 7, 4) || '-' ||
             substr({raw}, 1, 2) || '-' ||
             substr({raw}, 4, 2))
      ELSE NULL
    END
    """


def _find_transfer_peer_account(conn, tx_id: str, window_days: int = 10):
    """
    Return peer account_id for a given transfer tx_id, or None.
    Matches opposite sign, same abs(amount), different account, within +/- window_days.
    """
    # Pull the source tx with a normalized dateISO
    src = conn.execute(f"""
      SELECT
        t.id,
        t.account_id,
        CAST(t.amount AS REAL) AS amount,
        LOWER(TRIM(COALESCE(t.category,''))) AS category,
        COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
        {_dateiso_expr("COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))")} AS dateISO
      FROM transactions t
      WHERE t.id = ?
    """, (tx_id,)).fetchone()

    if not src:
        return None

    # Only label actual Transfer category patterns
    if (src["category"] or "") != "transfer":
        return None

    if not src["dateISO"]:
        return None

    amt = float(src["amount"] or 0.0)
    if amt == 0:
        return None

    abs_amt = abs(amt)
    sign = 1 if amt > 0 else -1

    # Find best peer candidate
    peer = conn.execute(f"""
      SELECT
        t.account_id AS peer_account_id,
        ABS(CAST(t.amount AS REAL)) AS abs_amt,
        CAST(t.amount AS REAL) AS amount,
        {_dateiso_expr("COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))")} AS dateISO
      FROM transactions t
      WHERE t.id != ?
        AND t.account_id != ?
        AND LOWER(TRIM(COALESCE(t.category,''))) = 'transfer'
        AND ABS(CAST(t.amount AS REAL)) = ?
        AND (CAST(t.amount AS REAL) * ?) < 0
        AND {_dateiso_expr("COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))")} IS NOT NULL
        AND dateISO BETWEEN date(?, '-' || ? || ' day') AND date(?, '+' || ? || ' day')
      ORDER BY ABS(julianday(dateISO) - julianday(?)) ASC
      LIMIT 1
    """, (
        src["id"], src["account_id"], abs_amt, sign,
        src["dateISO"], window_days, src["dateISO"], window_days,
        src["dateISO"],
    )).fetchone()

    return int(peer["peer_account_id"]) if peer else None


# =============================================================================
# App + Static Frontend
# =============================================================================


from LESCalc import (
    LESInputs as _LESInputs,
    W4Settings as _W4Settings,
    get_base_pay as _get_base_pay,
    get_bah as _get_bah,
    generate_les_right_side as _gen_les,
)


class LESProfileModel(BaseModel):
    paygrade: str
    service_start: str  # YYYY-MM-DD
    has_dependents: bool = False

    # entitlements
    bas: float = 465.77
    submarine_pay: float = 0.0
    career_sea_pay: float = 0.0
    spec_duty_pay: float = 0.0
    tsp_rate: float = 0.05
    bah_override: Optional[float] = None

    # meal deduction rule
    meal_rate: float = 13.30
    meal_end_day: int = 31
    meal_deduction_enabled: bool = False
    meal_deduction_start: Optional[str] = None  # YYYY-MM-DD


    # W-4
    filing_status: str = "S"  # S/M/H
    step2_multiple_jobs: bool = False
    dep_under17: int = 0
    other_dep: int = 0
    other_income_annual: float = 0.0
    other_deductions_annual: float = 0.0
    extra_withholding: float = 0.0

    # mid-month model inputs
    mid_month_fraction: float = 0.50
    allotments_total: float = 0.0
    mid_month_collections_total: float = 0.0

    fica_include_special_pays: bool = False


class LESPaychecksRequest(BaseModel):
    year: int
    month: int
    profile: LESProfileModel


def _adjust_prev_business_day(d: date) -> date:
    # If weekend, roll back to Friday
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


@app.post("/les/paychecks")
def les_paychecks(req: LESPaychecksRequest):
    y, m = req.year, req.month
    p = req.profile

    # as_of date: last day of the month being viewed
    last_dom = calendar.monthrange(y, m)[1]
    as_of = date(y, m, last_dom)

    # compute base pay from chart in LESCalc
    start_parts = [int(x) for x in p.service_start.split("-")]
    start_dt = date(start_parts[0], start_parts[1], start_parts[2])
    paygrade = p.paygrade.replace(" ", "").upper().replace("E", "E").replace("--", "-")
    base_pay = _get_base_pay(paygrade.replace("-", ""), start_dt, as_of)

    # compute BAH (table) unless overridden
    bah = float(p.bah_override) if p.bah_override is not None else _get_bah(paygrade.replace("-", ""), p.has_dependents)

    inp = _LESInputs(
        base_pay=base_pay,
        submarine_pay=p.submarine_pay,
        career_sea_pay=p.career_sea_pay,
        spec_duty_pay=p.spec_duty_pay,
        bas=p.bas,
        bah=bah,
    )

    w4 = _W4Settings(
        pay_periods_per_year=12,
        filing_status=p.filing_status,
        step2_multiple_jobs=p.step2_multiple_jobs,
        dep_under17=p.dep_under17,
        other_dep=p.other_dep,
        other_income_annual=p.other_income_annual,
        other_deductions_annual=p.other_deductions_annual,
        extra_withholding=p.extra_withholding,
    )

    # meal deduction: apply your rule via LESCalc.generate_les_right_side inputs
    les_kwargs = dict(
        tsp_rate=p.tsp_rate,
        fica_wages_include_special_pays=p.fica_include_special_pays,
        meal_rate_per_day=p.meal_rate,
        meal_year=y, meal_month=m, meal_end_day=p.meal_end_day,
        mid_month_fraction=p.mid_month_fraction,
        allotments_total=p.allotments_total,
        mid_month_collections_total=p.mid_month_collections_total,
    )

    allowed = set(inspect.signature(_gen_les).parameters.keys())
    les_kwargs = {k: v for k, v in les_kwargs.items() if k in allowed}

    out = _gen_les(inp, w4, **les_kwargs)

    # target paydays
    # --- paycheck targets: 1st + 15th of this month, plus 1st of next month ---
    targets = [date(y, m, 1), date(y, m, 15)]
    if m == 12:
        targets.append(date(y + 1, 1, 1))
    else:
        targets.append(date(y, m + 1, 1))

    hol_this = _us_federal_holidays_observed(y)

    def deposit_for_target(target: date) -> date:
        hol = hol_this if target.year == y else _us_federal_holidays_observed(target.year)
        d = target - timedelta(days=1)  # day-before rule
        return _previous_workday(d, hol)  # weekend/holiday rollback

    def _month_bounds(year: int, month: int):
        last_dom = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_dom)

    def _get_actual_midmonth_deposit(cur, year: int, month: int) -> float | None:
        """
        If we've already received the DFAS mid-month pay for (year, month),
        return the *deposit amount* (positive float). Otherwise None.
        """
        month_start, month_end = _month_bounds(year, month)
        target_dep = deposit_for_target(date(year, month, 15))

        # pull candidate DFAS income tx in this month (income is stored as NEGATIVE in your DB)
        rows = cur.execute("""
          SELECT postedDate, purchaseDate, amount, merchant
          FROM transactions
          WHERE account_id = 3 AND category = 'Income' AND UPPER(merchant) LIKE '%DFAS%'
        """).fetchall()

        candidates = []
        for r in rows:
            posted = parse_posted_date(r["postedDate"])
            purchase = parse_posted_date(r["purchaseDate"])
            tx_date = posted if posted is not None else purchase
            if tx_date is None:
                continue
            if not (month_start <= tx_date <= month_end):
                continue

            try:
                amt = float(r["amount"])
            except Exception:
                continue

            # expect DFAS income to be negative; convert to a positive "deposit" amount
            dep_amt = abs(amt)
            # keep only plausible mid-month window (closest to the expected deposit date)
            delta_days = abs((tx_date - target_dep).days)
            candidates.append((delta_days, tx_date, dep_amt))

        if not candidates:
            return None

        # choose nearest to expected mid-month deposit date
        candidates.sort(key=lambda x: (x[0], x[1]))
        best_delta, best_date, best_amt = candidates[0]

        # guardrail: only accept if it's reasonably close to the expected mid-month deposit date
        if best_delta > 5:
            return None

        return float(best_amt)

    def _compute_les_out_for_month(year: int, month: int):
        """
        Compute LES outputs for a given month using the *same* profile settings,
        but with base pay tied to that month’s as_of date (last day of month).
        """
        last_dom = calendar.monthrange(year, month)[1]
        as_of_local = date(year, month, last_dom)

        base_pay_local = _get_base_pay(paygrade.replace("-", ""), start_dt, as_of_local)
        bah_local = float(p.bah_override) if p.bah_override is not None else _get_bah(paygrade.replace("-", ""), p.has_dependents)

        inp_local = _LESInputs(
            base_pay=base_pay_local,
            submarine_pay=p.submarine_pay,
            career_sea_pay=p.career_sea_pay,
            spec_duty_pay=p.spec_duty_pay,
            bas=p.bas,
            bah=bah_local,
        )

        # meal-deduction toggle/date should respect this month’s as_of date
        apply_meal_local = bool(getattr(p, "meal_deduction_enabled", False))
        start_iso_local = getattr(p, "meal_deduction_start", None)
        if apply_meal_local and start_iso_local:
            try:
                apply_meal_local = (as_of_local >= parse_iso(str(start_iso_local)))
            except Exception:
                apply_meal_local = False

        les_kwargs_local = dict(
            tsp_rate=p.tsp_rate,
            fica_wages_include_special_pays=p.fica_include_special_pays,

            meal_rate_per_day=p.meal_rate,
            meal_year=(year if apply_meal_local else None),
            meal_month=(month if apply_meal_local else None),
            meal_end_day=(p.meal_end_day if apply_meal_local else None),

            # start each month from the configured "default" split (usually 0.5)
            mid_month_fraction=p.mid_month_fraction,
            allotments_total=p.allotments_total,
            mid_month_collections_total=p.mid_month_collections_total,
        )

        allowed = set(inspect.signature(_gen_les).parameters.keys())
        les_kwargs_local = {k: v for k, v in les_kwargs_local.items() if k in allowed}

        return _gen_les(inp_local, w4, **les_kwargs_local)

    # ---- Detect actual mid-month pay for the viewed month and adjust EOM ----
    conn2, cur2 = with_db_cursor()
    try:
        actual_mid = _get_actual_midmonth_deposit(cur2, y, m)
    finally:
        conn2.close()

    projected_monthly_net = float(out.mid_month_pay) + float(out.eom)

    mid_month_display = float(actual_mid) if actual_mid is not None else float(out.mid_month_pay)
    eom_display = (projected_monthly_net - mid_month_display) if actual_mid is not None else float(out.eom)

    # ---- Also compute the "1st of month" paycheck as PREVIOUS month’s EOM ----
    prev_year, prev_month = (y - 1, 12) if m == 1 else (y, m - 1)
    out_prev = _compute_les_out_for_month(prev_year, prev_month)
    projected_prev_net = float(out_prev.mid_month_pay) + float(out_prev.eom)

    # optional: if the previous month’s mid-month is present in DB, adjust that too
    conn3, cur3 = with_db_cursor()
    try:
        prev_actual_mid = _get_actual_midmonth_deposit(cur3, prev_year, prev_month)
    finally:
        conn3.close()

    prev_mid_display = float(prev_actual_mid) if prev_actual_mid is not None else float(out_prev.mid_month_pay)
    prev_eom_display = (projected_prev_net - prev_mid_display) if prev_actual_mid is not None else float(out_prev.eom)

    events = []
    for target in targets:
        dep = deposit_for_target(target)

        # same include rule you used in /recurring/calendar
        include = (
                (target.year == y and target.month == m) or
                (dep.year == y and dep.month == m)
        )
        if not include:
            continue

        if not (dep.year == y and dep.month == m):
            continue
        # Map targets to the correct month:
        # - 1st of the viewed month => previous month EOM
        # - 15th of the viewed month => this month mid-month (actual if present)
        # - 1st of next month (sometimes deposits early) => this month EOM (adjusted if mid-month is known)
        if target.year == y and target.month == m and target.day == 1:
            amt = prev_eom_display
            label = "MIL PAY (EOM)"
        elif target.year == y and target.month == m and target.day == 15:
            amt = mid_month_display
            label = "MIL PAY (Mid-Month)"
        else:
            amt = eom_display
            label = "MIL PAY (EOM)"

        events.append({
            "date": dep.isoformat(),
            "pay_target": target.isoformat(),
            "cadence": "paycheck",
            "merchant": label,
            "amount": round(float(amt), 2),
            "type": "Income",
            "account_id": 3,
            "spillover": not (dep.year == y and dep.month == m),
        })
    breakdown = {
        "as_of": as_of.isoformat(),
        "profile": {
            "paygrade": paygrade.replace("-", ""),
            "service_start": p.service_start,
            "has_dependents": bool(p.has_dependents),
        },
        "entitlements": {
            "base_pay": round(float(base_pay), 2),
            "bah": round(float(bah), 2),
            "bas": round(float(p.bas), 2),
            "submarine_pay": round(float(p.submarine_pay), 2),
            "career_sea_pay": round(float(p.career_sea_pay), 2),
            "spec_duty_pay": round(float(p.spec_duty_pay), 2),
        },
        "w4": {
            "filing_status": p.filing_status,
            "step2_multiple_jobs": bool(p.step2_multiple_jobs),
            "dep_under17": int(p.dep_under17),
            "other_dep": int(p.other_dep),
            "other_income_annual": round(float(p.other_income_annual), 2),
            "other_deductions_annual": round(float(p.other_deductions_annual), 2),
            "extra_withholding": round(float(p.extra_withholding), 2),
        },
        "rates": {
            "tsp_rate": float(p.tsp_rate),
            "meal_rate": float(p.meal_rate),
            "meal_end_day": int(p.meal_end_day),
            "mid_month_fraction": float(p.mid_month_fraction),
        },
        "deductions": {
            "federal_taxes": round(float(out.federal_taxes), 2),
            "fica_social_security": round(float(out.fica_social_security), 2),
            "fica_medicare": round(float(out.fica_medicare), 2),
            "sgli": round(float(out.sgli), 2),
            "afrh": round(float(out.afrh), 2),
            "roth_tsp": round(float(out.roth_tsp), 2),
            "meal_deduction": round(float(out.meal_deduction), 2),
            "allotments_total": round(float(p.allotments_total), 2),
            "mid_month_collections_total": round(float(p.mid_month_collections_total), 2),
        },
        "net": {
            "mid_month_pay": round(float(out.mid_month_pay), 2),
            "eom": round(float(out.eom), 2),
        },
    }

    return {"events": events, "breakdown": breakdown}


@app.get("/__ping")
def ping():
    return {"ok": True, "file": __file__}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return FileResponse("static/home.html")


@app.get("/account")
def account_page():
    return FileResponse("static/account.html")


# =============================================================================
# DB Helpers
# =============================================================================

def query_db(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def with_db_cursor():
    """
    Convenience helper: returns (conn, cur) configured with Row factory.
    Caller is responsible for closing conn.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


# =============================================================================
# Date Parsing Helpers
# =============================================================================

def parse_iso(d: str):
    return datetime.strptime(d, "%Y-%m-%d").date()


def parse_posted_date(s: str):
    if not s:
        return None
    s = str(s).strip()
    if s.lower() == "unknown":
        return None
    return datetime.strptime(s, "%m/%d/%y").date()


# =============================================================================
# Balance / Series Helpers (Net Worth, Savings, Investments, Accounts)
# =============================================================================


def parse_db_date(s):
    if not s:
        return None
    s = str(s).strip().lower()
    if s == "unknown":
        return None
    return datetime.strptime(s, "%m/%d/%y").date()


def apply_transaction(current_totals, account_id, amount, account_type):
    t = (account_type or "other").lower()
    amt = float(amount or 0)

    if t in ("investment"):
        # contributions increase net worth
        delta = amt
    else:
        # checking / credit spending reduces net worth
        delta = -amt

    current_totals[account_id] = current_totals.get(account_id, 0.0) + delta


def load_starting_balances(cur):
    cur.execute("""
      SELECT account_id, SUM(Start) AS total_start
      FROM StartingBalance
      GROUP BY account_id
    """)
    return {int(r["account_id"]): float(r["total_start"] or 0) for r in cur.fetchall()}


def load_account_type_map(cur):
    cur.execute("SELECT id, LOWER(accountType) AS t FROM accounts")
    return {int(r["id"]): (r["t"] or "other") for r in cur.fetchall()}


def load_transactions(cur):
    cur.execute("""
      SELECT
        t.postedDate,
        t.purchaseDate,
        t.account_id,
        t.amount,
        LOWER(a.accountType) AS accountType
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """)
    rows = cur.fetchall()

    tx = []
    for r in rows:
        posted = parse_posted_date(r["postedDate"])
        purchase = parse_posted_date(r["purchaseDate"])

        # RULE: if no posted date, use transaction (purchase) date
        tx_date = posted if posted is not None else purchase

        # Safety: skip totally broken rows
        if tx_date is None:
            continue

        amt_raw = r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            # skip junk like "unknown", "", None
            continue

        tx.append({
            "date": tx_date,
            "account_id": int(r["account_id"]),
            "amount": amt,
            "accountType": r["accountType"] or "other",
        })

    tx.sort(key=lambda t: t["date"])
    return tx


def build_series(start_date, end_date, starting, transactions, value_fn):
    """
    Rolls balances forward, then emits day-by-day values using value_fn(current_totals).
    Returns [{"date": "YYYY-MM-DD", "value": number}, ...]
    """
    current_totals = starting.copy()
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

        results.append({"date": day.isoformat(), "value": float(value_fn(current_totals))})
        day += timedelta(days=1)

    return results


def _table_exists(cur, name: str) -> bool:
    row = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    return row is not None


def _column_exists(cur, table: str, col: str) -> bool:
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def latest_rates_map(cur):
    """
    Returns { account_id: rate_decimal } for the most recent effective_date per account.
    Assumes interest_rates columns: account_id, effective_date, apr
    (You can treat 'apr' as a generic rate for any account type.)
    """
    rows = cur.execute("""
      SELECT r.account_id, r.apr
      FROM interest_rates r
      JOIN (
        SELECT account_id, MAX(effective_date) AS max_eff
        FROM interest_rates
        GROUP BY account_id
      ) last
        ON last.account_id = r.account_id
       AND last.max_eff = r.effective_date
    """).fetchall()

    out = {}
    for r in rows:
        try:
            out[int(r["account_id"])] = float(r["apr"])
        except Exception:
            pass
    return out


from recurring import get_recurring  # new file you created

# -----------------------------
# Transfer peer detection (best-effort)
# -----------------------------
MAX_TRANSFER_WINDOW_DAYS = 10  # allow weekends/holidays lag


def _round_cents(x: float) -> int:
    return int(round(float(x) * 100))


def _is_transfer_like(cat: str) -> bool:
    c = (cat or "").strip().lower()
    return c in ("transfer", "card payment")


def _parse_iso_date(s: str):
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None


def _business_days_between(a: dt.date, b: dt.date) -> int:
    if a > b:
        a, b = b, a
    days = 0
    cur = a
    while cur < b:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def attach_transfer_peers(rows: list[dict], conn: sqlite3.Connection) -> list[dict]:
    """Adds rows[i]['transfer_peer'] = 'Institution — Name' when a matching opposite-side transfer is found.
    Works on the provided row subset (fast enough for 10k rows).
    """
    if not rows:
        return rows

    cur = conn.cursor()
    acct_rows = cur.execute("SELECT id, institution, name FROM accounts").fetchall()
    acct_name = {int(r["id"]): f'{r["institution"]} — {r["name"]}' for r in acct_rows}

    # candidates are only transfer-like rows with a known normalized date
    cands = []
    for r in rows:
        if not _is_transfer_like(r.get("category")):
            continue
        d = _parse_iso_date(str(r.get("dateISO") or ""))
        if not d:
            continue
        amt = float(r.get("amount") or 0)
        cents = abs(_round_cents(amt))
        sign = -1 if amt < 0 else 1
        cands.append({
            "id": r.get("id"),
            "account_id": int(r.get("account_id") or 0),
            "date": d,
            "cents": cents,
            "sign": sign,
        })

    if not cands:
        return rows

    # index candidates by (cents, sign)
    by_key: dict[tuple[int, int], list[dict]] = {}
    for c in cands:
        by_key.setdefault((c["cents"], c["sign"]), []).append(c)

    # sort lists by date then id for stable matching
    for k in by_key:
        by_key[k].sort(key=lambda x: (x["date"], x["id"]))

    # for each transfer-like row, find best opposite-side candidate
    id_to_peer = {}
    for c in cands:
        opp_list = by_key.get((c["cents"], -c["sign"]), [])
        if not opp_list:
            continue

        best = None
        best_score = None

        for o in opp_list:
            if o["account_id"] == c["account_id"]:
                continue
            cal_days = abs((o["date"] - c["date"]).days)
            if cal_days > MAX_TRANSFER_WINDOW_DAYS:
                continue
            biz_days = _business_days_between(c["date"], o["date"])
            score = (biz_days, cal_days, str(o["id"]))

            if best_score is None or score < best_score:
                best_score = score
                best = o

        if best:
            id_to_peer[c["id"]] = acct_name.get(best["account_id"])

    # attach to output rows
    for r in rows:
        peer = id_to_peer.get(r.get("id"))
        if peer:
            r["transfer_peer"] = peer

    return rows


def build_transfer_display(tx_list, conn):
    """
    Given a list of tx (from recurring pattern),
    return 'From A to B' or None
    """
    if not tx_list:
        return None

    # pick a representative tx
    t = dict(tx_list[-1])

    # recurring patterns use `date` (YYYY-MM-DD); matcher expects `dateISO`
    t["dateISO"] = t.get("dateISO") or t.get("date")

    # reuse your existing peer matcher
    rows = [t]
    attach_transfer_peers(rows, conn)

    peer = rows[0].get("transfer_peer")
    if not peer:
        return None

    acct = int(rows[0].get("account_id") or 0)
    acct_name = None

    r = conn.execute(
        "SELECT institution, name FROM accounts WHERE id = ?",
        (acct,)
    ).fetchone()
    if r:
        acct_name = f"{r[0]} — {r[1]}"

    if not acct_name:
        return None

    # sign convention: positive = money left
    if float(rows[0]["amount"]) > 0:
        return f"From {acct_name} to {peer}"
    else:
        return f"From {peer} to {acct_name}"


@app.get("/recurring")
def recurring(min_occ: int = 3, include_stale: bool = False):
    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row

        for g in (groups or []):
            for p in (g.get("patterns") or []):
                tx = p.get("tx") or []
                if not tx:
                    continue

                # Only decorate patterns where ALL tx are Transfer
                cats = {(t.get("category") or "").strip().lower() for t in tx}
                if cats != {"transfer"}:
                    continue

                # Pick most recent tx in this pattern and find peer account
                tx_id = str(tx[-1].get("id"))
                peer_aid = _find_transfer_peer_account(conn, tx_id, window_days=10)
                if not peer_aid:
                    continue

                # Determine direction from representative tx amount
                try:
                    amt = float(tx[-1].get("amount") or 0.0)
                except Exception:
                    amt = 0.0

                a_from = _account_label(conn, int(tx[-1].get("account_id") or 0))
                a_to = _account_label(conn, int(peer_aid))

                # amt > 0 means money left this account
                label = f"From {a_from} to {a_to}" if amt > 0 else f"From {a_to} to {a_from}"

                p["merchant_display"] = label

            # If every pattern is a decorated transfer, decorate group title too
            labels = [pp.get("merchant_display") for pp in (g.get("patterns") or []) if pp.get("merchant_display")]
            if labels and len(labels) == len(g.get("patterns") or []):
                g["merchant_display"] = labels[0]

    finally:
        conn.close()

    return groups


# =============================================================================
# Series Endpoints (Net Worth / Savings / Investments)
# =============================================================================

@app.get("/net-worth")
def net_worth(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances(cur)
    transactions = load_transactions(cur)
    acct_types = load_account_type_map(cur)

    conn.close()

    current_totals = starting.copy()
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
        savings = 0.0
        cards_balance = 0.0  # signed: negative = owe, positive = surplus

        for aid, bal in current_totals.items():
            t = (acct_types.get(aid) or "other").lower()
            if t == "savings":
                savings += bal
            elif t == "credit":
                cards_balance += bal
            else:
                # checking + investment + other => "banks"
                banks += bal

        cards_owed = max(0.0, -cards_balance)  # positive debt magnitude for UI
        net = banks + savings + cards_balance  # signed contribution (liability reduces)

        results.append({
            "date": day.isoformat(),
            "value": float(net),
            "banks": float(banks),
            "savings": float(savings),
            "cards": float(cards_owed),  # what your UI expects
            "cards_balance": float(cards_balance)  # optional, handy for later
        })

        day += timedelta(days=1)

    return results


@app.get("/savings")
def savings(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances(cur)
    transactions = load_transactions(cur)
    acct_types = load_account_type_map(cur)  # ✅ before close

    conn.close()

    def savings_only(totals):
        return sum(bal for aid, bal in totals.items() if acct_types.get(aid) == "savings")

    return build_series(start_date, end_date, starting, transactions, value_fn=savings_only)


@app.get("/investments")
def investments(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances(cur)
    transactions = load_transactions(cur)
    acct_types = load_account_type_map(cur)  # ✅

    conn.close()

    def investments_only(totals):
        return sum(bal for aid, bal in totals.items() if acct_types.get(aid) == "investment")

    return build_series(start_date, end_date, starting, transactions, value_fn=investments_only)


# =============================================================================
# Transactions Feeds (Recent / Per-Account)
# =============================================================================

@app.get("/transactions")
def transactions(limit: int = 15):
    sql = """
      WITH tx AS (
        SELECT
          t.id,
          t.postedDate,
          t.purchaseDate,
          t.merchant,
          t.amount,
          t.status,
          t.account_id,
          t.category,
          a.institution AS bank,
          a.name        AS card,
          LOWER(a.accountType) AS accountType,

          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,

          CASE
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
              date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
              date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
            ELSE NULL
          END AS d

        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      )
      SELECT id, account_id, raw_date AS postedDate, merchant, amount, status, bank, card, accountType, TRIM(category) AS category, d AS dateISO
      FROM tx
      ORDER BY d DESC, id DESC
      LIMIT ?
    """

    rows = query_db(sql, (limit,))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        attach_transfer_peers(rows, conn)
    return rows


@app.get("/account-transactions")
def account_transactions(account_id: int, limit: int = 200):
    sql = """
      WITH tx AS (
        SELECT
          id,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
          merchant,
          amount,

          CASE
            WHEN length(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown'))) = 8 THEN
              date('20' || substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 7, 2) || '-' ||
                         substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 1, 2) || '-' ||
                         substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 4, 2))
            WHEN length(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown'))) = 10 THEN
              date(substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 7, 4) || '-' ||
                   substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 4, 2))
            ELSE NULL
          END AS d
        FROM transactions
        WHERE account_id = ?
      )
      SELECT id, raw_date AS postedDate, merchant, amount
      FROM tx
      ORDER BY d DESC, id DESC
      LIMIT ?
    """

    return query_db(sql, (account_id, limit))


# =============================================================================
# Bank Totals Sidebar
# =============================================================================

@app.get("/bank-totals")
def bank_totals():
    conn, cur = with_db_cursor()

    accounts = cur.execute("""
      SELECT id, institution, name, LOWER(accountType) AS accountType
      FROM accounts
    """).fetchall()

    starting = {
        int(r["account_id"]): float(r["start_total"] or 0)
        for r in cur.execute("""
        SELECT account_id, SUM(Start) AS start_total
        FROM StartingBalance
        GROUP BY account_id
      """).fetchall()
    }

    tx_totals = {
        int(r["account_id"]): float(r["trans_total"] or 0)
        for r in cur.execute("""
        SELECT account_id, SUM(amount) AS trans_total
        FROM transactions
        GROUP BY account_id
      """).fetchall()
    }

    conn.close()

    by_type = {"checking": [], "savings": [], "investment": [], "credit": [], "other": []}

    for a in accounts:
        aid = int(a["id"])
        acc_type = a["accountType"] or "other"

        start = starting.get(aid, 0.0)
        trans = tx_totals.get(aid, 0.0)

        # savings/investment: start + trans
        # everything else (checking/credit): start - trans
        balance = start - trans

        bucket = acc_type if acc_type in by_type else "other"
        display_name = f'{a["institution"]} — {a["name"]}'
        by_type[bucket].append({"id": aid, "name": display_name, "total": balance})

    for k in by_type:
        by_type[k].sort(key=lambda x: x["total"], reverse=True)

    return {
        k: {"total": sum(x["total"] for x in lst), "accounts": lst}
        for k, lst in by_type.items()
    }


# =============================================================================
# Categories + Rules
# =============================================================================

class RuleCreate(BaseModel):
    category: str
    keywords: List[str] = []  # e.g. ["chick fil a", "chick-fil-a"]
    regex: Optional[str] = None  # advanced override
    apply_now: bool = True


def build_pattern_from_keywords(keywords: List[str]) -> str:
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    if not cleaned:
        raise ValueError("No keywords provided")
    alts = "|".join(re.escape(k) for k in cleaned)
    return alts


def apply_rule_to_existing(cur, category: str, pattern: str, flags: str):
    # SQLite has no REGEXP by default; apply in Python.
    re_flags = re.IGNORECASE if "i" in (flags or "") else 0
    rx = re.compile(pattern, re_flags)

    rows = cur.execute("""
      SELECT id, merchant
      FROM transactions
      WHERE category IS NULL OR TRIM(category) = ''
    """).fetchall()

    matched_ids = []
    for r in rows:
        merchant = (r["merchant"] or "")
        if rx.search(merchant):
            matched_ids.append(r["id"])

    if matched_ids:
        cur.executemany(
            "UPDATE transactions SET category = ? WHERE id = ?",
            [(category, txid) for txid in matched_ids]
        )

    return len(matched_ids)


@app.get("/categories")
def list_categories():
    conn, cur = with_db_cursor()

    rows = cur.execute("""
      SELECT category FROM (
        SELECT TRIM(category) AS category
        FROM transactions
        WHERE category IS NOT NULL AND TRIM(category) <> ''
        UNION
        SELECT TRIM(category) AS category
        FROM CategoryRules
        WHERE category IS NOT NULL AND TRIM(category) <> ''
      )
      ORDER BY category COLLATE NOCASE
    """).fetchall()

    conn.close()
    return [r["category"] for r in rows]


@app.post("/category-rules")
def create_category_rule(payload: RuleCreate):
    category = payload.category.strip()
    if not category:
        return {"ok": False, "error": "Category is required"}

    if payload.regex and payload.regex.strip():
        pattern = payload.regex.strip()
    else:
        try:
            pattern = build_pattern_from_keywords(payload.keywords)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    flags = "i"  # default case-insensitive

    conn, cur = with_db_cursor()

    cur.execute("""
      INSERT INTO CategoryRules (category, pattern, flags, is_active)
      VALUES (?, ?, ?, 1)
    """, (category, pattern, flags))

    applied = 0
    if payload.apply_now:
        applied = apply_rule_to_existing(cur, category, pattern, flags)

    conn.commit()
    conn.close()

    return {"ok": True, "pattern": pattern, "applied": applied}


@app.get("/category-totals-month")
def category_totals_month():
    conn, cur = with_db_cursor()

    today = datetime.today().date()
    first = today.replace(day=1)

    if first.month == 12:
        next_month = datetime(first.year + 1, 1, 1).date()
    else:
        next_month = datetime(first.year, first.month + 1, 1).date()

    unassigned_all_time = cur.execute("""
      SELECT COUNT(*) AS c
      FROM transactions
      WHERE category IS NULL OR TRIM(category) = ''
    """).fetchone()["c"]

    rows = cur.execute("""
      WITH tx AS (
        SELECT
          TRIM(category) AS category,
          amount,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
date(
  '20' || substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 7, 2) || '-' ||
  substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 1, 2) || '-' ||
  substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 4, 2)
) AS d

        FROM transactions
        WHERE amount > 0
          AND category IS NOT NULL
          AND TRIM(category) <> ''
      )
      SELECT category, SUM(amount) AS total, COUNT(*) AS tx_count
      FROM tx
      WHERE d >= ? AND d < ?
      GROUP BY category
      ORDER BY total DESC
    """, (first.isoformat(), next_month.isoformat())).fetchall()

    return {
        "unassigned_all_time": int(unassigned_all_time or 0),
        "categories": [
            {
                "category": r["category"],
                "total": float(r["total"] or 0),
                "tx_count": int(r["tx_count"] or 0),
            }
            for r in rows
        ]
    }


@app.get("/unassigned")
def get_unassigned(limit: int = 25, mode: str = "freq"):
    """
    mode:
      - "freq"   => most frequent unassigned merchants
      - "recent" => most recent unassigned transactions
    """
    mode = (mode or "freq").strip().lower()
    conn, cur = with_db_cursor()

    if mode == "recent":
        rows = cur.execute("""
          WITH tx AS (
  SELECT
    t.id,
    COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
    t.merchant,
    t.amount,
    a.institution AS bank,
    a.name        AS card,

    CASE
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
        date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
        date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      ELSE NULL
    END AS d
  FROM transactions t
  JOIN accounts a ON a.id = t.account_id
  WHERE (t.category IS NULL OR TRIM(t.category) = '')
    AND t.merchant IS NOT NULL
    AND TRIM(t.merchant) <> ''
    AND LOWER(TRIM(t.merchant)) <> 'unknown'
)
SELECT id, raw_date AS postedDate, merchant, amount, bank, card
FROM tx
ORDER BY d DESC, id DESC
LIMIT ?

        """, (limit,)).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    # default: freq
    rows = cur.execute("""
      WITH ranked AS (
  SELECT
    t.id,
    t.merchant,
    t.amount,
    a.institution AS bank,
    a.name        AS card,
    COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
    COUNT(*) OVER (PARTITION BY t.merchant) AS usage_count,

    CASE
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
        date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
        date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      ELSE NULL
    END AS d
  FROM transactions t
  JOIN accounts a ON a.id = t.account_id
  WHERE (t.category IS NULL OR TRIM(t.category) = '')
    AND t.merchant IS NOT NULL
    AND TRIM(t.merchant) <> ''
    AND LOWER(TRIM(t.merchant)) <> 'unknown'
)
SELECT
  id,
  raw_date AS postedDate,
  merchant,
  amount,
  bank,
  card,
  usage_count
FROM ranked
ORDER BY usage_count DESC, d DESC, id DESC
LIMIT ?

    """, (limit,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


@app.get("/category-trend")
def category_trend(category: str, period: str = "1m"):
    conn, cur = with_db_cursor()
    cat = (category or "").strip().lower()

    if cat == "unknown merchant":
        rows = cur.execute("""
          WITH tx AS (
            SELECT
              t.amount,
              CASE
                WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
                  date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,2) || '-' ||
                             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
                WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
                  date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,4) || '-' ||
                       substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                       substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
                ELSE NULL
              END AS d
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE
              t.amount > 0
              AND LOWER(a.accountType) IN ('checking','credit')
              AND LOWER(TRIM(COALESCE(t.merchant,''))) = 'unknown'
              AND LOWER(TRIM(COALESCE(t.category,''))) NOT IN ('card payment','transfer')
          )
          SELECT d, SUM(amount) AS total
          FROM tx
          WHERE d IS NOT NULL
          GROUP BY d
          ORDER BY d ASC
        """).fetchall()
    else:
        rows = cur.execute("""
          WITH tx AS (
            SELECT
              amount,
              date(
                '20' || substr(postedDate, 7, 2) || '-' ||
                substr(postedDate, 1, 2) || '-' ||
                substr(postedDate, 4, 2)
              ) AS d
            FROM transactions
            WHERE TRIM(category) = TRIM(?)
          )
          SELECT d, SUM(amount) AS total
          FROM tx
          WHERE d IS NOT NULL
          GROUP BY d
          ORDER BY d ASC
        """, (category,)).fetchall()

    conn.close()

    daily = [
        {"date": r["d"], "amount": float(r["total"] or 0)}
        for r in rows if r["d"]
    ]

    return {"category": category, "period": period, "series": daily}


@app.get("/category-transactions")
def category_transactions(
        category: str,
        start: str,
        end: str,
        limit: int = 500
):
    sql = """
      WITH tx AS (
        SELECT
          t.id,
          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
          t.merchant,
          t.amount,
          TRIM(t.category) AS category,
          a.institution AS bank,
          a.name AS card,
          CASE
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
              date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
              date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,4) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
            ELSE NULL
          END AS d
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE TRIM(t.category) = TRIM(?)
      )
      SELECT *
      FROM tx
      WHERE d BETWEEN ? AND ?
      ORDER BY d DESC, id DESC
      LIMIT ?
    """
    return query_db(sql, (category, start, end, limit))


@app.get("/category-totals-lifetime")
def category_totals_lifetime():
    conn, cur = with_db_cursor()

    rows = cur.execute("""
      SELECT
        TRIM(category) AS category,
        SUM(amount) AS total
      FROM transactions
      WHERE category IS NOT NULL
        AND TRIM(category) <> ''
        AND amount > 0
      GROUP BY TRIM(category)
      ORDER BY total DESC
    """).fetchall()

    conn.close()

    return [
        {"category": r["category"], "total": float(r["total"] or 0)}
        for r in rows
    ]


# =============================================================================
# Account Details + Account Series
# =============================================================================

@app.get("/account/{account_id}")
def account_info(account_id: int):
    sql = """
      SELECT id, institution, name, LOWER(accountType) AS accountType
      FROM accounts
      WHERE id = ?
    """
    rows = query_db(sql, (account_id,))
    return rows[0] if rows else {"error": "Account not found"}


@app.get("/account-series")
def account_series(account_id: int, start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    # starting balance for this account
    cur.execute("""
      SELECT SUM(Start) AS s
      FROM StartingBalance
      WHERE account_id = ?
    """, (account_id,))
    bal = float(cur.fetchone()["s"] or 0.0)

    # account type
    cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # IMPORTANT: pull both postedDate and purchaseDate
    rows = cur.execute("""
      SELECT postedDate, purchaseDate, amount
      FROM transactions
      WHERE account_id = ?
    """, (account_id,)).fetchall()

    conn.close()

    tx = []
    for r in rows:
        posted = parse_posted_date(r["postedDate"])
        purchase = parse_posted_date(r["purchaseDate"])

        # RULE: if no posted date, use transaction (purchase) date
        tx_date = posted if posted is not None else purchase

        # skip broken rows (no date at all)
        if tx_date is None:
            continue

        amt_raw = r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            continue

        tx.append({
            "date": tx_date,
            "amount": amt,
        })

    tx.sort(key=lambda x: x["date"])

    i = 0

    # A) roll forward transactions BEFORE the start date
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


@app.get("/account-transactions-range")
def account_transactions_range(account_id: int, start: str, end: str, limit: int = 500):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start).isoformat()
    end_date = parse_iso(end).isoformat()

    # account type
    row = cur.execute(
        "SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # sign rule consistent with your series logic:
    # savings/investment: balance += amount
    # checking/credit/etc: balance -= amount
    sign = 1 if acc_type == "investment" else -1

    # starting balance from table
    row = cur.execute("""
        SELECT COALESCE(SUM(Start), 0) AS s
        FROM StartingBalance
        WHERE account_id = ?
    """, (account_id,)).fetchone()
    start_bal = float(row["s"] or 0.0)

    # roll forward all transactions BEFORE start_date
    row = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
          amount
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT COALESCE(SUM(amount), 0) AS s
      FROM norm
      WHERE d IS NOT NULL AND d < ?
    """, (account_id, start_date)).fetchone()

    before_sum = float(row["s"] or 0.0)
    starting_balance_at_range = start_bal + (sign * before_sum)

    # now fetch range tx and compute running balance inside range
    # inside /account-transactions-range, replace the "now fetch range tx..." query with this

    rows = cur.execute("""
      WITH base AS (
        SELECT
          id,
          merchant,
          amount,
          TRIM(category) AS category,
          COALESCE(NULLIF(status,''), 'posted') AS status,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          id,
          merchant,
          amount,
          category,
          status,
          raw_date,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      ),
      in_range AS (
        SELECT *
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN ? AND ?
        ORDER BY d ASC, id ASC
        LIMIT ?
      ),
      with_running AS (
        SELECT
          id,
          merchant,
          amount,
          category,
          status,
          raw_date AS effectiveDate,
          d AS dateISO,
          SUM(amount) OVER (ORDER BY d, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_sum
        FROM in_range
      )
      SELECT
        id,
        effectiveDate,
        dateISO,
        merchant,
        amount,
        category,
        status,
        (? + (? * running_sum)) AS balance_after
      FROM with_running
      ORDER BY dateISO DESC, id DESC
    """, (account_id, start_date, end_date, limit, starting_balance_at_range, sign)).fetchall()

    tx = [dict(r) for r in rows]
    # ---- Transfer peer detection (best-effort) ----
    # For rows categorized as Transfer / Card Payment, try to find the matching
    # opposite-signed transaction in a different account with the same abs(amount)
    # within a small date window. Adds:
    #   transfer_peer: "Institution — Name"
    #   transfer_peer_id: int
    #   transfer_dir: "from" | "to"   (relative to THIS account)
    transfer_cats = {"transfer", "card payment"}
    # Matching window: allow multi-day gaps (weekends/holidays/posting delays)
    MAX_WINDOW_DAYS = 10  # calendar days
    try:
        # Build account display map once
        acct_rows = cur.execute("SELECT id, institution, name FROM accounts").fetchall()
        acct_name = {int(r["id"]): f'{r["institution"]} — {r["name"]}' for r in acct_rows}

        # Expand window to catch 1-2 day posting differences
        start_minus = (parse_iso(start) - timedelta(days=MAX_WINDOW_DAYS)).isoformat()
        end_plus = (parse_iso(end) + timedelta(days=MAX_WINDOW_DAYS)).isoformat()

        cand = cur.execute("""
          WITH base AS (
            SELECT
              id,
              account_id,
              amount,
              TRIM(category) AS category,
              COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date
            FROM transactions
            WHERE TRIM(category) IS NOT NULL
              AND LOWER(TRIM(category)) IN ('transfer','card payment')
          ),
          norm AS (
            SELECT
              id,
              account_id,
              amount,
              category,
              CASE
                WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
                  date('20' || substr(raw_date, 7, 2) || '-' ||
                             substr(raw_date, 1, 2) || '-' ||
                             substr(raw_date, 4, 2))
                WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
                  date(substr(raw_date, 7, 4) || '-' ||
                       substr(raw_date, 1, 2) || '-' ||
                       substr(raw_date, 4, 2))
                ELSE NULL
              END AS d
            FROM base
          )
          SELECT id, account_id, amount, LOWER(TRIM(category)) AS cat, d AS dateISO
          FROM norm
          WHERE dateISO IS NOT NULL AND dateISO BETWEEN ? AND ?
        """, (start_minus, end_plus)).fetchall()

        candidates = [dict(r) for r in cand]

        def _daydiff(a: str, b: str) -> int:
            # iso yyyy-mm-dd
            da = datetime.strptime(a, "%Y-%m-%d").date()
            db = datetime.strptime(b, "%Y-%m-%d").date()
            return abs((da - db).days)

        def _bizdiff(a: str, b: str) -> int:
            # Count weekdays between two dates (approx business-day distance).
            da = datetime.strptime(a, "%Y-%m-%d").date()
            db = datetime.strptime(b, "%Y-%m-%d").date()
            if da > db:
                da, db = db, da
            days = 0
            d = da
            while d < db:
                d += timedelta(days=1)
                if d.weekday() < 5:  # Mon-Fri
                    days += 1
            return days

        used_candidate_ids = set()

        for row in tx:
            cat = (row.get("category") or "").strip().lower()
            if cat not in transfer_cats:
                continue

            a = float(row.get("amount") or 0.0)
            date_iso = row.get("dateISO") or None
            if not date_iso:
                continue

            best = None
            best_key = None

            for c in candidates:
                if c["id"] in used_candidate_ids:
                    continue
                if int(c["account_id"]) == int(account_id):
                    continue
                # opposite sign (in/out)
                ca = float(c["amount"] or 0.0)
                if a == 0 or ca == 0:
                    continue
                if (a > 0 and ca > 0) or (a < 0 and ca < 0):
                    continue
                # same magnitude (allow tiny rounding)
                if abs(abs(a) - abs(ca)) > 0.01:
                    continue
                # close date
                dd = _daydiff(date_iso, c["dateISO"])
                if dd > MAX_WINDOW_DAYS:
                    continue

                biz_dd = _bizdiff(date_iso, c["dateISO"])

                key = (biz_dd, dd, str(c["dateISO"]), str(c["id"]))
                if best is None or key < best_key:
                    best = c
                    best_key = key

            if best:
                used_candidate_ids.add(best["id"])
                peer_id = int(best["account_id"])
                row["transfer_peer_id"] = peer_id
                row["transfer_peer"] = acct_name.get(peer_id, f"Account {peer_id}")

                # direction relative to current account
                row["transfer_dir"] = "from" if a < 0 else "to"
    except Exception:
        # Never break the page if matching fails
        pass

    ending_balance = float(tx[0]["balance_after"]) if tx else float(starting_balance_at_range)

    # ---- DISPLAY NORMALIZATION (credit shows positive debt) ----
    if acc_type == "credit":
        starting_balance_at_range = -float(starting_balance_at_range)
        ending_balance = -float(ending_balance)
        for r in tx:
            r["balance_after"] = -float(r["balance_after"])

    conn.close()

    return {
        "account_id": account_id,
        "start": start_date,
        "end": end_date,
        "starting_balance": float(starting_balance_at_range),
        "ending_balance": float(ending_balance),
        "transactions": tx
    }


@app.get("/transactions-all")
def transactions_all(limit: int = 10000, offset: int = 0):
    sql = """
      WITH base AS (
        SELECT
          t.*,
          a.institution AS bank,
          a.name        AS card,
          LOWER(a.accountType) AS accountType,
          COALESCE(
            NULLIF(t.postedDate,'unknown'),
            NULLIF(t.purchaseDate,'unknown')
          ) AS raw_date
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      ),
      tx AS (
        SELECT
          base.*,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS dateISO
        FROM base
      )
      SELECT *
      FROM tx
      ORDER BY (dateISO IS NULL) ASC, dateISO DESC, id DESC
      LIMIT ? OFFSET ?
    """

    rows = query_db(sql, (limit, offset))

    # ✅ ADD THIS: attach transfer peers for Transfer / Card Payment rows
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        attach_transfer_peers(rows, conn)

    return rows


# TEST METHODS ------------------------------------------------------------------------------------------

from fastapi import Query


@app.get("/transactions-test")
def transactions_test(limit: int = Query(200, ge=1, le=10000), offset: int = Query(0, ge=0)):
    sql = f"""
      WITH tx AS (
        SELECT
          *,
          COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date
        FROM transactions_test
      )
      SELECT *
      FROM tx
      ORDER BY
        CASE
          WHEN raw_date IS NULL THEN 1
          WHEN length(raw_date) = 8 THEN
            date('20' || substr(raw_date,7,2) || '-' || substr(raw_date,1,2) || '-' || substr(raw_date,4,2))
          WHEN length(raw_date) = 10 THEN
            date(substr(raw_date,7,4) || '-' || substr(raw_date,1,2) || '-' || substr(raw_date,4,2))
          ELSE NULL
        END DESC,
        id DESC
      LIMIT ? OFFSET ?;
    """
    return query_db(sql, (limit, offset))


from fastapi.responses import FileResponse


@app.get("/transactions-test-page")
def transactions_test_page():
    return FileResponse("static/transactions_test_account.html")


@app.get("/transactions-test-account")
def transactions_test_account_page():
    return FileResponse("static/transactions_test_account.html")


@app.get("/transactions-test-range")
def transactions_test_range(account_id: int, start: str, end: str, limit: int = 500):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start).isoformat()
    end_date = parse_iso(end).isoformat()

    # account type (same as prod)
    row = cur.execute(
        "SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # sign rule (same as prod)
    # savings/investment: balance += amount
    # checking/credit/etc: balance -= amount
    sign = 1 if acc_type == "investment" else -1

    # starting balance from table (same as prod)
    row = cur.execute("""
        SELECT COALESCE(SUM(Start), 0) AS s
        FROM StartingBalance
        WHERE account_id = ?
    """, (account_id,)).fetchone()
    start_bal = float(row["s"] or 0.0)

    # roll forward all transactions BEFORE start_date (but from transactions_test)
    row = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
          amount
        FROM transactions_test
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT COALESCE(SUM(amount), 0) AS s
      FROM norm
      WHERE d IS NOT NULL AND d < ?
    """, (account_id, start_date)).fetchone()

    before_sum = float(row["s"] or 0.0)
    starting_balance_at_range = start_bal + (sign * before_sum)

    # now fetch range tx and compute running balance inside range (from transactions_test)
    rows = cur.execute("""
      WITH base AS (
        SELECT
          id,
          merchant,
          amount,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date
        FROM transactions_test
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          id,
          merchant,
          amount,
          raw_date,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      ),
      in_range AS (
        SELECT *
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN ? AND ?
        ORDER BY d ASC, id ASC
        LIMIT ?
      ),
      with_running AS (
        SELECT
          id,
          merchant,
          amount,
          raw_date AS effectiveDate,
            d AS dateISO,
          SUM(amount) OVER (ORDER BY d, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_sum
        FROM in_range
      )
      SELECT
        id,
        effectiveDate,
        dateISO,
        merchant,
        amount,
        (? + (? * running_sum)) AS balance_after
      FROM with_running
      ORDER BY dateISO DESC, id DESC
    """, (account_id, start_date, end_date, limit, starting_balance_at_range, sign)).fetchall()

    conn.close()

    tx = [dict(r) for r in rows]
    ending_balance = float(tx[0]["balance_after"]) if tx else float(starting_balance_at_range)

    # ---- DISPLAY NORMALIZATION (credit shows positive debt) ----
    if acc_type == "credit":
        starting_balance_at_range = abs(float(starting_balance_at_range))
        ending_balance = abs(float(ending_balance))
        for r in tx:
            r["balance_after"] = abs(float(r["balance_after"]))

    return {
        "account_id": account_id,
        "start": start_date,
        "end": end_date,
        "starting_balance": float(starting_balance_at_range),
        "ending_balance": float(ending_balance),
        "transactions": tx
    }


@app.get("/transactions-test-series")
def transactions_test_series(account_id: int, start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    # starting balance for this account (same as /account-series)
    cur.execute("""
      SELECT SUM(Start) AS s
      FROM StartingBalance
      WHERE account_id = ?
    """, (account_id,))
    bal = float(cur.fetchone()["s"] or 0.0)

    # account type (same as /account-series)
    cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # pull both postedDate and purchaseDate (BUT from transactions_test)
    rows = cur.execute("""
      SELECT postedDate, purchaseDate, amount
      FROM transactions_test
      WHERE account_id = ?
    """, (account_id,)).fetchall()

    conn.close()

    tx = []
    for r in rows:
        posted = parse_posted_date(r["postedDate"])
        purchase = parse_posted_date(r["purchaseDate"])
        tx_date = posted if posted is not None else purchase
        if tx_date is None:
            continue
        amt_raw = r["amount"]
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

        display_val = abs(bal) if acc_type == "credit" else bal
        results.append({"date": day.isoformat(), "value": float(display_val)})

        day += timedelta(days=1)

    return results


@app.get("/recurring/ignore")
def get_recurring_ignores():
    conn, cur = with_db_cursor()
    merchants = [r[0] for r in cur.execute("SELECT merchant FROM recurring_ignore_merchants")]
    categories = [r[0] for r in cur.execute("SELECT category FROM recurring_ignore_categories")]
    conn.close()
    return {"merchants": merchants, "categories": categories}


@app.post("/recurring/ignore/merchant")
def ignore_merchant(name: str):
    conn, cur = with_db_cursor()
    cur.execute(
        "INSERT OR IGNORE INTO recurring_ignore_merchants (merchant) VALUES (?)",
        (name.upper(),)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/ignore/category")
def ignore_category(name: str):
    conn, cur = with_db_cursor()
    cur.execute(
        "INSERT OR IGNORE INTO recurring_ignore_categories (category) VALUES (?)",
        (name.upper(),)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/spending")
def spending(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    # Pull transactions with effective date
    rows = cur.execute("""
      SELECT
        COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
        t.amount,
        TRIM(t.category) AS category,
        LOWER(a.accountType) AS accountType
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """).fetchall()

    conn.close()

    # Build date → spending map
    daily = {}

    for r in rows:
        d = parse_posted_date(r["raw_date"])
        if not d or d < start_date or d > end_date:
            continue

        try:
            amt = float(r["amount"])
        except (TypeError, ValueError):
            continue

        category = (r["category"] or "").strip().lower()

        # 🚫 EXCLUSIONS
        if category in ("card payment", "transfer"):
            continue

        # ✅ SPENDING
        if r["accountType"] in ("checking", "credit") and amt > 0:
            daily[d] = daily.get(d, 0.0) + amt

    # Emit full day-by-day series
    results = []
    day = start_date
    while day <= end_date:
        results.append({
            "date": day.isoformat(),
            "value": float(daily.get(day, 0))
        })
        day += timedelta(days=1)

    return results


@app.get("/spending-debug")
def spending_debug(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = cur.execute("""
      SELECT
        t.id,
        COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
        t.amount,
        t.merchant,
        TRIM(t.category) AS category,
        LOWER(a.accountType) AS accountType,
        a.institution AS bank,
        a.name AS account
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """).fetchall()

    conn.close()

    out = []

    for r in rows:
        d = parse_posted_date(r["raw_date"])
        if not d or d < start_date or d > end_date:
            continue

        try:
            amt = float(r["amount"])
        except (TypeError, ValueError):
            continue

        category = (r["category"] or "").strip().lower()

        # 🚫 EXCLUSIONS (same as /spending)
        if category in ("card payment", "transfer"):
            continue

        # ✅ ONLY include real spending
        if r["accountType"] in ("checking", "credit") and amt > 0:
            out.append({
                "date": d.isoformat(),
                "amount": amt,
                "merchant": r["merchant"],
                "category": r["category"],
                "bank": r["bank"],
                "account": r["account"]
            })

    return out


@app.get("/category-totals-range")
def category_totals_range(start: str, end: str):
    conn, cur = with_db_cursor()

    rows = cur.execute("""
      WITH tx AS (
        SELECT
          TRIM(t.category) AS category,
          t.amount,
          CASE
            -- MM/DD/YY
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
              date(
                '20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2)
              )

            -- MM/DD/YYYY
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
              date(
                substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
                substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2)
              )
            ELSE NULL
          END AS d
        FROM transactions t
        WHERE t.amount > 0
          AND t.category IS NOT NULL
          AND TRIM(t.category) <> ''
          AND LOWER(TRIM(t.category)) NOT IN ('card payment', 'transfer')

      )
      SELECT category, SUM(amount) AS total
      FROM tx
      WHERE d BETWEEN ? AND ?
      GROUP BY category
      ORDER BY total DESC
    """, (start, end)).fetchall()

    conn.close()

    return [
        {"category": r["category"], "total": float(r["total"] or 0)}
        for r in rows
    ]


from recurring import _norm_merchant, _amount_bucket  # matches your recurring.py helpers


@app.post("/recurring/ignore/pattern")
def ignore_pattern(merchant: str, amount: float, account_id: int = -1):
    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    conn, cur = with_db_cursor()
    cur.execute("""
      INSERT OR IGNORE INTO recurring_ignore_patterns
        (merchant_norm, amount_bucket, sign, account_id)
      VALUES (?, ?, ?, ?)
    """, (m_norm, bucket, sign, int(account_id)))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/override-cadence")
def override_cadence(merchant: str, amount: float, cadence: str, account_id: int = -1):
    cadence = (cadence or "").strip().lower()
    allowed = {"weekly", "biweekly", "monthly", "quarterly", "yearly", "irregular"}
    if cadence not in allowed:
        return {"ok": False, "error": f"cadence must be one of {sorted(allowed)}"}

    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    conn, cur = with_db_cursor()
    cur.execute("""
      INSERT INTO recurring_cadence_overrides
        (merchant_norm, amount_bucket, sign, account_id, cadence)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(merchant_norm, amount_bucket, sign, account_id)
      DO UPDATE SET cadence = excluded.cadence
    """, (m_norm, bucket, sign, int(account_id), cadence))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/merchant-alias")
def set_merchant_alias(alias: str, canonical: str):
    a = _norm_merchant(alias).upper()
    c = _norm_merchant(canonical).upper()
    if not a or not c:
        return {"ok": False, "error": "alias and canonical required"}

    conn, cur = with_db_cursor()
    cur.execute("""
      INSERT INTO merchant_aliases (alias, canonical)
      VALUES (?, ?)
      ON CONFLICT(alias) DO UPDATE SET canonical = excluded.canonical
    """, (a, c))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/merchant-alias/delete")
def delete_merchant_alias(alias: str):
    a = _norm_merchant(alias).upper()
    conn, cur = with_db_cursor()
    cur.execute("DELETE FROM merchant_aliases WHERE alias = ?", (a,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/unignore/merchant")
def unignore_merchant(name: str):
    conn, cur = with_db_cursor()
    cur.execute("DELETE FROM recurring_ignore_merchants WHERE merchant = ?", (name.upper(),))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/recurring/ignored-preview")
def recurring_ignored_preview(min_occ: int = 3, include_stale: bool = False):
    return get_ignored_merchants_preview(min_occ=min_occ, include_stale=include_stale)


# =========================
# Recurring Calendar
# =========================

def _interest_cycle_window(year: int, month: int, post_day: int | None):
    """
    Returns (start_date, end_date_exclusive) for the interest accrual period
    that pays on post_day in (year, month).

    Example: post_day=18 in Jan => cycle is Dec 19 .. Jan 18 (inclusive)
    """
    post_date = _interest_post_date(year, month, post_day)

    # previous month's posting date
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1

    prev_post = _interest_post_date(py, pm, post_day)

    start = prev_post + timedelta(days=1)
    end_excl = post_date + timedelta(days=1)
    return start, end_excl, post_date


def _interest_post_date(year: int, month: int, post_day: int | None) -> date:
    last_day = calendar.monthrange(year, month)[1]

    if post_day is None:
        return date(year, month, last_day)

    # clamp (e.g. 31 → Feb 28)
    day = min(int(post_day), last_day)
    return date(year, month, day)


def _add_months(d: date, months: int) -> date:
    # month-safe add: keeps "day of month" as close as possible
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _last_day_of_month(y, m))
    return date(y, m, day)


def _project_occurrences_for_month(last_seen: date, cadence: str, anchor_day: int, month_start: date, month_end: date):
    """
    Returns list[date] of projected occurrences within [month_start, month_end]
    using cadence + anchor_day (day-of-month from last_seen for month-based cadences).
    """
    out = []

    cadence = (cadence or "").lower().strip()
    if cadence in ("weekly", "biweekly"):
        step = 7 if cadence == "weekly" else 14

        # find first date >= month_start by stepping forward from last_seen
        d = last_seen
        # push to at least next cycle (don’t re-include last_seen itself)
        d = d + timedelta(days=step)

        # fast forward until we reach this month
        while d < month_start:
            d = d + timedelta(days=step)

        while d <= month_end:
            out.append(d)
            d = d + timedelta(days=step)

        return out

    if cadence in ("monthly", "quarterly", "yearly"):
        step_months = {"monthly": 1, "quarterly": 3, "yearly": 12}[cadence]

        # start from the NEXT cadence “slot” after last_seen
        base = last_seen
        cursor = _add_months(base.replace(day=min(anchor_day, _last_day_of_month(base.year, base.month))), step_months)

        # move forward until we’re in/after month_start
        while cursor < month_start:
            cursor = _add_months(cursor, step_months)

        # now add any occurrences inside the requested month
        while cursor <= month_end:
            out.append(cursor)
            cursor = _add_months(cursor, step_months)

        return out

    # irregular/unknown => no projections
    return out


# -----------------------------
# Hard-coded paycheck amounts
# -----------------------------
PAYCHECK_MERCHANT = "SALARY REGULAR INCOME FROM DFAS"

# Set these to whatever is correct for you
PAYCHECK_AMOUNT_FOR_DAY = {
    1: 1700.00,  # payday on the 1st (deposit date may be prior workday)
    15: 1400.00,  # payday on the 15th
}


# Optional: if you ever want different values in specific months:
# PAYCHECK_AMOUNT_BY_YYYYMM = {
#     "2026-01": {1: 1700.00, 15: 1400.00},
# }


def _find_paycheck_amount(groups) -> float:
    """
    Pull the real paycheck amount from recurring detection.
    Uses median to avoid outliers.
    """
    amounts = []

    for g in (groups or []):
        m = (g.get("merchant") or "").upper().strip()
        if m != PAYCHECK_MERCHANT:
            continue

        for p in (g.get("patterns") or []):
            try:
                amounts.append(abs(float(p.get("amount") or 0)))
            except Exception:
                pass

    if not amounts:
        return 0.0

    amounts.sort()
    return amounts[len(amounts) // 2]


@app.get("/recurring/calendar")
def recurring_calendar(year: int, month: int, min_occ: int = 3, include_stale: bool = False):
    """
    Returns projected recurring WITHDRAWALS for a given month.
    - uses get_recurring() output
    - excludes kind == "paycheck"
    """
    # clamp month
    if month < 1 or month > 12:
        return {"ok": False, "error": "month must be 1..12"}

    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    events = []
    for g in (groups or []):
        # 🚫 Skip paycheck-like recurring groups entirely
        if any((p.get("kind") or "").lower() == "paycheck" for p in (g.get("patterns") or [])):
            continue

        merchant = g.get("merchant") or ""

        for p in (g.get("patterns") or []):
            # only “recurring” (withdrawals), not paychecks
            if (p.get("kind") or "").lower() == "paycheck":
                continue

            cadence = (p.get("cadence") or "").lower().strip()
            if cadence in ("unknown", "irregular", ""):
                continue

            # Use last_seen anchor day (day-of-month) for month-based cadences
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

            # Transfer label (From A to B) for calendar too
            merch_label = merchant
            tx_list = p.get("tx") or []
            tx_ids = [t["id"] for t in tx_list if "id" in t]

            cat_label = get_category_from_db(tx_ids)

            # amount is already signed in recurring.py output (withdrawals are usually +)
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
                    "account_id": aid,  # ✅ NEW
                })

    # # ---- PAYCHECK EVENTS (derived from recurring data) ----
    # # Hard-coded paycheck amounts: based on the TARGET payday (1st vs 15th)
    # def paycheck_amount_for_target(target: date) -> float:
    #     # Optional per-month override (if you add PAYCHECK_AMOUNT_BY_YYYYMM)
    #     # key = f"{target.year:04d}-{target.month:02d}"
    #     # if key in PAYCHECK_AMOUNT_BY_YYYYMM:
    #     #     return float(PAYCHECK_AMOUNT_BY_YYYYMM[key].get(target.day, 0.0))
    #     return float(PAYCHECK_AMOUNT_FOR_DAY.get(target.day, 0.0))
    #
    # # targets: 1st + 15th of this month, plus 1st of next month (if deposit lands in this month)
    # targets = [date(year, month, 1), date(year, month, 15)]
    # if month == 12:
    #     targets.append(date(year + 1, 1, 1))
    # else:
    #     targets.append(date(year, month + 1, 1))
    #
    # hol_this = _us_federal_holidays_observed(year)
    #
    # def deposit_for_target(target: date) -> date:
    #     hol = hol_this if target.year == year else _us_federal_holidays_observed(target.year)
    #     d = target - timedelta(days=1)
    #     return _previous_workday(d, hol)
    #
    # for target in targets:
    #     dep = deposit_for_target(target)
    #
    #     # Include if:
    #     # 1) this paycheck's TARGET payday is in the requested month (Jan 1/15),
    #     #    even if the deposit date is in the previous month (Dec 31)
    #     # OR
    #     # 2) the deposit date lands in the requested month (the "early deposit" for next month's 1st)
    #     include = (
    #             (target.year == year and target.month == month) or
    #             (dep.year == year and dep.month == month)
    #     )
    #     if not include:
    #         continue
    #
    #     amt = paycheck_amount_for_target(target)
    #
    #     events.append({
    #         "date": dep.isoformat(),  # deposit day shown on calendar grid
    #         "merchant": PAYCHECK_MERCHANT,
    #         "amount": amt,  # ✅ hard-coded amount
    #         "cadence": "paycheck",
    #         "type": "Income",
    #         "account_id": 3,
    #         "pay_target": target.isoformat(),
    #         "spillover": not (dep.year == year and dep.month == month),
    #     })

    # ---- INTEREST EVENTS (estimated) ----
    # Put a single "Estimated Interest" income chip on the LAST day of the month
    conn, cur = with_db_cursor()

    acct_rows = cur.execute("""
      SELECT
        id,
        institution,
        name,
        LOWER(accountType) AS accountType,
        interest_post_day
      FROM accounts
      WHERE LOWER(accountType) IN ('checking', 'savings')
    """).fetchall()

    for a in acct_rows:
        aid = int(a["id"])
        est = _estimate_interest_for_account_month(cur, aid, year, month)

        # optional: ignore tiny pennies so calendar doesn't get noisy
        if abs(est) < 0.01:
            continue

        # show as income (positive number)
        post_date = _interest_post_date(
            year,
            month,
            a["interest_post_day"]
        )

        events.append({
            "date": post_date.isoformat(),
            "merchant": f'INTEREST — {a["institution"]} {a["name"]}',
            "amount": round(est, 2),
            "cadence": "interest",
            "type": "Interest",
            "account_id": aid,  # ✅ NEW
        })

    conn.close()

    events.sort(key=lambda e: (e["date"], e["merchant"], abs(e["amount"])))
    return {
        "ok": True,
        "year": year,
        "month": month,
        "start": month_start.isoformat(),
        "end": month_end.isoformat(),
        "events": events,
    }


def _month_range(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end  # [start, end)


def _get_rate_rows(cur, account_id: int):
    # return sorted effective-dated APRs
    rows = cur.execute("""
      SELECT effective_date, apr
      FROM interest_rates
      WHERE account_id = ?
      ORDER BY effective_date ASC
    """, (account_id,)).fetchall()
    out = []
    for r in rows:
        try:
            out.append((datetime.strptime(r["effective_date"], "%Y-%m-%d").date(), float(r["apr"])))
        except Exception:
            pass
    return out


def _apr_for_day(rate_rows, d: date) -> float:
    # rate_rows sorted asc by effective_date
    apr = 0.0
    for eff, r in rate_rows:
        if eff <= d:
            apr = r
        else:
            break
    return apr


def _estimate_interest_for_account_month(cur, account_id: int, year: int, month: int) -> float:
    """
    End-of-day balance convention:
      - apply that day's transactions to balance
      - then accrue interest for that day on resulting balance
    """
    row = cur.execute("SELECT interest_post_day FROM accounts WHERE id = ?", (account_id,)).fetchone()
    post_day = row["interest_post_day"] if row else None

    month_start, month_end, _post_date = _interest_cycle_window(year, month, post_day)

    # only do accounts that *should* earn deposit interest
    row = cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?", (account_id,)).fetchone()
    acc_type = (row["t"] if row else "other") or "other"
    if acc_type not in ("checking", "savings"):
        return 0.0

    # must have at least one rate row
    rate_rows = _get_rate_rows(cur, account_id)
    if not rate_rows:
        return 0.0

    # starting balance (sum of StartingBalance)
    row = cur.execute("""
      SELECT COALESCE(SUM(Start), 0) AS s
      FROM StartingBalance
      WHERE account_id = ?
    """, (account_id,)).fetchone()
    start_bal = float(row["s"] or 0.0)

    # sum of amounts BEFORE month_start using your “effective date” logic (posted else purchase)
    # and the same date normalization pattern you use elsewhere.
    row = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
          amount
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT COALESCE(SUM(amount), 0) AS s
      FROM norm
      WHERE d IS NOT NULL AND d < date(?)
    """, (account_id, month_start.isoformat())).fetchone()

    before_sum = float(row["s"] or 0.0)

    # Your balance convention for checking/savings in series:
    #   bal -= amount  (amount positive reduces balance)
    bal = start_bal - before_sum

    # daily net transactions within month grouped by dateISO
    rows = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
          amount
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT d, COALESCE(SUM(amount), 0) AS net
      FROM norm
      WHERE d IS NOT NULL
        AND d >= date(?)
        AND d < date(?)
      GROUP BY d
      ORDER BY d ASC
    """, (account_id, month_start.isoformat(), month_end.isoformat())).fetchall()

    net_by_day = {r["d"]: float(r["net"] or 0.0) for r in rows}

    total_interest = 0.0
    d = month_start
    while d < month_end:
        # apply transactions for the day (end-of-day balance)
        net = net_by_day.get(d.isoformat(), 0.0)
        bal = bal - net

        apr = _apr_for_day(rate_rows, d)
        daily_rate = apr / 365.0
        total_interest += (bal * daily_rate)

        d += timedelta(days=1)

    return float(total_interest)


# =============================================================================
# Unknown merchant (for reconciliation cards)
# =============================================================================

@app.get("/unknown-merchant-total-month")
def unknown_merchant_total_month():
    conn, cur = with_db_cursor()

    today = datetime.today().date()
    first = today.replace(day=1)

    if first.month == 12:
        next_month = datetime(first.year + 1, 1, 1).date()
    else:
        next_month = datetime(first.year, first.month + 1, 1).date()

    row = cur.execute("""
      WITH base AS (
        SELECT
          t.amount,
          t.merchant,
          TRIM(t.category) AS category,
          LOWER(a.accountType) AS accountType,
          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      ),
      norm AS (
        SELECT
          amount,
          merchant,
          category,
          accountType,
          CASE
            WHEN length(raw_date) = 8 THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN length(raw_date) = 10 THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT
        COALESCE(SUM(amount), 0) AS total,
        COALESCE(COUNT(*), 0)    AS tx_count
      FROM norm
      WHERE d IS NOT NULL
        AND d >= ? AND d < ?
        AND amount > 0
        AND accountType IN ('checking','credit')
        AND LOWER(TRIM(COALESCE(merchant,''))) = 'unknown'
        AND LOWER(TRIM(COALESCE(category,''))) NOT IN ('card payment','transfer')
    """, (first.isoformat(), next_month.isoformat())).fetchone()

    conn.close()
    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}


@app.get("/unknown-merchant-total-range")
def unknown_merchant_total_range(start: str, end: str):
    conn, cur = with_db_cursor()

    row = cur.execute("""
      WITH base AS (
        SELECT
          t.amount,
          t.merchant,
          TRIM(t.category) AS category,
          LOWER(a.accountType) AS accountType,
          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      ),
      norm AS (
        SELECT
          amount,
          merchant,
          category,
          accountType,
          CASE
            WHEN length(raw_date) = 8 THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN length(raw_date) = 10 THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT
        COALESCE(SUM(amount), 0) AS total,
        COALESCE(COUNT(*), 0)    AS tx_count
      FROM norm
      WHERE d IS NOT NULL
        AND d BETWEEN ? AND ?
        AND amount > 0
        AND accountType IN ('checking','credit')
        AND LOWER(TRIM(COALESCE(merchant,''))) = 'unknown'
        AND LOWER(TRIM(COALESCE(category,''))) NOT IN ('card payment','transfer')
    """, (start, end)).fetchone()

    conn.close()
    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}


def latest_rates_map(cur):
    """
    Returns { account_id: rate } where rate is the most recent
    interest_rates.apr for that account_id.
    """
    rows = cur.execute("""
      SELECT r.account_id, r.apr
      FROM interest_rates r
      JOIN (
        SELECT account_id, MAX(effective_date) AS max_eff
        FROM interest_rates
        GROUP BY account_id
      ) last
        ON last.account_id = r.account_id
       AND last.max_eff = r.effective_date
    """).fetchall()

    return {int(r["account_id"]): float(r["apr"]) for r in rows if r["apr"] is not None}


@app.get("/bank-info")
def bank_info():
    conn, cur = with_db_cursor()

    # Current rate (decimal) from interest_rates: 0.0425 means 4.25%
    rate_now = latest_rates_map(cur)

    # Be robust to schema (you said you won't add extra columns)
    has_credit_limit = _column_exists(cur, "accounts", "credit_limit")
    has_notes = _column_exists(cur, "accounts", "notes")  # only if you choose to add it
    has_card_benefits = _table_exists(cur, "card_benefits")

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

    accounts = cur.execute(account_select).fetchall()
    cards = cur.execute(card_select).fetchall()

    # Optional rewards table
    benefits_rows = []
    if has_card_benefits:
        benefits_rows = cur.execute("""
          SELECT account_id, category, cashback_percent
          FROM card_benefits
          ORDER BY account_id, category
        """).fetchall()

    conn.close()

    # Attach benefits by card
    by_card = {}
    for b in benefits_rows:
        aid = int(b["account_id"])
        by_card.setdefault(aid, []).append({
            "categories": [b["category"]] if b["category"] else [],
            "cashback_percent": float(b["cashback_percent"] or 0.0)
        })

    # Convert decimal rate -> percent number for the frontend pct() helper
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
            "apy": as_percent(rate_now.get(aid)),  # ✅ from interest_rates
        }
        if has_notes:
            item["notes"] = r["notes"]
        accounts_out.append(item)

    cards_out = []
    for r in cards:
        cid = int(r["card_id"])
        item = {
            "card_id": cid,
            "bank": r["bank"],
            "name": r["name"],
            "apr": as_percent(rate_now.get(cid)),  # ✅ from interest_rates
            "benefits": by_card.get(cid, []),
        }
        if has_credit_limit:
            item["credit_limit"] = r["credit_limit"]
        cards_out.append(item)

    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "accounts": accounts_out,
        "credit_cards": cards_out
    }


@app.post("/bank-info/refresh")
def bank_info_refresh():
    # placeholder for now
    return {"ok": True}


from pydantic import BaseModel


class RateUpsert(BaseModel):
    account_id: int
    rate_percent: float  # user enters 3.54 (percent)
    effective_date: str | None = None  # "YYYY-MM-DD" (optional)
    note: str | None = None


@app.post("/interest-rate")
def set_interest_rate(payload: RateUpsert):
    # validate
    try:
        rate_percent = float(payload.rate_percent)
    except Exception:
        return {"ok": False, "error": "rate_percent must be a number"}

    if rate_percent < 0 or rate_percent > 100:
        return {"ok": False, "error": "rate_percent must be between 0 and 100"}

    eff = payload.effective_date
    if not eff:
        eff = datetime.now().strftime("%Y-%m-%d")

    rate_decimal = rate_percent / 100.0

    conn, cur = with_db_cursor()

    # If you have a unique constraint on (account_id, effective_date) this is safe.
    # If you don't, this still prevents duplicates for the same date.
    cur.execute(
        "DELETE FROM interest_rates WHERE account_id = ? AND effective_date = ?",
        (int(payload.account_id), eff)
    )

    cur.execute("""
      INSERT INTO interest_rates (account_id, apr, effective_date, note, created_at)
      VALUES (?, ?, ?, ?, ?)
    """, (
        int(payload.account_id),
        float(rate_decimal),
        eff,
        (payload.note or "").strip() or None,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ))

    conn.commit()
    conn.close()

    return {"ok": True, "account_id": int(payload.account_id), "effective_date": eff, "rate_percent": rate_percent}


@app.get("/month-budget")
def month_budget(min_occ: int = 3, include_stale: bool = False):
    """
    Summary for the current month:
      - income_expected: projected income for the month (paychecks + interest)
      - spent_so_far: actual spending posted so far this month (excludes transfers/card payments)
      - bills_remaining: projected withdrawals remaining from today through month end
      - safe_to_spend: income_expected - spent_so_far - bills_remaining
    """
    today = date.today()
    year = today.year
    month = today.month

    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    # 1) Projected recurring events (withdrawals + income)
    cal = recurring_calendar(year=year, month=month, min_occ=min_occ, include_stale=include_stale)
    events = (cal or {}).get("events") or []

    # Only count *income* that lands in this account for the month budget card
    # (spending / bills remain all-accounts)
    spendable_account_id = 3

    income_expected = 0.0
    bills_remaining = 0.0

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

        is_income = (etype == "income") or (cadence in ("paycheck", "interest"))

        if is_income:
            # Only count income that deposits into the "spendable" account (default: account_id 3)
            try:
                aid = int(e.get("account_id") or -1)
            except Exception:
                aid = -1
            if aid == spendable_account_id:
                income_expected += max(0.0, amt)
            continue

        # Remaining bills: only future-ish events (today through month end)
        if ed < today:
            continue

        # Don't count transfers as "bills"
        if category.lower() == "transfer" or merchant.lower().startswith("from "):
            continue

        bills_remaining += abs(amt)

    # 2) Actual spending so far this month (same rules as /spending)
    conn, cur = with_db_cursor()
    tx_rows = cur.execute("""
      SELECT
        COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
        t.amount,
        TRIM(t.category) AS category,
        LOWER(a.accountType) AS accountType
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """).fetchall()
    conn.close()

    spent_so_far = 0.0
    for r in tx_rows:
        d = parse_posted_date(r["raw_date"])
        if not d:
            continue
        if d < month_start or d > today:
            continue

        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer"):
            continue

        try:
            amt = float(r["amount"])
        except Exception:
            continue

        if r["accountType"] in ("checking", "credit") and amt > 0:
            spent_so_far += amt

    safe_to_spend = income_expected - spent_so_far - bills_remaining

    return {
        "ok": True,
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "as_of": today.isoformat(),
        "income_expected": round(income_expected, 2),
        "spent_so_far": round(spent_so_far, 2),
        "bills_remaining": round(bills_remaining, 2),
        "safe_to_spend": round(safe_to_spend, 2),
    }


@app.get("/transaction/{tx_id}")
def transaction_detail(tx_id: str):
    """Return *all* columns for a single transaction, plus account metadata."""
    conn, cur = with_db_cursor()

    row = cur.execute(
        """
        SELECT
          t.*,
          a.institution AS bank,
          a.name        AS card,
          LOWER(a.accountType) AS accountType
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.id = ?
        LIMIT 1
        """,
        (tx_id,)
    ).fetchone()

    conn.close()
    if not row:
        return {"ok": False, "error": "not_found", "id": tx_id}

    return {"ok": True, "transaction": dict(row)}


@app.post("/transactions/{tx_id}/attach-receipt/{receipt_id}")
def attach_receipt(tx_id: str, receipt_id: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # verify tx exists
    cur.execute("SELECT 1 FROM transactions WHERE id=?", (tx_id,))
    if not cur.fetchone():
        con.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    # verify receipt exists
    cur.execute("SELECT 1 FROM receipts WHERE id=?", (receipt_id,))
    if not cur.fetchone():
        con.close()
        raise HTTPException(status_code=404, detail="Receipt not found")

    cur.execute(
        "INSERT OR IGNORE INTO transaction_receipts (transaction_id, receipt_id) VALUES (?, ?)",
        (tx_id, receipt_id),
    )
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/receipts-page")
def receipts_page():
    return FileResponse(os.path.join("static", "receipts.html"))

@app.get("/transactions/{tx_id}/receipts")
def list_receipts_for_tx(tx_id: str):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute("""
      SELECT r.id, r.created_at, r.merchant_name, r.purchase_date, r.total, r.parse_status, r.confidence
      FROM transaction_receipts tr
      JOIN receipts r ON r.id = tr.receipt_id
      WHERE tr.transaction_id = ?
      ORDER BY datetime(r.created_at) DESC
    """, (tx_id,)).fetchall()

    con.close()
    return {"tx_id": tx_id, "receipts": [dict(r) for r in rows]}
