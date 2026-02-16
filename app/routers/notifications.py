from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.core.config import NOTIF_SECRET, MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id, get_owner_tenant_id
from db import with_db_cursor, query_db

router = APIRouter()

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
    has_valid_secret = bool(NOTIF_SECRET) and (x_notif_secret == NOTIF_SECRET)
    if not (has_valid_secret or has_session_tenant):
        raise HTTPException(status_code=401, detail="Unauthorized")

    with with_db_cursor() as (conn, cur):
        try:
            dedupe_key = payload.dedupe_key
            if MULTI_TENANT_ENABLED and tid:
                dedupe_key = f"t{int(tid)}:{payload.dedupe_key}"
            cur.execute(
                """
                INSERT INTO notifications (tenant_id, kind, dedupe_key, subject, sender, body, is_read, dismissed)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                ((int(tid), payload.kind, dedupe_key, payload.subject, payload.sender, payload.body) if tid else (None, payload.kind, dedupe_key, payload.subject, payload.sender, payload.body)),
            )
            created = (cur.rowcount or 0) > 0
            conn.commit()
            return {"ok": True, "created": bool(created)}
        except Exception as e:
            conn.rollback()
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
