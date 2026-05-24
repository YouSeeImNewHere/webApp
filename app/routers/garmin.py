from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.core.tenancy import current_tenant_id, set_current_tenant_id, reset_current_tenant_id
from app.core.time import today_local
from app.routers.analytics import spending_unbudgeted_safe_range
from app.routers.page_payloads import _build_widget_payload_for_tenant_version

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
def garmin_info(tenant_id: Optional[int] = Query(default=None)):
    tid = _resolve_tenant_id(tenant_id)
    payload = _build_widget_payload_for_tenant_version(tid, 0)
    today = (payload.get("today") or {})
    credit = (payload.get("credit") or {})
    weekly_safe: list[float] = []
    weekly_spend: list[float] = []

    token = set_current_tenant_id(int(tid) if tid else None)
    try:
        end_d = today_local()
        start_d = end_d - timedelta(days=6)
        trend = spending_unbudgeted_safe_range(start=start_d.isoformat(), end=end_d.isoformat()) or {}
        series = trend.get("series") or []
        for p in series:
            weekly_safe.append(round(float((p or {}).get("daily_safe_to_spend") or 0.0), 2))
            weekly_spend.append(round(float((p or {}).get("unbudgeted_spend") or 0.0), 2))
    except Exception:
        weekly_safe = []
        weekly_spend = []
    finally:
        reset_current_tenant_id(token)

    return {
        "status": "OK",
        "safe_to_spend": round(float(payload.get("safe_to_spend") or 0.0), 2),
        "daily_limit": round(float(today.get("daily_limit") or today.get("baseline") or 0.0), 2),
        "remaining_today": round(float(today.get("remaining_today") or 0.0), 2),
        "credit_pct": int(credit.get("pct") or 0),
        "credit_used": round(float(credit.get("used") or 0.0), 2),
        "credit_cap": round(float(credit.get("cap") or 0.0), 2),
        "days_left": int(payload.get("days_left") or 0),
        "as_of": str(payload.get("as_of") or ""),
        "tenant_id": int(tid or 0),
        "weekly_safe": weekly_safe,
        "weekly_spend": weekly_spend,
    }
