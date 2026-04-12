from __future__ import annotations

import hashlib
import json
import secrets
import time
from threading import Lock
from typing import Any

from db import with_db_cursor
from app.core.redis_cache import get_redis

_WIDGET_TOKENS_READY = False
_WIDGET_TOKENS_READY_LOCK = Lock()

_TOKEN_CACHE_TTL_SEC = 300
_TOKEN_CACHE: dict[str, dict[str, Any]] = {}
_TOKEN_CACHE_LOCK = Lock()


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _redis_token_key(token_hash: str) -> str:
    return f"widget_token:v1:token:{token_hash}"


def _redis_active_key(tenant_id: int, user_email: str) -> str:
    return f"widget_token:v1:active:{int(tenant_id)}:{(user_email or '').strip().lower()}"


def _redis_store_active_token(token_hash: str, tenant_id: int, user_email: str) -> None:
    r = get_redis()
    if r is None:
        return
    payload = {
        "tenant_id": int(tenant_id),
        "user_email": (user_email or "").strip().lower(),
    }
    try:
        with r.pipeline() as p:
            p.set(_redis_token_key(token_hash), json.dumps(payload, separators=(",", ":")))
            p.set(_redis_active_key(int(tenant_id), payload["user_email"]), token_hash)
            p.execute()
    except Exception:
        return


def _redis_revoke_token(token_hash: str) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        raw = r.get(_redis_token_key(token_hash))
        if not raw:
            return
        payload = json.loads(raw)
        tenant_id = int(payload.get("tenant_id") or 0)
        email = str(payload.get("user_email") or "").strip().lower()
        with r.pipeline() as p:
            p.delete(_redis_token_key(token_hash))
            if tenant_id > 0 and email:
                p.delete(_redis_active_key(tenant_id, email))
            p.execute()
    except Exception:
        return


def _redis_resolve_token(token_hash: str) -> dict[str, Any] | None:
    r = get_redis()
    if r is None:
        return None
    try:
        raw = r.get(_redis_token_key(token_hash))
        if not raw:
            return None
        payload = json.loads(raw)
        tenant_id = int(payload.get("tenant_id") or 0)
        user_email = str(payload.get("user_email") or "").strip().lower()
        if tenant_id <= 0 or not user_email:
            return None
        active_hash = str(r.get(_redis_active_key(tenant_id, user_email)) or "")
        if active_hash != token_hash:
            return None
        return {"tenant_id": tenant_id, "user_email": user_email}
    except Exception:
        return None


def _db_resolve_token(token_hash: str) -> dict[str, Any] | None:
    _ensure_widget_tokens_table()
    if not token_hash:
        return None
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT tenant_id, user_email
            FROM widget_api_tokens
            WHERE token_hash = %s
              AND revoked_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(token_hash),),
        )
        row = dict(cur.fetchone() or {})
        conn.commit()
    tenant_id = int(row.get("tenant_id") or 0)
    user_email = str(row.get("user_email") or "").strip().lower()
    if tenant_id <= 0 or not user_email:
        return None
    return {"tenant_id": tenant_id, "user_email": user_email}


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

    revoked_hashes: list[str] = []
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            UPDATE widget_api_tokens
            SET revoked_at = now()
            WHERE tenant_id = %s
              AND lower(user_email) = lower(%s)
              AND revoked_at IS NULL
            RETURNING token_hash
            """,
            (tenant_id, email),
        )
        revoked_hashes = [str((r or {}).get("token_hash") or "") for r in (cur.fetchall() or [])]
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
    for old_hash in revoked_hashes:
        if old_hash:
            _redis_revoke_token(old_hash)
    _redis_store_active_token(token_hash, tenant_id, email)
    return token


def resolve_widget_token(token: str) -> dict[str, Any] | None:
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

    row = _redis_resolve_token(token_hash)
    if not row:
        # Fallback for environments where Redis is unavailable/stale or when
        # token issuance and widget fetch hit different worker processes.
        row = _db_resolve_token(token_hash)
    if not row:
        return None
    tenant_id = int(row.get("tenant_id") or 0)
    user_email = str(row.get("user_email") or "")
    if tenant_id <= 0:
        return None

    # Best-effort: rehydrate Redis active-token mapping when resolved from DB.
    _redis_store_active_token(token_hash, tenant_id, user_email)

    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[token_hash] = {
            "ts": now_ts,
            "tenant_id": tenant_id,
            "user_email": user_email,
        }
    return {"tenant_id": tenant_id, "user_email": user_email}


def prime_widget_tokens_cache_from_db() -> int:
    """
    One-time warmup at startup so existing tokens resolve from Redis.
    """
    _ensure_widget_tokens_table()
    r = get_redis()
    if r is None:
        return 0
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT token_hash, tenant_id, user_email
            FROM widget_api_tokens
            WHERE revoked_at IS NULL
            """
        )
        rows = cur.fetchall() or []
        conn.commit()
    seeded = 0
    for row in rows:
        token_hash = str((row or {}).get("token_hash") or "")
        tenant_id = int((row or {}).get("tenant_id") or 0)
        user_email = str((row or {}).get("user_email") or "").strip().lower()
        if not token_hash or tenant_id <= 0 or not user_email:
            continue
        _redis_store_active_token(token_hash, tenant_id, user_email)
        seeded += 1
    return int(seeded)
