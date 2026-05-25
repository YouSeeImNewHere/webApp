from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.core.tenancy import current_tenant_id, set_current_tenant_id, reset_current_tenant_id
from app.core.redis_cache import get_redis
from app.core.time import today_local
from app.routers.analytics import spending_unbudgeted_safe_range
from app.routers.accounts import bank_totals
from app.routers.page_payloads import (
    _build_widget_payload_for_tenant_version,
    _widget_redis_get_payload,
    _widget_redis_get_version,
    _widget_version_for_tenant_cached,
    refresh_widget_cache_for_tenant,
)
from db import query_db

router = APIRouter()


def _resolve_tenant_id(explicit_tid: Optional[int]) -> Optional[int]:
    if explicit_tid is not None:
        return int(explicit_tid)
    tid = current_tenant_id()
    if tid:
        return int(tid)
    fallback = int(os.getenv("GARMIN_TENANT_ID", "1"))
    return int(fallback)


@router.get("/garmin/info")
def garmin_info(
    tenant_id: Optional[int] = Query(default=None),
    widget_version: Optional[int] = Query(default=None),
    force: int = Query(default=0),
):
    tid = _resolve_tenant_id(tenant_id)
    force_refresh = int(force or 0) == 1

    payload = None
    current_version = 0

    if get_redis() is None:
        # Redis-less fallback: can only compute live payload.
        current_version = int(_widget_version_for_tenant_cached(tid))
        if (not force_refresh) and (widget_version is not None) and int(widget_version) == int(current_version):
            return {
                "status": "OK",
                "changed": False,
                "widget_version": int(current_version),
                "tenant_id": int(tid or 0),
            }
        payload = _build_widget_payload_for_tenant_version(tid, int(current_version))
    else:
        if force_refresh:
            # Force rebuild and bump, like manual widget refresh.
            current_version = int(refresh_widget_cache_for_tenant(tid, bump_version=True) or 0)
        else:
            current_version = int(_widget_redis_get_version(tid) or 0)
            if (widget_version is not None) and int(widget_version) == int(current_version):
                return {
                    "status": "OK",
                    "changed": False,
                    "widget_version": int(current_version),
                    "tenant_id": int(tid or 0),
                }

        payload = _widget_redis_get_payload(tid)
        if not isinstance(payload, dict):
            return {
                "status": "OK",
                "changed": False,
                "warming": True,
                "widget_version": int(current_version),
                "tenant_id": int(tid or 0),
            }

    today = (payload.get("today") or {})
    credit = (payload.get("credit") or {})
    month = (payload.get("month") or {})
    credit_accounts = (credit.get("accounts") or [])
    credit_cards = []
    for a in credit_accounts:
        if not isinstance(a, dict):
            continue
        raw_name = str(a.get("name") or "Card")
        name = "".join(ch if ord(ch) < 128 else "-" for ch in raw_name)
        credit_cards.append(
            {
                "name": name,
                "used": round(float(a.get("used") or 0.0), 2),
                "cap": round(float(a.get("cap") or 0.0), 2),
                "pct": int(a.get("pct") or 0),
            }
        )
    # Weekly trend payload for watch chart (7d), computed only when returning changed payload.
    weekly_safe = []
    weekly_spend = []
    weekly_dates = []
    account_rows = []
    token = set_current_tenant_id(int(tid) if tid else None)
    try:
        end_d = today_local()
        start_d = end_d - timedelta(days=6)
        trend = spending_unbudgeted_safe_range(start=start_d.isoformat(), end=end_d.isoformat()) or {}
        series = trend.get("series") or []
        for p in series:
            weekly_safe.append(round(float((p or {}).get("daily_safe_to_spend") or 0.0), 2))
            weekly_spend.append(round(float((p or {}).get("unbudgeted_spend") or 0.0), 2))
            weekly_dates.append(str((p or {}).get("date") or ""))
    except Exception:
        weekly_safe = []
        weekly_spend = []
    finally:
        reset_current_tenant_id(token)

    # Checking/Savings accounts with approximate month growth.
    token = set_current_tenant_id(int(tid) if tid else None)
    try:
        bt = bank_totals() or {}
        raw_accounts = []
        raw_accounts.extend(((bt.get("checking") or {}).get("accounts") or []))
        raw_accounts.extend(((bt.get("savings") or {}).get("accounts") or []))

        today_d = today_local()
        month_start = today_d.replace(day=1)
        month_end_excl = today_d + timedelta(days=1)
        tx_rows = query_db(
            """
            WITH base AS (
              SELECT
                t.account_id,
                t.amount::double precision AS amount,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'),
                         NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
                LOWER(a.accountType) AS account_type
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE LOWER(a.accountType) IN ('checking','savings')
                AND COALESCE(t.is_ignored, false) = false
                AND t.tenant_id = %s
                AND a.tenant_id = %s
            ),
            norm AS (
              SELECT
                account_id,
                amount,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT account_id, COALESCE(SUM(amount),0)::double precision AS amt
            FROM norm
            WHERE d IS NOT NULL
              AND d >= %s
              AND d < %s
            GROUP BY account_id
            """,
            (int(tid or 0), int(tid or 0), month_start, month_end_excl),
        ) or []
        month_amt_by_id = {int(r.get("account_id") or 0): float(r.get("amt") or 0.0) for r in tx_rows}

        for a in raw_accounts:
            aid = int(a.get("id") or 0)
            total_now = float(a.get("total") or 0.0)
            # For checking/savings balance math: balance = start - trans, so month delta ~= -month_tx.
            month_delta = -float(month_amt_by_id.get(aid, 0.0))
            month_start_bal = total_now - month_delta
            if abs(month_start_bal) < 1e-6:
                growth_pct = 0.0
            else:
                growth_pct = (month_delta / month_start_bal) * 100.0
            account_rows.append(
                {
                    "name": str(a.get("name") or "Account"),
                    "total": round(total_now, 2),
                    "growth_pct": round(growth_pct, 1),
                }
            )
        account_rows.sort(key=lambda x: abs(float(x.get("total") or 0.0)), reverse=True)
    except Exception:
        account_rows = []
    finally:
        reset_current_tenant_id(token)

    # Never return blank chart data to the watch. Keep 7 points.
    if len(weekly_safe) == 0 or len(weekly_spend) == 0:
        fallback_safe = round(float(today.get("daily_limit") or today.get("baseline") or 0.0), 2)
        weekly_safe = [fallback_safe, fallback_safe, fallback_safe, fallback_safe, fallback_safe, fallback_safe, fallback_safe]
        weekly_spend = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        end_d = today_local()
        weekly_dates = []
        i = 6
        while i >= 0:
            weekly_dates.append((end_d - timedelta(days=i)).isoformat())
            i -= 1

    return {
        "status": "OK",
        "changed": True,
        "widget_version": int(current_version),
        "safe_to_spend": round(float(payload.get("safe_to_spend") or 0.0), 2),
        "month_goal": round(float(month.get("free_spend_goal") or 0.0), 2),
        "daily_limit": round(float(today.get("daily_limit") or today.get("baseline") or 0.0), 2),
        "remaining_today": round(float(today.get("remaining_today") or 0.0), 2),
        "credit_pct": int(credit.get("pct") or 0),
        "credit_used": round(float(credit.get("used") or 0.0), 2),
        "credit_cap": round(float(credit.get("cap") or 0.0), 2),
        "credit_cards": credit_cards,
        "days_left": int(payload.get("days_left") or 0),
        "as_of": str(payload.get("as_of") or ""),
        "tenant_id": int(tid or 0),
        "accounts": account_rows,
        "weekly_safe": weekly_safe,
        "weekly_spend": weekly_spend,
        "weekly_dates": weekly_dates,
    }
