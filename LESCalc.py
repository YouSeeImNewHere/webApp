from dataclasses import dataclass
import calendar
from datetime import date

BASE_PAY_TABLE = {
    "E6": {0: 3276.60, 2: 3606.00, 3: 3765.00, 4: 3919.80, 6: 4080.60, 8: 4443.90, 10: 4585.20},
    "E5": {0: 3220.50, 2: 3466.50, 3: 3637.50, 4: 3802.20, 6: 3959.40, 8: 4124.40, 10: 4234.50},
    "E4": {0: 3027.30, 2: 3182.10, 3: 3354.90, 4: 3524.70, 6: 3675.60, 8: 3675.60, 10: 3675.60},
    "E3": {0: 2733.00, 2: 2904.60, 3: 3081.00, 4: 3081.00, 6: 3081.00, 8: 3081.00, 10: 3081.00},
    "E2": {0: 2599.20, 2: 2599.20, 3: 2599.20, 4: 2599.20, 6: 2599.20, 8: 2599.20, 10: 2599.20},
    "E1": {0: 2319.00, 2: 2319.00, 3: 2319.00, 4: 2319.00, 6: 2319.00, 8: 2319.00, 10: 2319.00},
}


# BAH lookup table (example values you provided)
# key: paygrade (rank), value: (with_dependents, without_dependents)
BAH_TABLE = {
    "E1": (2253.00, 1866.00),
    "E2": (2253.00, 1866.00),
    "E3": (2253.00, 1866.00),
    "E4": (2253.00, 1866.00),
    "E5": (2358.00, 2043.00),
    "E6": (2661.00, 2151.00),
}

def get_bah(paygrade: str, has_dependents: bool) -> float:
    """
    Returns BAH for the given paygrade based on whether member has dependents.
    """
    if paygrade not in BAH_TABLE:
        raise ValueError(f"Unknown paygrade {paygrade}. Add it to BAH_TABLE.")
    with_dep, without_dep = BAH_TABLE[paygrade]
    return with_dep if has_dependents else without_dep

def years_of_service(start: date, as_of: date) -> float:
    return (as_of - start).days / 365.2425

YOS_BANDS = [0, 2, 3, 4, 6, 8, 10]

def yos_band(yos: float) -> int:
    # returns the threshold (0,2,3,4,6,8,10)
    band = 0
    for t in YOS_BANDS:
        if yos >= t:
            band = t
    return band

def get_base_pay(paygrade: str, service_start: date, as_of: date) -> float:
    if paygrade not in BASE_PAY_TABLE:
        raise ValueError(f"Paygrade {paygrade} not in BASE_PAY_TABLE.")
    yos = years_of_service(service_start, as_of)
    band = yos_band(yos)
    row = BASE_PAY_TABLE[paygrade]
    if band not in row:
        raise ValueError(f"No base pay value for {paygrade} at YOS band {band}.")
    return row[band]

@dataclass
class LESInputs:
    base_pay: float
    submarine_pay: float
    career_sea_pay: float
    spec_duty_pay: float
    bas: float
    bah: float

@dataclass
class W4Settings:
    pay_periods_per_year: int      # monthly=12
    filing_status: str             # "S", "M", "H"
    step2_multiple_jobs: bool      # Mult Jobs checkbox
    dep_under17: int               # count
    other_dep: int                 # count
    other_income_annual: float     # W-4 4a
    other_deductions_annual: float # W-4 4b
    extra_withholding: float       # W-4 4c (per pay period)

@dataclass
class LESOutputs:
    federal_taxes: float
    fica_social_security: float
    fica_medicare: float
    sgli: float
    afrh: float
    roth_tsp: float
    meal_deduction: float
    mid_month_pay: float
    eom: float

def truncate_cents(x: float) -> float:
    return int(x * 100) / 100.0

def calc_meal_deduction(rate_per_day: float, year: int, month: int, end_day: int) -> float:
    """
    DFAS-y rule you specified:
      - charge 1.00 for days 1..(end_day-1)
      - on end_day charge:
          * 1.00 if end_day is the last day of the month
          * 0.25 otherwise
      - final amount is truncated to cents (to match your LES)
    """
    if end_day <= 0:
        return 0.0

    last_dom = calendar.monthrange(year, month)[1]
    last_day_fraction = 1.0 if end_day >= last_dom else 0.25

    full_days = max(0, end_day - 1)
    charged_days = full_days + last_day_fraction
    return truncate_cents(rate_per_day * charged_days)


def compute_fitw_worksheet_1a_monthly_single_standard(
    wage_period: float,
    w4: W4Settings,
) -> float:
    """
    Matches your LES using Worksheet 1A + Annual Percentage Method table
    for STANDARD withholding schedules (Step2 unchecked), Single.
    """
    P = w4.pay_periods_per_year

    # Worksheet 1A line 1g (standard amount) for Step2 unchecked:
    # - $12,900 if MFJ
    # - $8,600 otherwise (Single/HOH/MFS)
    if (w4.filing_status == "M") and (not w4.step2_multiple_jobs):
        standard_amount = 12900.00
    else:
        standard_amount = 8600.00

    # Step 1 (annualize + adjustments)
    annual_wages = wage_period * P
    annual_wages += w4.other_income_annual
    adjusted_annual = annual_wages - (w4.other_deductions_annual + standard_amount)
    if adjusted_annual < 0:
        adjusted_annual = 0.0

    # Step 2: Annual Percentage Method table lookup
    # For your income range, Single STANDARD row is:
    # A=18,325  B=54,875  C=1,192.50  D=12%
    # (If you want this fully general, we’d encode the whole table and pick the row.)
    A, B, C, D = 18325.00, 54875.00, 1192.50, 0.12
    if not (A <= adjusted_annual < B):
        raise ValueError("Adjusted annual wage fell outside the hardcoded bracket; "
                         "encode full Pub 15-T table to generalize.")

    annual_tax = C + D * (adjusted_annual - A)
    per_period_tax = annual_tax / P

    # Step 3 credits: Step 3 is $2,000 per child under 17 + $500 other dep (annual)
    step3_annual_credit = (w4.dep_under17 * 2000.0) + (w4.other_dep * 500.0)
    per_period_credit = step3_annual_credit / P
    per_period_tax = per_period_tax - per_period_credit
    if per_period_tax < 0:
        per_period_tax = 0.0

    # Step 4c extra withholding
    per_period_tax = per_period_tax + w4.extra_withholding

    # Your LES matches truncate-to-cents behavior at the end
    return truncate_cents(per_period_tax)

def generate_les_right_side(
    inp: LESInputs,
    w4: W4Settings,
    tsp_rate: float = 0.05,
    sgli: float = 26.00,
    afrh: float = 0.50,
    fica_wages_include_special_pays: bool = False,

    # NEW: meal deduction inputs
    meal_rate_per_day: float = 13.30,
    meal_year: int | None = None,
    meal_month: int | None = None,
    meal_end_day: int | None = None,

    mid_month_pay: float = 0.0,
) -> LESOutputs:
    # Meal deduction (computed if year/month/end_day provided; otherwise 0.0)
    if meal_year is not None and meal_month is not None and meal_end_day is not None:
        meal_deduction = calc_meal_deduction(meal_rate_per_day, meal_year, meal_month, meal_end_day)
    else:
        meal_deduction = 0.0


    # Taxable wages ("Wage Period" on LES)
    taxable = inp.base_pay + inp.submarine_pay + inp.career_sea_pay + inp.spec_duty_pay

    # Federal withholding via Worksheet 1A (your case)
    fed = compute_fitw_worksheet_1a_monthly_single_standard(taxable, w4)

    # FICA wages: your LES shows base-pay-only FICA
    fica_wages = taxable if fica_wages_include_special_pays else inp.base_pay

    fica_ss = truncate_cents(fica_wages * 0.062)
    fica_med = truncate_cents(fica_wages * 0.0145)

    roth_tsp = truncate_cents(inp.base_pay * tsp_rate)

    # Total entitlements (include BAH/BAS; do NOT include mid-month here)
    # Total entitlements
    total_entitlements = taxable + inp.bas + inp.bah

    # Deductions excluding mid-month (and excluding allotments if you add them later)
    deductions_no_mid = fed + fica_ss + fica_med + sgli + afrh + roth_tsp + meal_deduction

    # NEW: compute mid-month pay
    mid_month_pay = calc_mid_month_pay(
        total_entitlements=total_entitlements,
        total_deductions_excluding_mid=deductions_no_mid,
        allotments_total=0.0,  # set from LES/allotments data if any
        mid_month_fraction=0.5,  # default
        mid_month_collections_total=0.0,  # set from LES collections if any
    )

    # Total deductions includes mid-month
    total_deductions = deductions_no_mid + mid_month_pay

    # EOM deposit
    eom = truncate_cents(total_entitlements - total_deductions)

    return LESOutputs(
        federal_taxes=fed,
        fica_social_security=fica_ss,
        fica_medicare=fica_med,
        sgli=sgli,
        afrh=afrh,
        roth_tsp=roth_tsp,
        meal_deduction=meal_deduction,
        mid_month_pay=mid_month_pay,
        eom=eom,
    )

def calc_mid_month_pay(
    total_entitlements: float,
    total_deductions_excluding_mid: float,
    allotments_total: float = 0.0,
    mid_month_fraction: float = 0.5,
    mid_month_collections_total: float = 0.0,
) -> float:
    """
    Deterministic DFAS-style model:
      1) Compute projected monthly net (excluding the MID-MONTH-PAY line itself)
      2) Mid-month is a fraction of projected net (commonly 0.5)
      3) Subtract half of allotments from mid-month (DFAS rule)
      4) Subtract any mid-month-specific collections
      5) Truncate to cents to match your LES behavior
    """
    projected_monthly_net = (
        total_entitlements
        - total_deductions_excluding_mid
        - allotments_total
    )
    mid = (
        mid_month_fraction * projected_monthly_net
        - 0.5 * allotments_total
        - mid_month_collections_total
    )
    return truncate_cents(mid)

paygrade = "E4"          # rank
has_dependents = False   # True/False
bah = get_bah(paygrade, has_dependents)

service_start_date = date(2021, 6, 30)
as_of_date = date(2025, 11, 30)  # pick month end or LES date

base_pay = get_base_pay(paygrade, service_start_date, as_of_date)

inp = LESInputs(
    base_pay=base_pay,
    submarine_pay=270.00,
    career_sea_pay=160.00,
    spec_duty_pay=150.00,
    bas=465.77,
    bah=bah,
)

w4 = W4Settings(
    pay_periods_per_year=12,
    filing_status="S",
    step2_multiple_jobs=False,
    dep_under17=0,
    other_dep=0,
    other_income_annual=0.00,
    other_deductions_annual=0.00,
    extra_withholding=0.00,
)

# October: ends on last day (31) => full day on the 31st
inp_nov = LESInputs(
    base_pay=base_pay,
    submarine_pay=270.00,
    career_sea_pay=160.00,
    spec_duty_pay=150.00,
    bas=465.77,
    bah=1866.00,   # <-- November BAH
)

out_nov = generate_les_right_side(
    inp_nov, w4,
    meal_rate_per_day=13.30,
    meal_year=2025, meal_month=11, meal_end_day=19,
)


print(inp_nov)
print(out_nov)
