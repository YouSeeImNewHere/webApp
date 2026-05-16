from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from app.core.transactions_ignore import ensure_transactions_ignore_column
from app.routers.category_rules import month_budget_home_cached
from db import query_db

router = APIRouter()

_EXCLUDED_SPEND_CATEGORIES = {"transfer", "card payment", "cash withdrawal"}
_SUBSCRIPTION_HINT_CATEGORIES = {
    "subscription",
    "subscriptions",
    "utilities",
    "insurance",
    "internet",
    "phone",
    "rent",
    "mortgage",
}


def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=401, detail="unauthorized")
    return int(tid)


def _parse_month_yyyy_mm(raw: str | None) -> tuple[int, int]:
    txt = str(raw or "").strip()
    if not txt:
        now = datetime.now()
        return int(now.year), int(now.month)
    try:
        dt = datetime.strptime(txt, "%Y-%m")
        return int(dt.year), int(dt.month)
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(int(year), int(month), 1)
    end = date(int(year), int(month), calendar.monthrange(int(year), int(month))[1])
    return start, end


def _norm_category(v: Any) -> str:
    return str(v or "").strip().lower()


def _to_amount(v: Any) -> float:
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0


def _pct_change(curr: float, prev: float) -> float | None:
    if abs(prev) < 1e-9:
        return None
    return ((float(curr) - float(prev)) / abs(float(prev))) * 100.0


def _month_tx_rows(tid: int | None, start_date: date, end_date: date) -> list[dict[str, Any]]:
    return query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            t.account_id::bigint AS account_id,
            t.amount::double precision AS amount,
            TRIM(COALESCE(t.merchant, '')) AS merchant,
            TRIM(COALESCE(t.category, '')) AS category,
            LOWER(a.accountType) AS account_type,
            TRIM(COALESCE(a.institution, '')) AS bank,
            TRIM(COALESCE(a.name, '')) AS account_name,
            COALESCE(NULLIF(TRIM(t.postedDate), 'unknown'), NULLIF(TRIM(t.purchaseDate), 'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date) = 8 THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT id, account_id, amount, merchant, category, account_type, bank, account_name, d
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        ORDER BY d ASC, id ASC
        """,
        ((int(tid), int(tid), start_date, end_date) if tid else (start_date, end_date)),
    )


def _account_start_end_rows(tid: int | None, start_date: date, end_date: date) -> list[dict[str, Any]]:
    return query_db(
        f"""
        WITH tx_base AS (
          SELECT
            t.account_id::bigint AS account_id,
            t.amount::double precision AS amount,
            LOWER(a.accountType) AS account_type,
            COALESCE(NULLIF(TRIM(t.postedDate), 'unknown'), NULLIF(TRIM(t.purchaseDate), 'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          {"WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false" if tid else "WHERE COALESCE(t.is_ignored, false) = false"}
        ),
        tx_norm AS (
          SELECT
            account_id,
            account_type,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date) = 8 THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d,
            CASE
              WHEN account_type = 'investment' THEN amount
              ELSE -amount
            END AS delta
          FROM tx_base
        ),
        seed AS (
          SELECT account_id::bigint AS account_id, COALESCE(SUM(start), 0)::double precision AS start_total
          FROM startingbalance
          {"WHERE tenant_id = %s" if tid else ""}
          GROUP BY account_id
        )
        SELECT
          a.id::bigint AS account_id,
          TRIM(COALESCE(a.institution, '')) AS bank,
          TRIM(COALESCE(a.name, '')) AS account_name,
          LOWER(a.accountType) AS account_type,
          COALESCE(s.start_total, 0)::double precision AS start_seed,
          COALESCE(SUM(CASE WHEN t.d < %s THEN t.delta ELSE 0 END), 0)::double precision AS delta_before,
          COALESCE(SUM(CASE WHEN t.d BETWEEN %s AND %s THEN t.delta ELSE 0 END), 0)::double precision AS delta_in_month
        FROM accounts a
        LEFT JOIN seed s ON s.account_id = a.id
        LEFT JOIN tx_norm t ON t.account_id = a.id
        {"WHERE a.tenant_id = %s" if tid else ""}
        GROUP BY a.id, a.institution, a.name, a.accountType, s.start_total
        ORDER BY LOWER(a.institution), LOWER(a.name), a.id
        """,
        (
            (int(tid), int(tid), int(tid), start_date, start_date, end_date, int(tid))
            if tid
            else (start_date, start_date, end_date)
        ),
    )


@router.get("/reports/monthly")
def monthly_report(month: str = Query(default="", description="YYYY-MM")):
    ensure_transactions_ignore_column()
    tid = _require_tenant_id()
    year, mm = _parse_month_yyyy_mm(month)
    start_date, end_date = _month_bounds(year, mm)

    prev_year, prev_month = (year - 1, 12) if mm == 1 else (year, mm - 1)
    prev_start, prev_end = _month_bounds(prev_year, prev_month)

    rows = [dict(r) for r in _month_tx_rows(tid, start_date, end_date)]
    prev_rows = [dict(r) for r in _month_tx_rows(tid, prev_start, prev_end)]

    category_totals: dict[str, float] = {}
    spending_total = 0.0
    income_total = 0.0

    biggest_outflows: list[dict[str, Any]] = []
    biggest_inflows: list[dict[str, Any]] = []

    recurring_hits: dict[str, dict[str, Any]] = {}
    for r in rows:
        amt = _to_amount(r.get("amount"))
        category = _norm_category(r.get("category"))
        acct_type = str(r.get("account_type") or "").strip().lower()
        merchant = str(r.get("merchant") or "").strip()
        d = r.get("d")
        d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d or "")

        if (
            amt > 0
            and acct_type in {"checking", "credit"}
            and category not in _EXCLUDED_SPEND_CATEGORIES
        ):
            spending_total += amt
            key = category or "Uncategorized"
            category_totals[key] = category_totals.get(key, 0.0) + amt
            biggest_outflows.append(
                {
                    "date": d_iso,
                    "merchant": merchant or "(No merchant)",
                    "category": r.get("category") or "",
                    "amount": round(amt, 2),
                    "account": f'{r.get("bank") or ""} {r.get("account_name") or ""}'.strip(),
                }
            )

            merch_key = (merchant or "").strip().upper()
            if merch_key:
                bucket = recurring_hits.get(merch_key)
                if not bucket:
                    bucket = {
                        "merchant": merchant,
                        "count": 0,
                        "total": 0.0,
                        "category": r.get("category") or "",
                    }
                    recurring_hits[merch_key] = bucket
                bucket["count"] = int(bucket.get("count") or 0) + 1
                bucket["total"] = float(bucket.get("total") or 0.0) + amt
                if not bucket.get("category") and r.get("category"):
                    bucket["category"] = r.get("category")

        if amt < 0 and acct_type in {"checking", "savings", "investment"}:
            inflow = abs(amt)
            income_total += inflow
            biggest_inflows.append(
                {
                    "date": d_iso,
                    "merchant": merchant or "(No merchant)",
                    "category": r.get("category") or "",
                    "amount": round(inflow, 2),
                    "account": f'{r.get("bank") or ""} {r.get("account_name") or ""}'.strip(),
                }
            )

    prev_spending = 0.0
    prev_income = 0.0
    for r in prev_rows:
        amt = _to_amount(r.get("amount"))
        category = _norm_category(r.get("category"))
        acct_type = str(r.get("account_type") or "").strip().lower()
        if (
            amt > 0
            and acct_type in {"checking", "credit"}
            and category not in _EXCLUDED_SPEND_CATEGORIES
        ):
            prev_spending += amt
        if amt < 0 and acct_type in {"checking", "savings", "investment"}:
            prev_income += abs(amt)

    acct_rows = [dict(r) for r in _account_start_end_rows(tid, start_date, end_date)]
    accounts_out: list[dict[str, Any]] = []
    total_start_balance = 0.0
    total_end_balance = 0.0
    for a in acct_rows:
        start_bal = _to_amount(a.get("start_seed")) + _to_amount(a.get("delta_before"))
        end_bal = start_bal + _to_amount(a.get("delta_in_month"))
        total_start_balance += start_bal
        total_end_balance += end_bal
        accounts_out.append(
            {
                "account_id": int(a.get("account_id") or 0),
                "bank": a.get("bank") or "",
                "name": a.get("account_name") or "",
                "account_type": a.get("account_type") or "",
                "start_balance": round(start_bal, 2),
                "end_balance": round(end_bal, 2),
                "change": round(end_bal - start_bal, 2),
            }
        )

    categories_out = [
        {"category": (k if k != "uncategorized" else "Uncategorized"), "amount": round(v, 2)}
        for k, v in sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    recurring_out = []
    for bucket in recurring_hits.values():
        count = int(bucket.get("count") or 0)
        cat = _norm_category(bucket.get("category"))
        if count >= 2 or cat in _SUBSCRIPTION_HINT_CATEGORIES:
            recurring_out.append(
                {
                    "merchant": bucket.get("merchant") or "(No merchant)",
                    "category": bucket.get("category") or "",
                    "hits": count,
                    "total": round(float(bucket.get("total") or 0.0), 2),
                }
            )
    recurring_out.sort(key=lambda x: (x["total"], x["hits"]), reverse=True)

    biggest_outflows.sort(key=lambda x: x["amount"], reverse=True)
    biggest_inflows.sort(key=lambda x: x["amount"], reverse=True)

    try:
        mb = month_budget_home_cached(year, mm)
    except Exception:
        mb = {}

    budget_allocated = _to_amount((mb or {}).get("allocations_total"))
    budget_spent = _to_amount((mb or {}).get("budgeted_spent_total"))
    budget_remaining = max(0.0, budget_allocated - budget_spent)

    return {
        "ok": True,
        "month": f"{year:04d}-{mm:02d}",
        "range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "summary": {
            "income": round(income_total, 2),
            "spending": round(spending_total, 2),
            "net": round(income_total - spending_total, 2),
            "starting_balance": round(total_start_balance, 2),
            "ending_balance": round(total_end_balance, 2),
        },
        "category_breakdown": categories_out,
        "account_summary": accounts_out,
        "biggest_transactions": {
            "outflows": biggest_outflows[:8],
            "inflows": biggest_inflows[:8],
        },
        "recurring_subscriptions": recurring_out[:10],
        "budget_performance": {
            "planned_allocations": round(budget_allocated, 2),
            "actual_spent_on_allocated": round(budget_spent, 2),
            "remaining_allocated": round(budget_remaining, 2),
            "free_spend_so_far": round(_to_amount((mb or {}).get("spent_so_far")), 2),
        },
        "changes_vs_previous_month": {
            "income_prev_month": round(prev_income, 2),
            "spending_prev_month": round(prev_spending, 2),
            "income_change_pct": (round(_pct_change(income_total, prev_income), 2) if _pct_change(income_total, prev_income) is not None else None),
            "spending_change_pct": (round(_pct_change(spending_total, prev_spending), 2) if _pct_change(spending_total, prev_spending) is not None else None),
            "income_change_abs": round(income_total - prev_income, 2),
            "spending_change_abs": round(spending_total - prev_spending, 2),
        },
    }
