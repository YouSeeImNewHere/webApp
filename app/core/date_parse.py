from datetime import date, datetime
from typing import Optional
from fastapi import HTTPException
from app.core.config import ISO_DATE_RE

def parse_iso(s: str) -> date:
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Bad ISO date: {s!r}")

def parse_posted_date(raw: Optional[object]) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()

    x = str(raw).strip()
    if not x or x.lower() == "unknown":
        return None

    if ISO_DATE_RE.match(x):
        try:
            return datetime.fromisoformat(x).date()
        except Exception:
            return None

    try:
        if len(x) == 8:
            return datetime.strptime(x, "%m/%d/%y").date()
        if len(x) == 10:
            return datetime.strptime(x, "%m/%d/%Y").date()
    except Exception:
        return None

    return None
