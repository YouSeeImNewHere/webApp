from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.core.tenancy import current_tenant_id, set_current_tenant_id, reset_current_tenant_id
from app.core.redis_cache import get_redis
from app.core.time import today_local
from app.routers.analytics import spending_unbudgeted_safe_range
from app.routers.page_payloads import (
    _build_widget_payload_for_tenant_version,
    _widget_redis_get_payload,
    _widget_redis_get_version,
    _widget_version_for_tenant_cached,
    refresh_widget_cache_for_tenant,
)

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
    credit_accounts = (credit.get("accounts") or [])
    credit_cards = []
    for a in credit_accounts:
        if not isinstance(a, dict):
            continue
        credit_cards.append(
            {
                "name": str(a.get("name") or "Card"),
                "used": round(float(a.get("used") or 0.0), 2),
                "cap": round(float(a.get("cap") or 0.0), 2),
                "pct": int(a.get("pct") or 0),
            }
        )
    # Weekly trend payload for watch chart (7d), computed only when returning changed payload.
    weekly_safe = []
    weekly_spend = []
    weekly_dates = []
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
        "daily_limit": round(float(today.get("daily_limit") or today.get("baseline") or 0.0), 2),
        "remaining_today": round(float(today.get("remaining_today") or 0.0), 2),
        "credit_pct": int(credit.get("pct") or 0),
        "credit_used": round(float(credit.get("used") or 0.0), 2),
        "credit_cap": round(float(credit.get("cap") or 0.0), 2),
        "credit_cards": credit_cards,
        "days_left": int(payload.get("days_left") or 0),
        "as_of": str(payload.get("as_of") or ""),
        "tenant_id": int(tid or 0),
        "weekly_safe": weekly_safe,
        "weekly_spend": weekly_spend,
        "weekly_dates": weekly_dates,
    }
