from __future__ import annotations

import time
from typing import Any

import requests as _requests

from db import with_db_cursor, query_db
from app.core.config import FCM_PROJECT_ID, FCM_SERVICE_ACCOUNT_PATH

_access_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def fcm_configured() -> bool:
    return bool(FCM_PROJECT_ID and FCM_SERVICE_ACCOUNT_PATH)


def ensure_android_push_devices_table_pg() -> None:
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS android_push_devices (
                id BIGSERIAL PRIMARY KEY,
                tenant_id BIGINT,
                user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                device_name TEXT,
                app_version TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                revoked_at TIMESTAMPTZ
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_android_push_devices_tenant_id ON android_push_devices(tenant_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_android_push_devices_user_id ON android_push_devices(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_android_push_devices_revoked_at ON android_push_devices(revoked_at)")
        conn.commit()


def register_android_push_device(
    *,
    tenant_id: int,
    user_id: int,
    token: str,
    device_name: str | None = None,
    app_version: str | None = None,
) -> None:
    ensure_android_push_devices_table_pg()
    clean_token = str(token or "").strip()
    if not clean_token:
        raise ValueError("invalid_device_token")
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO android_push_devices (
                tenant_id, user_id, token, device_name, app_version, revoked_at, last_seen_at
            )
            VALUES (%s, %s, %s, %s, %s, NULL, now())
            ON CONFLICT (token)
            DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                user_id = EXCLUDED.user_id,
                device_name = EXCLUDED.device_name,
                app_version = EXCLUDED.app_version,
                revoked_at = NULL,
                last_seen_at = now()
            """,
            (
                int(tenant_id),
                int(user_id),
                clean_token[:4096],
                (device_name or None),
                (app_version or None),
            ),
        )
        conn.commit()


def revoke_android_push_device(*, token: str, user_id: int | None = None) -> bool:
    ensure_android_push_devices_table_pg()
    clean_token = str(token or "").strip()
    if not clean_token:
        return False
    with with_db_cursor() as (conn, cur):
        if user_id:
            cur.execute(
                """
                UPDATE android_push_devices
                SET revoked_at = now()
                WHERE token = %s AND user_id = %s AND revoked_at IS NULL
                """,
                (clean_token, int(user_id)),
            )
        else:
            cur.execute(
                """
                UPDATE android_push_devices
                SET revoked_at = now()
                WHERE token = %s AND revoked_at IS NULL
                """,
                (clean_token,),
            )
        changed = int(cur.rowcount or 0) > 0
        conn.commit()
    return changed


def active_android_push_device_count_for_user(user_id: int) -> int:
    ensure_android_push_devices_table_pg()
    rows = query_db(
        """
        SELECT COUNT(*) AS count
        FROM android_push_devices
        WHERE user_id = %s AND revoked_at IS NULL
        """,
        (int(user_id),),
    )
    return int((rows[0] or {}).get("count") or 0) if rows else 0


def _get_access_token() -> str | None:
    now = time.time()
    if _access_token_cache["token"] and now < float(_access_token_cache["expires_at"]) - 60:
        return _access_token_cache["token"]
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleAuthRequest

        creds = service_account.Credentials.from_service_account_file(
            FCM_SERVICE_ACCOUNT_PATH,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
        creds.refresh(GoogleAuthRequest())
        _access_token_cache["token"] = creds.token
        _access_token_cache["expires_at"] = creds.expiry.timestamp() if creds.expiry else now + 3000
        return creds.token
    except Exception:
        return None


def send_android_push_to_tenant(
    *,
    tenant_id: int,
    notification_id: int,
    kind: str,
    subject: str,
    body: str,
) -> dict[str, int]:
    ensure_android_push_devices_table_pg()
    if not fcm_configured():
        return {"attempted": 0, "sent": 0}

    rows = query_db(
        """
        SELECT token
        FROM android_push_devices
        WHERE tenant_id = %s AND revoked_at IS NULL
        ORDER BY id ASC
        """,
        (int(tenant_id),),
    )
    if not rows:
        return {"attempted": 0, "sent": 0}

    access_token = _get_access_token()
    if not access_token:
        return {"attempted": 0, "sent": 0}

    url = f"https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    attempted = 0
    sent = 0
    for row in rows:
        token = str((row or {}).get("token") or "").strip()
        if not token:
            continue
        attempted += 1
        message = {
            "message": {
                "token": token,
                "notification": {
                    "title": str(subject or "Notification"),
                    "body": str(body or ""),
                },
                "data": {
                    "notification_id": str(int(notification_id)),
                    "kind": str(kind or ""),
                },
                "android": {"priority": "high"},
            }
        }
        try:
            resp = _requests.post(url, headers=headers, json=message, timeout=15)
            if resp.status_code == 200:
                sent += 1
            elif resp.status_code in (400, 404) and "UNREGISTERED" in resp.text:
                revoke_android_push_device(token=token)
        except Exception:
            pass
    return {"attempted": attempted, "sent": sent}
