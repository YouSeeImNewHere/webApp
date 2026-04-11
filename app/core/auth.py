from __future__ import annotations

import base64
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, JSONResponse, HTMLResponse

from db import with_db_cursor
from app.core.tenancy import (
    register_google_user,
    get_user_by_email,
    set_current_tenant_id,
    reset_current_tenant_id,
    list_pending_users,
    approve_user,
)
from app.core.widget_tokens import resolve_widget_token
from app.core.config import (
    WIDGET_SECRET,
    SESSION_SECRET,
    SESSION_MAX_AGE_DAYS,
    APP_PASSWORD,
    NOTIF_SECRET,
    IS_RENDER,
    MULTI_TENANT_ENABLED,
    OWNER_GOOGLE_EMAIL,
    WEBAPP_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    GOOGLE_PUBSUB_TOPIC,
)

router = APIRouter()
_PUSH_PROCESS_LOCK = threading.Lock()
_OAUTH_TABLES_LOCK = threading.Lock()
_OAUTH_TABLES_READY = False

# Public endpoints (no login required)
PUBLIC_EXACT = {
    "/__ping",
    "/login",
    "/favicon.ico",
    "/__whoami",
    "/health",
    "/gmail/push",
    "/gmail/oauth/callback",
    "/gmail/watch/renew",
}
PUBLIC_PREFIXES = {"/static/"}


def _is_authed(request: Request) -> bool:
    try:
        return bool(request.session.get("authed"))
    except Exception:
        return False


def _needs_google_identity(request: Request) -> bool:
    if not MULTI_TENANT_ENABLED:
        return False
    return not bool((request.session.get("google_email") or "").strip())


def _is_oauth_bootstrap_path(path: str) -> bool:
    return path in {
        "/gmail/oauth/start",
        "/gmail/oauth/callback",
        "/gmail/oauth/status",
    }


def _is_owner_request(request: Request) -> bool:
    preview_header = str(request.headers.get("x-non-admin-preview") or "").strip().lower()
    if preview_header in {"1", "true", "yes", "on"}:
        return False
    if not MULTI_TENANT_ENABLED:
        return True
    session_email = (request.session.get("google_email") or "").strip().lower()
    owner_email = (OWNER_GOOGLE_EMAIL or "").strip().lower()
    return bool(owner_email) and session_email == owner_email


def _tenant_id_for_email(email: str | None) -> int | None:
    e = _normalize_email(email)
    if not e:
        return None
    try:
        user = get_user_by_email(e) if MULTI_TENANT_ENABLED else None
        tid = (user or {}).get("tenant_id")
        return int(tid) if tid else None
    except Exception:
        return None


@router.get("/health")
def health():
    return {"status": "ok"}


def _require_google_env():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")


def _google_redirect_uri() -> str:
    if GOOGLE_OAUTH_REDIRECT_URI:
        return GOOGLE_OAUTH_REDIRECT_URI
    if WEBAPP_URL:
        return f"{WEBAPP_URL}/gmail/oauth/callback"
    return "http://localhost:8000/gmail/oauth/callback"


def _is_transient_admin_shutdown_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return (
        "terminating connection due to administrator command" in s
        or "connection is closed" in s
        or "server closed the connection unexpectedly" in s
        or "could not receive data from server" in s
        or "ssl connection has been closed unexpectedly" in s
        or "adminshutdown" in s
    )


def _run_db_with_retry(fn):
    for i in range(4):
        try:
            return fn()
        except Exception as e:
            if i < 3 and _is_transient_admin_shutdown_error(e):
                time.sleep(0.35 * (i + 1))
                continue
            raise


def _ensure_oauth_tables():
    global _OAUTH_TABLES_READY
    if _OAUTH_TABLES_READY:
        return
    with _OAUTH_TABLES_LOCK:
        if _OAUTH_TABLES_READY:
            return

        def _create():
            with with_db_cursor() as (conn, cur):
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gmail_oauth_tokens (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        google_email TEXT,
                        access_token TEXT NOT NULL,
                        refresh_token TEXT,
                        token_type TEXT,
                        scope TEXT,
                        expires_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                # Migrate legacy single-row schema (id default 1) to multi-row IDs.
                cur.execute("ALTER TABLE gmail_oauth_tokens ALTER COLUMN id DROP DEFAULT")
                cur.execute("CREATE SEQUENCE IF NOT EXISTS gmail_oauth_tokens_id_seq")
                cur.execute("ALTER TABLE gmail_oauth_tokens ALTER COLUMN id SET DEFAULT nextval('gmail_oauth_tokens_id_seq')")
                cur.execute(
                    """
                    SELECT setval(
                      'gmail_oauth_tokens_id_seq',
                      GREATEST((SELECT COALESCE(MAX(id), 0) FROM gmail_oauth_tokens), 1),
                      true
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_gmail_oauth_tokens_google_email_lower
                    ON gmail_oauth_tokens ((lower(google_email)))
                    WHERE google_email IS NOT NULL
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gmail_push_state (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        last_history_id TEXT,
                        google_email TEXT,
                        last_processed_count INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                # Migrate legacy single-row schema (id default 1) to multi-row IDs.
                cur.execute("ALTER TABLE gmail_push_state ALTER COLUMN id DROP DEFAULT")
                cur.execute("CREATE SEQUENCE IF NOT EXISTS gmail_push_state_id_seq")
                cur.execute("ALTER TABLE gmail_push_state ALTER COLUMN id SET DEFAULT nextval('gmail_push_state_id_seq')")
                cur.execute(
                    """
                    SELECT setval(
                      'gmail_push_state_id_seq',
                      GREATEST((SELECT COALESCE(MAX(id), 0) FROM gmail_push_state), 1),
                      true
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_gmail_push_state_google_email_lower
                    ON gmail_push_state ((lower(google_email)))
                    WHERE google_email IS NOT NULL
                    """
                )
                conn.commit()

        _run_db_with_retry(_create)
        _OAUTH_TABLES_READY = True


def _normalize_email(v: str | None) -> str:
    return str(v or "").strip().lower()


def _get_google_tokens(google_email: str | None = None):
    _ensure_oauth_tables()
    email = _normalize_email(google_email)

    def _query():
        with with_db_cursor() as (_, cur):
            if email:
                cur.execute(
                    """
                    SELECT id, google_email, access_token, refresh_token, token_type, scope, expires_at
                    FROM gmail_oauth_tokens
                    WHERE lower(google_email) = lower(%s)
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (email,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, google_email, access_token, refresh_token, token_type, scope, expires_at
                    FROM gmail_oauth_tokens
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """
                )
            return cur.fetchone()

    return _run_db_with_retry(_query)


def _list_connected_google_emails() -> list[str]:
    _ensure_oauth_tables()

    def _query():
        with with_db_cursor() as (_, cur):
            cur.execute(
                """
                SELECT DISTINCT lower(google_email) AS google_email
                FROM gmail_oauth_tokens
                WHERE google_email IS NOT NULL
                  AND btrim(google_email) <> ''
                ORDER BY lower(google_email) ASC
                """
            )
            return cur.fetchall() or []

    rows = _run_db_with_retry(_query) or []
    out: list[str] = []
    for r in rows:
        e = _normalize_email((r or {}).get("google_email"))
        if e:
            out.append(e)
    return out


def get_connected_google_email(google_email: str | None = None) -> str:
    row = _get_google_tokens(google_email=google_email) or {}
    return str(row.get("google_email") or "").strip().lower()


def _save_google_tokens(
    *,
    access_token: str,
    refresh_token: str | None,
    token_type: str | None,
    scope: str | None,
    expires_at: datetime | None,
    google_email: str | None,
):
    _ensure_oauth_tables()
    email = _normalize_email(google_email)
    if not email:
        raise RuntimeError("google_email_required")

    def _write():
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE gmail_oauth_tokens
                SET
                    access_token = %s,
                    refresh_token = COALESCE(%s, refresh_token),
                    token_type = %s,
                    scope = %s,
                    expires_at = %s,
                    updated_at = now()
                WHERE lower(google_email) = lower(%s)
                """,
                (access_token, refresh_token, token_type, scope, expires_at, email),
            )
            if int(cur.rowcount or 0) <= 0:
                cur.execute(
                    """
                    INSERT INTO gmail_oauth_tokens
                        (google_email, access_token, refresh_token, token_type, scope, expires_at, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, now())
                    """,
                    (email, access_token, refresh_token, token_type, scope, expires_at),
                )
            conn.commit()

    _run_db_with_retry(_write)


def _get_last_history_id(google_email: str | None = None) -> str | None:
    _ensure_oauth_tables()
    email = _normalize_email(google_email)
    if not email:
        return None

    def _query():
        with with_db_cursor() as (_, cur):
            cur.execute(
                """
                SELECT last_history_id
                FROM gmail_push_state
                WHERE lower(google_email) = lower(%s)
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (email,),
            )
            return cur.fetchone()

    row = _run_db_with_retry(_query)
    if not row:
        return None
    return row.get("last_history_id")


def _save_push_state(
    *,
    last_history_id: str | None,
    google_email: str | None,
    processed_count: int = 0,
    last_error: str | None = None,
):
    _ensure_oauth_tables()
    email = _normalize_email(google_email)
    if not email:
        return

    def _write():
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE gmail_push_state
                SET
                    last_history_id = %s,
                    last_processed_count = %s,
                    last_error = %s,
                    updated_at = now()
                WHERE lower(google_email) = lower(%s)
                """,
                (last_history_id, int(processed_count), last_error, email),
            )
            if int(cur.rowcount or 0) <= 0:
                cur.execute(
                    """
                    INSERT INTO gmail_push_state
                        (google_email, last_history_id, last_processed_count, last_error, updated_at)
                    VALUES
                        (%s, %s, %s, %s, now())
                    """,
                    (email, last_history_id, int(processed_count), last_error),
                )
            conn.commit()

    _run_db_with_retry(_write)


def _refresh_google_access_token_if_needed(google_email: str | None = None):
    email = _normalize_email(google_email)
    if not email:
        return None, "google_email_required"
    row = _get_google_tokens(google_email=email)
    if not row:
        return None, "not_connected"

    access_token = row.get("access_token") or ""
    refresh_token = row.get("refresh_token") or ""
    expires_at = row.get("expires_at")
    now_utc = datetime.now(timezone.utc)

    if access_token and expires_at:
        try:
            expires_utc = expires_at.astimezone(timezone.utc)
        except Exception:
            expires_utc = expires_at.replace(tzinfo=timezone.utc)
        if expires_utc > (now_utc + timedelta(seconds=120)):
            return access_token, None

    if not refresh_token:
        return None, "token_expired_no_refresh_token"

    _require_google_env()
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=20,
    )
    if token_resp.status_code != 200:
        return None, f"refresh_failed_http_{token_resp.status_code}"

    td = token_resp.json()
    new_access = td.get("access_token") or ""
    if not new_access:
        return None, "refresh_missing_access_token"

    expires_in = int(td.get("expires_in") or 3600)
    new_expires = now_utc + timedelta(seconds=max(0, expires_in - 60))
    _save_google_tokens(
        access_token=new_access,
        refresh_token=td.get("refresh_token") or refresh_token,
        token_type=td.get("token_type") or row.get("token_type") or "Bearer",
        scope=td.get("scope") or row.get("scope"),
        expires_at=new_expires,
        google_email=row.get("google_email") or email,
    )
    return new_access, None


def _gmail_history_message_ids(access_token: str, start_history_id: str):
    message_ids: set[str] = set()
    page_token = None
    latest_history_id = start_history_id

    while True:
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": 500,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/history",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=20,
        )

        if resp.status_code == 404:
            return None, latest_history_id, "stale_history_id"
        if resp.status_code != 200:
            return None, latest_history_id, f"history_list_failed_http_{resp.status_code}"

        data = resp.json() or {}
        latest_history_id = str(data.get("historyId") or latest_history_id)

        for h in data.get("history") or []:
            for added in h.get("messagesAdded") or []:
                msg = added.get("message") or {}
                mid = msg.get("id")
                if mid:
                    message_ids.add(str(mid))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return sorted(message_ids), latest_history_id, None


def _trigger_event_processing(include_processed: bool = False, google_email: str | None = None):
    if not _PUSH_PROCESS_LOCK.acquire(blocking=False):
        print("gmail push: processing already in progress; skipping duplicate trigger")
        return False

    def _run():
        try:
            from emails import emailFetch

            run_email = _normalize_email(google_email) or None
            tid = _tenant_id_for_email(run_email) if run_email else None
            print(f"gmail push: starting emailFetch.run email={run_email or '-'} tenant_id={tid if tid is not None else '-'}")
            emailFetch.run(
                include_processed=include_processed,
                rules_user_email=run_email,
            )
        except Exception as e:
            print("gmail push: emailFetch.run failed:", repr(e))
        finally:
            _PUSH_PROCESS_LOCK.release()

    threading.Thread(target=_run, daemon=True).start()
    return True


def _is_notif_secret_authorized(request: Request) -> bool:
    provided = (request.headers.get("x-notif-secret", "") or "").strip()
    expected = (NOTIF_SECRET or "").strip()
    return bool(expected) and provided == expected


def _extract_widget_token(request: Request) -> str:
    # Primary header used by the Scriptable widget.
    token = (request.headers.get("x-widget-token") or "").strip()
    if token:
        return token

    # Common API auth convention.
    authz = (request.headers.get("authorization") or "").strip()
    if authz.lower().startswith("bearer "):
        bearer = authz[7:].strip()
        if bearer:
            return bearer

    # Back-compat fallback for older clients.
    legacy = (request.headers.get("x-widget-secret") or "").strip()
    if legacy:
        return legacy

    # Last-resort fallback for clients that cannot set custom headers.
    qp = (request.query_params.get("widget_token") or "").strip()
    if qp:
        return qp
    return ""


def _start_gmail_watch(google_email: str | None = None):
    if not GOOGLE_PUBSUB_TOPIC:
        return JSONResponse(
            {"ok": False, "error": "GOOGLE_PUBSUB_TOPIC not set"},
            status_code=500,
        )

    email = _normalize_email(google_email)
    if not email:
        return JSONResponse({"ok": False, "error": "google_email_required"}, status_code=400)
    access_token, err = _refresh_google_access_token_if_needed(email)
    if not access_token:
        return JSONResponse({"ok": False, "error": err}, status_code=401)

    resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/watch",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "topicName": GOOGLE_PUBSUB_TOPIC,
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "INCLUDE",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        body_txt = resp.text[:500]
        body_l = body_txt.lower()
        if resp.status_code == 403 and (
            "insufficient authentication scopes" in body_l
            or "insufficient permission" in body_l
            or "access_token_scope_insufficient" in body_l
        ):
            return JSONResponse(
                {
                    "ok": False,
                    "error": "gmail_reauth_required_scopes",
                    "status": 403,
                    "hint": "Reconnect Google in Settings to grant required Gmail scopes.",
                    "body": body_txt,
                },
                status_code=403,
            )
        return JSONResponse(
            {
                "ok": False,
                "error": "gmail_watch_failed",
                "status": resp.status_code,
                "body": body_txt,
            },
            status_code=502,
        )

    data = resp.json()
    watch_history_id = str(data.get("historyId") or "")
    if watch_history_id:
        _save_push_state(
            last_history_id=watch_history_id,
            google_email=(_get_google_tokens(google_email=email) or {}).get("google_email") or email,
            processed_count=0,
            last_error=None,
        )
    return {
        "ok": True,
        "historyId": watch_history_id,
        "expiration": data.get("expiration"),
    }


@router.get("/gmail/oauth/start")
def gmail_oauth_start(request: Request, next: str = "/settings"):
    try:
        _require_google_env()
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    state = secrets.token_urlsafe(24)
    request.session["google_oauth_state"] = state
    request.session["google_oauth_next"] = next if next.startswith("/") else "/settings"

    scopes = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ]
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        # Ensure Google returns a refresh token on reconnects.
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/gmail/oauth/callback")
def gmail_oauth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return JSONResponse({"ok": False, "error": f"oauth_error:{error}"}, status_code=400)
    if not code:
        return JSONResponse({"ok": False, "error": "missing_code"}, status_code=400)

    expected_state = request.session.get("google_oauth_state")
    if not expected_state or expected_state != state:
        return JSONResponse({"ok": False, "error": "invalid_oauth_state"}, status_code=400)

    try:
        _require_google_env()
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": _google_redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if token_resp.status_code != 200:
        return JSONResponse(
            {"ok": False, "error": "token_exchange_failed", "status": token_resp.status_code, "body": token_resp.text[:400]},
            status_code=502,
        )

    td = token_resp.json()
    access_token = td.get("access_token") or ""
    if not access_token:
        return JSONResponse({"ok": False, "error": "missing_access_token"}, status_code=502)

    expires_in = int(td.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in - 60))
    google_email = None
    google_sub = None
    try:
        profile_resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if profile_resp.status_code == 200:
            profile = profile_resp.json() or {}
            google_email = profile.get("email")
            google_sub = profile.get("id")
    except Exception:
        google_email = None
        google_sub = None

    _save_google_tokens(
        access_token=access_token,
        refresh_token=td.get("refresh_token"),
        token_type=td.get("token_type") or "Bearer",
        scope=td.get("scope"),
        expires_at=expires_at,
        google_email=google_email,
    )
    user_row = register_google_user(google_sub=google_sub, email=google_email)

    # Auto-start Gmail watch for new/returning approved users so incoming mail
    # triggers fetch processing without a manual Settings click.
    should_auto_watch = (not MULTI_TENANT_ENABLED) or bool((user_row or {}).get("status") == "approved")
    if should_auto_watch:
        try:
            _start_gmail_watch(google_email=google_email)
            _trigger_event_processing(google_email=google_email)
        except Exception as e:
            print("gmail oauth callback: auto watch start failed:", repr(e))

    request.session["google_oauth_state"] = None
    request.session["google_email"] = google_email
    next_url = request.session.get("google_oauth_next") or "/settings"
    return RedirectResponse(url=next_url, status_code=302)


@router.get("/gmail/oauth/status")
def gmail_oauth_status(request: Request):
    session_email = _normalize_email(request.session.get("google_email"))
    row = _get_google_tokens(google_email=session_email)
    if not row:
        return {"ok": True, "connected": False}

    exp = row.get("expires_at")
    expires_iso = exp.astimezone(timezone.utc).isoformat() if exp else None
    return {
        "ok": True,
        "connected": True,
        "email": row.get("google_email"),
        "scope": row.get("scope"),
        "expires_at": expires_iso,
        "has_refresh_token": bool(row.get("refresh_token")),
    }


@router.post("/gmail/oauth/disconnect")
def gmail_oauth_disconnect(request: Request):
    _ensure_oauth_tables()
    session_email = _normalize_email(request.session.get("google_email"))
    if not session_email:
        return {"ok": True, "connected": False}

    def _delete():
        with with_db_cursor() as (conn, cur):
            cur.execute("DELETE FROM gmail_oauth_tokens WHERE lower(google_email) = lower(%s)", (session_email,))
            conn.commit()

    _run_db_with_retry(_delete)
    return {"ok": True, "connected": False}


@router.post("/gmail/watch/start")
def gmail_watch_start(request: Request):
    session_email = _normalize_email(request.session.get("google_email"))
    return _start_gmail_watch(google_email=session_email)


@router.post("/gmail/watch/renew")
def gmail_watch_renew(request: Request):
    if not _is_notif_secret_authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    emails = _list_connected_google_emails()
    if not emails:
        return {"ok": False, "error": "no_connected_gmail_accounts", "results": []}

    results: list[dict[str, object]] = []
    renewed = 0
    failed = 0
    for email in emails:
        res = _start_gmail_watch(google_email=email)
        if isinstance(res, JSONResponse):
            failed += 1
            payload = {}
            try:
                payload = json.loads((res.body or b"{}").decode("utf-8", "ignore")) or {}
            except Exception:
                payload = {}
            results.append(
                {
                    "email": email,
                    "ok": False,
                    "status_code": int(getattr(res, "status_code", 500) or 500),
                    "error": str(payload.get("error") or "watch_renew_failed"),
                    "detail": payload,
                }
            )
            continue

        if isinstance(res, dict) and bool(res.get("ok")):
            renewed += 1
            results.append(
                {
                    "email": email,
                    "ok": True,
                    "historyId": str(res.get("historyId") or ""),
                    "expiration": res.get("expiration"),
                }
            )
        else:
            failed += 1
            results.append(
                {
                    "email": email,
                    "ok": False,
                    "error": "watch_renew_failed_unknown",
                }
            )

    return {
        "ok": failed == 0,
        "renewed": int(renewed),
        "failed": int(failed),
        "results": results,
    }


@router.get("/gmail/push/state")
def gmail_push_state(request: Request):
    _ensure_oauth_tables()
    session_email = _normalize_email(request.session.get("google_email"))
    if not session_email:
        return {"ok": True, "state": {}}

    def _query():
        with with_db_cursor() as (_, cur):
            cur.execute(
                """
                SELECT last_history_id, google_email, last_processed_count, last_error, updated_at
                FROM gmail_push_state
                WHERE lower(google_email) = lower(%s)
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (session_email,),
            )
            return cur.fetchone()

    row = _run_db_with_retry(_query)
    return {"ok": True, "state": row or {}}


@router.post("/gmail/fetch-now")
def gmail_fetch_now(request: Request):
    if not _is_owner_request(request):
        return JSONResponse({"ok": False, "error": "owner_only"}, status_code=403)
    # Manual fetch is for validation/troubleshooting; include ProcessedNew-labeled mail.
    started = _trigger_event_processing(include_processed=True)
    return {"ok": True, "started": bool(started), "status": "started" if started else "already_running"}


# ---------------------------------------------------------
# Gmail Push Webhook (Pub/Sub -> FastAPI)
# ---------------------------------------------------------
@router.post("/gmail/push")
async def gmail_push(request: Request):
    try:
        envelope = await request.json()
    except Exception:
        return {"status": "invalid_json"}

    if "message" not in envelope:
        return {"status": "no_message"}

    msg = envelope["message"]
    data_raw = msg.get("data")
    if not data_raw:
        return {"status": "no_data"}

    data = base64.b64decode(data_raw).decode("utf-8")
    payload = json.loads(data)

    history_id = str(payload.get("historyId") or "")
    email = payload.get("emailAddress")
    tenant_id = _tenant_id_for_email(email)

    print("Gmail push received")
    print("History ID:", history_id)
    print("Email:", email)
    print("Tenant ID:", tenant_id if tenant_id is not None else "-")

    if not history_id:
        return {"status": "missing_history_id"}

    def _safe_save(last_history_id: str, google_email: str | None, processed_count: int, last_error: str | None):
        try:
            _save_push_state(
                last_history_id=last_history_id,
                google_email=google_email,
                processed_count=processed_count,
                last_error=last_error,
            )
        except Exception as e:
            print("gmail push: failed to save push state:", repr(e))

    try:
        access_token, err = _refresh_google_access_token_if_needed(email)
    except Exception as e:
        msg = f"token_refresh_failed:{type(e).__name__}"
        print("gmail push: transient failure during token refresh:", repr(e))
        _safe_save(last_history_id=history_id, google_email=email, processed_count=0, last_error=msg)
        return {"status": "transient_error", "error": msg}

    if not access_token:
        _safe_save(last_history_id=history_id, google_email=email, processed_count=0, last_error=err)
        return {"status": "token_error", "error": err}

    try:
        start_history_id = _get_last_history_id(email)
    except Exception as e:
        msg = f"history_checkpoint_read_failed:{type(e).__name__}"
        print("gmail push: transient failure reading checkpoint:", repr(e))
        _safe_save(last_history_id=history_id, google_email=email, processed_count=0, last_error=msg)
        return {"status": "transient_error", "error": msg}

    if not start_history_id:
        # First push after enabling watch: set checkpoint and wait for next event.
        _safe_save(last_history_id=history_id, google_email=email, processed_count=0, last_error=None)
        return {"status": "initialized", "history_id": history_id}

    message_ids, latest_history_id, hist_err = _gmail_history_message_ids(access_token, start_history_id)
    if hist_err == "stale_history_id":
        # History window rolled over; reset checkpoint and continue from now.
        _safe_save(last_history_id=history_id, google_email=email, processed_count=0, last_error=hist_err)
        return {"status": "reset_checkpoint", "reason": hist_err, "history_id": history_id}
    if hist_err:
        _safe_save(last_history_id=start_history_id, google_email=email, processed_count=0, last_error=hist_err)
        return {"status": "history_error", "error": hist_err}

    message_ids = message_ids or []
    next_history = str(latest_history_id or history_id)
    _safe_save(
        last_history_id=next_history,
        google_email=email,
        processed_count=len(message_ids),
        last_error=None,
    )

    if message_ids:
        print(f"gmail push: {len(message_ids)} new message(s) since history {start_history_id}")
        _trigger_event_processing(google_email=email)

    return {
        "status": "ok",
        "processed_count": len(message_ids),
        "last_history_id": next_history,
    }


class RequireLoginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        tenant_token = set_current_tenant_id(None)
        request.state.tenant_id = None
        try:
            request.state.google_email = _normalize_email(request.session.get("google_email"))
        except Exception:
            request.state.google_email = ""

        try:
            # Widget endpoints: OAuth-bound widget token auth.
            if path.startswith("/widget/"):
                widget_token = _extract_widget_token(request)
                if widget_token:
                    subject = resolve_widget_token(widget_token)
                    if not subject:
                        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
                    resolved_tid = int(subject["tenant_id"])
                    set_current_tenant_id(resolved_tid)
                    request.state.tenant_id = resolved_tid
                    return await call_next(request)

                # Legacy fallback for single-tenant mode only.
                if (not MULTI_TENANT_ENABLED) and WIDGET_SECRET:
                    provided = request.headers.get("x-widget-secret", "")
                    if provided == WIDGET_SECRET:
                        return await call_next(request)
                return JSONResponse({"ok": False, "error": "widget_token_required"}, status_code=401)

            # Always allow these
            if path in PUBLIC_EXACT:
                return await call_next(request)

            # Allow /static/* assets, but block direct access to html pages unless authed
            if any(path.startswith(p) for p in PUBLIC_PREFIXES):
                # Shared chrome partials are fetched and injected into other pages.
                # Redirecting them to /login causes the login page HTML to be injected.
                if path == "/static/shared/shared.html":
                    return await call_next(request)
                if path.lower().endswith(".html") and not _is_authed(request):
                    return RedirectResponse(url=f"/login?next={path}", status_code=302)
                return await call_next(request)

            # Everything else requires auth
            if not _is_authed(request):
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    return RedirectResponse(url=f"/login?next={path}", status_code=302)
                return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

            # After app-password auth, require Google identity for multi-tenant access.
            if _needs_google_identity(request) and path != "/gmail/oauth/start":
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    return RedirectResponse(url=f"/gmail/oauth/start?next={path}", status_code=302)
                return JSONResponse({"ok": False, "error": "google_auth_required"}, status_code=401)

            # Allow OAuth bootstrap endpoints before tenant mapping exists.
            if _is_oauth_bootstrap_path(path):
                return await call_next(request)

            # Multi-tenant gate: every authed user must be approved and mapped to a tenant.
            if MULTI_TENANT_ENABLED:
                session_email = (request.session.get("google_email") or "").strip().lower()
                user = get_user_by_email(session_email)
                if not user:
                    return JSONResponse({"ok": False, "error": "user_not_registered"}, status_code=403)
                if user.get("status") != "approved":
                    return JSONResponse({"ok": False, "error": "user_pending_approval"}, status_code=403)
                tenant_id = user.get("tenant_id")
                if not tenant_id:
                    return JSONResponse({"ok": False, "error": "tenant_not_assigned"}, status_code=403)
                resolved_tid = int(tenant_id)
                set_current_tenant_id(resolved_tid)
                request.state.tenant_id = resolved_tid

            return await call_next(request)
        finally:
            reset_current_tenant_id(tenant_token)



@router.get("/favicon.ico")
async def favicon():
    return FileResponse("static/icons/favicon.ico")


@router.get("/login")
def login_page(next: str = "/"):
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="format-detection" content="telephone=no">
        <title>Login</title>
        <style>
          body {{
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
            max-width: 420px; margin: 60px auto; padding: 0 16px;
          }}
          .card {{
            border: 1px solid #ddd; border-radius: 14px; padding: 18px;
            box-shadow: 0 6px 24px rgba(0,0,0,.06);
          }}
          input {{
            width: 100%; padding: 10px 12px; border-radius: 10px;
            border: 1px solid #ccc; font-size: 16px; margin-top: 8px;
          }}
          button {{
            width: 100%; margin-top: 12px; padding: 10px 12px; border-radius: 10px;
            border: 0; font-size: 16px; cursor: pointer;
          }}
          .hint {{ color: #666; font-size: 13px; margin-top: 10px; }}
        </style>
      </head>

      <body>
        <div class="card">
          <h2 style="margin:0 0 10px 0;">Login</h2>

          <form method="post" action="/login" autocomplete="off">
            <input type="hidden" name="next" value="{next}"/>

            <!-- Fake hidden password field (tricks iOS/Chrome) -->
            <input type="password" style="display:none">

            <label>Access code</label>
            <input
              name="secret_field_1"
              type="password"
              autocomplete="new-password"
              autocorrect="off"
              autocapitalize="none"
              spellcheck="false"
              autofocus
            />

            <button type="submit">Continue</button>
          </form>

          <div class="hint">This site is private.</div>
          <div class="hint" style="margin-top:12px;">After password, Google sign-in starts automatically.</div>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(html)


@router.post("/login")
async def login(request: Request):
    if not APP_PASSWORD:
        # Fail closed if you forgot to set APP_PASSWORD on Render
        return JSONResponse({"ok": False, "error": "APP_PASSWORD not set on server"}, status_code=500)

    ct = (request.headers.get("content-type") or "").lower()
    password = ""
    next_url = "/"

    # Support both form and JSON
    if "application/json" in ct:
        data = await request.json()
        password = str(data.get("password", ""))
        next_url = str(data.get("next", "/") or "/")
    else:
        form = await request.form()
        password = (str(form.get("secret_field_1", "")) or "").strip()
        next_url = str(form.get("next", "/") or "/")

    # Never land on internal shared partials after login.
    if next_url.startswith("/static/shared/"):
        next_url = "/"

    if password != APP_PASSWORD:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse({"ok": False, "error": "bad_password"}, status_code=401)

    request.session["authed"] = True
    request.session["app_password_ok"] = True
    if MULTI_TENANT_ENABLED:
        next_url = next_url if next_url.startswith("/") else "/"
        session_google_email = str(request.session.get("google_email") or "").strip()
        if not session_google_email:
            oauth_start = f"/gmail/oauth/start?next={next_url}"
            return RedirectResponse(url=oauth_start, status_code=302)
        return RedirectResponse(url=next_url, status_code=302)

    # If it was a form submit, always redirect
    if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
        return RedirectResponse(url=next_url or "/", status_code=302)

    # Otherwise JSON (fetch)
    if not next_url.startswith("/"):
        next_url = "/"
    return {"ok": True}


@router.get("/__whoami")
def __whoami(request: Request):
    return {
        "authed": bool(request.session.get("authed")),
        "cookies": dict(request.cookies),
        "session": dict(request.session),
    }


@router.get("/admin/pending-users")
def admin_pending_users(request: Request):
    if not _is_authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    if not _is_owner_request(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    rows = list_pending_users()
    return {"ok": True, "items": rows}


class ApproveUserBody(BaseModel):
    workspace_name: str | None = None


@router.post("/admin/pending-users/{user_id}/approve")
def admin_approve_user(user_id: int, request: Request, body: ApproveUserBody | None = None):
    if not _is_authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    if not _is_owner_request(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    row = approve_user(user_id=int(user_id), workspace_name=(body.workspace_name if body else None))
    if not row:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return {"ok": True, "user": row}


@router.post("/logout")
def logout(request: Request):
    try:
        request.session.clear()
    except Exception:
        pass
    return {"ok": True}


def add_auth_middlewares(app):
    """Register auth/session middleware on the FastAPI app."""
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET env var is required")

    # NOTE: In Starlette/FastAPI, the last added middleware runs first.
    # We add SessionMiddleware last so request.session exists inside RequireLoginMiddleware.
    app.add_middleware(RequireLoginMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=SESSION_SECRET,
        session_cookie="webapp_session",
        same_site="lax",
        max_age=int(max(1, int(SESSION_MAX_AGE_DAYS)) * 24 * 60 * 60),
        https_only=IS_RENDER,
    )
