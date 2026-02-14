from __future__ import annotations

import os
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import FileResponse
from starlette.responses import HTMLResponse, RedirectResponse

from db import with_db_cursor
from app.core.config import BUILD_ID
from app.core.templates import templates

router = APIRouter()

# =============================================================================
# Pages / Static routes (ported from pages.py)
# =============================================================================
# Serve /static/*


@router.get("/__ping")
def ping():
    return {"ok": True, "file": __file__}

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    resp = templates.TemplateResponse(
        "pages/home/home.html",
        {
            "request": request,
            "BUILD_ID": BUILD_ID,
        }
    )

    # 🔑 VERY important for iOS webapp
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"

    return resp

@router.get("/settings")
def settings_page():
    return FileResponse("static/settings.html")

@router.get("/account")
def account_page():
    return FileResponse("static/account.html")

@router.get("/transaction/{tx_id}")
def transaction_detail(tx_id: str):
    """Return *all* columns for a single transaction, plus account metadata (Postgres)."""
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT
              t.*,
              a.institution AS bank,
              a.name        AS card,
              LOWER(a.accountType) AS "accountType"
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.id = %s
            LIMIT 1
            """,
            (tx_id,),
        )
        row = cur.fetchone()

    if not row:
        # txInspect.js throws on !res.ok, so make it a real 404
        raise HTTPException(status_code=404, detail={"ok": False, "error": "not_found", "id": tx_id})

    return {"ok": True, "transaction": dict(row)}

@router.get("/receipts-page")
def receipts_page():
    return FileResponse(os.path.join("static", "receipts.html"))
