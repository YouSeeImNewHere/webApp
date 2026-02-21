from __future__ import annotations

import os
from threading import Lock
from typing import Any

_REDIS_LOCK = Lock()
_REDIS_CLIENT: Any = None


def get_redis():
    """
    Returns a shared Redis client or None when REDIS_URL is not configured
    (or redis package/client initialization fails).
    """
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
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
            return _REDIS_CLIENT
        except Exception:
            return None
