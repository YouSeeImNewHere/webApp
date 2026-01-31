from __future__ import annotations
from fastapi import FastAPI, HTTPException, Query
import re
import inspect
import os
from typing import Tuple, Callable, List, Any, Dict, Optional

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import date as _date, timedelta as _timedelta, datetime, datetime as _datetime
from datetime import date, timedelta
import calendar
import json
from pydantic import BaseModel

from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from recurring import get_recurring, _norm_merchant, _amount_bucket, get_ignored_merchants_preview
from db import query_db, with_db_cursor, open_pool, close_pool
from dotenv import load_dotenv
load_dotenv()

from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
import time

BUILD_ID = str(int(time.time()))

templates = Jinja2Templates(directory="static")

try:
    from Receipts.receipts import router as receipts_router
except Exception:
    receipts_router = None

MAX_TRANSFER_WINDOW_DAYS = 10
CATEGORY_RULES_TABLE = "categoryrules"
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI()
if receipts_router is not None:
    app.include_router(receipts_router)

@app.on_event("startup")
def _startup():
    open_pool()

@app.on_event("shutdown")
def _shutdown():
    close_pool()

# =============================================================================
# Auth (cookie session) — simple password gate for Render deployment
# =============================================================================

SESSION_SECRET = (os.getenv("SESSION_SECRET", "") or "").strip()
APP_PASSWORD = (os.getenv("APP_PASSWORD", "") or "").strip().strip('"').strip("'")

if not SESSION_SECRET:
    # In production you MUST set this in Render env vars (random long string).
    # Leaving it empty would make session signing insecure / broken.
    raise RuntimeError("SESSION_SECRET env var is required")

is_render = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID"))
is_prod = os.getenv("ENV", "").lower() == "prod"

# Signed cookie session
is_render = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID"))

def _is_authed(request: Request) -> bool:
    try:
        return bool(request.session.get("authed"))
    except Exception:
        return False

PUBLIC_EXACT = {"/__ping", "/login", "/favicon.ico", "/__whoami"}

PUBLIC_PREFIXES = {"/static/"}

class RequireLoginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

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

@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/icon/favicon.ico")

@app.get("/login")
def login_page(next: str = "/"):
    # Basic single-file login form so you don't need to create a new static page.
    # Uses POST /login with a form field "password".
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
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
          <form method="post" action="/login">
            <input type="hidden" name="next" value="{next}"/>
            <label>Password</label>
            <input name="password" type="password" autocomplete="current-password" autofocus />
            <button type="submit">Continue</button>
          </form>
          <div class="hint">This site is private.</div>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/login")
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
        password = (str(form.get("password", "")) or "").strip()
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

@app.get("/__whoami")
def __whoami(request: Request):
    return {
        "authed": bool(request.session.get("authed")),
        "cookies": dict(request.cookies),
        "session": dict(request.session),
    }

@app.post("/logout")
def logout(request: Request):
    try:
        request.session.clear()
    except Exception:
        pass
    return {"ok": True}

app.add_middleware(RequireLoginMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="webapp_session",
    same_site="lax",
    max_age=None,
    https_only=is_render,
)

# =============================================================================
# Pages / Static routes (ported from pages.py)
# =============================================================================
# Serve /static/*

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/__ping")
def ping():
    return {"ok": True, "file": __file__}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    resp = templates.TemplateResponse(
        "home.html",
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


@app.get("/settings")
def settings_page():
    return FileResponse("static/settings.html")

@app.get("/account")
def account_page():
    return FileResponse("static/account.html")

@app.get("/transactions-test-page")
def transactions_test_page():
    return FileResponse("static/transactions_test_account.html")

@app.get("/transactions-test-account")
def transactions_test_account_page():
    return FileResponse("static/transactions_test_account.html")

@app.get("/transaction/{tx_id}")
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

@app.get("/receipts-page")
def receipts_page():
    return FileResponse(os.path.join("static", "receipts.html"))

# =============================================================================
# Notifications (Postgres)
# =============================================================================

def ensure_notifications_table():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                dedupe_key TEXT UNIQUE NOT NULL,
                subject TEXT,
                sender TEXT,
                body TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                dismissed BOOLEAN NOT NULL DEFAULT FALSE
            );
            """
        )
        conn.commit()

class NotificationPush(BaseModel):
    kind: str = "credit_usage"
    dedupe_key: str
    subject: str
    sender: str = "System"
    body: str = ""

@app.post("/notifications/push")
def push_notification(payload: NotificationPush):
    ensure_notifications_table()
    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                """
                INSERT INTO notifications (kind, dedupe_key, subject, sender, body)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                (payload.kind, payload.dedupe_key, payload.subject, payload.sender, payload.body),
            )
            conn.commit()
            return {"ok": True}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/notifications")
def list_notifications(limit: int = 200):
    ensure_notifications_table()
    rows = query_db(
        """
        SELECT id, subject, sender, created_at, is_read
        FROM notifications
        WHERE dismissed = FALSE
        ORDER BY is_read ASC, created_at DESC
        LIMIT %s
        """,
        (int(limit),),
    )

    return {
        "items": [
            {
                "id": r["id"],
                "subject": r["subject"],
                "sender": r["sender"],
                "created_at": (
                    r["created_at"].isoformat()
                    if r.get("created_at") and hasattr(r["created_at"], "isoformat")
                    else (str(r.get("created_at")) if r.get("created_at") else None)
                ),
                "is_read": bool(r["is_read"]),
            }
            for r in rows
        ]
    }

@app.get("/notifications/unread-count")
def unread_count():
    ensure_notifications_table()
    rows = query_db(
        """
        SELECT COUNT(*)::int AS n
        FROM notifications
        WHERE dismissed = FALSE AND is_read = FALSE
        """
    )
    return {"unread": int(rows[0]["n"]) if rows else 0}

@app.get("/notifications/{notif_id}")
def get_notification(notif_id: int):
    ensure_notifications_table()
    rows = query_db(
        """
        SELECT id, subject, sender, body, created_at, is_read, dismissed
        FROM notifications
        WHERE id = %s
        LIMIT 1
        """,
        (int(notif_id),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Notification not found")
    r = rows[0]

    created = r["created_at"]
    return {
        "id": r["id"],
        "subject": r["subject"],
        "sender": r["sender"],
        "body": r["body"],
        "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),

        "is_read": bool(r["is_read"]),
        "dismissed": bool(r["dismissed"]),
    }

@app.post("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int):
    ensure_notifications_table()
    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (int(notif_id),))
        conn.commit()
    return {"ok": True}

@app.post("/notifications/{notif_id}/dismiss")
def dismiss_notification(notif_id: int):
    ensure_notifications_table()
    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET dismissed = TRUE WHERE id = %s", (int(notif_id),))
        conn.commit()
    return {"ok": True}

@app.post("/notifications/mark-all-read")
def mark_all_notifications_read():
    ensure_notifications_table()
    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET is_read = TRUE WHERE dismissed = FALSE")
        conn.commit()
    return {"ok": True}

@app.post("/notifications/clear-read")
def clear_read_notifications():
    ensure_notifications_table()
    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET dismissed = TRUE WHERE dismissed = FALSE AND is_read = TRUE")
        conn.commit()
    return {"ok": True}

# =============================================================================
# Transactions feeds (Postgres)
# =============================================================================

def _is_transfer_like(cat: Optional[str]) -> bool:
    c = (cat or "").strip().lower()
    return c in ("transfer", "card payment")

def _cents(x: float) -> int:
    return int(round(abs(float(x)) * 100))

def attach_transfer_peers_pg(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Adds:
      - transfer_peer: "Institution — Name"
      - transfer_peer_id: int
    for rows whose category is Transfer/Card Payment.

    We do this in Python so we don't need tricky SQL across your mixed date formats.
    """
    if not rows:
        return rows

    # Build account display map
    acct_rows = query_db("SELECT id, institution, name FROM accounts")
    acct_name = {int(a["id"]): f'{a["institution"]} — {a["name"]}' for a in acct_rows}

    # Work only on candidates in the current payload that have dateISO
    cands = []
    for r in rows:
        if not _is_transfer_like(r.get("category")):
            continue
        d = r.get("dateISO")
        if not d:
            continue
        try:
            amt = float(r.get("amount") or 0.0)
        except Exception:
            continue
        if amt == 0:
            continue
        cands.append(
            {
                "id": r.get("id"),
                "account_id": int(r.get("account_id") or 0),
                "date": d if isinstance(d, date) else datetime.fromisoformat(str(d)).date(),
                "cents": _cents(amt),
                "sign": 1 if amt > 0 else -1,
            }
        )

    if not cands:
        return rows

    # Define a wide window to query possible peers just once
    min_d = min(c["date"] for c in cands) - timedelta(days=MAX_TRANSFER_WINDOW_DAYS)
    max_d = max(c["date"] for c in cands) + timedelta(days=MAX_TRANSFER_WINDOW_DAYS)

    peer_rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.account_id,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE LOWER(TRIM(COALESCE(t.category,''))) IN ('transfer','card payment')
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT id, account_id, amount, category, d
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN %s AND %s
        """,
        (min_d, max_d),
    )

    peers = []
    for p in peer_rows:
        try:
            amt = float(p["amount"] or 0.0)
        except Exception:
            continue
        if amt == 0:
            continue
        peers.append(
            {
                "id": p["id"],
                "account_id": int(p["account_id"]),
                "date": p["d"],
                "cents": _cents(amt),
                "sign": 1 if amt > 0 else -1,
            }
        )

    # Index peers by (cents, sign) for quick lookup
    by_key: Dict[tuple[int, int], List[dict]] = {}
    for p in peers:
        by_key.setdefault((p["cents"], p["sign"]), []).append(p)
    for k in by_key:
        by_key[k].sort(key=lambda x: (x["date"], str(x["id"])))

    used_peer_ids = set()
    id_to_peer = {}

    for c in cands:
        opp = by_key.get((c["cents"], -c["sign"]), [])
        best = None
        best_score = None

        for o in opp:
            if o["id"] in used_peer_ids:
                continue
            if o["account_id"] == c["account_id"]:
                continue
            dd = abs((o["date"] - c["date"]).days)
            if dd > MAX_TRANSFER_WINDOW_DAYS:
                continue
            score = (dd, str(o["id"]))
            if best_score is None or score < best_score:
                best_score = score
                best = o

        if best:
            used_peer_ids.add(best["id"])
            id_to_peer[c["id"]] = (best["account_id"], acct_name.get(best["account_id"]))

    for r in rows:
        pid = id_to_peer.get(r.get("id"))
        if pid:
            peer_id, peer_label = pid
            r["transfer_peer_id"] = int(peer_id)
            r["transfer_peer"] = peer_label or f"Account {peer_id}"

    return rows

class TxCategoryUpdate(BaseModel):
    category: str = ""

@app.post("/transaction/{tx_id}/category")
def transaction_set_category(tx_id: str, body: TxCategoryUpdate):
    category = (body.category or "").strip()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            UPDATE transactions
            SET category = %s
            WHERE id = %s
            """,
            (category, tx_id),
        )
        if (cur.rowcount or 0) == 0:
            conn.rollback()
            raise HTTPException(status_code=404, detail={"ok": False, "error": "not_found", "id": tx_id})

        conn.commit()

    return {"ok": True, "id": tx_id, "category": category}

# =============================================================================
# Balance / Series Helpers (Postgres)
# Ported from balances.py
# =============================================================================

def apply_transaction(current_totals: Dict[int, float], account_id: int, amount: float, account_type: Optional[str]) -> None:
    """
    Same rule as sqlite version:
      - investment: contributions increase net worth (delta = +amount)
      - everything else: spending reduces net worth (delta = -amount)
    """
    t = (account_type or "other").lower()
    amt = float(amount or 0.0)

    if t in ("investment",):
        delta = amt
    else:
        delta = -amt

    current_totals[int(account_id)] = float(current_totals.get(int(account_id), 0.0)) + float(delta)

def load_starting_balances_pg() -> Dict[int, float]:
    """
    StartingBalance table -> {account_id: sum(start)}.
    Matches sqlite logic. :contentReference[oaicite:1]{index=1}
    """
    rows = query_db(
        """
        SELECT account_id::int AS account_id, COALESCE(SUM(start), 0)::double precision AS total_start
        FROM startingbalance
        GROUP BY account_id
        """
    )
    return {int(r["account_id"]): float(r["total_start"] or 0.0) for r in rows}

def load_account_type_map_pg() -> Dict[int, str]:
    """
    accounts -> {id: lower(accountType)}.
    Matches sqlite logic. :contentReference[oaicite:2]{index=2}
    """
    rows = query_db("SELECT id::int AS id, LOWER(accounttype) AS t FROM accounts")
    return {int(r["id"]): (r["t"] or "other") for r in rows}

def load_transactions_pg() -> List[Dict[str, Any]]:
    """
    Loads normalized transactions as:
      [{"date": date, "account_id": int, "amount": float, "accountType": str}, ...]
    Rule preserved: use postedDate if present else purchaseDate; skip unknown/broken.
    :contentReference[oaicite:3]{index=3}
    """
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.account_id::int AS account_id,
            t.amount::double precision AS amount,
            LOWER(a.accountType) AS accountType,
            COALESCE(
              NULLIF(TRIM(t.postedDate), 'unknown'),
              NULLIF(TRIM(t.purchaseDate), 'unknown')
            ) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            account_id,
            amount,
            accountType,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT account_id, amount, accountType, d
        FROM norm
        WHERE d IS NOT NULL
        ORDER BY d ASC, account_id ASC
        """
    )

    tx: List[Dict[str, Any]] = []
    for r in rows:
        # Safety: amount can be NULL or non-numeric if data is messy
        try:
            amt = float(r["amount"])
        except Exception:
            continue

        d = r["d"]
        if not d:
            continue

        tx.append({
            "date": d,
            "account_id": int(r["account_id"]),
            "amount": amt,
            "accountType": (r.get("account_type") or "other"),
        })

    # already ordered by SQL, but keep stable:
    tx.sort(key=lambda t: t["date"])
    return tx

def build_series(
    start_date: _date,
    end_date: _date,
    starting: Dict[int, float],
    transactions: List[Dict[str, Any]],
    value_fn: Callable[[Dict[int, float]], float],
) -> List[Dict[str, Any]]:
    """
    Same behavior as sqlite build_series: roll forward, then emit daily values.
    :contentReference[oaicite:4]{index=4}
    """
    current_totals = dict(starting)
    results: List[Dict[str, Any]] = []
    tx_index = 0

    # A) roll forward before start_date
    while tx_index < len(transactions) and transactions[tx_index]["date"] < start_date:
        t = transactions[tx_index]
        apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
        tx_index += 1

    # B) day-by-day
    day = start_date
    while day <= end_date:
        while tx_index < len(transactions) and transactions[tx_index]["date"] == day:
            t = transactions[tx_index]
            apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
            tx_index += 1

        results.append({"date": day.isoformat(), "value": float(value_fn(current_totals))})
        day += _timedelta(days=1)

    return results

def latest_rates_map_pg() -> Dict[int, float]:
    """
    Returns {account_id: apr} for the most recent effective_date per account.
    Postgres equivalent of latest_rates_map(). :contentReference[oaicite:5]{index=5}
    """
    rows = query_db(
        """
        SELECT r.account_id::int AS account_id, r.apr::double precision AS apr
        FROM interest_rates r
        JOIN (
          SELECT account_id, MAX(effective_date) AS max_eff
          FROM interest_rates
          GROUP BY account_id
        ) last
          ON last.account_id = r.account_id
         AND last.max_eff = r.effective_date
        """
    )

    out: Dict[int, float] = {}
    for r in rows:
        try:
            out[int(r["account_id"])] = float(r["apr"])
        except Exception:
            pass
    return out

@app.get("/transactions")
def transactions(limit: int = Query(15, ge=1, le=1000)):
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.postedDate,
            t.purchaseDate,
            t.merchant,
            t.amount::double precision AS amount,
            t.status,
            t.account_id,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accounttype) AS account_type,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          id,
          account_id,
          raw_date AS postedDate,
          merchant,
          amount,
          status,
          bank,
          card,
          account_type,
          category,
          d AS "dateISO"
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (int(limit),),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    return rows

@app.get("/account-transactions")
def account_transactions(account_id: int, limit: int = Query(200, ge=1, le=5000)):
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.merchant,
            t.amount::double precision AS amount,
            TRIM(t.category) AS category
          FROM transactions t
          WHERE t.account_id = %s
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          id,
          account_id,
          raw_date AS postedDate,
          merchant,
          amount,
          status,
          bank,
          card,
          account_type AS "accountType",
          category,
          d AS "dateISO"
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (int(account_id), int(account_id), int(limit)),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    return rows

from fastapi import Query

@app.get("/transactions-all")
def transactions_all(
    limit: int = Query(50, ge=1, le=50000),
    offset: int = Query(0, ge=0),

    # NEW
    q: str = "",
    start: str = "",
    end: str = "",
    amt_mode: str = "any",     # any|exact|min|max|between (JS sends this)
    amt_min: float | None = None,
    amt_max: float | None = None,
    amt_abs: int = 1,          # 1 => abs(amount)
):
    """
    Paginated feed with server-side filtering for All Transactions page.
    """
    q = (q or "").strip()
    start = (start or "").strip()
    end = (end or "").strip()
    amt_mode = (amt_mode or "any").strip().lower()
    use_abs = bool(int(amt_abs or 0))

    where = []
    params = []

    # text search across merchant/bank/card/category
    if q:
        where.append("""
          (
            COALESCE(t.merchant,'') ILIKE %s OR
            COALESCE(a.institution,'') ILIKE %s OR
            COALESCE(a.name,'') ILIKE %s OR
            COALESCE(t.category,'') ILIKE %s
          )
        """)
        like = f"%{q}%"
        params.extend([like, like, like, like])

    # date window (ISO yyyy-mm-dd)
    if start:
        # parse_iso already exists in your file
        sd = parse_iso(start)
        where.append("d >= %s")
        params.append(sd)

    if end:
        ed = parse_iso(end)
        where.append("d <= %s")
        params.append(ed)

    # amount filter
    amt_expr = "ABS(t.amount::double precision)" if use_abs else "t.amount::double precision"

    # If caller sets min/max directly, honor them (regardless of amt_mode)
    if amt_min is not None:
        where.append(f"{amt_expr} >= %s")
        params.append(float(amt_min))
    if amt_max is not None:
        where.append(f"{amt_expr} <= %s")
        params.append(float(amt_max))

    # Build WHERE clause safely
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.*,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            base.*,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          *,
          d AS "dateISO"
        FROM norm
        {where_sql}
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [int(limit), int(offset)]),
    )

    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    return rows

# -----------------------------------------------------------------------------
# /account-series (single account balance series)
# -----------------------------------------------------------------------------
@app.get("/account-series")
def account_series(account_id: int, start: str, end: str):
    """
    Postgres port of your sqlite /account-series.

    Rules preserved:
      - Use postedDate if present, else purchaseDate.
      - Skip rows with no usable date or non-numeric amount.
      - Roll forward transactions before start, then emit daily values.
      - investment: bal += amount
        else:        bal -= amount
      - credit display value is (-bal)
    """

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    with with_db_cursor() as (conn, cur):
        # starting balance for this account
        cur.execute(
            """
            SELECT COALESCE(SUM(start), 0)::double precision AS s
            FROM startingbalance
            WHERE account_id = %s
            """,
            (int(account_id),),
        )
        bal = float((cur.fetchone() or {}).get("s") or 0.0)

        # account type
        cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s", (int(account_id),))
        row = cur.fetchone()
        acc_type = (row["t"] if row else "other") or "other"

        # pull both postedDate and purchaseDate (stored as strings in your schema)
        cur.execute(
            """
            SELECT posteddate, purchasedate, amount
            FROM transactions
            WHERE account_id = %s
            """,
            (int(account_id),),
        )
        rows = cur.fetchall() or []

    # psycopg2 DictCursor rows support both dict-style and key access; be defensive
    tx: List[Dict[str, Any]] = []
    for r in rows:
        posted_raw = (r.get("postedDate") or r.get("posteddate")) if hasattr(r, "get") else r["posteddate"]
        purchase_raw = (r.get("purchaseDate") or r.get("purchasedate")) if hasattr(r, "get") else r["purchasedate"]

        posted = parse_posted_date(posted_raw)
        purchase = parse_posted_date(purchase_raw)

        tx_date = posted if posted is not None else purchase
        if tx_date is None:
            continue

        amt_raw = r.get("amount") if hasattr(r, "get") else r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            continue

        tx.append({"date": tx_date, "amount": amt})

    tx.sort(key=lambda x: x["date"])

    i = 0

    # A) roll forward transactions BEFORE the start date
    while i < len(tx) and tx[i]["date"] < start_date:
        amt = tx[i]["amount"]
        if acc_type == "investment":
            bal += amt
        else:
            bal -= amt
        i += 1

    # B) day-by-day series
    results = []
    day = start_date
    while day <= end_date:
        while i < len(tx) and tx[i]["date"] == day:
            amt = tx[i]["amount"]
            if acc_type == "investment":
                bal += amt
            else:
                bal -= amt
            i += 1

        display_val = (-bal) if acc_type == "credit" else bal
        results.append({"date": day.isoformat(), "value": float(display_val)})
        day += timedelta(days=1)

    return results

# -----------------------------------------------------------------------------
# /account-transactions-range (Postgres)
# -----------------------------------------------------------------------------
@app.get("/account-transactions-range")
def account_transactions_range(
    account_id: int,
    start: str,
    end: str,
    limit: int = Query(500, ge=1, le=5000),
):
    start_d = parse_iso(start)   # python date
    end_d = parse_iso(end)       # python date

    # For SQL comparisons
    start_date = start_d.isoformat()  # 'YYYY-MM-DD'
    end_date = end_d.isoformat()

    with with_db_cursor() as (conn, cur):
        # account type
        cur.execute(
            "SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s",
            (int(account_id),),
        )
        row = cur.fetchone()
        acc_type = (row["t"] if row else "other") or "other"

        # sign rule consistent with your series logic:
        # investment: balance += amount
        # others:     balance -= amount
        sign = 1 if acc_type == "investment" else -1

        # starting balance from table
        cur.execute(
            """
            SELECT COALESCE(SUM(start), 0)::double precision AS s
            FROM startingbalance
            WHERE account_id = %s
            """,
            (int(account_id),),
        )
        row = cur.fetchone()
        start_bal = float((row["s"] if row else 0.0) or 0.0)

        # roll forward all transactions BEFORE start_date (effective date = posted else purchase)
        cur.execute(
            """
            WITH base AS (
              SELECT
                COALESCE(
                  NULLIF(TRIM(postedDate), 'unknown'),
                  NULLIF(TRIM(purchaseDate), 'unknown')
                ) AS raw_date,
                amount::double precision AS amount
              FROM transactions
              WHERE account_id = %s
            ),
            norm AS (
              SELECT
                amount,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT COALESCE(SUM(amount), 0)::double precision AS s
            FROM norm
            WHERE d IS NOT NULL AND d < %s::date
            """,
            (int(account_id), start_date),
        )
        row = cur.fetchone()
        before_sum = float((row["s"] if row else 0.0) or 0.0)

        starting_balance_at_range = start_bal + (sign * before_sum)

        # now fetch range tx and compute running balance inside range
        cur.execute(
            """
            WITH base AS (
              SELECT
                id,
                %s::int AS account_id,
                merchant,
                amount::double precision AS amount,
                TRIM(category) AS category,
                COALESCE(NULLIF(TRIM(status), ''), 'posted') AS status,
                COALESCE(
                  NULLIF(TRIM(postedDate), 'unknown'),
                  NULLIF(TRIM(purchaseDate), 'unknown')
                ) AS raw_date
              FROM transactions
              WHERE account_id = %s
            ),
            norm AS (
              SELECT
                id,
                account_id,
                merchant,
                amount,
                category,
                status,
                raw_date,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            ),
            in_range AS (
              SELECT *
              FROM norm
              WHERE d IS NOT NULL
                AND d BETWEEN %s::date AND %s::date
              ORDER BY d ASC, id ASC
              LIMIT %s
            ),
            with_running AS (
              SELECT
                id,
                account_id,
                merchant,
                amount,
                category,
                status,
                raw_date AS "effectiveDate",
                d AS "dateISO",
                SUM(amount) OVER (ORDER BY d, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_sum
              FROM in_range
            )
            SELECT
              id,
              account_id,
              "effectiveDate",
              "dateISO",
              merchant,
              amount,
              category,
              status,
              (%s::double precision + (%s::double precision * running_sum))::double precision AS balance_after
            FROM with_running
            ORDER BY "dateISO" DESC, id DESC
            """,
            (
                int(account_id),
                int(account_id),
                start_date,
                end_date,
                int(limit),
                float(starting_balance_at_range),
                float(sign),
            ),
        )
        rows = cur.fetchall() or []

        tx = [dict(r) for r in rows]

        # Peer detection: you already have this helper in app_postgres.py.
        # It adds transfer_peer + transfer_peer_id for transfer/card payment rows.
        # (It expects: id, account_id, amount, category, dateISO)
        attach_transfer_peers_pg(tx)

    # direction relative to THIS account (matches your prior behavior)
    transfer_cats = {"transfer", "card payment"}
    for r in tx:
        cat = (r.get("category") or "").strip().lower()
        if cat in transfer_cats:
            try:
                a = float(r.get("amount") or 0.0)
            except Exception:
                a = 0.0
            r["transfer_dir"] = "from" if a < 0 else "to"

    ending_balance = float(tx[0]["balance_after"]) if tx else float(starting_balance_at_range)

    # ---- DISPLAY NORMALIZATION (credit shows positive debt) ----
    if acc_type == "credit":
        starting_balance_at_range = -float(starting_balance_at_range)
        ending_balance = -float(ending_balance)
        for r in tx:
            r["balance_after"] = -float(r["balance_after"])

    return {
        "account_id": int(account_id),
        "start": start_date,
        "end": end_date,
        "starting_balance": float(starting_balance_at_range),
        "ending_balance": float(ending_balance),
        "transactions": tx,
    }

# =============================================================================
# Accounts / Bank endpoints (Postgres) — ported from accounts.py
# =============================================================================

def _pg_column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    )
    return cur.fetchone() is not None

def _pg_table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = %s
        LIMIT 1
        """,
        (table,),
    )
    return cur.fetchone() is not None

def _to_float_or_zero(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0

@app.get("/account/{account_id}")
def account_info(account_id: int):
    sql = """
      SELECT id, institution, name, LOWER(accountType) AS accounttype
      FROM accounts
      WHERE id = %s
    """
    rows = query_db(sql, (int(account_id),))
    return rows[0] if rows else {"error": "Account not found"}

@app.get("/bank-info")
def bank_info():
    with with_db_cursor() as (conn, cur):
        # Current rate (decimal) from interest_rates: 0.0425 means 4.25%
        # Your app_postgres.py already defines latest_rates_map_pg()
        rate_now = latest_rates_map_pg()

        # Be robust to schema (no hard requirement for optional columns/tables)
        has_credit_limit = _pg_column_exists(cur, "accounts", "credit_limit")
        has_notes = _pg_column_exists(cur, "accounts", "notes")  # only if you added it
        has_card_benefits = _pg_table_exists(cur, "card_benefits")

        # Build SELECT lists without requiring non-existent columns
        account_select = """
          SELECT id AS account_id,
                 institution AS bank,
                 name,
                 LOWER(accountType) AS type
        """
        if has_notes:
            account_select += ", notes"
        account_select += """
          FROM accounts
          WHERE LOWER(accountType) != 'credit'
          ORDER BY institution, name
        """

        card_select = """
          SELECT id AS card_id,
                 institution AS bank,
                 name
        """
        if has_credit_limit:
            card_select += ", credit_limit"
        card_select += """
          FROM accounts
          WHERE LOWER(accountType) = 'credit'
          ORDER BY institution, name
        """

        cur.execute(account_select)
        accounts = cur.fetchall()

        cur.execute(card_select)
        cards = cur.fetchall()

        benefits_rows = []
        if has_card_benefits:
            cur.execute(
                """
                SELECT account_id, category, cashback_percent
                FROM card_benefits
                ORDER BY account_id, category
                """
            )
            benefits_rows = cur.fetchall()

    # Attach benefits by card
    by_card: Dict[int, List[Dict[str, Any]]] = {}
    for b in benefits_rows:
        aid = int(b["account_id"])
        by_card.setdefault(aid, []).append(
            {
                "categories": [b["category"]] if b.get("category") else [],
                "cashback_percent": float(b.get("cashback_percent") or 0.0),
            }
        )

    def as_percent(rate_decimal):
        if rate_decimal is None:
            return None
        try:
            return float(rate_decimal) * 100.0
        except Exception:
            return None

    accounts_out = []
    for r in accounts:
        aid = int(r["account_id"])
        item = {
            "account_id": aid,
            "bank": r["bank"],
            "name": r["name"],
            "type": r["type"],
            "apy": as_percent(rate_now.get(aid)),
        }
        if has_notes:
            item["notes"] = r.get("notes")
        accounts_out.append(item)

    cards_out = []
    for r in cards:
        cid = int(r["card_id"])
        item = {
            "card_id": cid,
            "bank": r["bank"],
            "name": r["name"],
            "apr": as_percent(rate_now.get(cid)),
            "benefits": by_card.get(cid, []),
        }
        if has_credit_limit:
            item["credit_limit"] = r.get("credit_limit")
        cards_out.append(item)

    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "accounts": accounts_out,
        "credit_cards": cards_out,
    }

@app.post("/bank-info/refresh")
def bank_info_refresh():
    # placeholder for now
    return {"ok": True}

@app.get("/bank-totals")
def bank_totals():
    with with_db_cursor() as (conn, cur):
        has_credit_limit = _pg_column_exists(cur, "accounts", "credit_limit")

        accounts_sql = """
          SELECT id, institution, name, LOWER(accountType) AS accounttype
        """
        if has_credit_limit:
            accounts_sql += ", credit_limit"
        accounts_sql += """
          FROM accounts
        """

        cur.execute(accounts_sql)
        accounts = cur.fetchall()

        cur.execute(
            """
            SELECT account_id, SUM(start) AS start_total
            FROM "startingbalance"
            GROUP BY account_id
            """
        )
        starting_rows = cur.fetchall()

        cur.execute(
            """
            SELECT account_id, SUM(amount) AS trans_total
            FROM transactions
            GROUP BY account_id
            """
        )
        tx_rows = cur.fetchall()

    starting = {int(r["account_id"]): float(r["start_total"] or 0) for r in starting_rows}
    tx_totals = {int(r["account_id"]): float(r["trans_total"] or 0) for r in tx_rows}

    by_type = {"checking": [], "savings": [], "investment": [], "credit": [], "other": []}

    for a in accounts:
        aid = int(a["id"])
        acc_type = (a.get("accounttype") or "other").lower()

        start = starting.get(aid, 0.0)
        trans = tx_totals.get(aid, 0.0)

        # NOTE: preserving your existing logic from accounts.py (start - trans)
        balance = start - trans

        bucket = acc_type if acc_type in by_type else "other"
        display_name = f'{a["institution"]} — {a["name"]}'
        item = {"id": aid, "name": display_name, "total": balance}

        if bucket == "credit" and has_credit_limit:
            item["credit_limit"] = _to_float_or_zero(a.get("credit_limit"))

        by_type[bucket].append(item)

    for k in by_type:
        by_type[k].sort(key=lambda x: x["total"], reverse=True)

    return {k: {"total": sum(x["total"] for x in lst), "accounts": lst} for k, lst in by_type.items()}

# =============================================================================
# Analytics endpoints (Postgres) — ported from analytics.py
# =============================================================================

# --- Date helpers (safe, small, self-contained) ---
def parse_iso(s: str) -> date:
    # expects "YYYY-MM-DD"
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Bad ISO date: {s!r}")

def parse_posted_date(raw: Optional[object]) -> Optional[_date]:
    if raw is None:
        return None

    # If psycopg ever gives you real date/datetime types, handle them.
    if isinstance(raw, _date) and not isinstance(raw, _datetime):
        return raw
    if isinstance(raw, _datetime):
        return raw.date()

    x = str(raw).strip()
    if not x or x.lower() == "unknown":
        return None

    # ISO: YYYY-MM-DD
    if _ISO_RE.match(x):
        try:
            return _datetime.fromisoformat(x).date()
        except Exception:
            return None

    # Legacy formats from your old SQLite/email parsing
    try:
        if len(x) == 8:   # MM/DD/YY
            return _datetime.strptime(x, "%m/%d/%y").date()
        if len(x) == 10:  # MM/DD/YYYY
            return _datetime.strptime(x, "%m/%d/%Y").date()
    except Exception:
        return None

    return None

def _last_day_of_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]

# -----------------------------------------------------------------------------
# /net-worth
# -----------------------------------------------------------------------------
@app.get("/net-worth")
def net_worth(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances_pg()
    transactions = load_transactions_pg()
    acct_types = load_account_type_map_pg()

    current_totals = dict(starting)
    results = []
    tx_index = 0

    # A) roll forward before start_date
    while tx_index < len(transactions) and transactions[tx_index]["date"] < start_date:
        t = transactions[tx_index]
        apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
        tx_index += 1

    # B) day-by-day
    day = start_date
    while day <= end_date:
        while tx_index < len(transactions) and transactions[tx_index]["date"] == day:
            t = transactions[tx_index]
            apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
            tx_index += 1

        banks = 0.0
        savings_total = 0.0
        cards_balance = 0.0  # signed: negative = owe, positive = surplus

        for aid, bal in current_totals.items():
            t = (acct_types.get(aid) or "other").lower()
            if t == "savings":
                savings_total += bal
            elif t == "credit":
                cards_balance += bal
            else:
                banks += bal

        cards_owed = max(0.0, -cards_balance)
        net = banks + savings_total + cards_balance

        results.append(
            {
                "date": day.isoformat(),
                "value": float(net),
                "banks": float(banks),
                "savings": float(savings_total),
                "cards": float(cards_owed),
                "cards_balance": float(cards_balance),
            }
        )

        day += timedelta(days=1)

    return results

# -----------------------------------------------------------------------------
# /savings
# -----------------------------------------------------------------------------
@app.get("/savings")
def savings(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances_pg()
    transactions = load_transactions_pg()
    acct_types = load_account_type_map_pg()

    def savings_only(totals: Dict[int, float]) -> float:
        return sum(bal for aid, bal in totals.items() if (acct_types.get(aid) or "").lower() == "savings")

    return build_series(start_date, end_date, starting, transactions, value_fn=savings_only)

# -----------------------------------------------------------------------------
# /investments
# -----------------------------------------------------------------------------
@app.get("/investments")
def investments(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances_pg()
    transactions = load_transactions_pg()
    acct_types = load_account_type_map_pg()

    def investments_only(totals: Dict[int, float]) -> float:
        return sum(bal for aid, bal in totals.items() if (acct_types.get(aid) or "").lower() == "investment")

    return build_series(start_date, end_date, starting, transactions, value_fn=investments_only)

# -----------------------------------------------------------------------------
# /spending
# -----------------------------------------------------------------------------
@app.get("/spending")
def spending(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT d, amount, category, accountType
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        """,
        (start_date, end_date),
    )

    daily: Dict[date, float] = {}
    for r in rows:
        d = r["d"]
        if not d:
            continue
        try:
            amt = float(r["amount"])
        except Exception:
            continue

        category = (r["category"] or "").strip().lower()

        # exclusions
        if category in ("card payment", "transfer"):
            continue

        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            daily[d] = daily.get(d, 0.0) + amt

    results = []
    day = start_date
    while day <= end_date:
        results.append({"date": day.isoformat(), "value": float(daily.get(day, 0.0))})
        day += timedelta(days=1)

    return results

# -----------------------------------------------------------------------------
# /spending-debug
# -----------------------------------------------------------------------------
@app.get("/spending-debug")
def spending_debug(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            t.merchant,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType,
            a.institution AS bank,
            a.name AS account
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT id, d, amount, merchant, category, accountType, bank, account
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        ORDER BY d DESC, id DESC
        """,
        (start_date, end_date),
    )

    out = []
    for r in rows:
        try:
            amt = float(r["amount"])
        except Exception:
            continue

        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer"):
            continue

        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            out.append(
                {
                    "date": r["d"].isoformat(),
                    "amount": amt,
                    "merchant": r["merchant"],
                    "category": r["category"],
                    "bank": r["bank"],
                    "account": r["account"],
                }
            )

    return out

# -----------------------------------------------------------------------------
# /category-totals-month
# -----------------------------------------------------------------------------
@app.get("/category-totals-month")
def category_totals_month():
    today = datetime.today().date()
    first = today.replace(day=1)
    next_month = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)

    unassigned = query_db(
        """
        SELECT COUNT(*)::int AS c
        FROM transactions
        WHERE category IS NULL OR TRIM(category) = ''
        """
    )[0]["c"]

    rows = query_db(
        """
        WITH base AS (
          SELECT
            TRIM(category) AS category,
            t.amount::double precision AS amount,
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE t.amount::double precision > 0
            AND t.category IS NOT NULL
            AND TRIM(t.category) <> ''
        ),
        norm AS (
          SELECT
            category,
            amount,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT category, SUM(amount) AS total, COUNT(*)::int AS tx_count
        FROM norm
        WHERE d IS NOT NULL AND d >= %s AND d < %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (first, next_month),
    )

    return {
        "unassigned_all_time": int(unassigned or 0),
        "categories": [
            {"category": r["category"], "total": float(r["total"] or 0), "tx_count": int(r["tx_count"] or 0)}
            for r in rows
        ],
    }

# -----------------------------------------------------------------------------
# /category-trend
# -----------------------------------------------------------------------------
@app.get("/category-trend")
def category_trend(category: str, period: str = "1m"):
    cat = (category or "").strip().lower()

    if cat == "unknown merchant":
        rows = query_db(
            """
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.merchant,''))) AS merchant,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                LOWER(a.accountType) AS accountType,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              JOIN accounts a ON a.id = t.account_id
              WHERE t.amount::double precision > 0
                AND LOWER(a.accountType) IN ('checking','credit')
            ),
            norm AS (
              SELECT
                amount,
                merchant,
                category,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT d, SUM(amount) AS total
            FROM norm
            WHERE d IS NOT NULL
              AND merchant = 'unknown'
              AND category NOT IN ('card payment','transfer')
            GROUP BY d
            ORDER BY d ASC
            """
        )
    else:
        rows = query_db(
            """
            WITH base AS (
              SELECT
                t.amount::double precision AS amount,
                LOWER(TRIM(COALESCE(t.category,''))) AS category,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
              FROM transactions t
              WHERE LOWER(TRIM(COALESCE(t.category,''))) = LOWER(TRIM(%s))
            ),
            norm AS (
              SELECT
                amount,
                CASE
                  WHEN raw_date IS NULL THEN NULL
                  WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                  WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                  ELSE NULL
                END AS d
              FROM base
            )
            SELECT d, SUM(amount) AS total
            FROM norm
            WHERE d IS NOT NULL
            GROUP BY d
            ORDER BY d ASC
            """,
            (category,),
        )

    daily = [{"date": r["d"].isoformat(), "amount": float(r["total"] or 0)} for r in rows if r.get("d")]
    return {"category": category, "period": period, "series": daily}

# -----------------------------------------------------------------------------
# /category-transactions
# -----------------------------------------------------------------------------
@app.get("/category-transactions")
def category_transactions(category: str, start: str, end: str, limit: int = 500):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.postedDate AS postedDate_raw,
            t.purchaseDate AS purchaseDate_raw,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS postedDate,
            t.merchant,
            t.amount::double precision AS amount,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          WHERE TRIM(t.category) = TRIM(%s)
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT DISTINCT
          id,
          postedDate,
          merchant,
          amount,
          category,
          bank,
          card,
          d AS "dateISO",
          postedDate_raw,
          purchaseDate_raw
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        ORDER BY d DESC, id DESC
        LIMIT %s
        """,
        (category, start_date, end_date, int(limit)),
    )
    return [dict(r) for r in rows]

# -----------------------------------------------------------------------------
# /category-totals-lifetime
# -----------------------------------------------------------------------------
@app.get("/category-totals-lifetime")
def category_totals_lifetime():
    rows = query_db(
        """
        SELECT
          TRIM(category) AS category,
          SUM(amount::double precision) AS total
        FROM transactions
        WHERE category IS NOT NULL
          AND TRIM(category) <> ''
          AND amount::double precision > 0
        GROUP BY TRIM(category)
        ORDER BY total DESC
        """
    )
    return [{"category": r["category"], "total": float(r["total"] or 0)} for r in rows]

# -----------------------------------------------------------------------------
# /category-totals-range
# -----------------------------------------------------------------------------
@app.get("/category-totals-range")
def category_totals_range(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = query_db(
        """
        WITH base AS (
          SELECT
            TRIM(t.category) AS category,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS cat_lc,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE t.amount::double precision > 0
            AND t.category IS NOT NULL
            AND TRIM(t.category) <> ''
            AND LOWER(TRIM(t.category)) NOT IN ('card payment','transfer')
        ),
        norm AS (
          SELECT
            category,
            amount,
            cat_lc,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT category, SUM(amount) AS total
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN %s AND %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (start_date, end_date),
    )

    return [{"category": r["category"], "total": float(r["total"] or 0)} for r in rows]

# =============================================================================
# Categories endpoints (Postgres) — ported from categories.py
# =============================================================================

def get_category_from_db_pg(tx_ids: List[int]) -> Optional[str]:
    """
    Postgres version of categories.py:get_category_from_db(tx_ids)
    Returns the first non-empty category found among tx_ids (or None).
    """
    if not tx_ids:
        return None

    # NOTE: use = ANY(%s) to pass a python list safely as a Postgres array
    rows = query_db(
        """
        SELECT category
        FROM transactions
        WHERE id = ANY(%s)
          AND category IS NOT NULL
          AND TRIM(category) <> ''
        LIMIT 1
        """,
        (tx_ids,),
    )
    return rows[0]["category"] if rows else None

@app.get("/categories")
def list_categories():
    """
    Union of:
      - distinct categories present in transactions
      - distinct categories present in CategoryRules
    """
    rows = query_db(
        """
        SELECT category FROM (
          SELECT DISTINCT TRIM(category) AS category
          FROM transactions
          WHERE category IS NOT NULL AND TRIM(category) <> ''

          UNION

          SELECT DISTINCT TRIM(category) AS category
          FROM "categoryrules"
          WHERE category IS NOT NULL AND TRIM(category) <> ''
        ) u
        ORDER BY LOWER(category) ASC
        """
    )
    return [r["category"] for r in rows]

# =============================================================================
# Category Rules (Postgres) — ported from category_rules.py
# =============================================================================

# -----------------------------
# Pydantic models (same API)
# -----------------------------
class RuleCreate(BaseModel):
    category: str
    keywords: List[str] = []
    regex: Optional[str] = None
    apply_now: bool = True

class RuleUpdate(BaseModel):
    category: str
    reapply_existing: bool = False

class RuleActiveUpdate(BaseModel):
    is_active: bool

class RuleTestBody(BaseModel):
    pattern: str
    flags: str = "i"
    limit: int = 50

# -----------------------------
# Helpers
# -----------------------------
def build_pattern_from_keywords(keywords: List[str]) -> str:
    kws = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if not kws:
        raise ValueError("Provide at least one keyword or a regex")

    # Escape each keyword then OR them together; allow flexible whitespace/dash matching
    parts = []
    for k in kws:
        esc = re.escape(k)
        esc = esc.replace(r"\ ", r"[\s\-]+")
        parts.append(esc)
    return "(" + "|".join(parts) + ")"

def _compile_rule(pattern: str, flags: str):
    # Only used for /test to show matched boolean in Python too.
    # For actual DB apply/count we use Postgres regex (~ / ~*).
    f = 0
    if flags and "i" in flags.lower():
        f |= re.IGNORECASE
    return re.compile(pattern, f)

def _pg_regex_operator(flags: str) -> str:
    # i => case-insensitive
    if flags and "i" in flags.lower():
        return "~*"
    return "~"

def _recent_merchants(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns merchants with counts from *recent-ish* transactions.
    Uses Postgres date parsing on your string dates (MM/DD/YY or MM/DD/YYYY).
    """
    limit = max(1, min(int(limit), 200))
    rows = query_db(
        """
        WITH base AS (
          SELECT
            TRIM(COALESCE(merchant,'')) AS merchant,
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date
          FROM transactions
          WHERE merchant IS NOT NULL AND TRIM(merchant) <> ''
        ),
        norm AS (
          SELECT
            merchant,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT merchant, COUNT(*)::int AS count
        FROM norm
        WHERE d IS NOT NULL AND d >= (CURRENT_DATE - INTERVAL '120 days')
        GROUP BY merchant
        ORDER BY COUNT(*) DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in rows]

def _rule_match_count(pattern: str, flags: str) -> int:
    op = _pg_regex_operator(flags)
    rows = query_db(
        f"""
        SELECT COUNT(*)::int AS n
        FROM transactions
        WHERE merchant IS NOT NULL
          AND TRIM(merchant) <> ''
          AND merchant {op} %s
        """,
        (pattern,),
    )
    return int(rows[0]["n"]) if rows else 0

def apply_rule_to_existing(category: str, pattern: str, flags: str) -> int:
    """
    Apply rule only to transactions with empty/NULL category.
    Returns rows updated.
    """
    op = _pg_regex_operator(flags)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            UPDATE transactions
            SET category = %s
            WHERE (category IS NULL OR TRIM(category) = '')
              AND merchant IS NOT NULL
              AND TRIM(merchant) <> ''
              AND merchant {op} %s
            """,
            (category, pattern),
        )
        updated = int(cur.rowcount or 0)
        conn.commit()
        return updated

def _apply_rule_override(category: str, pattern: str, flags: str) -> int:
    """
    Force override category for all matching transactions.
    Returns rows updated.
    """
    op = _pg_regex_operator(flags)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            UPDATE transactions
            SET category = %s
            WHERE merchant IS NOT NULL
              AND TRIM(merchant) <> ''
              AND merchant {op} %s
            """,
            (category, pattern),
        )
        updated = int(cur.rowcount or 0)
        conn.commit()
        return updated

# -----------------------------
# Endpoints
# -----------------------------
@app.post("/category-rules")
def create_category_rule(payload: RuleCreate):
    category = (payload.category or "").strip()
    if not category:
        return {"ok": False, "error": "Category is required"}

    if payload.regex and payload.regex.strip():
        pattern = payload.regex.strip()
    else:
        try:
            pattern = build_pattern_from_keywords(payload.keywords)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    flags = "i"  # default

    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                f"""
                INSERT INTO {CATEGORY_RULES_TABLE} (category, pattern, flags, is_active)
                VALUES (%s, %s, %s, TRUE)
                """,
                (category, pattern, flags),
            )
            applied = 0
            if payload.apply_now:
                conn.commit()  # commit rule insert before large update
                applied = apply_rule_to_existing(category, pattern, flags)
            else:
                conn.commit()
            return {"ok": True, "pattern": pattern, "applied": int(applied)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/category-rules/list")
def list_category_rules(include_inactive: int = 0, with_counts: int = 0):
    where = ""
    if not include_inactive:
        where = "WHERE COALESCE(is_active, TRUE) = TRUE"

    rows = query_db(
        f"""
        SELECT id, pattern, flags, category, COALESCE(is_active, TRUE) AS is_active
        FROM {CATEGORY_RULES_TABLE}
        {where}
        ORDER BY COALESCE(is_active, TRUE) DESC, id DESC
        """
    )

    rules = [dict(r) for r in rows]

    if with_counts:
        # Use Postgres regex for fast counts
        for r in rules:
            try:
                r["match_count"] = _rule_match_count(r["pattern"], r.get("flags") or "i")
            except Exception:
                r["match_count"] = 0
                r["regex_error"] = "Invalid regex"

    return rules

@app.post("/category-rules/{rule_id}")
def update_category_rule(rule_id: int, payload: RuleUpdate):
    category = (payload.category or "").strip()
    if not category:
        return {"ok": False, "error": "Category is required"}

    rows = query_db(
        f"""
        SELECT id, pattern, flags
        FROM {CATEGORY_RULES_TABLE}
        WHERE id = %s
        LIMIT 1
        """,
        (int(rule_id),),
    )
    if not rows:
        return {"ok": False, "error": "Rule not found"}

    pattern = rows[0]["pattern"]
    flags = rows[0].get("flags") or "i"

    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                f"UPDATE {CATEGORY_RULES_TABLE} SET category = %s WHERE id = %s",
                (category, int(rule_id)),
            )

            applied = 0
            if payload.reapply_existing:
                # override category on ALL matches
                conn.commit()  # commit rule edit first
                applied = _apply_rule_override(category, pattern, flags)
            else:
                conn.commit()

            # refresh match count (nice UX)
            try:
                match_count = _rule_match_count(pattern, flags)
            except Exception:
                match_count = 0

            return {"ok": True, "applied": int(applied), "match_count": int(match_count)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/category-rules/{rule_id}/active")
def set_rule_active(rule_id: int, payload: RuleActiveUpdate):
    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                f"UPDATE {CATEGORY_RULES_TABLE} SET is_active = %s WHERE id = %s",
                (bool(payload.is_active), int(rule_id)),
            )
            conn.commit()
            return {"ok": True, "id": int(rule_id), "is_active": bool(payload.is_active)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@app.delete("/category-rules/{rule_id}")
def delete_rule(rule_id: int):
    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(f"DELETE FROM {CATEGORY_RULES_TABLE} WHERE id = %s", (int(rule_id),))
            conn.commit()
            return {"ok": True, "deleted": int(rule_id)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/category-rules/test")
def test_rule(body: RuleTestBody):
    pattern = (body.pattern or "").strip()
    if not pattern:
        return {"ok": False, "error": "Pattern is required"}

    flags = (body.flags or "i").strip()

    # validate regex early (same behavior)
    try:
        rx = _compile_rule(pattern, flags)
    except Exception as e:
        return {"ok": False, "error": f"Invalid regex: {e}"}

    recent = _recent_merchants(limit=body.limit)

    tested = []
    for r in recent:
        merchant = r["merchant"]
        tested.append(
            {
                "merchant": merchant,
                "count": int(r["count"]),
                "matched": bool(rx.search(merchant or "")),
            }
        )

    return {"ok": True, "tested": tested}

# -----------------------------------------------------------------------------
# /unknown-merchant-total-month
# -----------------------------------------------------------------------------
@app.get("/unknown-merchant-total-month")
def unknown_merchant_total_month():
    today = datetime.today().date()
    first = today.replace(day=1)
    next_month = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)

    row = query_db(
        """
        WITH base AS (
          SELECT
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.merchant,''))) AS merchant,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            amount, merchant, category, accountType,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          COALESCE(SUM(amount), 0)::double precision AS total,
          COALESCE(COUNT(*), 0)::int AS tx_count
        FROM norm
        WHERE d IS NOT NULL
          AND d >= %s AND d < %s
          AND amount > 0
          AND accountType IN ('checking','credit')
          AND merchant = 'unknown'
          AND category NOT IN ('card payment','transfer')
        """,
        (first, next_month),
    )[0]

    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}

# -----------------------------------------------------------------------------
# /unknown-merchant-total-range
# -----------------------------------------------------------------------------
@app.get("/unknown-merchant-total-range")
def unknown_merchant_total_range(start: str, end: str):
    start_date = parse_iso(start)
    end_date = parse_iso(end)

    row = query_db(
        """
        WITH base AS (
          SELECT
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.merchant,''))) AS merchant,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            amount, merchant, category, accountType,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          COALESCE(SUM(amount), 0)::double precision AS total,
          COALESCE(COUNT(*), 0)::int AS tx_count
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
          AND amount > 0
          AND accountType IN ('checking','credit')
          AND merchant = 'unknown'
          AND category NOT IN ('card payment','transfer')
        """,
        (start_date, end_date),
    )[0]

    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}

# -----------------------------------------------------------------------------
# /month-budget
# NOTE: assumes recurring_calendar(...) exists in your app_postgres.py (same as sqlite version)
# -----------------------------------------------------------------------------

@app.get("/month-budget")
def month_budget(min_occ: int = 3, include_stale: bool = False):
    """
    Summary for the current month:
      - income_expected: projected income for the month (paychecks + interest)
      - spent_so_far: actual spending posted so far this month (excludes transfers/card payments)
      - bills_remaining: projected withdrawals remaining from today through month end
      - safe_to_spend: income_expected - spent_so_far - bills_remaining
    """
    today = date.today()
    year = today.year
    month = today.month

    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    # 1) Projected recurring events (withdrawals + income)
    cal = recurring_calendar(year=year, month=month, min_occ=min_occ, include_stale=include_stale)
    events = (cal or {}).get("events") or []

    spendable_account_id = 3  # keep your original assumption

    income_expected = 0.0
    bills_remaining = 0.0

    for e in events:
        d = str(e.get("date") or "")
        if not d:
            continue
        try:
            ed = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue

        if ed < month_start or ed > month_end:
            continue

        amt = float(e.get("amount") or 0.0)
        etype = str(e.get("type") or "").lower().strip()
        cadence = str(e.get("cadence") or "").lower().strip()
        category = str(e.get("category") or "").strip()
        merchant = str(e.get("merchant") or "")

        is_income = (etype == "income") or (cadence in ("paycheck", "interest"))

        if is_income:
            try:
                aid = int(e.get("account_id") or -1)
            except Exception:
                aid = -1
            if aid == spendable_account_id:
                income_expected += max(0.0, amt)
            continue

        if ed < today:
            continue

        if category.lower() == "transfer" or merchant.lower().startswith("from "):
            continue

        bills_remaining += abs(amt)

    # 2) Actual spending so far this month (same rules as /spending)
    tx_rows = query_db(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            LOWER(a.accountType) AS accountType
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT d, amount, category, accountType
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
        """,
        (month_start, today),
    )

    spent_so_far = 0.0
    for r in tx_rows:
        category = (r["category"] or "").strip().lower()
        if category in ("card payment", "transfer"):
            continue

        try:
            amt = float(r["amount"])
        except Exception:
            continue

        if (r["accounttype"] or "").lower() in ("checking", "credit") and amt > 0:
            spent_so_far += amt

    safe_to_spend = income_expected - spent_so_far - bills_remaining

    return {
        "ok": True,
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "as_of": today.isoformat(),
        "income_expected": round(income_expected, 2),
        "spent_so_far": round(spent_so_far, 2),
        "bills_remaining": round(bills_remaining, 2),
        "safe_to_spend": round(safe_to_spend, 2),
    }

# =============================================================================
# LES (Postgres)
# =============================================================================

from LESCalc import (
    LESInputs as _LESInputs,
    W4Settings as _W4Settings,
    get_base_pay as _get_base_pay,
    get_bah as _get_bah,
    generate_les_right_side as _gen_les,
)

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    weekday: 0=Mon..6=Sun
    n: 1..5
    """
    d = date(year, month, 1)
    # advance to first desired weekday
    while d.weekday() != weekday:
        d += timedelta(days=1)
    # then jump (n-1) weeks
    d += timedelta(days=7 * (n - 1))
    return d

def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    last_dom = calendar.monthrange(year, month)[1]
    d = date(year, month, last_dom)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d

def _observe_holiday(d: date) -> date:
    # If holiday lands Sat => observed Fri; Sun => observed Mon
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d

def _us_federal_holidays_observed(year: int) -> set[date]:
    """
    Minimal US federal observed holidays set, enough for your DFAS deposit logic.
    """
    hol = set()

    # New Year's Day (Jan 1)
    hol.add(_observe_holiday(date(year, 1, 1)))

    # MLK Day (3rd Mon in Jan)
    hol.add(_nth_weekday_of_month(year, 1, 0, 3))

    # Washington's Birthday / Presidents Day (3rd Mon in Feb)
    hol.add(_nth_weekday_of_month(year, 2, 0, 3))

    # Memorial Day (last Mon in May)
    hol.add(_last_weekday_of_month(year, 5, 0))

    # Juneteenth (Jun 19)
    hol.add(_observe_holiday(date(year, 6, 19)))

    # Independence Day (Jul 4)
    hol.add(_observe_holiday(date(year, 7, 4)))

    # Labor Day (1st Mon in Sep)
    hol.add(_nth_weekday_of_month(year, 9, 0, 1))

    # Columbus Day (2nd Mon in Oct)
    hol.add(_nth_weekday_of_month(year, 10, 0, 2))

    # Veterans Day (Nov 11)
    hol.add(_observe_holiday(date(year, 11, 11)))

    # Thanksgiving (4th Thu in Nov)
    hol.add(_nth_weekday_of_month(year, 11, 3, 4))

    # Christmas Day (Dec 25)
    hol.add(_observe_holiday(date(year, 12, 25)))

    return hol

def _previous_workday(d: date, holidays: set[date]) -> date:
    # roll back for weekend/holiday
    while d.weekday() >= 5 or d in holidays:
        d -= timedelta(days=1)
    return d

class LESProfileModel(BaseModel):
    paygrade: str
    service_start: str  # YYYY-MM-DD
    has_dependents: bool = False

    # entitlements
    bas: float = 465.77
    submarine_pay: float = 0.0
    career_sea_pay: float = 0.0
    spec_duty_pay: float = 0.0
    tsp_rate: float = 0.05
    bah_override: Optional[float] = None

    # meal deduction rule
    meal_rate: float = 13.30
    meal_end_day: int = 31
    meal_deduction_enabled: bool = False
    meal_deduction_start: Optional[str] = None  # YYYY-MM-DD

    # W-4
    filing_status: str = "S"  # S/M/H
    step2_multiple_jobs: bool = False
    dep_under17: int = 0
    other_dep: int = 0
    other_income_annual: float = 0.0
    other_deductions_annual: float = 0.0
    extra_withholding: float = 0.0

    # mid-month model inputs
    mid_month_fraction: float = 0.50
    allotments_total: float = 0.0
    mid_month_collections_total: float = 0.0

    fica_include_special_pays: bool = False

class LESPaychecksRequest(BaseModel):
    year: int
    month: int
    profile: LESProfileModel

@app.post("/les/paychecks")
def les_paychecks(req: LESPaychecksRequest):
    y, m = int(req.year), int(req.month)
    p = req.profile

    # as_of date: last day of the month being viewed
    last_dom = calendar.monthrange(y, m)[1]
    as_of = date(y, m, last_dom)

    # compute base pay from chart in LESCalc
    start_parts = [int(x) for x in p.service_start.split("-")]
    start_dt = date(start_parts[0], start_parts[1], start_parts[2])
    paygrade = p.paygrade.replace(" ", "").upper().replace("--", "-")
    base_pay = _get_base_pay(paygrade.replace("-", ""), start_dt, as_of)

    # compute BAH (table) unless overridden
    bah = float(p.bah_override) if p.bah_override is not None else _get_bah(paygrade.replace("-", ""), p.has_dependents)

    inp = _LESInputs(
        base_pay=base_pay,
        submarine_pay=p.submarine_pay,
        career_sea_pay=p.career_sea_pay,
        spec_duty_pay=p.spec_duty_pay,
        bas=p.bas,
        bah=bah,
    )

    w4 = _W4Settings(
        pay_periods_per_year=12,
        filing_status=p.filing_status,
        step2_multiple_jobs=p.step2_multiple_jobs,
        dep_under17=p.dep_under17,
        other_dep=p.other_dep,
        other_income_annual=p.other_income_annual,
        other_deductions_annual=p.other_deductions_annual,
        extra_withholding=p.extra_withholding,
    )

    # meal deduction: apply your rule via LESCalc.generate_les_right_side inputs
    les_kwargs = dict(
        tsp_rate=p.tsp_rate,
        fica_wages_include_special_pays=p.fica_include_special_pays,
        meal_rate_per_day=p.meal_rate,
        meal_year=y, meal_month=m, meal_end_day=p.meal_end_day,
        mid_month_fraction=p.mid_month_fraction,
        allotments_total=p.allotments_total,
        mid_month_collections_total=p.mid_month_collections_total,
    )

    allowed = set(inspect.signature(_gen_les).parameters.keys())
    les_kwargs = {k: v for k, v in les_kwargs.items() if k in allowed}
    out = _gen_les(inp, w4, **les_kwargs)

    # --- paycheck targets: 1st + 15th of this month, plus 1st of next month ---
    targets = [date(y, m, 1), date(y, m, 15)]
    if m == 12:
        targets.append(date(y + 1, 1, 1))
    else:
        targets.append(date(y, m + 1, 1))

    hol_this = _us_federal_holidays_observed(y)

    def deposit_for_target(target: date) -> date:
        hol = hol_this if target.year == y else _us_federal_holidays_observed(target.year)
        d = target - timedelta(days=1)  # day-before rule
        return _previous_workday(d, hol)  # weekend/holiday rollback

    def _month_bounds(year: int, month: int):
        last_dom_local = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_dom_local)

    def _get_actual_midmonth_deposit(cur, year: int, month: int) -> float | None:
        """
        If we've already received the DFAS mid-month pay for (year, month),
        return the *deposit amount* (positive float). Otherwise None.

        Assumes your DB stores income as NEGATIVE amounts (same as your sqlite version).
        """
        month_start, month_end = _month_bounds(year, month)
        target_dep = deposit_for_target(date(year, month, 15))

        # pull candidate DFAS income tx in this month
        cur.execute(
            """
            SELECT postedDate, purchaseDate, amount, merchant
            FROM transactions
            WHERE account_id = %s
              AND category = 'Income'
              AND UPPER(merchant) LIKE '%%DFAS%%'
            """,
            (3,),
        )
        rows = cur.fetchall() or []

        candidates = []
        for r in rows:
            posted = parse_posted_date(r.get("posteddate") or r.get("postedDate"))
            purchase = parse_posted_date(r.get("purchasedate") or r.get("purchaseDate"))
            tx_date = posted if posted is not None else purchase
            if tx_date is None:
                continue
            if not (month_start <= tx_date <= month_end):
                continue

            try:
                amt = float(r.get("amount"))
            except Exception:
                continue

            dep_amt = abs(amt)
            delta_days = abs((tx_date - target_dep).days)
            candidates.append((delta_days, tx_date, dep_amt))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[0], x[1]))
        best_delta, _, best_amt = candidates[0]
        if best_delta > 5:
            return None
        return float(best_amt)

    def _compute_les_out_for_month(year: int, month: int):
        last_dom_local = calendar.monthrange(year, month)[1]
        as_of_local = date(year, month, last_dom_local)

        base_pay_local = _get_base_pay(paygrade.replace("-", ""), start_dt, as_of_local)
        bah_local = float(p.bah_override) if p.bah_override is not None else _get_bah(paygrade.replace("-", ""), p.has_dependents)

        inp_local = _LESInputs(
            base_pay=base_pay_local,
            submarine_pay=p.submarine_pay,
            career_sea_pay=p.career_sea_pay,
            spec_duty_pay=p.spec_duty_pay,
            bas=p.bas,
            bah=bah_local,
        )

        # meal-deduction toggle/date should respect this month’s as_of date
        apply_meal_local = bool(getattr(p, "meal_deduction_enabled", False))
        start_iso_local = getattr(p, "meal_deduction_start", None)
        if apply_meal_local and start_iso_local:
            try:
                apply_meal_local = (as_of_local >= parse_iso(str(start_iso_local)))
            except Exception:
                apply_meal_local = False

        les_kwargs_local = dict(
            tsp_rate=p.tsp_rate,
            fica_wages_include_special_pays=p.fica_include_special_pays,

            meal_rate_per_day=p.meal_rate,
            meal_year=(year if apply_meal_local else None),
            meal_month=(month if apply_meal_local else None),
            meal_end_day=(p.meal_end_day if apply_meal_local else None),

            mid_month_fraction=p.mid_month_fraction,
            allotments_total=p.allotments_total,
            mid_month_collections_total=p.mid_month_collections_total,
        )

        allowed_local = set(inspect.signature(_gen_les).parameters.keys())
        les_kwargs_local = {k: v for k, v in les_kwargs_local.items() if k in allowed_local}

        return _gen_les(inp_local, w4, **les_kwargs_local)

    # ---- Detect actual mid-month pay for the viewed month and adjust EOM ----
    with with_db_cursor() as (conn2, cur2):
        actual_mid = _get_actual_midmonth_deposit(cur2, y, m)

    projected_monthly_net = float(out.mid_month_pay) + float(out.eom)
    mid_month_display = float(actual_mid) if actual_mid is not None else float(out.mid_month_pay)
    eom_display = (projected_monthly_net - mid_month_display) if actual_mid is not None else float(out.eom)

    # ---- Also compute the "1st of month" paycheck as PREVIOUS month’s EOM ----
    prev_year, prev_month = (y - 1, 12) if m == 1 else (y, m - 1)
    out_prev = _compute_les_out_for_month(prev_year, prev_month)
    projected_prev_net = float(out_prev.mid_month_pay) + float(out_prev.eom)

    with with_db_cursor() as (conn3, cur3):
        prev_actual_mid = _get_actual_midmonth_deposit(cur3, prev_year, prev_month)

    prev_mid_display = float(prev_actual_mid) if prev_actual_mid is not None else float(out_prev.mid_month_pay)
    prev_eom_display = (projected_prev_net - prev_mid_display) if prev_actual_mid is not None else float(out_prev.eom)

    events = []
    for target in targets:
        dep = deposit_for_target(target)

        include = ((target.year == y and target.month == m) or (dep.year == y and dep.month == m))
        if not include:
            continue

        # only emit events that land in the viewed month
        if not (dep.year == y and dep.month == m):
            continue

        # Map targets to the correct month:
        if target.year == y and target.month == m and target.day == 1:
            amt = prev_eom_display
            label = "MIL PAY (EOM)"
        elif target.year == y and target.month == m and target.day == 15:
            amt = mid_month_display
            label = "MIL PAY (Mid-Month)"
        else:
            amt = eom_display
            label = "MIL PAY (EOM)"

        events.append({
            "date": dep.isoformat(),
            "pay_target": target.isoformat(),
            "cadence": "paycheck",
            "merchant": label,
            "amount": round(float(amt), 2),
            "type": "Income",
            "account_id": 3,
            "spillover": not (dep.year == y and dep.month == m),
        })

    breakdown = {
        "as_of": as_of.isoformat(),
        "profile": {
            "paygrade": paygrade.replace("-", ""),
            "service_start": p.service_start,
            "has_dependents": bool(p.has_dependents),
        },
        "entitlements": {
            "base_pay": round(float(base_pay), 2),
            "bah": round(float(bah), 2),
            "bas": round(float(p.bas), 2),
            "submarine_pay": round(float(p.submarine_pay), 2),
            "career_sea_pay": round(float(p.career_sea_pay), 2),
            "spec_duty_pay": round(float(p.spec_duty_pay), 2),
        },
        "w4": {
            "filing_status": p.filing_status,
            "step2_multiple_jobs": bool(p.step2_multiple_jobs),
            "dep_under17": int(p.dep_under17),
            "other_dep": int(p.other_dep),
            "other_income_annual": round(float(p.other_income_annual), 2),
            "other_deductions_annual": round(float(p.other_deductions_annual), 2),
            "extra_withholding": round(float(p.extra_withholding), 2),
        },
        "rates": {
            "tsp_rate": float(p.tsp_rate),
            "meal_rate": float(p.meal_rate),
            "meal_end_day": int(p.meal_end_day),
            "mid_month_fraction": float(p.mid_month_fraction),
        },
        "deductions": {
            "federal_taxes": round(float(out.federal_taxes), 2),
            "fica_social_security": round(float(out.fica_social_security), 2),
            "fica_medicare": round(float(out.fica_medicare), 2),
            "sgli": round(float(out.sgli), 2),
            "afrh": round(float(out.afrh), 2),
            "roth_tsp": round(float(out.roth_tsp), 2),
            "meal_deduction": round(float(out.meal_deduction), 2),
            "allotments_total": round(float(p.allotments_total), 2),
            "mid_month_collections_total": round(float(p.mid_month_collections_total), 2),
        },
        "net": {
    # model (projected)
    "projected_mid_month": round(float(out.mid_month_pay), 2),
    "projected_eom": round(float(out.eom), 2),
    "projected_monthly_net": round(float(projected_monthly_net), 2),

    # display (what the UI should show)
    "mid_month_pay": round(float(mid_month_display), 2),
    "eom": round(float(eom_display), 2),

    # helpful flags for the UI logic
    "mid_month_is_actual": bool(actual_mid is not None),
    "mid_month_actual": round(float(actual_mid), 2) if actual_mid is not None else None,
},

    }

    return {"events": events, "breakdown": breakdown}

# =============================================================================
# LES Profile (les_profile)
# =============================================================================

@app.get("/les-profile")
def get_les_profile(key: str = "default"):
    _ensure_les_profile_table_pg()

    rows = query_db(
        "SELECT profile_json FROM les_profile WHERE key = %s LIMIT 1",
        (key,),
    )
    if not rows:
        return {"key": key, "profile": {}}

    try:
        profile = json.loads(rows[0]["profile_json"] or "{}")
    except Exception:
        profile = {}

    return {"key": key, "profile": profile}

class SaveLESProfileBody(BaseModel):
    key: str = "default"
    profile: Dict[str, Any]

@app.post("/les-profile")
def save_les_profile(body: SaveLESProfileBody):
    _ensure_les_profile_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO les_profile(key, profile_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET profile_json = EXCLUDED.profile_json,
                          updated_at = now()
            """,
            (body.key, json.dumps(body.profile)),
        )
        conn.commit()

    return {"key": body.key, "profile": body.profile}

# =============================================================================
# Notifications (Postgres) — ported from notifications.py
# Table: notifications   (per your DB screenshot)
# =============================================================================

def ensure_notifications_table_pg():
    """
    Safe guard (optional). Keeps schema close to sqlite version but Postgres-native.
    Uses LOWERCASE table name: notifications.
    """
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                subject TEXT,
                sender TEXT,
                body TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                dismissed BOOLEAN NOT NULL DEFAULT FALSE
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_dismissed ON notifications(dismissed)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)")
        conn.commit()

class NotificationPush(BaseModel):
    kind: str = "credit_usage"
    dedupe_key: str
    subject: str
    sender: str = "System"
    body: str = ""

def _to_local_display_pg(ts: Optional[object]) -> str:
    """
    Input is a TIMESTAMPTZ coming back as a python datetime (usually tz-aware).
    Return the same style string your sqlite version used: 'Wed 01/24/2026 09:41 PM'.
    """
    try:
        if ts is None:
            return ""
        if isinstance(ts, str):
            # fallback: parse ISO-ish
            dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt_utc = ts  # likely datetime
        dt_local = dt_utc.astimezone()
        return dt_local.strftime("%a %m/%d/%Y %I:%M %p")
    except Exception:
        try:
            return str(ts)
        except Exception:
            return ""

@app.post("/notifications/push")
def push_notification(payload: NotificationPush):
    ensure_notifications_table_pg()

    with with_db_cursor() as (conn, cur):
        try:
            cur.execute(
                """
                INSERT INTO notifications (kind, dedupe_key, subject, sender, body, is_read, dismissed)
                VALUES (%s, %s, %s, %s, %s, FALSE, FALSE)
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                (payload.kind, payload.dedupe_key, payload.subject, payload.sender, payload.body),
            )
            created = (cur.rowcount or 0) > 0
            conn.commit()
            return {"ok": True, "created": bool(created)}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/notifications")
def list_notifications(limit: int = 200):
    ensure_notifications_table_pg()

    rows = query_db(
        """
        SELECT id, subject, sender, created_at, is_read
        FROM notifications
        WHERE dismissed = FALSE
        ORDER BY is_read ASC, id DESC
        LIMIT %s
        """,
        (int(limit),),
    )

    items = []
    for r in rows:
        items.append(
            {
                "id": int(r["id"]),
                "subject": r.get("subject"),
                "sender": r.get("sender"),
                "created_at": (r["created_at"].isoformat() if r.get("created_at") else None),
                "created_at_local": _to_local_display_pg(r.get("created_at")),
                "is_read": bool(r.get("is_read")),
            }
        )

    return {"items": items}

@app.get("/notifications/unread-count")
def unread_count():
    ensure_notifications_table_pg()

    rows = query_db(
        """
        SELECT COUNT(*)::int AS n
        FROM notifications
        WHERE dismissed = FALSE AND is_read = FALSE
        """
    )
    return {"unread": int(rows[0]["n"]) if rows else 0}

@app.get("/notifications/{notif_id}")
def get_notification(notif_id: int):
    ensure_notifications_table_pg()

    rows = query_db(
        """
        SELECT id, subject, sender, body, created_at, is_read, dismissed
        FROM notifications
        WHERE id = %s
        LIMIT 1
        """,
        (int(notif_id),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Notification not found")

    r = rows[0]
    return {
        "id": int(r["id"]),
        "subject": r.get("subject"),
        "sender": r.get("sender"),
        "body": r.get("body") or "",
        "created_at": (r["created_at"].isoformat() if r.get("created_at") else None),
        "created_at_local": _to_local_display_pg(r.get("created_at")),
        "is_read": bool(r.get("is_read")),
        "dismissed": bool(r.get("dismissed")),
    }

@app.post("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int):
    ensure_notifications_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (int(notif_id),))
        conn.commit()
    return {"ok": True}

@app.post("/notifications/{notif_id}/dismiss")
def dismiss_notification(notif_id: int):
    ensure_notifications_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET dismissed = TRUE WHERE id = %s", (int(notif_id),))
        conn.commit()
    return {"ok": True}

@app.post("/notifications/mark-all-read")
def mark_all_notifications_read():
    ensure_notifications_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute("UPDATE notifications SET is_read = TRUE WHERE dismissed = FALSE")
        conn.commit()
    return {"ok": True}

@app.post("/notifications/clear-read")
def clear_read_notifications():
    ensure_notifications_table_pg()

    with with_db_cursor() as (conn, cur):
        # Dismiss anything already read
        cur.execute("UPDATE notifications SET dismissed = TRUE WHERE dismissed = FALSE AND is_read = TRUE")
        conn.commit()
    return {"ok": True}

# =============================================================================
# Recurring (Postgres) — ported from recurring.py
# =============================================================================

# -----------------------------
# Transfer peer helpers (Postgres)
# -----------------------------
def _account_label_pg(account_id: int) -> str:
    rows = query_db(
        "SELECT institution, name FROM accounts WHERE id = %s LIMIT 1",
        (int(account_id),),
    )
    if not rows:
        return f"Account {account_id}"
    r = rows[0]
    return f'{r["institution"]} {r["name"]}'.strip()

def _find_transfer_peer_account_pg(tx_id: int, window_days: int = 10) -> int | None:
    """
    Given a transfer tx_id, find the 'other side' transfer account within +/- window_days
    matching opposite sign and same abs(amount) cents, different account_id.
    """
    # 1) load the anchor tx (normalized date)
    anchor = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.account_id::int AS account_id,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE t.id = %s
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT id, account_id, amount, category, d
        FROM norm
        LIMIT 1
        """,
        (int(tx_id),),
    )
    if not anchor:
        return None

    a = anchor[0]
    if not a.get("d"):
        return None

    try:
        amt = float(a["amount"] or 0.0)
    except Exception:
        return None
    if amt == 0:
        return None

    aid = int(a["account_id"])
    d0: date = a["d"]
    cents = int(round(abs(amt) * 100))
    sign = 1 if amt > 0 else -1

    d_min = d0 - timedelta(days=int(window_days))
    d_max = d0 + timedelta(days=int(window_days))

    # 2) find the best opposite-sign peer in window
    peer = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.account_id::int AS account_id,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE LOWER(TRIM(COALESCE(t.category,''))) IN ('transfer','card payment')
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT account_id, d, amount
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND %s
          AND account_id <> %s
          AND (round(abs(amount) * 100))::int = %s
          AND (
            (%s =  1 AND amount < 0) OR
            (%s = -1 AND amount > 0)
          )
        ORDER BY ABS(d - %s) ASC, id DESC
        LIMIT 1
        """,
        (d_min, d_max, aid, cents, sign, sign, d0),
    )
    if not peer:
        return None
    return int(peer[0]["account_id"])

# =============================================================================
# Recurring + category + interest helpers (Postgres ports)
# =============================================================================

# =============================================================================
# Interest rate helpers (Postgres)
# =============================================================================

def _get_rate_rows(cur, account_id: int) -> List[Tuple[date, float]]:
    """
    Postgres version:
      - reads effective-dated APR rows from interest_rates
      - returns sorted list[(effective_date: date, apr: float)]
    """
    cur.execute(
        """
        SELECT effective_date, apr
        FROM interest_rates
        WHERE account_id = %s
        ORDER BY effective_date ASC
        """,
        (int(account_id),),
    )
    rows = cur.fetchall() or []

    out: List[Tuple[date, float]] = []
    for r in rows:
        try:
            eff = r["effective_date"]
            # psycopg2 typically returns date for DATE columns
            if isinstance(eff, date):
                eff_d = eff
            else:
                eff_d = datetime.strptime(str(eff), "%Y-%m-%d").date()
            out.append((eff_d, float(r["apr"])))
        except Exception:
            pass
    return out

def _interest_cycle_window(year: int, month: int, post_day: int | None):
    """
    Postgres version (DB-agnostic logic).

    Returns (start_date, end_date_exclusive, post_date) for the interest accrual period
    that pays on post_day in (year, month).

    Example: post_day=18 in Jan => cycle is Dec 19 .. Jan 18 (inclusive)
    """
    # Use your Postgres version if you added it; otherwise keep your old name.
    try:
        post_date = _interest_post_date(year, month, post_day)
    except NameError:
        post_date = _interest_post_date(year, month, post_day)

    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1

    try:
        prev_post = _interest_post_date(py, pm, post_day)
    except NameError:
        prev_post = _interest_post_date(py, pm, post_day)

    start = prev_post + timedelta(days=1)
    end_excl = post_date + timedelta(days=1)
    return start, end_excl, post_date

def _apr_for_day(rate_rows: List[Tuple[date, float]], d: date) -> float:
    """
    rate_rows sorted asc by effective_date; returns the latest apr whose eff<=d.
    """
    apr = 0.0
    for eff, r in rate_rows:
        if eff <= d:
            apr = float(r)
        else:
            break
    return float(apr)

def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _last_day_of_month(y, m))
    return date(y, m, day)

def _project_occurrences_for_month(last_seen: date, cadence: str, anchor_day: int, month_start: date, month_end: date):
    """
    Returns list[date] of projected occurrences within [month_start, month_end]
    using cadence + anchor_day (day-of-month from last_seen for month-based cadences).
    """
    out = []
    cadence = (cadence or "").lower().strip()

    if cadence in ("weekly", "biweekly"):
        step = 7 if cadence == "weekly" else 14

        d = last_seen + timedelta(days=step)  # don't re-include last_seen itself
        while d < month_start:
            d += timedelta(days=step)

        while d <= month_end:
            out.append(d)
            d += timedelta(days=step)

        return out

    if cadence in ("monthly", "quarterly", "yearly"):
        step_months = {"monthly": 1, "quarterly": 3, "yearly": 12}[cadence]

        base = last_seen
        base_anchor = base.replace(day=min(anchor_day, _last_day_of_month(base.year, base.month)))
        cursor = _add_months(base_anchor, step_months)

        while cursor < month_start:
            cursor = _add_months(cursor, step_months)

        while cursor <= month_end:
            out.append(cursor)
            cursor = _add_months(cursor, step_months)

        return out

    return out

def get_category_from_db(tx_ids):
    """
    Postgres replacement for sqlite get_category_from_db(tx_ids).
    Returns the first non-empty category among those tx ids (or None).
    """
    if not tx_ids:
        return None

    rows = query_db(
        """
        SELECT category
        FROM transactions
        WHERE id = ANY(%s)
          AND category IS NOT NULL
          AND TRIM(category) <> ''
        LIMIT 1
        """,
        (list(map(int, tx_ids)),),
    )
    return rows[0]["category"] if rows else None

def _estimate_interest_for_account_month(cur, account_id: int, year: int, month: int) -> float:
    """
    Postgres port of your sqlite _estimate_interest_for_account_month.

    End-of-day balance convention:
      - apply that day's transactions to balance
      - then accrue interest for that day on resulting balance

    Depends on your existing helpers (same as sqlite version):
      - _interest_cycle_window(year, month, post_day) -> (month_start, month_end, post_date)
      - _get_rate_rows(cur, account_id)
      - _apr_for_day(rate_rows, d)
    """
    # interest_post_day
    cur.execute("SELECT interest_post_day FROM accounts WHERE id = %s", (int(account_id),))
    row = cur.fetchone()
    post_day = row["interest_post_day"] if row else None

    month_start, month_end, _post_date = _interest_cycle_window(year, month, post_day)

    # only checking/savings
    cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = %s", (int(account_id),))
    row = cur.fetchone()
    acc_type = (row["t"] if row else "other") or "other"
    if acc_type not in ("checking", "savings"):
        return 0.0

    rate_rows = _get_rate_rows(cur, account_id)
    if not rate_rows:
        return 0.0

    # starting balance (Postgres table name: startingbalance)
    # Column name might be start or start depending on how pgloader created it.
    # If you get a column error here, change start -> start.
    cur.execute(
        """
        SELECT COALESCE(SUM(start), 0)::double precision AS s
        FROM startingbalance
        WHERE account_id = %s
        """,
        (int(account_id),),
    )
    row = cur.fetchone()
    start_bal = float((row["s"] if row else 0.0) or 0.0)

    # Sum of amounts BEFORE month_start using effective date logic (posted else purchase)
    cur.execute(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
            amount::double precision AS amount
          FROM transactions
          WHERE account_id = %s
        ),
        norm AS (
          SELECT
            amount,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT COALESCE(SUM(amount), 0)::double precision AS s
        FROM norm
        WHERE d IS NOT NULL AND d < %s
        """,
        (int(account_id), month_start),
    )
    row = cur.fetchone()
    before_sum = float((row["s"] if row else 0.0) or 0.0)

    # balance convention: bal -= amount
    bal = start_bal - before_sum

    # daily net within [month_start, month_end) (same half-open as your sqlite loop)
    cur.execute(
        """
        WITH base AS (
          SELECT
            COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
            amount::double precision AS amount
          FROM transactions
          WHERE account_id = %s
        ),
        norm AS (
          SELECT
            amount,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT d, COALESCE(SUM(amount), 0)::double precision AS net
        FROM norm
        WHERE d IS NOT NULL
          AND d >= %s
          AND d < %s
        GROUP BY d
        ORDER BY d ASC
        """,
        (int(account_id), month_start, month_end),
    )
    rows = cur.fetchall() or []
    net_by_day = {r["d"]: float(r["net"] or 0.0) for r in rows if r.get("d") is not None}

    total_interest = 0.0
    d = month_start
    while d < month_end:
        net = net_by_day.get(d, 0.0)
        bal = bal - net

        apr = _apr_for_day(rate_rows, d)
        daily_rate = apr / 365.0
        total_interest += (bal * daily_rate)

        d += timedelta(days=1)

    return float(total_interest)

def _interest_post_date(year: int, month: int, post_day: int | None) -> date:
    """
    Same logic as sqlite version, DB-agnostic.
    """
    last_day = calendar.monthrange(year, month)[1]
    if post_day is None:
        return date(year, month, last_day)
    day = min(int(post_day), last_day)
    return date(year, month, day)

# -----------------------------
# Endpoints
# -----------------------------
@app.get("/recurring")
def recurring(min_occ: int = 3, include_stale: bool = False):
    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    # decorate transfer patterns with "From A to B"
    for g in (groups or []):
        for p in (g.get("patterns") or []):
            tx = p.get("tx") or []
            if not tx:
                continue

            cats = {(t.get("category") or "").strip().lower() for t in tx}
            if cats != {"transfer"}:
                continue

            # representative tx
            try:
                rep = tx[-1]
                tx_id = int(rep.get("id"))
            except Exception:
                continue

            peer_aid = _find_transfer_peer_account_pg(tx_id, window_days=10)
            if not peer_aid:
                continue

            try:
                amt = float(rep.get("amount") or 0.0)
            except Exception:
                amt = 0.0

            a_from = _account_label_pg(int(rep.get("account_id") or 0))
            a_to = _account_label_pg(int(peer_aid))

            label = f"From {a_from} to {a_to}" if amt > 0 else f"From {a_to} to {a_from}"
            p["merchant_display"] = label

        labels = [pp.get("merchant_display") for pp in (g.get("patterns") or []) if pp.get("merchant_display")]
        if labels and len(labels) == len(g.get("patterns") or []):
            g["merchant_display"] = labels[0]

    return groups

@app.get("/recurring/ignore")
def get_recurring_ignores():
    merchants_rows = query_db("SELECT merchant FROM recurring_ignore_merchants ORDER BY merchant ASC")
    categories_rows = query_db("SELECT category FROM recurring_ignore_categories ORDER BY category ASC")
    merchants = [r["merchant"] for r in merchants_rows]
    categories = [r["category"] for r in categories_rows]
    return {"merchants": merchants, "categories": categories}

@app.post("/recurring/ignore/merchant")
def ignore_merchant(name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_ignore_merchants (merchant)
            VALUES (%s)
            ON CONFLICT DO NOTHING
            """,
            (name.upper(),),
        )
        conn.commit()
    return {"ok": True}

@app.post("/recurring/ignore/category")
def ignore_category(name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_ignore_categories (category)
            VALUES (%s)
            ON CONFLICT DO NOTHING
            """,
            (name.upper(),),
        )
        conn.commit()
    return {"ok": True}

@app.post("/recurring/ignore/pattern")
def ignore_pattern(merchant: str, amount: float, account_id: int = -1):
    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_ignore_patterns (merchant_norm, amount_bucket, sign, account_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (m_norm, bucket, sign, int(account_id)),
        )
        conn.commit()
    return {"ok": True}

@app.post("/recurring/override-cadence")
def override_cadence(merchant: str, amount: float, cadence: str, account_id: int = -1):
    cadence = (cadence or "").strip().lower()
    allowed = {"weekly", "biweekly", "monthly", "quarterly", "yearly", "irregular"}
    if cadence not in allowed:
        return {"ok": False, "error": f"cadence must be one of {sorted(allowed)}"}

    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO recurring_cadence_overrides
              (merchant_norm, amount_bucket, sign, account_id, cadence)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (merchant_norm, amount_bucket, sign, account_id)
            DO UPDATE SET cadence = EXCLUDED.cadence
            """,
            (m_norm, bucket, sign, int(account_id), cadence),
        )
        conn.commit()
    return {"ok": True}

@app.post("/recurring/merchant-alias")
def set_merchant_alias(alias: str, canonical: str):
    a = _norm_merchant(alias).upper()
    c = _norm_merchant(canonical).upper()
    if not a or not c:
        return {"ok": False, "error": "alias and canonical required"}

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO merchant_aliases (alias, canonical)
            VALUES (%s, %s)
            ON CONFLICT (alias) DO UPDATE SET canonical = EXCLUDED.canonical
            """,
            (a, c),
        )
        conn.commit()
    return {"ok": True}

@app.post("/recurring/merchant-alias/delete")
def delete_merchant_alias(alias: str):
    a = _norm_merchant(alias).upper()
    with with_db_cursor() as (conn, cur):
        cur.execute("DELETE FROM merchant_aliases WHERE alias = %s", (a,))
        conn.commit()
    return {"ok": True}

@app.post("/recurring/unignore/merchant")
def unignore_merchant(name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute("DELETE FROM recurring_ignore_merchants WHERE merchant = %s", (name.upper(),))
        conn.commit()
    return {"ok": True}

@app.get("/recurring/ignored-preview")
def recurring_ignored_preview(min_occ: int = 3, include_stale: bool = False):
    return get_ignored_merchants_preview(min_occ=min_occ, include_stale=include_stale)

@app.get("/recurring/calendar")
def recurring_calendar(year: int, month: int, min_occ: int = 3, include_stale: bool = False):
    """
    Returns projected recurring WITHDRAWALS for a given month.
    - uses get_recurring() output
    - excludes kind == "paycheck"
    """
    if month < 1 or month > 12:
        return {"ok": False, "error": "month must be 1..12"}

    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    events = []
    for g in (groups or []):
        # Skip paycheck-like groups
        if any((p.get("kind") or "").lower() == "paycheck" for p in (g.get("patterns") or [])):
            continue

        merchant = g.get("merchant") or ""

        for p in (g.get("patterns") or []):
            if (p.get("kind") or "").lower() == "paycheck":
                continue

            cadence = (p.get("cadence") or "").lower().strip()
            if cadence in ("unknown", "irregular", ""):
                continue

            last_seen_iso = p.get("last_seen")
            if not last_seen_iso:
                continue

            try:
                last_seen_d = datetime.strptime(last_seen_iso, "%Y-%m-%d").date()
            except Exception:
                continue

            anchor_day = last_seen_d.day

            occs = _project_occurrences_for_month(
                last_seen=last_seen_d,
                cadence=cadence,
                anchor_day=anchor_day,
                month_start=month_start,
                month_end=month_end,
            )

            merch_label = merchant
            tx_list = p.get("tx") or []

            def to_int_id(v):
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.isdigit():
                    return int(v)
                return None

            tx_ids = [t["id"] for t in tx_list if isinstance(t.get("id"), str)]

            # use your PG version if present; fall back to existing name if you kept it
            try:
                cat_label = get_category_from_db_pg(tx_ids)  # preferred in app_postgres
            except NameError:
                cat_label = get_category_from_db(tx_ids)     # if you kept old helper name

            amt = float(p.get("amount") or 0.0)
            aid = int(p.get("account_id") or -1)
            for d in occs:
                events.append({
                    "date": d.isoformat(),
                    "merchant": merch_label,
                    "merchant_display": merch_label,
                    "category": cat_label,
                    "amount": amt,
                    "cadence": cadence,
                    "account_id": aid,
                })

    # ---- INTEREST EVENTS (estimated) ----
    # Uses your existing helpers: _estimate_interest_for_account_month, _interest_post_date
    acct_rows = query_db(
        """
        SELECT id, institution, name, LOWER(accountType) AS accounttype, interest_post_day
        FROM accounts
        WHERE LOWER(accountType) IN ('checking', 'savings')
        """
    )

    with with_db_cursor() as (conn, cur):
        for a in acct_rows:
            aid = int(a["id"])
            est = _estimate_interest_for_account_month(cur, aid, year, month)

            if abs(est) < 0.01:
                continue

            post_date = _interest_post_date(year, month, a["interest_post_day"])

            events.append({
                "date": post_date.isoformat(),
                "merchant": f'INTEREST — {a["institution"]} {a["name"]}',
                "amount": round(est, 2),
                "cadence": "interest",
                "type": "Interest",
                "account_id": aid,
            })

    events.sort(key=lambda e: (e["date"], e["merchant"], abs(e["amount"])))
    return {
        "ok": True,
        "year": year,
        "month": month,
        "start": month_start.isoformat(),
        "end": month_end.isoformat(),
        "events": events,
    }

# =============================================================================
# Settings (Postgres) — ported from settings.py
# =============================================================================

# -----------------------------
# Models (same API)
# -----------------------------
class RateUpsert(BaseModel):
    account_id: int
    rate_percent: float  # user enters 3.54 (percent)
    effective_date: Optional[str] = None  # "YYYY-MM-DD" (optional)
    note: Optional[str] = None

class SaveLayoutBody(BaseModel):
    key: str
    layout: Dict[str, Any]

class SaveLESProfileBody(BaseModel):
    key: str = "default"
    profile: Dict[str, Any]

class SavingsGoalIn(BaseModel):
    mode: str  # "percent" | "amount"
    value: float

# -----------------------------
# Table ensure helpers (Postgres)
# -----------------------------
def _ensure_app_settings_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()

def _ensure_ui_layout_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_layout (
              key TEXT PRIMARY KEY,
              layout_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()

def _ensure_les_profile_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS les_profile (
              key TEXT PRIMARY KEY,
              profile_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()

def _ensure_interest_rates_table_pg():
    # Your DB screenshot shows interest_rates exists, but this makes it robust.
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS interest_rates (
              id SERIAL PRIMARY KEY,
              account_id INT NOT NULL,
              apr DOUBLE PRECISION NOT NULL,
              effective_date DATE NOT NULL,
              note TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        # helpful uniqueness to prevent dupes per account/day
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname='public'
                  AND indexname='ux_interest_rates_account_day'
              ) THEN
                CREATE UNIQUE INDEX ux_interest_rates_account_day
                  ON interest_rates(account_id, effective_date);
              END IF;
            END $$;
            """
        )
        conn.commit()

# =============================================================================
# Savings Goal (app_settings)
# =============================================================================
@app.get("/settings/savings-goal")
def get_savings_goal():
    _ensure_app_settings_pg()

    rows = query_db(
        "SELECT value_json FROM app_settings WHERE key = %s LIMIT 1",
        ("savings_goal",),
    )
    if not rows:
        return {"mode": "percent", "value": 0}

    try:
        j = json.loads(rows[0]["value_json"] or "{}")
    except Exception:
        j = {}

    mode = j.get("mode", "percent")
    value = float(j.get("value", 0) or 0)

    if mode not in ("percent", "amount"):
        mode = "percent"
    if value < 0:
        value = 0
    if mode == "percent" and value > 100:
        value = 100

    return {"mode": mode, "value": value}

@app.post("/settings/savings-goal")
def set_savings_goal(body: SavingsGoalIn):
    mode = body.mode if body.mode in ("percent", "amount") else None
    if mode is None:
        raise HTTPException(status_code=422, detail="mode must be 'percent' or 'amount'")

    value = float(body.value)
    if value < 0:
        raise HTTPException(status_code=422, detail="value must be >= 0")
    if mode == "percent" and value > 100:
        raise HTTPException(status_code=422, detail="percent must be <= 100")

    payload = json.dumps({"mode": mode, "value": value})

    _ensure_app_settings_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO app_settings(key, value_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET value_json = EXCLUDED.value_json,
                          updated_at = now()
            """,
            ("savings_goal", payload),
        )
        conn.commit()

    return {"ok": True}

# =============================================================================
# UI Layout (ui_layout)
# =============================================================================

@app.get("/ui-layout")
def get_ui_layout(key: str):
    _ensure_ui_layout_table_pg()

    rows = query_db(
        "SELECT layout_json FROM ui_layout WHERE key = %s LIMIT 1",
        (key,),
    )
    if not rows:
        return {"key": key, "layout": {}}

    try:
        layout = json.loads(rows[0]["layout_json"] or "{}")
    except Exception:
        layout = {}

    return {"key": key, "layout": layout}

@app.post("/ui-layout")
def save_ui_layout(body: SaveLayoutBody):
    _ensure_ui_layout_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO ui_layout(key, layout_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET layout_json = EXCLUDED.layout_json,
                          updated_at = now()
            """,
            (body.key, json.dumps(body.layout)),
        )
        conn.commit()

    return {"key": body.key, "layout": body.layout}

# =============================================================================
# Interest Rates (interest_rates)
# =============================================================================

@app.post("/interest-rate")
def set_interest_rate(payload: RateUpsert):
    try:
        rate_percent = float(payload.rate_percent)
    except Exception:
        return {"ok": False, "error": "rate_percent must be a number"}

    if rate_percent < 0 or rate_percent > 100:
        return {"ok": False, "error": "rate_percent must be between 0 and 100"}

    eff = (payload.effective_date or "").strip() or datetime.now().strftime("%Y-%m-%d")
    rate_decimal = rate_percent / 100.0

    _ensure_interest_rates_table_pg()

    with with_db_cursor() as (conn, cur):
        # Upsert on (account_id, effective_date)
        cur.execute(
            """
            INSERT INTO interest_rates (account_id, apr, effective_date, note, created_at)
            VALUES (%s, %s, %s::date, %s, now())
            ON CONFLICT (account_id, effective_date)
            DO UPDATE SET apr = EXCLUDED.apr,
                          note = EXCLUDED.note
            """,
            (
                int(payload.account_id),
                float(rate_decimal),
                eff,
                (payload.note or "").strip() or None,
            ),
        )
        conn.commit()

    return {
        "ok": True,
        "account_id": int(payload.account_id),
        "effective_date": eff,
        "rate_percent": rate_percent,
    }

# =============================================================================
# Transactions (Postgres) — ported from transactions.py
# Tables used (per your screenshot): transactions, accounts
# =============================================================================

@app.get("/transactions")
def transactions(limit: int = Query(15, ge=1, le=1000)):
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            t.postedDate,
            t.purchaseDate,
            t.merchant,
            t.amount::double precision AS amount,
            t.status,
            t.account_id,
            TRIM(t.category) AS category,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          id,
          account_id,
          raw_date AS postedDate,
          merchant,
          amount,
          status,
          bank,
          card,
          accountType,
          category,
          d AS "dateISO"
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (int(limit),),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    return rows

@app.get("/account-transactions")
def account_transactions(account_id: int, limit: int = Query(200, ge=1, le=5000)):
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.id,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
            t.merchant,
            t.amount::double precision AS amount,
            TRIM(t.category) AS category
          FROM transactions t
          WHERE t.account_id = %s
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT
          id,
          raw_date AS postedDate,
          merchant,
          amount,
          category,
          d AS "dateISO",
          %s::int AS account_id
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (int(account_id), int(account_id), int(limit)),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    return rows

@app.get("/transactions-all")
def transactions_all(limit: int = Query(10000, ge=1, le=50000), offset: int = Query(0, ge=0)):
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.*,
            a.institution AS bank,
            a.name AS card,
            LOWER(a.accountType) AS accountType,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            base.*,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT *, d AS "dateISO"
        FROM norm
        ORDER BY d DESC NULLS LAST, id DESC
        LIMIT %s OFFSET %s
        """,
        (int(limit), int(offset)),
    )
    rows = [dict(r) for r in rows]
    attach_transfer_peers_pg(rows)
    return rows

# =============================================================================
# Page payload endpoints (one request per page)
# =============================================================================

def _call_optional(fn, *args, **kwargs):
    """
    Call fn if it exists, otherwise return None.
    Lets you add bundles without hard-breaking if a feature isn't present.
    """
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None

@app.get("/page/home")
def page_home(
    tx_limit: int = Query(15, ge=1, le=200),
):
    """
    One-shot payload for home.html/home.js
    Bundle the things home currently fetches separately.
    """
    payload: Dict[str, Any] = {
        "transactions": transactions(limit=tx_limit),
        "category_totals_month": category_totals_month(),
        "notifications_unread": unread_count(),
        "bank_totals": bank_totals(),
        # add this if you have month_budget() defined in this file:
        "month_budget": _call_optional(globals().get("month_budget")),
    }
    return payload

@app.get("/page/account/{account_id}")
def page_account(
    account_id: int,
    tx_limit: int = Query(200, ge=1, le=2000),
):
    """
    One-shot payload for account.html/account.js
    """
    payload: Dict[str, Any] = {
        "account": account_info(account_id=account_id),                        # existing route fn【turn10file2†app_postgres.py†L1-L12】
        "transactions": account_transactions(account_id=account_id, limit=tx_limit),  # existing route fn【turn10file0†app_postgres.py†L54-L99】
        # Add any account charts/series endpoints your account.js calls:
        # "account_series": account_series(account_id=account_id, start=..., end=...),
    }
    return payload

@app.get("/page/all-transactions")
def page_all_transactions(
    limit: int = Query(2000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
):
    """
    One-shot payload for all-transactions.html/all-transactions.js
    Uses your existing 'transactions-all' endpoint function.
    """
    # transactions_all() exists right after transactions() in your file【turn10file0†app_postgres.py†L100-L103】
    payload: Dict[str, Any] = {
        "rows": transactions_all(limit=limit, offset=offset),
        "notifications_unread": unread_count(),
    }
    return payload

@app.get("/page/category")
def page_category(
    c: str,
    # add date window params here if your category page needs them
):
    """
    One-shot payload for category.html/category.js
    Fill in with the existing category endpoints your category.js currently calls.
    """
    # These function names are placeholders — wire to whatever your app_postgres.py already has.
    # Example:
    #   category_trend(c=...)
    #   category_transactions(c=..., limit=..., offset=...)
    payload: Dict[str, Any] = {
        "category": c,
        # "trend": category_trend(c=c),
        # "transactions": category_transactions(c=c, limit=500, offset=0),
        "notifications_unread": unread_count(),
    }
    return payload

@app.get("/page/recurring")
def page_recurring():
    """
    One-shot payload for recurring.html/recurring_page.js
    Bundle whatever recurring_page.js fetches.
    """
    payload: Dict[str, Any] = {
        # If you have endpoints like get_recurring() / calendar preview, add them:
        # "recurring": get_recurring_endpoint(...),
        # "ignored_preview": get_ignored_merchants_preview(...),
        "notifications_unread": unread_count(),
    }
    return payload

# -----------------------------------------------------------------------------
# /unassigned  (Postgres)
# -----------------------------------------------------------------------------
@app.get("/unassigned")
def get_unassigned(limit: int = 25, mode: str = "freq"):
    """
    mode:
      - "freq"   => most frequent unassigned merchants
      - "recent" => most recent unassigned transactions
    """
    limit = max(1, min(int(limit or 25), 500))
    mode = (mode or "freq").strip().lower()

    # shared normalization: postedDate/purchaseDate are strings like MM/DD/YY or MM/DD/YYYY (or 'unknown')
    base_cte = """
      WITH base AS (
        SELECT
          t.id,
          COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
          TRIM(t.merchant) AS merchant,
          t.amount::double precision AS amount,
          a.institution AS bank,
          a.name        AS card
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE (t.category IS NULL OR TRIM(t.category) = '')
          AND t.merchant IS NOT NULL
          AND TRIM(t.merchant) <> ''
          AND LOWER(TRIM(t.merchant)) <> 'unknown'
      ),
      norm AS (
        SELECT
          *,
          CASE
            WHEN raw_date IS NULL THEN NULL
            WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
            WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
            ELSE NULL
          END AS d
        FROM base
      )
    """

    if mode == "recent":
        rows = query_db(
            base_cte
            + """
            SELECT
              id,
              raw_date AS "postedDate",
              merchant,
              amount,
              bank,
              card
            FROM norm
            ORDER BY d DESC NULLS LAST, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in rows]

    # default: freq
    rows = query_db(
        base_cte
        + """
        SELECT
          id,
          raw_date AS "postedDate",
          merchant,
          amount,
          bank,
          card,
          COUNT(*) OVER (PARTITION BY merchant) AS usage_count
        FROM norm
        ORDER BY usage_count DESC, d DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in rows]
