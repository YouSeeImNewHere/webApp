from __future__ import annotations

import os
from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import WIDGET_SECRET, SESSION_SECRET, APP_PASSWORD, IS_RENDER
from app.core.time import today_local, now_local

router = APIRouter()

# Public endpoints
PUBLIC_EXACT = {"/__ping", "/login", "/favicon.ico", "/__whoami", "/health"}
PUBLIC_PREFIXES = {"/static/"}

def _is_authed(request: Request) -> bool:
    try:
        return bool(request.session.get("authed"))
    except Exception:
        return False

@router.get("/health")
def health():
    return {"status": "ok"}

class RequireLoginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Widget endpoints: allow header-based auth (Shortcut/Scriptable)
        if path.startswith("/widget/"):
            provided = request.headers.get("x-widget-secret", "")
            if WIDGET_SECRET and provided == WIDGET_SECRET:
                return await call_next(request)
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

        # Always allow these
        if path in PUBLIC_EXACT:
            return await call_next(request)

        # Allow /static/* assets, but block direct access to html pages unless authed
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            if path.lower().endswith(".html") and not _is_authed(request):
                return RedirectResponse(url=f"/login?next={path}", status_code=302)
            return await call_next(request)

        # Everything else requires auth
        if _is_authed(request):
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url=f"/login?next={path}", status_code=302)

        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

@router.get("/favicon.ico")
async def favicon():
    return FileResponse("static/icons/favicon.ico")

# =============================================================================
# Auth (cookie session) — simple password gate for Render deployment
# =============================================================================




# Signed cookie session

def _is_authed(request: Request) -> bool:
    try:
        return bool(request.session.get("authed"))
    except Exception:
        return False

PUBLIC_EXACT = {"/__ping", "/login", "/favicon.ico", "/__whoami", "/health"}

PUBLIC_PREFIXES = {"/static/"}

@router.get("/health")
def health():
    return {"status": "ok"}

class RequireLoginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/widget/"):
            provided = request.headers.get("x-widget-secret", "")
            if WIDGET_SECRET and provided == WIDGET_SECRET:
                return await call_next(request)
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

            # always allow these
        if path in PUBLIC_EXACT:
            return await call_next(request)
        # always allow these
        if path in PUBLIC_EXACT:
            return await call_next(request)

        # allow /static/* assets, but block direct access to html pages
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            if path.lower().endswith(".html") and not _is_authed(request):
                return RedirectResponse(url=f"/login?next={path}", status_code=302)
            return await call_next(request)

        # DEBUG (optional) - DO NOT touch request.session unless SessionMiddleware ran
        scope_has_session = ("session" in request.scope)
        scope_session = dict(request.scope.get("session") or {}) if scope_has_session else {}

        # everything else requires auth
        if _is_authed(request):
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url=f"/login?next={path}", status_code=302)

        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

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

        <!-- Helps disable iOS smart autofill heuristics -->
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

          <!-- 🚫 Disable browser password saving -->
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

    # Support both form and JSON
    ct = (request.headers.get("content-type") or "").lower()
    password = ""
    next_url = "/"

    if "application/json" in ct:
        data = await request.json()
        password = str(data.get("password", ""))
        next_url = str(data.get("next", "/") or "/")
    else:
        form = await request.form()
        password = (str(form.get("secret_field_1", "")) or "").strip()
        next_url = str(form.get("next", "/") or "/")

    if password != APP_PASSWORD:
        # For HTML posts, redirect back to login (could add an error message if you want).
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse({"ok": False, "error": "bad_password"}, status_code=401)

    request.session["authed"] = True

    # If it was a form submit, always redirect (browser posts often have Accept: */*)
    if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
        return RedirectResponse(url=next_url or "/", status_code=302)

    if not next_url.startswith("/"):
        next_url = "/"

    # Otherwise JSON (fetch)
    return {"ok": True}

@router.get("/__whoami")
def __whoami(request: Request):
    return {
        "authed": bool(request.session.get("authed")),
        "cookies": dict(request.cookies),
        "session": dict(request.session),
    }

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
        # In production you MUST set this in Render env vars (random long string).
        raise RuntimeError("SESSION_SECRET env var is required")

    app.add_middleware(RequireLoginMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=SESSION_SECRET,
        session_cookie="webapp_session",
        same_site="lax",
        max_age=None,
        https_only=IS_RENDER,
    )
