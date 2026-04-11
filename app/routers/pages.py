from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Form, Query
from fastapi.responses import FileResponse
from starlette.responses import HTMLResponse, RedirectResponse

from db import with_db_cursor
from app.core.config import BUILD_ID, MULTI_TENANT_ENABLED, OWNER_GOOGLE_EMAIL
from app.core.templates import templates
from app.core.tenancy import current_tenant_id, get_or_create_onboarding_state

router = APIRouter()

# =============================================================================
# Pages / Static routes (ported from pages.py)
# =============================================================================
# Serve /static/*


def _match_category_rule_for_transaction(
    merchant: str | None,
    category: str | None,
):
    merchant_text = (merchant or "").strip()
    category_text = (category or "").strip()
    if not merchant_text or not category_text:
        return None

    rows = with_db_cursor()
    with rows as (_, cur):
        cur.execute(
            """
            SELECT id, pattern, COALESCE(flags, 'i') AS flags
            FROM categoryrules
            WHERE COALESCE(is_active, TRUE) = TRUE
              AND TRIM(COALESCE(category, '')) = TRIM(%s)
            ORDER BY id DESC
            """,
            (category_text,),
        )
        rules = cur.fetchall() or []

    for r in rules:
        pattern = (r.get("pattern") or "").strip()
        if not pattern:
            continue
        flags = (r.get("flags") or "i").lower()
        py_flags = re.IGNORECASE if ("i" in flags) else 0
        try:
            if re.search(pattern, merchant_text, py_flags):
                return {
                    "id": int(r["id"]),
                    "pattern": pattern,
                }
        except re.error:
            continue
    return None


def _git_recent_updates(limit: int = 40) -> list[dict[str, object]]:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"-n{int(max(1, min(limit, 200)))}",
                "--pretty=format:%H%x1f%h%x1f%ct%x1f%s",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except Exception:
        return []

    if proc.returncode != 0:
        return []

    out: list[dict[str, object]] = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split("\x1f", 3)
        if len(parts) != 4:
            continue
        full_hash, short_hash, ts_raw, subject = parts
        try:
            ts_int = int(ts_raw)
        except Exception:
            ts_int = 0
        out.append(
            {
                "id": full_hash.strip(),
                "short_id": short_hash.strip(),
                "ts": ts_int,
                "subject": (subject or "").strip(),
            }
        )
    return out


@router.get("/__ping")
def ping():
    return {"ok": True, "file": __file__}


@router.get("/app/updates")
def app_updates(request: Request, limit: int = Query(40, ge=1, le=200)):
    if not bool(request.session.get("authed")):
        raise HTTPException(status_code=401, detail="unauthorized")
    updates = _git_recent_updates(limit=int(limit))
    latest_id = (updates[0].get("id") if updates else None) or str(BUILD_ID)
    return {
        "ok": True,
        "build_id": str(BUILD_ID),
        "latest_id": str(latest_id),
        "updates": updates,
    }

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    if MULTI_TENANT_ENABLED:
        tid = current_tenant_id()
        if tid:
            state = get_or_create_onboarding_state(int(tid))
            if not bool(state.get("wizard_completed")):
                with with_db_cursor() as (_, cur):
                    cur.execute("SELECT COUNT(*)::int AS n FROM accounts WHERE tenant_id = %s", (int(tid),))
                    row = cur.fetchone() or {}
                if int(row.get("n") or 0) == 0:
                    return RedirectResponse(url="/setup", status_code=302)

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
    return FileResponse("static/pages/settings/settings.html")

@router.get("/widgets")
def widgets_page():
    return FileResponse("static/pages/widgets/widgets.html")

@router.get("/income-wizard")
def income_wizard_page():
    return FileResponse("static/pages/income-wizard/income-wizard.html")

@router.get("/notification-settings")
def notification_settings_page():
    path = "static/pages/notification-settings/notification-settings.html"
    if os.path.exists(path):
        return FileResponse(path)
    # Fail safe in case the notification-settings page was not included in deploy.
    return FileResponse("static/pages/settings/settings.html")


@router.get("/admin")
def admin_page(request: Request):
    if not bool(request.session.get("authed")):
        raise HTTPException(status_code=401, detail="unauthorized")
    if not _is_owner_request(request):
        raise HTTPException(status_code=403, detail="forbidden")
    return FileResponse("static/pages/admin/admin.html")

@router.get("/account")
def account_page():
    return FileResponse("static/pages/account/account.html")

@router.get("/transaction/{tx_id}")
def transaction_detail(tx_id: str):
    """Return *all* columns for a single transaction, plus account metadata (Postgres)."""
    tid = current_tenant_id() if MULTI_TENANT_ENABLED else None
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            SELECT
              t.*,
              a.institution AS bank,
              a.name        AS card,
              LOWER(a.accountType) AS "accountType"
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.id = %s
              {"AND t.tenant_id = %s AND a.tenant_id = %s" if tid else ""}
            LIMIT 1
            """,
            ((tx_id, int(tid), int(tid)) if tid else (tx_id,)),
        )
        row = cur.fetchone()

    if not row:
        # txInspect.js throws on !res.ok, so make it a real 404
        raise HTTPException(status_code=404, detail={"ok": False, "error": "not_found", "id": tx_id})

    tx = dict(row)
    matched_rule = _match_category_rule_for_transaction(
        merchant=tx.get("merchant"),
        category=tx.get("category"),
    )
    tx["category_rule_id"] = matched_rule["id"] if matched_rule else None
    tx["category_rule_pattern"] = matched_rule["pattern"] if matched_rule else None

    return {"ok": True, "transaction": tx}

@router.get("/receipts-page")
def receipts_page():
    return FileResponse(os.path.join("static", "pages", "receipts", "receipts.html"))


@router.get("/email-parser-wizard")
def email_parser_wizard_page():
    return FileResponse(os.path.join("static", "pages", "email-parser-wizard", "email-parser-wizard.html"))
def _is_owner_request(request: Request) -> bool:
    preview_header = str(request.headers.get("x-non-admin-preview") or "").strip().lower()
    if preview_header in {"1", "true", "yes", "on"}:
        return False
    if not MULTI_TENANT_ENABLED:
        return True
    session_email = (request.session.get("google_email") or "").strip().lower()
    owner_email = (OWNER_GOOGLE_EMAIL or "").strip().lower()
    return bool(owner_email) and session_email == owner_email
