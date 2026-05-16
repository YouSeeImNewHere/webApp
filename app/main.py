from __future__ import annotations
import logging
import os
import time
from urllib.parse import parse_qsl, urlencode
from app.core import auth
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.middleware.gzip import GZipMiddleware
from app.routers.csv_upload import router as csv_upload_router

from db import open_pool, close_pool, ensure_performance_indexes

from app.core.templates import templates  # ensure templates init
from app.core.auth import add_auth_middlewares
from app.core.config import BUILD_ID
from app.core.tenancy import initialize_tenancy, current_tenant_id
from app.core.account_totals_cache import ensure_account_totals_cache_pg
from app.core.home_snapshot_cache import ensure_home_snapshot_cache_pg
from app.core.widget_tokens import prime_widget_tokens_cache_from_db
from app.core.redis_cache import get_redis
from app.core.admin_error_events import (
    ensure_admin_error_events_table_pg,
    log_admin_error_event,
)
from app.core.email_parse_events import ensure_email_parse_events_table_pg

# Routers
from app.routers import (
    pages,
    notifications,
    transactions_feeds,
    balances,
    accounts,
    analytics,
    categories,
    category_rules,
    les,
    les_profile,
    recurring,
    settings,
    savings_goal,
    budget_groups,
    funds,
    ui_layout,
    interest_rates,
    transactions,
    page_payloads,
    admin,
    onboarding,
    email_parser_trial,
    reports,
)


def _env_enabled(name: str, default: str = "1") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


_SENSITIVE_QUERY_KEYS = {
    "token",
    "widget_token",
    "access_token",
    "refresh_token",
    "code",
    "state",
}


def _scrub_query_string(raw_query: str) -> str:
    q = str(raw_query or "").strip()
    if not q:
        return ""
    try:
        pairs = parse_qsl(q, keep_blank_values=True)
    except Exception:
        return ""
    scrubbed: list[tuple[str, str]] = []
    for k, v in pairs:
        key = str(k or "")
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            scrubbed.append((key, "***"))
        else:
            scrubbed.append((key, str(v or "")))
    return urlencode(scrubbed)


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=700)
    logger = logging.getLogger("app.perf")
    # Emit tenant-aware request lines through Uvicorn's error logger
    # (access logger has a strict 5-arg formatter contract).
    request_logger = logging.getLogger("uvicorn.error")
    request_logger.setLevel(logging.INFO)
    slow_request_ms = int(os.getenv("SLOW_REQUEST_MS", "450"))
    log_all_timings = os.getenv("LOG_ALL_REQUEST_TIMINGS", "0").strip() == "1"

    def _capture_admin_error(
        request: Request,
        *,
        status_code: int,
        error_message: str,
    ) -> None:
        path = request.url.path or ""
        if path.startswith("/static/"):
            return
        if path.startswith("/admin/error-notifications"):
            return
        low_path = path.strip().lower()
        if low_path in {
            "/.well-known/appspecific/com.chrome.devtools.json",
        }:
            return
        if bool(getattr(request.state, "_admin_error_captured", False)):
            return
        try:
            tid = getattr(request.state, "tenant_id", None)
            if tid is None:
                tid = current_tenant_id()
            session_email = ""
            try:
                session_email = str(request.session.get("google_email") or "").strip().lower()
            except Exception:
                session_email = ""
            if not session_email:
                session_email = str(getattr(request.state, "google_email", "") or "").strip().lower()
            client_ip = str((request.client.host if request.client else "") or "")
            log_admin_error_event(
                tenant_id=(int(tid) if tid else None),
                user_email=(session_email or None),
                method=str(request.method or ""),
                path=path,
                query_string=_scrub_query_string(request.url.query or ""),
                page_url=(request.headers.get("x-client-page-url") or ""),
                referer=(request.headers.get("referer") or ""),
                request_id=(request.headers.get("x-request-id") or ""),
                status_code=int(status_code or 500),
                error_message=str(error_message or f"HTTP {int(status_code or 500)}"),
                client_ip=client_ip,
                user_agent=(request.headers.get("user-agent") or ""),
            )
            request.state._admin_error_captured = True
        except Exception:
            pass

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        status_code = int(getattr(exc, "status_code", 500) or 500)
        if status_code >= 400:
            _capture_admin_error(
                request,
                status_code=status_code,
                error_message=str(getattr(exc, "detail", "") or f"HTTP {status_code}"),
            )
        return JSONResponse(status_code=status_code, content={"detail": exc.detail})

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
        status_code = int(getattr(exc, "status_code", 500) or 500)
        if status_code >= 400:
            _capture_admin_error(
                request,
                status_code=status_code,
                error_message=str(getattr(exc, "detail", "") or f"HTTP {status_code}"),
            )
        return JSONResponse(status_code=status_code, content={"detail": exc.detail})

    @app.middleware("http")
    async def static_cache_control(request: Request, call_next):
        t0 = time.perf_counter()
        path = request.url.path or ""
        try:
            response = await call_next(request)
        except Exception as exc:
            _capture_admin_error(
                request,
                status_code=500,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            raise
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if (request.url.scheme or "").lower() == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" in content_type:
            response.headers.setdefault(
                "Content-Security-Policy",
                "; ".join(
                    [
                        "default-src 'self'",
                        "base-uri 'self'",
                        "frame-ancestors 'none'",
                        "object-src 'none'",
                        "form-action 'self'",
                        "img-src 'self' data: blob:",
                        "style-src 'self' 'unsafe-inline'",
                        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                        "connect-src 'self' https://cdn.jsdelivr.net https://www.googleapis.com https://oauth2.googleapis.com https://gmail.googleapis.com",
                    ]
                ),
            )

        if not path.startswith("/static/"):
            tid = getattr(request.state, "tenant_id", None)
            if tid is None:
                try:
                    tid = current_tenant_id()
                except Exception:
                    tid = None
            session_email = ""
            try:
                session_email = str(request.session.get("google_email") or "").strip().lower()
            except Exception:
                session_email = ""
            if not session_email:
                session_email = str(getattr(request.state, "google_email", "") or "").strip().lower()
            client_ip = ""
            try:
                client_ip = str((request.client.host if request.client else "") or "")
            except Exception:
                client_ip = ""
            request_logger.info(
                f"request method={request.method} path={path} status={response.status_code} "
                f"tenant_id={(tid if tid is not None else '-')} "
                f"email={(session_email or '-')} ip={(client_ip or '-')} ms={elapsed_ms}"
            )
            if log_all_timings or elapsed_ms >= float(slow_request_ms):
                logger.info(
                    "request_timing method=%s path=%s status=%s ms=%s",
                    request.method,
                    path,
                    response.status_code,
                    elapsed_ms,
                )
            if int(response.status_code or 0) >= 400:
                _capture_admin_error(
                    request,
                    status_code=int(response.status_code or 500),
                    error_message=f"HTTP {int(response.status_code or 500)}",
                )

        if path.startswith("/static/"):
            lower = path.lower()
            query = request.url.query or ""
            has_build_version = ("v=" in query)
            is_email_wizard_asset = lower.startswith("/static/pages/email-parser-wizard/")
            is_versioned_partial = (
                has_build_version
                and (lower.startswith("/static/partials/") or lower == "/static/shared/shared.html")
            )
            if is_email_wizard_asset:
                # Wizard assets are referenced from a static FileResponse HTML page
                # without build query params, so force revalidation to avoid stale JS.
                response.headers["Cache-Control"] = "no-cache"
            elif is_versioned_partial:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif lower.endswith((".html", ".webmanifest")) or lower.endswith("/sw.js"):
                response.headers["Cache-Control"] = "no-cache"
            else:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    # Serve /static/*
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Lifecycle
    @app.on_event("startup")
    def _startup():
        open_pool()
        ensure_performance_indexes()
        ensure_account_totals_cache_pg()
        ensure_home_snapshot_cache_pg()
        ensure_admin_error_events_table_pg()
        ensure_email_parse_events_table_pg()
        initialize_tenancy()
        try:
            r = get_redis()
            if r is None:
                request_logger.warning("redis startup status=disconnected")
            else:
                request_logger.info("redis startup status=connected")
        except Exception as e:
            request_logger.warning(f"redis startup status=error detail={type(e).__name__}")
        if _env_enabled("ENABLE_STARTUP_WARMUP", "1"):
            prime_widget_tokens_cache_from_db()
            # Import lazily: avoids eager module work when warmup is disabled.
            from app.routers.page_payloads import prime_widget_cache_from_db

            prime_widget_cache_from_db()
        else:
            request_logger.info("startup warmup status=skipped")

    @app.on_event("shutdown")
    def _shutdown():
        close_pool()

    # Auth/session middleware must be registered before most requests
    add_auth_middlewares(app)

    # Routers
    app.include_router(pages.router)
    app.include_router(notifications.router)
    app.include_router(transactions_feeds.router)
    app.include_router(balances.router)
    app.include_router(accounts.router)
    app.include_router(analytics.router)
    app.include_router(categories.router)
    app.include_router(category_rules.router)
    app.include_router(les.router)
    app.include_router(les_profile.router)
    app.include_router(recurring.router)
    app.include_router(settings.router)
    app.include_router(savings_goal.router)
    app.include_router(budget_groups.router)
    app.include_router(funds.router)
    app.include_router(ui_layout.router)
    app.include_router(interest_rates.router)
    app.include_router(transactions.router)
    app.include_router(page_payloads.router)
    app.include_router(admin.router)
    app.include_router(onboarding.router)
    app.include_router(email_parser_trial.router)
    app.include_router(reports.router)
    if _env_enabled("ENABLE_RECEIPTS_ROUTES", "1"):
        from app.routers import receipts

        app.include_router(receipts.router)
    else:
        request_logger.info("receipts routes status=disabled")
    app.include_router(auth.router)
    app.include_router(csv_upload_router)

    return app

app = create_app()
