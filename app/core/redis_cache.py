from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any
from urllib.parse import urlparse

_REDIS_LOCK = Lock()
_REDIS_CLIENT: Any = None
_REDIS_INIT_LOGGED = False
_LOG = logging.getLogger("app.redis")


def _safe_redis_target(url: str) -> str:
    """
    Return a sanitized redis endpoint (no credentials) for logs.
    """
    try:
        parsed = urlparse(str(url or "").strip())
        scheme = str(parsed.scheme or "redis")
        netloc = str(parsed.netloc or "")
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]
        path = str(parsed.path or "")
        return f"{scheme}://{netloc}{path}"
    except Exception:
        return "<invalid_redis_url>"


def get_redis():
    """
    Returns a shared Redis client or None when REDIS_URL is not configured
    (or redis package/client initialization fails).
    """
    global _REDIS_CLIENT
    global _REDIS_INIT_LOGGED
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        if not _REDIS_INIT_LOGGED:
            _LOG.warning("Redis disabled: REDIS_URL is not set")
            _REDIS_INIT_LOGGED = True
        return None

    with _REDIS_LOCK:
        if _REDIS_CLIENT is not None:
            return _REDIS_CLIENT
        try:
            from redis import Redis

            client = Redis.from_url(
                url,
                decode_responses=True,
                socket_timeout=1.5,
                health_check_interval=30,
            )
            client.ping()
            _REDIS_CLIENT = client
            _LOG.info("Redis connected: %s", _safe_redis_target(url))
            _REDIS_INIT_LOGGED = True
            return _REDIS_CLIENT
        except ImportError as e:
            if not _REDIS_INIT_LOGGED:
                _LOG.exception("Redis unavailable: python 'redis' package import failed: %s", e)
                _REDIS_INIT_LOGGED = True
            return None
        except Exception:
            if not _REDIS_INIT_LOGGED:
                _LOG.exception("Redis connection failed for %s", _safe_redis_target(url))
                _REDIS_INIT_LOGGED = True
            return None
