from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query

from app.routers.balances import latest_rates_map_pg
from db import with_db_cursor, query_db, run_db_retry

router = APIRouter()

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

@router.get("/account/{account_id}")
def account_info(account_id: int):
    sql = """
      SELECT id, institution, name, LOWER(accountType) AS accounttype
      FROM accounts
      WHERE id = %s
    """
    rows = query_db(sql, (int(account_id),))
    return rows[0] if rows else {"error": "Account not found"}

@router.get("/bank-info")
def bank_info():
    def _run():
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
                    SELECT
                        card_id AS account_id,
                        benefit_type AS category,
                        rate AS cashback_percent
                    FROM card_benefits
                    ORDER BY card_id, benefit_type, start_date NULLS FIRST, end_date NULLS LAST
                    """
                )
                benefits_rows = cur.fetchall()

        return rate_now, has_notes, has_credit_limit, accounts, cards, benefits_rows

    rate_now, has_notes, has_credit_limit, accounts, cards, benefits_rows = run_db_retry(_run, retries=1)

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

@router.post("/bank-info/refresh")
def bank_info_refresh():
    # placeholder for now
    return {"ok": True}

@router.get("/bank-totals")
def bank_totals():
    def _run():
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
        return has_credit_limit, accounts, starting_rows, tx_rows

    has_credit_limit, accounts, starting_rows, tx_rows = run_db_retry(_run, retries=1)

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
