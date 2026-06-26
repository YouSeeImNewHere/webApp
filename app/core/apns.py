from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

from db import with_db_cursor, query_db
from app.core.config import (
    APNS_AUTH_KEY_PATH,
    APNS_AUTH_KEY_P8,
    APNS_KEY_ID,
    APNS_TEAM_ID,
    APNS_TOPIC,
    APNS_USE_SANDBOX,
)


def apns_configured() -> bool:
    return bool(APNS_KEY_ID and APNS_TEAM_ID and APNS_TOPIC and _private_key_bytes())


def ensure_ios_push_devices_table_pg() -> None:
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ios_push_devices (
                id BIGSERIAL PRIMARY KEY,
                tenant_id BIGINT,
                user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                device_name TEXT,
                bundle_id TEXT,
                app_version TEXT,
                environment TEXT NOT NULL DEFAULT 'sandbox',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                revoked_at TIMESTAMPTZ
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ios_push_devices_tenant_id ON ios_push_devices(tenant_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ios_push_devices_user_id ON ios_push_devices(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ios_push_devices_revoked_at ON ios_push_devices(revoked_at)")
        conn.commit()


def register_ios_push_device(
    *,
    tenant_id: int,
    user_id: int,
    token: str,
    device_name: str | None = None,
    bundle_id: str | None = None,
    app_version: str | None = None,
    environment: str | None = None,
) -> None:
    ensure_ios_push_devices_table_pg()
    clean_token = _normalize_device_token(token)
    if not clean_token:
        raise ValueError("invalid_device_token")
    env_value = "production" if str(environment or "").strip().lower() == "production" else "sandbox"
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO ios_push_devices (
                tenant_id, user_id, token, device_name, bundle_id, app_version, environment, revoked_at, last_seen_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, now())
            ON CONFLICT (token)
            DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                user_id = EXCLUDED.user_id,
                device_name = EXCLUDED.device_name,
                bundle_id = EXCLUDED.bundle_id,
                app_version = EXCLUDED.app_version,
                environment = EXCLUDED.environment,
                revoked_at = NULL,
                last_seen_at = now()
            """,
            (
                int(tenant_id),
                int(user_id),
                clean_token,
                _trim(device_name, 120),
                _trim(bundle_id, 160),
                _trim(app_version, 60),
                env_value,
            ),
        )
        conn.commit()


def revoke_ios_push_device(*, token: str, user_id: int | None = None) -> bool:
    ensure_ios_push_devices_table_pg()
    clean_token = _normalize_device_token(token)
    if not clean_token:
        return False
    with with_db_cursor() as (conn, cur):
        if user_id:
            cur.execute(
                """
                UPDATE ios_push_devices
                SET revoked_at = now()
                WHERE token = %s
                  AND user_id = %s
                  AND revoked_at IS NULL
                """,
                (clean_token, int(user_id)),
            )
        else:
            cur.execute(
                """
                UPDATE ios_push_devices
                SET revoked_at = now()
                WHERE token = %s
                  AND revoked_at IS NULL
                """,
                (clean_token,),
            )
        changed = int(cur.rowcount or 0) > 0
        conn.commit()
    return changed


def active_ios_push_device_count_for_user(user_id: int) -> int:
    ensure_ios_push_devices_table_pg()
    rows = query_db(
        """
        SELECT COUNT(*) AS count
        FROM ios_push_devices
        WHERE user_id = %s
          AND revoked_at IS NULL
        """,
        (int(user_id),),
    )
    return int((rows[0] or {}).get("count") or 0) if rows else 0


def send_ios_push_to_tenant(
    *,
    tenant_id: int,
    notification_id: int,
    kind: str,
    subject: str,
    body: str,
) -> dict[str, int]:
    ensure_ios_push_devices_table_pg()
    if not apns_configured():
        return {"attempted": 0, "sent": 0}

    rows = query_db(
        """
        SELECT token, environment
        FROM ios_push_devices
        WHERE tenant_id = %s
          AND revoked_at IS NULL
        ORDER BY id ASC
        """,
        (int(tenant_id),),
    )
    if not rows:
        return {"attempted": 0, "sent": 0}

    provider_token = _build_provider_token()
    payload = {
        "aps": {
            "alert": {
                "title": str(subject or "Notification"),
                "body": str(body or ""),
            },
            "sound": "default",
        },
        "notification_id": int(notification_id),
        "kind": str(kind or ""),
    }
    attempted = 0
    sent = 0
    for row in rows:
        token = str((row or {}).get("token") or "").strip().lower()
        if not token:
            continue
        attempted += 1
        env_value = str((row or {}).get("environment") or "").strip().lower()
        ok, should_revoke = _send_single_apns_push(
            token=token,
            environment=(env_value or ("sandbox" if APNS_USE_SANDBOX else "production")),
            provider_token=provider_token,
            payload=payload,
        )
        if ok:
            sent += 1
        elif should_revoke:
            revoke_ios_push_device(token=token)
    return {"attempted": attempted, "sent": sent}


def _send_single_apns_push(
    *,
    token: str,
    environment: str,
    provider_token: str,
    payload: dict[str, Any],
) -> tuple[bool, bool]:
    host = "api.push.apple.com"
    env_value = str(environment or "").strip().lower()
    if env_value == "sandbox" or (not env_value and APNS_USE_SANDBOX):
        host = "api.sandbox.push.apple.com"
    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--http2",
        "--write-out",
        "\n%{http_code}",
        "--header",
        f"authorization: bearer {provider_token}",
        "--header",
        f"apns-topic: {APNS_TOPIC}",
        "--header",
        "apns-push-type: alert",
        "--header",
        "content-type: application/json",
        "--data",
        json.dumps(payload, separators=(",", ":")),
        f"https://{host}/3/device/{token}",
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=12)
    except Exception as exc:
        import logging; logging.getLogger("apns").error("apns curl exception: %s", exc)
        return False, False

    raw = str(result.stdout or "")
    parts = raw.rsplit("\n", 1)
    response_body = parts[0].strip() if parts else ""
    try:
        status_code = int(parts[1].strip()) if len(parts) > 1 else 0
    except Exception:
        status_code = 0
    import logging; logging.getLogger("apns").warning(
        "apns send: host=%s status=%s body=%r stderr=%r", host, status_code, response_body, result.stderr
    )
    if status_code == 200:
        return True, False
    should_revoke = False
    if status_code in {400, 410}:
        try:
            reason = str((json.loads(response_body) or {}).get("reason") or "")
        except Exception:
            reason = ""
        if reason in {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}:
            should_revoke = True
    return False, should_revoke


def _build_provider_token() -> str:
    header = {"alg": "ES256", "kid": APNS_KEY_ID}
    payload = {"iss": APNS_TEAM_ID, "iat": int(time.time())}
    signing_input = ".".join((_b64json(header), _b64json(payload))).encode("utf-8")
    key = serialization.load_pem_private_key(_private_key_bytes(), password=None)
    signature_der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(signature_der)
    signature_raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input.decode('utf-8')}.{_b64(signature_raw)}"


def _private_key_bytes() -> bytes:
    raw_p8 = str(APNS_AUTH_KEY_P8 or "").strip()
    if raw_p8:
        normalized = raw_p8.replace("\\n", "\n")
        return normalized.encode("utf-8")
    path = str(APNS_AUTH_KEY_PATH or "").strip()
    if not path:
        return b""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except Exception:
        return b""


def _b64json(value: dict[str, Any]) -> str:
    return _b64(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _trim(value: str | None, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _normalize_device_token(raw: str | None) -> str:
    token = "".join(ch for ch in str(raw or "").strip().lower() if ch.isalnum())
    if len(token) < 32:
        return ""
    return token[:512]
