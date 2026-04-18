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
    get_user_by_email,
)
from app.core.pushover import send_pushover
from db import query_db, with_db_cursor

router = APIRouter()

_SEQUENCE_REALIGN_TABLES = {
    "card_benefits",
    "card_benefits_new",
    "interest_rates",
    "interest_rates_new",
}


def _realign_table_id_sequence(cur, table_name: str) -> None:
    """
    Ensure SERIAL/BIGSERIAL id sequences are >= MAX(id) for known tables.
    This prevents duplicate-key failures after manual/migrated inserts.
    """
    if table_name not in _SEQUENCE_REALIGN_TABLES:
        return
    try:
        cur.execute("SELECT to_regclass(%s) AS tbl", (table_name,))
        row = cur.fetchone() or {}
        if not row.get("tbl"):
            return
        cur.execute("SELECT pg_get_serial_sequence(%s, 'id') AS seq", (table_name,))
        seq_row = cur.fetchone() or {}
        seq_name = str(seq_row.get("seq") or "").strip()
        if not seq_name:
            return
        cur.execute(
            f"""
            SELECT setval(
              %s,
              GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table_name}), 1),
              true
            )
            """,
            (seq_name,),
        )
    except Exception:
        return


def _require_tenant_id() -> int:
    if not MULTI_TENANT_ENABLED:
        raise HTTPException(status_code=400, detail="onboarding_requires_multi_tenant")
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


def _table_exists(cur, table_name: str) -> bool:
    try:
        cur.execute("SELECT to_regclass(%s) AS tbl", (table_name,))
        row = cur.fetchone() or {}
        return bool(row.get("tbl"))
    except Exception:
        return False


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
    receives_emails: bool = True
    is_paycheck_account: bool = False


class OnboardingPushoverKeyBody(BaseModel):
    user_key: str | None = None


class OnboardingPushoverTestBody(BaseModel):
    user_key: str | None = None


def _ensure_accounts_config_columns(cur) -> None:
    cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS receives_emails BOOLEAN NOT NULL DEFAULT TRUE")
    cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_paycheck_account BOOLEAN NOT NULL DEFAULT FALSE")


def _ensure_csv_mapping_presets_table_pg() -> None:
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS csv_mapping_presets (
              id BIGSERIAL PRIMARY KEY,
              tenant_id BIGINT,
              account_id BIGINT NOT NULL,
              institution_key TEXT NOT NULL,
              preset_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_csv_mapping_presets_scope
            ON csv_mapping_presets (
              COALESCE(tenant_id, 0),
              account_id,
              lower(institution_key)
            )
            """
        )
        conn.commit()


def _ensure_email_parser_trial_drafts_table_pg() -> None:
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_parser_trial_drafts (
                id BIGSERIAL PRIMARY KEY,
                tenant_id BIGINT NOT NULL DEFAULT 0,
                user_email TEXT NOT NULL,
                name TEXT NOT NULL,
                account_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'trial_inactive',
                draft_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.commit()


@router.get("/setup")
def setup_page():
    return FileResponse("static/pages/setup/setup.html")


@router.get("/onboarding/status")
def onboarding_status(request: Request):
    tid = _require_tenant_id()
    _ensure_csv_mapping_presets_table_pg()
    _ensure_email_parser_trial_drafts_table_pg()
    with with_db_cursor() as (conn, cur):
        _ensure_accounts_config_columns(cur)
        conn.commit()
    state = get_or_create_onboarding_state(tid)
    session_email = (request.session.get("google_email") or "").strip().lower()
    pushover_user_key_set = bool(get_user_pushover_key_by_email(session_email))
    user = get_user_by_email(session_email) if session_email else None
    can_set_starting_balance = bool((user or {}).get("is_owner"))

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
        SELECT id, institution, name, LOWER(accounttype) AS accounttype,
               interest_post_day, credit_limit,
               COALESCE(receives_emails, TRUE) AS receives_emails,
               COALESCE(is_paycheck_account, FALSE) AS is_paycheck_account
        FROM accounts
        WHERE tenant_id = %s
        ORDER BY institution, name
        """,
        (tid,),
    )
    account_ids = [int((a or {}).get("id") or 0) for a in (accounts or []) if int((a or {}).get("id") or 0) > 0]
    benefit_rows: list[dict[str, Any]] = []
    if account_ids:
        with with_db_cursor() as (_, cur):
            if _table_exists(cur, "card_benefits"):
                cur.execute(
                    """
                    SELECT card_id, benefit_type, rate
                    FROM card_benefits
                    WHERE tenant_id = %s
                      AND card_id = ANY(%s)
                    ORDER BY card_id, id ASC
                    """,
                    (tid, account_ids),
                )
                benefit_rows = [dict(r) for r in (cur.fetchall() or [])]
    benefits_by_card: dict[int, list[dict[str, Any]]] = {}
    for row in benefit_rows:
        card_id = int((row or {}).get("card_id") or 0)
        if card_id <= 0:
            continue
        benefits_by_card.setdefault(card_id, []).append(
            {
                "benefit_type": str((row or {}).get("benefit_type") or "").strip(),
                "cashback_percent": float((row or {}).get("rate") or 0.0),
            }
        )

    csv_ready_ids: set[int] = set()
    parser_ready_ids: set[int] = set()
    if account_ids:
        rows_csv = query_db(
            """
            SELECT DISTINCT account_id
            FROM csv_mapping_presets
            WHERE COALESCE(tenant_id, 0) = %s
              AND lower(institution_key) = lower(%s)
              AND account_id = ANY(%s)
            """,
            (int(tid), "__account__", account_ids),
        ) or []
        csv_ready_ids = {int((r or {}).get("account_id") or 0) for r in rows_csv}

        rows_parser = query_db(
            """
            SELECT DISTINCT account_id
            FROM email_parser_trial_drafts
            WHERE tenant_id = %s
              AND account_id = ANY(%s)
            """,
            (int(tid), account_ids),
        ) or []
        parser_ready_ids = {int((r or {}).get("account_id") or 0) for r in rows_parser}

    out_accounts = []
    for row in (accounts or []):
        a = dict(row)
        aid = int(a.get("id") or 0)
        receives_emails = bool(a.get("receives_emails", True))
        csv_ready = bool(aid and aid in csv_ready_ids)
        parser_ready = bool(aid and aid in parser_ready_ids)
        parser_required = receives_emails
        complete = bool(csv_ready and (parser_ready if parser_required else True))
        missing = []
        if not csv_ready:
            missing.append("CSV importer")
        if parser_required and not parser_ready:
            missing.append("Email parser")
        a["setup"] = {
            "complete": complete,
            "csv_mapping_ready": csv_ready,
            "parser_required": parser_required,
            "parser_ready": parser_ready,
            "missing": missing,
        }
        a["card_benefits"] = benefits_by_card.get(aid, [])
        out_accounts.append(a)

    return {
        "ok": True,
        "tenant_id": tid,
        "can_set_starting_balance": can_set_starting_balance,
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
        "accounts": out_accounts,
        "next_actions": [
            "Add at least one account",
            "Run CSV import from Settings",
            "Optionally save your Pushover user key",
        ] + (["Add a starting balance for each account"] if can_set_starting_balance else []),
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
        _ensure_accounts_config_columns(cur)
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
            INSERT INTO accounts (
                institution, name, accounttype, interest_post_day, credit_limit, tenant_id, receives_emails, is_paycheck_account
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                institution,
                name,
                accounttype,
                body.interest_post_day,
                body.credit_limit,
                tid,
                bool(body.receives_emails),
                bool(body.is_paycheck_account),
            ),
        )
        new_id = int(cur.fetchone()["id"])

        if bool(body.is_paycheck_account):
            cur.execute(
                """
                UPDATE accounts
                SET is_paycheck_account = FALSE
                WHERE tenant_id = %s AND id <> %s
                """,
                (tid, new_id),
            )

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
            _realign_table_id_sequence(cur, "interest_rates")
            _realign_table_id_sequence(cur, "interest_rates_new")
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
            _realign_table_id_sequence(cur, "card_benefits")
            _realign_table_id_sequence(cur, "card_benefits_new")
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


@router.put("/onboarding/accounts/{account_id}")
def onboarding_update_account(account_id: int, body: OnboardingAccountCreate):
    tid = _require_tenant_id()

    institution = (body.institution or "").strip()
    name = (body.name or "").strip()
    accounttype = (body.accounttype or "").strip().lower()
    if not institution or not name or not accounttype:
        raise HTTPException(status_code=422, detail="institution, name, accounttype are required")
    if accounttype not in {"checking", "savings", "credit", "investment"}:
        raise HTTPException(status_code=422, detail="accounttype must be checking|savings|credit|investment")
    raw_benefits = body.card_benefits
    if accounttype != "credit" and raw_benefits:
        raise HTTPException(status_code=422, detail="card_benefits allowed only for credit accounts")
    benefits: list[tuple[str, float]] = []
    if raw_benefits is not None:
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
    account_id_i = int(account_id)

    with with_db_cursor() as (conn, cur):
        _ensure_accounts_config_columns(cur)
        cur.execute(
            "SELECT id FROM accounts WHERE id = %s AND tenant_id = %s LIMIT 1",
            (account_id_i, tid),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="account_not_found_for_tenant")

        cur.execute(
            """
            UPDATE accounts
            SET institution = %s,
                name = %s,
                accounttype = %s,
                interest_post_day = %s,
                credit_limit = %s,
                receives_emails = %s,
                is_paycheck_account = %s
            WHERE id = %s AND tenant_id = %s
            """,
            (
                institution,
                name,
                accounttype,
                body.interest_post_day,
                body.credit_limit,
                bool(body.receives_emails),
                bool(body.is_paycheck_account),
                account_id_i,
                tid,
            ),
        )
        if bool(body.is_paycheck_account):
            cur.execute(
                """
                UPDATE accounts
                SET is_paycheck_account = FALSE
                WHERE tenant_id = %s AND id <> %s
                """,
                (tid, account_id_i),
            )

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
                    account_id_i,
                    institution,
                    float(body.starting_balance),
                    start_date,
                    tid,
                ),
            )

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
            _realign_table_id_sequence(cur, "interest_rates")
            _realign_table_id_sequence(cur, "interest_rates_new")
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
                    account_id_i,
                    float(apy_val) / 100.0,
                    start_date,
                    "setup_wizard_apy",
                    tid,
                ),
            )

        if accounttype == "credit" and raw_benefits is not None:
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
            cur.execute("DELETE FROM card_benefits WHERE tenant_id = %s AND card_id = %s", (tid, account_id_i))
            _realign_table_id_sequence(cur, "card_benefits")
            _realign_table_id_sequence(cur, "card_benefits_new")
            for category, pct in benefits:
                cur.execute(
                    """
                    INSERT INTO card_benefits (card_id, benefit_type, rate, start_date, tenant_id)
                    VALUES (%s, %s, %s, %s::date, %s)
                    """,
                    (
                        account_id_i,
                        category,
                        pct,
                        start_date,
                        tid,
                    ),
                )

        conn.commit()

    set_onboarding_completed(tid, False)
    return {"ok": True, "account_id": account_id_i}


@router.delete("/onboarding/accounts/{account_id}")
def onboarding_delete_account(account_id: int):
    tid = _require_tenant_id()
    account_id_i = int(account_id)
    if account_id_i <= 0:
        raise HTTPException(status_code=422, detail="invalid_account_id")

    with with_db_cursor() as (conn, cur):
        cur.execute(
            "SELECT id FROM accounts WHERE id = %s AND tenant_id = %s LIMIT 1",
            (account_id_i, tid),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="account_not_found_for_tenant")

        cur.execute(
            "DELETE FROM transactions WHERE tenant_id = %s AND account_id = %s",
            (tid, account_id_i),
        )
        deleted_tx = int(cur.rowcount or 0)

        cur.execute(
            "DELETE FROM startingbalance WHERE tenant_id = %s AND account_id = %s",
            (tid, account_id_i),
        )
        if _table_exists(cur, "interest_rates"):
            cur.execute(
                "DELETE FROM interest_rates WHERE tenant_id = %s AND account_id = %s",
                (tid, account_id_i),
            )
        if _table_exists(cur, "card_benefits"):
            cur.execute(
                "DELETE FROM card_benefits WHERE tenant_id = %s AND card_id = %s",
                (tid, account_id_i),
            )
        if _table_exists(cur, "csv_mapping_presets"):
            cur.execute(
                "DELETE FROM csv_mapping_presets WHERE COALESCE(tenant_id, 0) = %s AND account_id = %s",
                (tid, account_id_i),
            )
        if _table_exists(cur, "email_parser_trial_drafts"):
            cur.execute(
                "DELETE FROM email_parser_trial_drafts WHERE tenant_id = %s AND account_id = %s",
                (tid, account_id_i),
            )

        cur.execute(
            "DELETE FROM accounts WHERE id = %s AND tenant_id = %s",
            (account_id_i, tid),
        )
        conn.commit()

    set_onboarding_completed(tid, False)
    return {"ok": True, "account_id": account_id_i, "deleted_transactions": deleted_tx}
