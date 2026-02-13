from __future__ import annotations

from zoneinfo import ZoneInfo
from datetime import datetime, date

APP_TZ = ZoneInfo("America/Los_Angeles")

def today_local() -> date:
    return datetime.now(APP_TZ).date()

def now_local() -> datetime:
    return datetime.now(APP_TZ)
