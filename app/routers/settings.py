from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db import with_db_cursor, query_db
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenant_keys import scoped_key
from app.core.roundups import get_roundup_settings, set_roundup_settings
from app.core.home_snapshot_cache import bump_home_snapshot_version
from app.core.tenancy import current_tenant_id, get_user_by_email
from app.core.widget_tokens import issue_widget_token

router = APIRouter()

# =============================================================================
# Settings (Postgres) — ported from settings.py
# =============================================================================

# -----------------------------
# Models (same API)
# -----------------------------
class RateUpsert(BaseModel):
    account_id: int
    rate_percent: float  # user enters 3.54 (percent)
    effective_date: Optional[str] = None  # "YYYY-MM-DD" (optional)
    note: Optional[str] = None

class SaveLayoutBody(BaseModel):
    key: str
    layout: Dict[str, Any]

class SaveLESProfileBody(BaseModel):
    key: str = "default"
    profile: Dict[str, Any]

class SavingsGoalIn(BaseModel):
    mode: str  # "percent" | "amount"
    value: float

class DailyWeightsIn(BaseModel):
    weekday_points: float
    weekend_points: float

class RoundUpSettingsIn(BaseModel):
    enabled: bool


class EmailParserBackfillIn(BaseModel):
    days: int = 1
    include_processed: bool = True
    max_emails: int = 2000

# -----------------------------
# Table ensure helpers (Postgres)
# -----------------------------
def _ensure_app_settings_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_settings_tenant_id ON app_settings(tenant_id)")
        conn.commit()

def _ensure_ui_layout_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_layout (
              key TEXT PRIMARY KEY,
              layout_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute("ALTER TABLE ui_layout ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ui_layout_tenant_id ON ui_layout(tenant_id)")
        conn.commit()

def _ensure_les_profile_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS les_profile (
              key TEXT PRIMARY KEY,
              profile_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute("ALTER TABLE les_profile ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_les_profile_tenant_id ON les_profile(tenant_id)")
        conn.commit()

def _ensure_interest_rates_table_pg():
    # Your DB screenshot shows interest_rates exists, but this makes it robust.
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS interest_rates (
              id SERIAL PRIMARY KEY,
              account_id INT NOT NULL,
              apr DOUBLE PRECISION NOT NULL,
              effective_date DATE NOT NULL,
              note TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute("ALTER TABLE interest_rates ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_interest_rates_tenant_id ON interest_rates(tenant_id)")
        # helpful uniqueness to prevent dupes per account/day
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname='public'
                  AND indexname='ux_interest_rates_account_day'
              ) THEN
                CREATE UNIQUE INDEX ux_interest_rates_account_day
                  ON interest_rates(account_id, effective_date);
              END IF;
            END $$;
            """
        )
        conn.commit()


def _coerce_points(v: object, default: float) -> float:
    try:
        x = float(v)
    except Exception:
        return default
    if x <= 0:
        return default
    if x > 10:
        return 10.0
    return x


@router.get("/settings/daily-weights")
def get_daily_weights():
    _ensure_app_settings_pg()
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (scoped_key("daily_weights"),),
    )
    if not rows:
        return {"weekday_points": 1.0, "weekend_points": 2.0}

    try:
        j = json.loads(rows[0].get("value_json") or "{}")
    except Exception:
        j = {}

    weekday_points = _coerce_points(j.get("weekday_points"), 1.0)
    weekend_points = _coerce_points(j.get("weekend_points"), 2.0)
    return {"weekday_points": weekday_points, "weekend_points": weekend_points}


@router.post("/settings/daily-weights")
def set_daily_weights(body: DailyWeightsIn):
    weekday_points = _coerce_points(body.weekday_points, -1.0)
    weekend_points = _coerce_points(body.weekend_points, -1.0)
    if weekday_points <= 0 or weekend_points <= 0:
        raise HTTPException(status_code=422, detail="points must be > 0")

    payload = json.dumps(
        {
            "weekday_points": float(weekday_points),
            "weekend_points": float(weekend_points),
        }
    )

    _ensure_app_settings_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO app_settings(key, value_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET value_json = EXCLUDED.value_json,
                          updated_at = now()
            """,
            (scoped_key("daily_weights"), payload),
        )
        conn.commit()
    bump_home_snapshot_version(current_tenant_id())
    return {"ok": True, "weekday_points": weekday_points, "weekend_points": weekend_points}


@router.get("/settings/round-ups")
def get_roundups():
    cfg = get_roundup_settings()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "category": str(cfg.get("category") or "Round-ups"),
    }


@router.post("/settings/round-ups")
def set_roundups(body: RoundUpSettingsIn):
    cfg = set_roundup_settings(enabled=bool(body.enabled))
    bump_home_snapshot_version(current_tenant_id())
    return {
        "ok": True,
        "enabled": bool(cfg.get("enabled", False)),
        "category": str(cfg.get("category") or "Round-ups"),
    }


def _require_approved_session_user(request: Request) -> tuple[int, str]:
    session_email = (request.session.get("google_email") or "").strip().lower()
    if not session_email:
        raise HTTPException(status_code=401, detail="google_auth_required")

    user = get_user_by_email(session_email)
    if not user:
        raise HTTPException(status_code=403, detail="user_not_registered")
    if user.get("status") != "approved":
        raise HTTPException(status_code=403, detail="user_pending_approval")

    tenant_id_raw = user.get("tenant_id")
    tenant_id = int(tenant_id_raw) if tenant_id_raw else 0
    if tenant_id <= 0:
        raise HTTPException(status_code=403, detail="tenant_not_assigned")
    return tenant_id, session_email


@router.post("/settings/widget-token")
def create_widget_token(request: Request):
    if not MULTI_TENANT_ENABLED:
        raise HTTPException(status_code=400, detail="widget_token_requires_multi_tenant")
    tenant_id, session_email = _require_approved_session_user(request)

    token = issue_widget_token(tenant_id=tenant_id, user_email=session_email)
    return {"ok": True, "widget_token": token, "tenant_id": tenant_id}


@router.post("/settings/widget-script")
def create_widget_script(request: Request):
    if not MULTI_TENANT_ENABLED:
        raise HTTPException(status_code=400, detail="widget_token_requires_multi_tenant")
    tenant_id, session_email = _require_approved_session_user(request)
    token = issue_widget_token(tenant_id=tenant_id, user_email=session_email)

    script_path = Path("scripts") / "scriptable_finance_widget.js"
    script_template = script_path.read_text(encoding="utf-8")

    base_url = str(request.base_url).rstrip("/")
    script = re.sub(
        r'const\s+BASE_URL\s*=\s*"[^"]*";',
        f'const BASE_URL = "{base_url}";',
        script_template,
        count=1,
    )
    script = re.sub(
        r'const\s+WIDGET_TOKEN\s*=\s*"[^"]*";',
        f'const WIDGET_TOKEN = "{token}";',
        script,
        count=1,
    )
    return {"ok": True, "tenant_id": tenant_id, "script": script}


@router.post("/settings/email-parser/run")
def run_email_parser_backfill(body: EmailParserBackfillIn, request: Request):
    _, session_email = _require_approved_session_user(request)
    days = max(1, min(int(body.days or 1), 60))
    include_processed = bool(body.include_processed)
    max_emails = max(1, min(int(body.max_emails or 2000), 10000))
    try:
        from emails import emailFetch
        result = emailFetch.run_manual_wizard_parse(
            lookback_days=days,
            include_processed=include_processed,
            max_emails=max_emails,
            rules_user_email=session_email,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"email_parser_backfill_failed:{type(e).__name__}:{e}")
