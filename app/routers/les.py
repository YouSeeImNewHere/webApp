from __future__ import annotations

import inspect
import calendar
from datetime import timedelta, date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.analytics import parse_posted_date, parse_iso
from db import with_db_cursor
from app.core.time import today_local

router = APIRouter()

# =============================================================================
# LES (Postgres)
# =============================================================================

from LESCalc import (
    LESInputs as _LESInputs,
    W4Settings as _W4Settings,
    get_base_pay as _get_base_pay,
    get_bah as _get_bah,
    generate_les_right_side as _gen_les,
)

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    weekday: 0=Mon..6=Sun
    n: 1..5
    """
    d = date(year, month, 1)
    # advance to first desired weekday
    while d.weekday() != weekday:
        d += timedelta(days=1)
    # then jump (n-1) weeks
    d += timedelta(days=7 * (n - 1))
    return d

def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    last_dom = calendar.monthrange(year, month)[1]
    d = date(year, month, last_dom)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d

def _observe_holiday(d: date) -> date:
    # If holiday lands Sat => observed Fri; Sun => observed Mon
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d

def _us_federal_holidays_observed(year: int) -> set[date]:
    """
    Minimal US federal observed holidays set, enough for your DFAS deposit logic.
    """
    hol = set()

    # New Year's Day (Jan 1)
    hol.add(_observe_holiday(date(year, 1, 1)))

    # MLK Day (3rd Mon in Jan)
    hol.add(_nth_weekday_of_month(year, 1, 0, 3))

    # Washington's Birthday / Presidents Day (3rd Mon in Feb)
    hol.add(_nth_weekday_of_month(year, 2, 0, 3))

    # Memorial Day (last Mon in May)
    hol.add(_last_weekday_of_month(year, 5, 0))

    # Juneteenth (Jun 19)
    hol.add(_observe_holiday(date(year, 6, 19)))

    # Independence Day (Jul 4)
    hol.add(_observe_holiday(date(year, 7, 4)))

    # Labor Day (1st Mon in Sep)
    hol.add(_nth_weekday_of_month(year, 9, 0, 1))

    # Columbus Day (2nd Mon in Oct)
    hol.add(_nth_weekday_of_month(year, 10, 0, 2))

    # Veterans Day (Nov 11)
    hol.add(_observe_holiday(date(year, 11, 11)))

    # Thanksgiving (4th Thu in Nov)
    hol.add(_nth_weekday_of_month(year, 11, 3, 4))

    # Christmas Day (Dec 25)
    hol.add(_observe_holiday(date(year, 12, 25)))

    return hol

def _previous_workday(d: date, holidays: set[date]) -> date:
    # roll back for weekend/holiday
    while d.weekday() >= 5 or d in holidays:
        d -= timedelta(days=1)
    return d

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

@router.post("/les/paychecks")
def les_paychecks(req: LESPaychecksRequest):
    y, m = int(req.year), int(req.month)
    p = req.profile

    # as_of date: last day of the month being viewed
    last_dom = calendar.monthrange(y, m)[1]
    as_of = date(y, m, last_dom)

    # compute base pay from chart in LESCalc
    start_parts = [int(x) for x in p.service_start.split("-")]
    start_dt = date(start_parts[0], start_parts[1], start_parts[2])
    paygrade = p.paygrade.replace(" ", "").upper().replace("--", "-")
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
        last_dom_local = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_dom_local)

    def _get_actual_midmonth_deposit(cur, year: int, month: int) -> float | None:
        """
        If we've already received the DFAS mid-month pay for (year, month),
        return the *deposit amount* (positive float). Otherwise None.

        Assumes your DB stores income as NEGATIVE amounts (same as your sqlite version).
        """
        month_start, month_end = _month_bounds(year, month)
        target_dep = deposit_for_target(date(year, month, 15))

        # pull candidate DFAS paycheck tx in this month.
        # Do not hard-require category/account here: some imports temporarily
        # misclassify income rows or route deposits to a different account.
        # We still prefer account 3 + Income rows when ranking candidates.
        cur.execute(
            """
            SELECT postedDate, purchaseDate, amount, merchant, account_id, category
            FROM transactions
            WHERE UPPER(merchant) LIKE '%%DFAS%%'
            """,
        )
        rows = cur.fetchall() or []

        candidates = []
        for r in rows:
            posted = parse_posted_date(r.get("posteddate") or r.get("postedDate"))
            purchase = parse_posted_date(r.get("purchasedate") or r.get("purchaseDate"))
            tx_date = posted if posted is not None else purchase
            if tx_date is None:
                continue
            if not (month_start <= tx_date <= month_end):
                continue

            try:
                amt = float(r.get("amount"))
            except Exception:
                continue

            if abs(amt) < 100:
                continue

            dep_amt = abs(amt)
            delta_days = abs((tx_date - target_dep).days)
            acct_rank = 0 if int(r.get("account_id") or 0) == 3 else 1
            category = str(r.get("category") or "").strip().lower()
            cat_rank = 0 if category == "income" else 1
            candidates.append((delta_days, acct_rank, cat_rank, tx_date, dep_amt))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        best_delta, _, _, _, best_amt = candidates[0]
        if best_delta > 5:
            return None
        return float(best_amt)

    def _compute_les_out_for_month(year: int, month: int):
        last_dom_local = calendar.monthrange(year, month)[1]
        as_of_local = date(year, month, last_dom_local)

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

            mid_month_fraction=p.mid_month_fraction,
            allotments_total=p.allotments_total,
            mid_month_collections_total=p.mid_month_collections_total,
        )

        allowed_local = set(inspect.signature(_gen_les).parameters.keys())
        les_kwargs_local = {k: v for k, v in les_kwargs_local.items() if k in allowed_local}

        return _gen_les(inp_local, w4, **les_kwargs_local)

    # ---- Detect actual mid-month pay for the viewed month and adjust EOM ----
    with with_db_cursor() as (conn2, cur2):
        actual_mid = _get_actual_midmonth_deposit(cur2, y, m)

    projected_monthly_net = float(out.mid_month_pay) + float(out.eom)
    mid_month_display = float(actual_mid) if actual_mid is not None else float(out.mid_month_pay)
    eom_display = (projected_monthly_net - mid_month_display) if actual_mid is not None else float(out.eom)

    # ---- Also compute the "1st of month" paycheck as PREVIOUS month’s EOM ----
    prev_year, prev_month = (y - 1, 12) if m == 1 else (y, m - 1)
    out_prev = _compute_les_out_for_month(prev_year, prev_month)
    projected_prev_net = float(out_prev.mid_month_pay) + float(out_prev.eom)

    with with_db_cursor() as (conn3, cur3):
        prev_actual_mid = _get_actual_midmonth_deposit(cur3, prev_year, prev_month)

    prev_mid_display = float(prev_actual_mid) if prev_actual_mid is not None else float(out_prev.mid_month_pay)
    prev_eom_display = (projected_prev_net - prev_mid_display) if prev_actual_mid is not None else float(out_prev.eom)

    events = []
    for target in targets:
        dep = deposit_for_target(target)

        include = ((target.year == y and target.month == m) or (dep.year == y and dep.month == m))
        if not include:
            continue

        # only emit events that land in the viewed month
        if not (dep.year == y and dep.month == m):
            continue

        # Map targets to the correct month:
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
    # model (projected)
    "projected_mid_month": round(float(out.mid_month_pay), 2),
    "projected_eom": round(float(out.eom), 2),
    "projected_monthly_net": round(float(projected_monthly_net), 2),

    # display (what the UI should show)
    "mid_month_pay": round(float(mid_month_display), 2),
    "eom": round(float(eom_display), 2),

    # helpful flags for the UI logic
    "mid_month_is_actual": bool(actual_mid is not None),
    "mid_month_actual": round(float(actual_mid), 2) if actual_mid is not None else None,
},

    }

    return {"events": events, "breakdown": breakdown}
