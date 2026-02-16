from __future__ import annotations
from app.core import auth
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from app.routers.csv_upload import router as csv_upload_router

from db import open_pool, close_pool

from app.core.templates import templates  # ensure templates init
from app.core.auth import add_auth_middlewares
from app.core.config import BUILD_ID
from app.core.tenancy import initialize_tenancy

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
    onboarding,
)

def create_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def static_cache_control(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path or ""
        if path.startswith("/static/"):
            lower = path.lower()
            query = request.url.query or ""
            has_build_version = ("v=" in query)
            is_versioned_partial = (
                has_build_version
                and (lower.startswith("/static/partials/") or lower == "/static/shared/shared.html")
            )
            if is_versioned_partial:
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
        initialize_tenancy()

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
    app.include_router(onboarding.router)
    app.include_router(auth.router)
    app.include_router(csv_upload_router)

    return app

app = create_app()
