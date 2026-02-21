from __future__ import annotations
import logging
import os
import time
from app.core import auth
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.middleware.gzip import GZipMiddleware
from app.routers.csv_upload import router as csv_upload_router

from db import open_pool, close_pool, ensure_performance_indexes

from app.core.templates import templates  # ensure templates init
from app.core.auth import add_auth_middlewares
from app.core.config import BUILD_ID
from app.core.tenancy import initialize_tenancy
from app.core.account_totals_cache import ensure_account_totals_cache_pg
from app.core.home_snapshot_cache import ensure_home_snapshot_cache_pg
from app.core.widget_tokens import prime_widget_tokens_cache_from_db

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
)
from app.routers.page_payloads import prime_widget_cache_from_db

def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=700)
    logger = logging.getLogger("app.perf")
    slow_request_ms = int(os.getenv("SLOW_REQUEST_MS", "450"))
    log_all_timings = os.getenv("LOG_ALL_REQUEST_TIMINGS", "0").strip() == "1"

    @app.middleware("http")
    async def static_cache_control(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        path = request.url.path or ""
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)

        if not path.startswith("/static/"):
            if log_all_timings or elapsed_ms >= float(slow_request_ms):
                logger.info(
                    "request_timing method=%s path=%s status=%s ms=%s",
                    request.method,
                    path,
                    response.status_code,
                    elapsed_ms,
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

    # Optional receipts router (kept identical to prior behavior)
    try:
        from Receipts.receipts import router as receipts_router
    except Exception:
        receipts_router = None
    if receipts_router is not None:
        app.include_router(receipts_router)

    # Serve /static/*
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Lifecycle
    @app.on_event("startup")
    def _startup():
        open_pool()
        ensure_performance_indexes()
        ensure_account_totals_cache_pg()
        ensure_home_snapshot_cache_pg()
        initialize_tenancy()
        prime_widget_tokens_cache_from_db()
        prime_widget_cache_from_db()

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
    app.include_router(auth.router)
    app.include_router(csv_upload_router)

    return app

app = create_app()
