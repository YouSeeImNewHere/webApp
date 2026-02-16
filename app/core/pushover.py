from __future__ import annotations

import os
import requests


def _pushover_creds(user_key: str | None = None) -> tuple[str, str]:
    token = (os.getenv("PUSHOVER_API_TOKEN") or os.getenv("PUSHOVER_TOKEN") or "").strip()
    user = (user_key or "").strip()
    return token, user


def pushover_enabled(user_key: str | None = None) -> bool:
    token, user = _pushover_creds(user_key=user_key)
    return bool(token) and bool(user)


def send_pushover(title: str, message: str, user_key: str | None = None) -> bool:
    token, user = _pushover_creds(user_key=user_key)
    if not token or not user:
        return False
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": token,
                "user": user,
                "title": str(title or "Alert"),
                "message": str(message or ""),
            },
            timeout=8,
        )
        return bool(r.status_code == 200)
    except Exception:
        return False
