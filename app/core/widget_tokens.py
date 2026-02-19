from __future__ import annotations

import hashlib
import secrets
import time
from threading import Lock
from typing import Any

from db import with_db_cursor

_WIDGET_TOKENS_READY = False
_WIDGET_TOKENS_READY_LOCK = Lock()

_TOKEN_CACHE_TTL_SEC = 300
_TOKEN_CACHE: dict[str, dict[str, Any]] = {}
_TOKEN_CACHE_LOCK = Lock()


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _ensure_widget_tokens_table() -> None:
    global _WIDGET_TOKENS_READY
    if _WIDGET_TOKENS_READY:
        return
    with _WIDGET_TOKENS_READY_LOCK:
        if _WIDGET_TOKENS_READY:
            return
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS widget_api_tokens (
                  id BIGSERIAL PRIMARY KEY,
                  tenant_id BIGINT NOT NULL,
                  user_email TEXT NOT NULL,
                  token_hash TEXT NOT NULL UNIQUE,
                  token_prefix TEXT NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  last_used_at TIMESTAMPTZ NULL,
                  revoked_at TIMESTAMPTZ NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_widget_api_tokens_tenant_email_active
                ON widget_api_tokens (tenant_id, user_email, revoked_at)
                """
            )
            conn.commit()
        _WIDGET_TOKENS_READY = True


def issue_widget_token(tenant_id: int, user_email: str) -> str:
    _ensure_widget_tokens_table()
    tenant_id = int(tenant_id)
    email = (user_email or "").strip().lower()
    if tenant_id <= 0:
        raise ValueError("tenant_id_required")
    if not email:
        raise ValueError("user_email_required")

    token = f"wgt_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(token)
    token_prefix = token[:14]

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            UPDATE widget_api_tokens
            SET revoked_at = now()
            WHERE tenant_id = %s
              AND lower(user_email) = lower(%s)
              AND revoked_at IS NULL
            """,
            (tenant_id, email),
        )
        cur.execute(
            """
            INSERT INTO widget_api_tokens (tenant_id, user_email, token_hash, token_prefix)
            VALUES (%s, %s, %s, %s)
            """,
            (tenant_id, email, token_hash, token_prefix),
        )
        conn.commit()

    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[token_hash] = {
            "ts": time.time(),
            "tenant_id": tenant_id,
            "user_email": email,
        }
    return token


def resolve_widget_token(token: str) -> dict[str, Any] | None:
    _ensure_widget_tokens_table()
    token_hash = _hash_token(token)
    if not token_hash:
        return None

    now_ts = time.time()
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(token_hash)
        if cached and (now_ts - float(cached.get("ts") or 0.0)) < _TOKEN_CACHE_TTL_SEC:
            return {
                "tenant_id": int(cached.get("tenant_id") or 0),
                "user_email": str(cached.get("user_email") or ""),
            }

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT tenant_id, user_email
            FROM widget_api_tokens
            WHERE token_hash = %s
              AND revoked_at IS NULL
            LIMIT 1
            """,
            (token_hash,),
        )
        row = cur.fetchone() or {}
        if not row:
            conn.commit()
            return None

        cur.execute(
            """
            UPDATE widget_api_tokens
            SET last_used_at = now()
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        conn.commit()

    tenant_id = int(row.get("tenant_id") or 0)
    user_email = str(row.get("user_email") or "")
    if tenant_id <= 0:
        return None

    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[token_hash] = {
            "ts": now_ts,
            "tenant_id": tenant_id,
            "user_email": user_email,
        }
    return {"tenant_id": tenant_id, "user_email": user_email}
