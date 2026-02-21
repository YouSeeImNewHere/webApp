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
from app.core.tenancy import current_tenant_id, get_user_by_email, get_user_pushover_key_by_email
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

class NotificationPrefsIn(BaseModel):
    credit_usage: Optional[bool] = None
    credit_usage_total: Optional[bool] = None
    budget_over: Optional[bool] = None

DEFAULT_NOTIFICATION_PREFS: Dict[str, bool] = {
    "credit_usage": True,
    "credit_usage_total": True,
    "budget_over": True,
}

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


def _ensure_csv_mapping_presets_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS csv_mapping_presets (
              id BIGSERIAL PRIMARY KEY,
              tenant_id BIGINT,
              account_id BIGINT NOT NULL,
              institution_key TEXT NOT NULL,
              preset_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_csv_mapping_presets_scope
            ON csv_mapping_presets (
              COALESCE(tenant_id, 0),
              account_id,
              lower(institution_key)
            )
            """
        )
        conn.commit()


def _ensure_email_parser_trial_drafts_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_parser_trial_drafts (
                id BIGSERIAL PRIMARY KEY,
                tenant_id BIGINT NOT NULL DEFAULT 0,
                user_email TEXT NOT NULL,
                name TEXT NOT NULL,
                account_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'trial_inactive',
                draft_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.commit()


@router.get("/settings/initial-setup-status")
def get_initial_setup_status():
    _ensure_csv_mapping_presets_table_pg()
    _ensure_email_parser_trial_drafts_table_pg()
    tid = current_tenant_id()
    tid0 = int(tid or 0)

    with with_db_cursor() as (conn, cur):
        cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS receives_emails BOOLEAN NOT NULL DEFAULT TRUE")
        if MULTI_TENANT_ENABLED and tid:
            cur.execute(
                """
                SELECT id, institution, name, COALESCE(receives_emails, TRUE) AS receives_emails
                FROM accounts
                WHERE tenant_id = %s
                ORDER BY institution ASC, name ASC, id ASC
                """,
                (int(tid),),
            )
        else:
            cur.execute(
                """
                SELECT id, institution, name, COALESCE(receives_emails, TRUE) AS receives_emails
                FROM accounts
                ORDER BY institution ASC, name ASC, id ASC
                """
            )
        accounts = [dict(r) for r in (cur.fetchall() or [])]
        account_ids = [int(r.get("id") or 0) for r in accounts if int(r.get("id") or 0) > 0]

        csv_ready_ids: set[int] = set()
        parser_ready_ids: set[int] = set()

        if account_ids:
            cur.execute(
                """
                SELECT DISTINCT account_id
                FROM csv_mapping_presets
                WHERE COALESCE(tenant_id, 0) = %s
                  AND lower(institution_key) = lower(%s)
                  AND account_id = ANY(%s)
                """,
                (tid0, "__account__", account_ids),
            )
            csv_ready_ids = {int((r or {}).get("account_id") or 0) for r in (cur.fetchall() or [])}

            cur.execute(
                """
                SELECT DISTINCT account_id
                FROM email_parser_trial_drafts
                WHERE tenant_id = %s
                  AND account_id = ANY(%s)
                """,
                (tid0, account_ids),
            )
            parser_ready_ids = {int((r or {}).get("account_id") or 0) for r in (cur.fetchall() or [])}
        conn.commit()

    total_accounts = len(account_ids)
    email_required_ids = [int(r.get("id") or 0) for r in accounts if bool(r.get("receives_emails", True))]
    csv_ready_count = sum(1 for aid in account_ids if aid in csv_ready_ids)
    parser_ready_count = sum(1 for aid in email_required_ids if aid in parser_ready_ids)

    total_requirements = int(total_accounts + len(email_required_ids))
    completed_requirements = int(csv_ready_count + parser_ready_count)
    percent = int(round((completed_requirements * 100.0) / total_requirements)) if total_requirements > 0 else 0
    if percent < 0:
        percent = 0
    if percent > 100:
        percent = 100

    missing_csv = []
    missing_parser = []
    for a in accounts:
        aid = int(a.get("id") or 0)
        label = f"{str(a.get('institution') or '').strip()} - {str(a.get('name') or '').strip()}".strip(" -")
        if aid and aid not in csv_ready_ids:
            missing_csv.append(label or f"Account {aid}")
        if bool(a.get("receives_emails", True)) and aid and aid not in parser_ready_ids:
            missing_parser.append(label or f"Account {aid}")

    complete = bool(total_requirements > 0 and completed_requirements >= total_requirements)
    return {
        "ok": True,
        "complete": complete,
        "percent": percent,
        "counts": {
            "accounts_total": total_accounts,
            "accounts_with_csv_mapping": csv_ready_count,
            "accounts_expect_email": len(email_required_ids),
            "accounts_with_parser": parser_ready_count,
            "requirements_total": total_requirements,
            "requirements_done": completed_requirements,
        },
        "missing": {
            "csv_mapping": missing_csv,
            "email_parser": missing_parser,
        },
    }


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


def _normalize_notification_prefs(raw: object) -> Dict[str, bool]:
    if not isinstance(raw, dict):
        raw = {}
    out: Dict[str, bool] = dict(DEFAULT_NOTIFICATION_PREFS)
    for key in out.keys():
        if key in raw:
            out[key] = bool(raw.get(key))
    return out


@router.get("/settings/notifications")
def get_notification_settings(request: Request):
    _ensure_app_settings_pg()
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (scoped_key("notification_prefs"),),
    )
    raw: object = {}
    if rows:
        try:
            raw = json.loads(rows[0].get("value_json") or "{}")
        except Exception:
            raw = {}
    prefs = _normalize_notification_prefs(raw)
    session_email = (request.session.get("google_email") or "").strip().lower()
    user_key = get_user_pushover_key_by_email(session_email) if session_email else None
    return {
        "prefs": prefs,
        "pushover_user_key_set": bool(user_key),
        "pushover_user_key": (str(user_key) if user_key else None),
    }


@router.post("/settings/notifications")
def set_notification_settings(body: NotificationPrefsIn):
    _ensure_app_settings_pg()
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (scoped_key("notification_prefs"),),
    )
    raw: object = {}
    if rows:
        try:
            raw = json.loads(rows[0].get("value_json") or "{}")
        except Exception:
            raw = {}
    prefs = _normalize_notification_prefs(raw)

    updates = body.model_dump(exclude_none=True)
    for k in DEFAULT_NOTIFICATION_PREFS.keys():
        if k in updates:
            prefs[k] = bool(updates[k])

    payload = json.dumps(prefs)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO app_settings(key, value_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET value_json = EXCLUDED.value_json,
                          updated_at = now()
            """,
            (scoped_key("notification_prefs"), payload),
        )
        conn.commit()
    return {"ok": True, "prefs": prefs}


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


@router.get("/settings/view-flags")
def get_settings_view_flags(request: Request):
    session_email = (request.session.get("google_email") or "").strip().lower()
    if not session_email:
        return {"ok": True, "is_owner": False}
    user = get_user_by_email(session_email) or {}
    return {"ok": True, "is_owner": bool(user.get("is_owner"))}
