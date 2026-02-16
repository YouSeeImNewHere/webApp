from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import (
    current_tenant_id,
    get_or_create_onboarding_state,
    set_onboarding_completed,
    get_user_pushover_key_by_email,
    set_user_pushover_key_by_email,
)
from app.core.pushover import send_pushover
from db import query_db, with_db_cursor

router = APIRouter()


def _require_tenant_id() -> int:
    if not MULTI_TENANT_ENABLED:
        raise HTTPException(status_code=400, detail="onboarding_requires_multi_tenant")
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


class OnboardingCompleteBody(BaseModel):
    completed: bool = True


class OnboardingAccountCreate(BaseModel):
    institution: str
    name: str
    accounttype: str
    interest_post_day: int | None = None
    credit_limit: float | None = None
    apy_percent: float | None = None
    starting_balance: float | None = None
    starting_date: str | None = None  # YYYY-MM-DD
    card_benefits: list[dict[str, Any]] | None = None


class OnboardingPushoverKeyBody(BaseModel):
    user_key: str | None = None


class OnboardingPushoverTestBody(BaseModel):
    user_key: str | None = None


@router.get("/setup")
def setup_page():
    return FileResponse("static/pages/setup/setup.html")


@router.get("/onboarding/status")
def onboarding_status(request: Request):
    tid = _require_tenant_id()
    state = get_or_create_onboarding_state(tid)
    session_email = (request.session.get("google_email") or "").strip().lower()
    pushover_user_key_set = bool(get_user_pushover_key_by_email(session_email))

    account_count = int(
        (query_db("SELECT COUNT(*)::int AS n FROM accounts WHERE tenant_id = %s", (tid,))[0] or {}).get("n") or 0
    )
    tx_count = int(
        (query_db("SELECT COUNT(*)::int AS n FROM transactions WHERE tenant_id = %s", (tid,))[0] or {}).get("n") or 0
    )
    sb_count = int(
        (query_db("SELECT COUNT(*)::int AS n FROM startingbalance WHERE tenant_id = %s", (tid,))[0] or {}).get("n") or 0
    )
    accounts = query_db(
        """
        SELECT id, institution, name, LOWER(accounttype) AS accounttype
        FROM accounts
        WHERE tenant_id = %s
        ORDER BY institution, name
        """,
        (tid,),
    )

    return {
        "ok": True,
        "tenant_id": tid,
        "wizard_completed": bool(state.get("wizard_completed")),
        "steps": {
            "accounts_added": account_count > 0,
            "starting_balances_added": sb_count > 0,
            "transactions_imported": tx_count > 0,
            "pushover_user_key_set": pushover_user_key_set,
        },
        "counts": {
            "accounts": account_count,
            "starting_balances": sb_count,
            "transactions": tx_count,
        },
        "accounts": [dict(r) for r in accounts],
        "next_actions": [
            "Add at least one account",
            "Add a starting balance for each account",
            "Run CSV import from Settings",
            "Optionally save your Pushover user key",
        ],
    }


@router.post("/onboarding/pushover-key")
def onboarding_set_pushover_key(body: OnboardingPushoverKeyBody, request: Request):
    _require_tenant_id()
    session_email = (request.session.get("google_email") or "").strip().lower()
    if not session_email:
        raise HTTPException(status_code=401, detail="google_auth_required")

    user_key = (body.user_key or "").strip()
    if user_key and len(user_key) > 128:
        raise HTTPException(status_code=422, detail="user_key_too_long")

    changed = set_user_pushover_key_by_email(session_email, user_key if user_key else None)
    if not changed:
        raise HTTPException(status_code=404, detail="user_not_found")

    return {"ok": True, "user_key_set": bool(user_key)}


@router.post("/onboarding/pushover-test")
def onboarding_send_pushover_test(body: OnboardingPushoverTestBody, request: Request):
    tid = _require_tenant_id()
    session_email = (request.session.get("google_email") or "").strip().lower()
    if not session_email:
        raise HTTPException(status_code=401, detail="google_auth_required")

    input_key = (body.user_key or "").strip()
    user_key = input_key or (get_user_pushover_key_by_email(session_email) or "")
    if not user_key:
        raise HTTPException(status_code=422, detail="pushover_user_key_required")
    if len(user_key) > 128:
        raise HTTPException(status_code=422, detail="user_key_too_long")

    sent = send_pushover(
        "WebApp Test Notification",
        f"Test notification from setup wizard (tenant {int(tid)}).",
        user_key=user_key,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="pushover_send_failed")
    return {"ok": True, "sent": True}


@router.post("/onboarding/complete")
def onboarding_complete(body: OnboardingCompleteBody):
    tid = _require_tenant_id()
    set_onboarding_completed(tid, bool(body.completed))
    return {"ok": True, "tenant_id": tid, "wizard_completed": bool(body.completed)}


@router.post("/onboarding/accounts")
def onboarding_create_account(body: OnboardingAccountCreate):
    tid = _require_tenant_id()

    institution = (body.institution or "").strip()
    name = (body.name or "").strip()
    accounttype = (body.accounttype or "").strip().lower()
    if not institution or not name or not accounttype:
        raise HTTPException(status_code=422, detail="institution, name, accounttype are required")
    if accounttype not in {"checking", "savings", "credit", "investment"}:
        raise HTTPException(status_code=422, detail="accounttype must be checking|savings|credit|investment")
    raw_benefits = body.card_benefits or []
    if accounttype != "credit" and raw_benefits:
        raise HTTPException(status_code=422, detail="card_benefits allowed only for credit accounts")
    benefits: list[tuple[str, float]] = []
    for b in raw_benefits:
        category = str((b or {}).get("benefit_type") or "").strip()
        if not category:
            raise HTTPException(status_code=422, detail="card benefit category is required")
        try:
            pct = float((b or {}).get("cashback_percent"))
        except Exception:
            raise HTTPException(status_code=422, detail="card benefit cashback_percent must be numeric")
        if pct < 0 or pct > 100:
            raise HTTPException(status_code=422, detail="card benefit cashback_percent must be between 0 and 100")
        benefits.append((category, pct))
    if body.apy_percent is not None:
        try:
            apy_val = float(body.apy_percent)
        except Exception:
            raise HTTPException(status_code=422, detail="apy_percent must be numeric")
        if apy_val < 0 or apy_val > 100:
            raise HTTPException(status_code=422, detail="apy_percent must be between 0 and 100")
    else:
        apy_val = None

    start_date = (body.starting_date or "").strip() or date.today().isoformat()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT id
            FROM accounts
            WHERE tenant_id = %s AND institution = %s AND name = %s
            LIMIT 1
            """,
            (tid, institution, name),
        )
        row = cur.fetchone()
        if row:
            raise HTTPException(status_code=409, detail="account_already_exists_for_tenant")

        cur.execute(
            """
            INSERT INTO accounts (institution, name, accounttype, interest_post_day, credit_limit, tenant_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                institution,
                name,
                accounttype,
                body.interest_post_day,
                body.credit_limit,
                tid,
            ),
        )
        new_id = int(cur.fetchone()["id"])

        if body.starting_balance is not None:
            cur.execute(
                """
                INSERT INTO startingbalance (account_id, bank, start, date, tenant_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (account_id) DO UPDATE SET
                  bank = EXCLUDED.bank,
                  start = EXCLUDED.start,
                  date = EXCLUDED.date,
                  tenant_id = EXCLUDED.tenant_id
                """,
                (
                    new_id,
                    institution,
                    float(body.starting_balance),
                    start_date,
                    tid,
                ),
            )

        # Store APY for checking/savings/investment accounts in interest_rates.
        if apy_val is not None and accounttype in {"checking", "savings", "investment"}:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS interest_rates (
                  id SERIAL PRIMARY KEY,
                  account_id INT NOT NULL,
                  apr DOUBLE PRECISION NOT NULL,
                  effective_date DATE NOT NULL,
                  note TEXT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE interest_rates ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_interest_rates_tenant_id ON interest_rates(tenant_id)")
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
            cur.execute(
                """
                INSERT INTO interest_rates (account_id, apr, effective_date, note, created_at, tenant_id)
                VALUES (%s, %s, %s::date, %s, now(), %s)
                ON CONFLICT (account_id, effective_date)
                DO UPDATE SET
                  apr = EXCLUDED.apr,
                  note = EXCLUDED.note,
                  tenant_id = EXCLUDED.tenant_id
                """,
                (
                    new_id,
                    float(apy_val) / 100.0,
                    start_date,
                    "setup_wizard_apy",
                    tid,
                ),
            )

        if accounttype == "credit" and benefits:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS card_benefits (
                  id SERIAL PRIMARY KEY,
                  card_id INT NOT NULL,
                  benefit_type TEXT NOT NULL,
                  rate DOUBLE PRECISION NOT NULL,
                  start_date DATE,
                  end_date DATE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE card_benefits ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_card_benefits_card_id ON card_benefits(card_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_card_benefits_tenant_id ON card_benefits(tenant_id)")
            for category, pct in benefits:
                cur.execute(
                    """
                    INSERT INTO card_benefits (card_id, benefit_type, rate, start_date, tenant_id)
                    VALUES (%s, %s, %s, %s::date, %s)
                    """,
                    (
                        new_id,
                        category,
                        pct,
                        start_date,
                        tid,
                    ),
                )

        conn.commit()

    set_onboarding_completed(tid, False)
    return {"ok": True, "account_id": new_id}
