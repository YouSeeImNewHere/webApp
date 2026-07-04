from __future__ import annotations

from datetime import datetime
import hmac
import json
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from app.core.config import NOTIF_SECRET, MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id, get_owner_tenant_id, get_user_by_email
from app.core.pushover import send_pushover
from app.core.apns import (
    apns_configured,
    register_ios_push_device,
    revoke_ios_push_device,
    active_ios_push_device_count_for_user,
    send_ios_push_to_tenant,
)
from db import with_db_cursor, query_db

router = APIRouter()

DEFAULT_NOTIFICATION_PREFS: Dict[str, bool] = {
    "disable_all": False,
    "ios_push": True,
    "credit_usage": True,
    "credit_usage_total": True,
    "budget_over": True,
    "safe_to_spend_daily": True,
    "category_drift": True,
    "runway_warning": True,
    "savings_streak": True,
    "subscription_creep": True,
    "high_spend_cooldown": True,
    "small_win_reinforcement": True,
    "user_signup_pending": True,
    "cron_error": True,
}

# =============================================================================
# Notifications (Postgres) — ported from notifications.py
# Table: notifications   (per your DB screenshot)
# =============================================================================
def _require_tenant_id(for_secret_push: bool = False) -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if tid:
        return int(tid)
    if for_secret_push:
        owner_tid = get_owner_tenant_id()
        if owner_tid:
            return int(owner_tid)
    raise HTTPException(status_code=403, detail="tenant_required")


def _settings_key_for_tenant(raw_key: str, tenant_id: int | None = None) -> str:
    if MULTI_TENANT_ENABLED and tenant_id:
        return f"t{int(tenant_id)}:{raw_key}"
    return raw_key


def _ensure_app_settings_pg() -> None:
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


def _notification_prefs_for_tenant(tenant_id: int | None) -> Dict[str, bool]:
    _ensure_app_settings_pg()
    key = _settings_key_for_tenant("notification_prefs", tenant_id=tenant_id)
    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        (key,),
    )
    if not rows:
        return dict(DEFAULT_NOTIFICATION_PREFS)
    try:
        raw = json.loads(rows[0].get("value_json") or "{}")
    except Exception:
        raw = {}
    out = dict(DEFAULT_NOTIFICATION_PREFS)
    if isinstance(raw, dict):
        for k in out.keys():
            if k in raw:
                out[k] = bool(raw.get(k))
    return out


def _notification_kind_enabled(kind: str, tenant_id: int | None) -> bool:
    prefs = _notification_prefs_for_tenant(tenant_id)
    if bool(prefs.get("disable_all")):
        return False
    if kind not in prefs:
        return False
    return bool(prefs.get(kind))


def _resolve_pushover_key_for_tenant(tenant_id: int | None) -> str | None:
    if not tenant_id:
        return None
    rows = query_db(
        """
        SELECT pushover_user_key
        FROM users
        WHERE tenant_id = %s
          AND NULLIF(TRIM(COALESCE(pushover_user_key, '')), '') IS NOT NULL
        ORDER BY is_owner DESC, id ASC
        LIMIT 1
        """,
        (int(tenant_id),),
    )
    if not rows:
        return None
    key = (rows[0].get("pushover_user_key") or "").strip()
    return key or None


def ensure_notifications_table_pg():
    """
    Safe guard (optional). Keeps schema close to sqlite version but Postgres-native.
    Uses LOWERCASE table name: notifications.
    """
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                tenant_id BIGINT,
                kind TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                subject TEXT,
                sender TEXT,
                body TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                dismissed BOOLEAN NOT NULL DEFAULT FALSE
            );
            """
        )
        cur.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_dismissed ON notifications(dismissed)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_tenant_id ON notifications(tenant_id)")
        conn.commit()

class NotificationPush(BaseModel):
    kind: str = "credit_usage"
    dedupe_key: str
    subject: str
    sender: str = "System"
    body: str = ""


class IOSPushDeviceBody(BaseModel):
    token: str
    device_name: str | None = None
    bundle_id: str | None = None
    app_version: str | None = None
    environment: str | None = None


class IOSPushTestBody(BaseModel):
    title: str | None = None
    body: str | None = None


def create_notification(
    *,
    kind: str,
    dedupe_key: str,
    subject: str,
    sender: str = "System",
    body: str = "",
    tenant_id: int | None = None,
) -> bool:
    """
    Insert a notification with dedupe semantics.
    Returns True if created, False if deduped/no-op.
    """
    ensure_notifications_table_pg()
    if not _notification_kind_enabled(str(kind or "").strip(), tenant_id):
        return False
    dkey = str(dedupe_key or "").strip()
    if not dkey:
        return False
    if MULTI_TENANT_ENABLED and tenant_id:
        dkey = f"t{int(tenant_id)}:{dkey}"

    notification_id: int | None = None
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO notifications (tenant_id, kind, dedupe_key, subject, sender, body, is_read, dismissed)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)
            ON CONFLICT (dedupe_key) DO NOTHING
            RETURNING id
            """,
            ((int(tenant_id), kind, dkey, subject, sender, body) if tenant_id else (None, kind, dkey, subject, sender, body)),
        )
        row = cur.fetchone()
        created = bool(row and row.get("id"))
        notification_id = int(row.get("id")) if row and row.get("id") is not None else None
        conn.commit()
        created_bool = bool(created)
    if created_bool:
        try:
            prefs = _notification_prefs_for_tenant(tenant_id)
            ios_push_active = (
                tenant_id
                and notification_id
                and not bool(prefs.get("disable_all"))
                and bool(prefs.get("ios_push"))
                and apns_configured()
            )
            user_key = _resolve_pushover_key_for_tenant(tenant_id)
            if user_key and not ios_push_active:
                send_pushover(subject or "Notification", body or "", user_key=user_key)
        except Exception:
            pass
        try:
            if ios_push_active:
                send_ios_push_to_tenant(
                    tenant_id=int(tenant_id),
                    notification_id=int(notification_id),
                    kind=str(kind or ""),
                    subject=str(subject or "Notification"),
                    body=str(body or ""),
                )
        except Exception:
            pass
    return created_bool


def _session_email(request: Request) -> str:
    for key in ("google_email", "email", "user_email"):
        val = str(request.session.get(key) or "").strip().lower()
        if val:
            return val
    return ""


def _user_for_session_or_tenant(request: Request, tid: int | None) -> dict | None:
    session_email = _session_email(request)
    if session_email:
        return get_user_by_email(session_email)
    # Bearer-token auth (iOS) — no session cookie; resolve by tenant_id
    if tid and MULTI_TENANT_ENABLED:
        with with_db_cursor() as (_, cur):
            cur.execute(
                "SELECT id, email, status, tenant_id, is_owner FROM users WHERE tenant_id = %s AND is_owner = TRUE LIMIT 1",
                (int(tid),),
            )
            row = cur.fetchone()
        return dict(row) if row else None
    return None


def _notification_prefs_for_session_request(request: Request) -> tuple[dict[str, bool], dict | None, int | None]:
    tid = _require_tenant_id()
    user = _user_for_session_or_tenant(request, tid)
    prefs = _notification_prefs_for_tenant(tid)
    return prefs, user, tid

def _to_local_display_pg(ts: Optional[object]) -> str:
    """
    Input is a TIMESTAMPTZ coming back as a python datetime (usually tz-aware).
    Return the same style string your sqlite version used: 'Wed 01/24/2026 09:41 PM'.
    """
    try:
        if ts is None:
            return ""
        if isinstance(ts, str):
            # fallback: parse ISO-ish
            dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt_utc = ts  # likely datetime
        dt_local = dt_utc.astimezone()
        return dt_local.strftime("%a %m/%d/%Y %I:%M %p")
    except Exception:
        try:
            return str(ts)
        except Exception:
            return ""

@router.post("/notifications/push")
def push_notification(payload: NotificationPush, x_notif_secret: str = Header(default="")):
    ensure_notifications_table_pg()
    tid = _require_tenant_id(for_secret_push=True)

    # Allow either:
    # 1) Server-to-server secret pushes, or
    # 2) Authenticated in-app pushes (session tenant present).
    # Home uses in-app pushes for credit-usage notifications.
    has_session_tenant = bool(current_tenant_id())
    provided_secret = str(x_notif_secret or "")
    expected_secret = str(NOTIF_SECRET or "")
    has_valid_secret = bool(expected_secret) and bool(provided_secret) and hmac.compare_digest(provided_secret, expected_secret)
    if not (has_valid_secret or has_session_tenant):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        created = create_notification(
            kind=payload.kind,
            dedupe_key=payload.dedupe_key,
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            tenant_id=tid,
        )
        return {"ok": True, "created": bool(created)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/notifications")
def list_notifications(limit: int = 200):
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    rows = query_db(
        f"""
        SELECT id, kind, subject, sender, created_at, is_read
        FROM notifications
        WHERE dismissed = FALSE
        {"AND tenant_id = %s" if tid else ""}
        ORDER BY is_read ASC, id DESC
        LIMIT %s
        """,
        ((int(tid), int(limit)) if tid else (int(limit),)),
    )

    items = []
    for r in rows:
        items.append(
            {
                "id": int(r["id"]),
                "kind": r.get("kind"),
                "subject": r.get("subject"),
                "sender": r.get("sender"),
                "created_at": (r["created_at"].isoformat() if r.get("created_at") else None),
                "created_at_local": _to_local_display_pg(r.get("created_at")),
                "is_read": bool(r.get("is_read")),
            }
        )

    return {"items": items}


@router.post("/notifications/ios/devices")
def upsert_ios_push_device(body: IOSPushDeviceBody, request: Request):
    tid = _require_tenant_id()
    user = _user_for_session_or_tenant(request, tid)
    if not tid or not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        register_ios_push_device(
            tenant_id=int(tid),
            user_id=int(user.get("id") or 0),
            token=body.token,
            device_name=body.device_name,
            bundle_id=body.bundle_id,
            app_version=body.app_version,
            environment=body.environment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    count = active_ios_push_device_count_for_user(int(user.get("id") or 0))
    return {"ok": True, "device_count": int(count), "apns_configured": bool(apns_configured())}


@router.delete("/notifications/ios/devices")
def delete_ios_push_device(body: IOSPushDeviceBody, request: Request):
    tid = _require_tenant_id()
    user = _user_for_session_or_tenant(request, tid)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    changed = revoke_ios_push_device(token=body.token, user_id=int(user.get("id") or 0))
    count = active_ios_push_device_count_for_user(int(user.get("id") or 0))
    return {"ok": True, "revoked": bool(changed), "device_count": int(count)}


@router.post("/notifications/ios/test")
def send_ios_push_test(body: IOSPushTestBody, request: Request):
    prefs, user, tid = _notification_prefs_for_session_request(request)
    if not user or not tid:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not apns_configured():
        raise HTTPException(status_code=503, detail="ios_push_not_configured")
    if bool(prefs.get("disable_all")) or not bool(prefs.get("ios_push")):
        raise HTTPException(status_code=409, detail="ios_push_disabled")
    device_count = active_ios_push_device_count_for_user(int(user.get("id") or 0))
    if device_count <= 0:
        raise HTTPException(status_code=409, detail="ios_push_device_not_registered")

    title = str((body.title or "").strip() or "Quail Test Notification")
    message = str((body.body or "").strip() or "This is a test push from Quail.")
    result = send_ios_push_to_tenant(
        tenant_id=int(tid),
        notification_id=0,
        kind="ios_push_test",
        subject=title,
        body=message,
    )
    if int(result.get("sent") or 0) <= 0:
        raise HTTPException(status_code=502, detail="ios_push_send_failed")
    return {
        "ok": True,
        "sent": int(result.get("sent") or 0),
        "attempted": int(result.get("attempted") or 0),
    }


@router.post("/notifications/ios/test-both-envs")
def send_ios_push_test_both_envs(request: Request):
    """Debug endpoint: tries the stored token against both sandbox and production APNs."""
    from app.core.apns import _build_provider_token, _send_single_apns_push, ensure_ios_push_devices_table_pg
    tid = _require_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    ensure_ios_push_devices_table_pg()
    rows = query_db(
        "SELECT token, environment FROM ios_push_devices WHERE tenant_id = %s AND revoked_at IS NULL ORDER BY id DESC LIMIT 1",
        (int(tid),),
    )
    if not rows:
        raise HTTPException(status_code=409, detail="no_device_registered")
    token = str((rows[0] or {}).get("token") or "").strip()
    db_env = str((rows[0] or {}).get("environment") or "").strip()
    provider_token = _build_provider_token()
    payload = {"aps": {"alert": {"title": "Quail env probe", "body": "env test"}, "sound": "default"}, "kind": "env_probe"}
    prod_ok, _ = _send_single_apns_push(token=token, environment="production", provider_token=provider_token, payload=payload)
    sand_ok, _ = _send_single_apns_push(token=token, environment="sandbox", provider_token=provider_token, payload=payload)
    return {"token_prefix": token[:8], "token_len": len(token), "db_env": db_env, "production_ok": prod_ok, "sandbox_ok": sand_ok}

@router.get("/notifications/unread-count")
def unread_count():
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    rows = query_db(
        f"""
        SELECT COUNT(*)::int AS n
        FROM notifications
        WHERE dismissed = FALSE AND is_read = FALSE
        {"AND tenant_id = %s" if tid else ""}
        """,
        ((int(tid),) if tid else ()),
    )
    return {"unread": int(rows[0]["n"]) if rows else 0}

@router.get("/notifications/{notif_id}")
def get_notification(notif_id: int):
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    rows = query_db(
        f"""
        SELECT id, kind, subject, sender, body, created_at, is_read, dismissed
        FROM notifications
        WHERE id = %s
        {"AND tenant_id = %s" if tid else ""}
        LIMIT 1
        """,
        ((int(notif_id), int(tid)) if tid else (int(notif_id),)),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Notification not found")

    r = rows[0]
    return {
        "id": int(r["id"]),
        "kind": r.get("kind"),
        "subject": r.get("subject"),
        "sender": r.get("sender"),
        "body": r.get("body") or "",
        "created_at": (r["created_at"].isoformat() if r.get("created_at") else None),
        "created_at_local": _to_local_display_pg(r.get("created_at")),
        "is_read": bool(r.get("is_read")),
        "dismissed": bool(r.get("dismissed")),
    }

@router.post("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int):
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    with with_db_cursor() as (conn, cur):
        if tid:
            cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND tenant_id = %s", (int(notif_id), int(tid)))
        else:
            cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (int(notif_id),))
        conn.commit()
    return {"ok": True}

@router.post("/notifications/{notif_id}/dismiss")
def dismiss_notification(notif_id: int):
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    with with_db_cursor() as (conn, cur):
        if tid:
            cur.execute("UPDATE notifications SET dismissed = TRUE WHERE id = %s AND tenant_id = %s", (int(notif_id), int(tid)))
        else:
            cur.execute("UPDATE notifications SET dismissed = TRUE WHERE id = %s", (int(notif_id),))
        conn.commit()
    return {"ok": True}

@router.post("/notifications/mark-all-read")
def mark_all_notifications_read():
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    with with_db_cursor() as (conn, cur):
        if tid:
            cur.execute("UPDATE notifications SET is_read = TRUE WHERE dismissed = FALSE AND tenant_id = %s", (int(tid),))
        else:
            cur.execute("UPDATE notifications SET is_read = TRUE WHERE dismissed = FALSE")
        conn.commit()
    return {"ok": True}

@router.post("/notifications/clear-read")
def clear_read_notifications():
    ensure_notifications_table_pg()
    tid = _require_tenant_id()

    with with_db_cursor() as (conn, cur):
        # Dismiss anything already read
        if tid:
            cur.execute(
                "UPDATE notifications SET dismissed = TRUE WHERE dismissed = FALSE AND is_read = TRUE AND tenant_id = %s",
                (int(tid),),
            )
        else:
            cur.execute("UPDATE notifications SET dismissed = TRUE WHERE dismissed = FALSE AND is_read = TRUE")
        conn.commit()
    return {"ok": True}
