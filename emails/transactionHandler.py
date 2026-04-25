from __future__ import annotations

import csv
import json
import re
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Optional

from db import with_db_cursor

KEYS_FILE = Path(__file__).resolve().parent / "withdrawalKey_test.json"

# Legacy compatibility for modules that still import DB_PATH for sqlite-based receipt helpers.
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "finance.db"))

# Keep this default aligned with your test-mode workflows
USE_TEST_TABLE = True

_ALLOWED_TX_TABLES = {"transactions", "transactions_test"}


def add_key(cost, date, time, msg_id_str: str, account_id: int, seq: int = 0):
    # build key using new format
    key = makeKey(cost, date, account_id=account_id, seq=seq)

    if KEYS_FILE.exists():
        with KEYS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    if key in data:
        print("\n=== KEY ALREADY EXISTS ===")
        return False

    data[key] = {
        "cost": cost,
        "date": date,
        "time": time,
        "account_id": account_id,
        "msg_id": msg_id_str,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    print("\n=== ADDED KEY ===")
    with KEYS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True


def delete_key(key: str):
    if KEYS_FILE.exists():
        with KEYS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    if key not in data:
        return False

    del data[key]

    with KEYS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True


def checkKey(mail, key: str):
    if KEYS_FILE.exists():
        with KEYS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    if key in data:
        print("\n=== DELETING KEY ===")

        original_msg_id = data[key].get("msg_id")
        if original_msg_id:
            # move the original withdrawal email to "ToBeDeleted"
            mail.store(original_msg_id, "+X-GM-LABELS", "(ToBeDeleted)")

            # optional: remove labels you no longer want on it
            mail.store(original_msg_id, "-X-GM-LABELS", "(ProcessedNew)")
            mail.store(original_msg_id, "-X-GM-LABELS", "(NavyFedPurchase)")

        delete_key(key)


def normalize_date_mmddyy(value, *, default_to_today: bool = True) -> str:
    s = str(value or "").strip()
    if not s:
        return datetime.now().strftime("%m/%d/%y") if default_to_today else ""

    for fmt in (
        "%m/%d/%y",
        "%m/%d/%Y",
        "%m-%d-%y",
        "%m-%d-%Y",
        "%m.%d.%y",
        "%m.%d.%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d-%b-%Y",
        "%d %b %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%a, %b %d, %Y",
        "%a %b %d, %Y",
        "%a, %d %b %Y",
    ):
        try:
            return datetime.strptime(s, fmt).strftime("%m/%d/%y")
        except Exception:
            continue

    try:
        return parsedate_to_datetime(s).strftime("%m/%d/%y")
    except Exception:
        pass

    if default_to_today:
        return datetime.now().strftime("%m/%d/%y")
    return ""


def makeKey(cost, date, account_id: int, seq: int = 0):
    normalized_date = normalize_date_mmddyy(date, default_to_today=True)
    date_token = normalized_date.replace("/", "")

    s = str(cost).strip()
    if not s or s.lower() == "unknown":
        # still unique-ish: account + date + "unknown" + seq
        return f"{account_id}_{date_token}_unknown_{seq}"

    # normalize amount but KEEP sign
    try:
        amt = float(s.replace("$", "").replace(",", ""))
        return f"{account_id}_{date_token}_{amt:.2f}_{seq}"
    except Exception:
        return f"{account_id}_{date_token}_unknown_{seq}"


def _parse_mmddyy(d: str):
    try:
        return datetime.strptime(d, "%m/%d/%y").date()
    except Exception:
        return None


def _parse_hhmm_ampm(t: str):
    # expects like "07:27 AM"
    try:
        return datetime.strptime(t.strip(), "%I:%M %p").time()
    except Exception:
        return None


def find_matching_key(cost: str, date: str, time: str, account_id: int) -> Optional[str]:
    """
    Find a pending withdrawal key that matches this transaction by:
      - same account_id
      - same amount (ignoring sign)
      - time matches exactly
      - date is same day or +/- 1 day

    Returns the matched KEY (the one that already exists in KEYS_FILE),
    or None if no match.
    """
    data = {}
    if KEYS_FILE.exists():
        with KEYS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

    # normalize wanted amount (ignore sign)
    want_amt = abs(float(str(cost).replace("$", "").replace(",", "").strip()))
    want_date = _parse_mmddyy(date)
    want_time = _parse_hhmm_ampm(time)

    if want_date is None:
        return None

    candidate_dates = {
        want_date,
        want_date - timedelta(days=1),
        want_date + timedelta(days=1),
    }

    for key, meta in data.items():
        # key format: "{account_id}_{mmddyyNoSlashes}_{amount}_{seq}"
        parts = key.split("_")
        if len(parts) < 4:
            continue

        try:
            k_account_id = int(parts[0])
            k_amt = abs(float(parts[2]))
        except Exception:
            continue

        # account must match
        if k_account_id != int(account_id):
            continue

        # amount must match (ignore sign)
        if k_amt != want_amt:
            continue

        stored_date = meta.get("date")  # "11/15/25"
        stored_time = meta.get("time")  # "07:27 AM"
        s_date = _parse_mmddyy(stored_date)
        s_time = _parse_hhmm_ampm(stored_time)

        if s_date is None:
            continue

        # date fuzzy match
        if s_date not in candidate_dates:
            continue

        # time match (strict)
        if want_time and s_time and (want_time != s_time):
            continue

        return key

    return None


def assign_category(cur, merchant: str) -> str:
    """
    Auto-assign category using categoryrules (Postgres).

    NOTE: app_postgresOld.py uses CATEGORY_RULES_TABLE = "categoryrules".
    """
    rows = cur.execute(
        """
        SELECT category, pattern, flags
        FROM categoryrules
        WHERE is_active = TRUE
        """
    ).fetchall()

    m = merchant or ""
    for r in rows:
        # psycopg rows are dict-like (RealDictCursor)
        pattern = (r.get("pattern") if isinstance(r, dict) else r[1]) or ""
        flags = (r.get("flags") if isinstance(r, dict) else r[2]) or ""
        cat = (r.get("category") if isinstance(r, dict) else r[0]) or ""

        rx = re.compile(pattern, re.IGNORECASE if "i" in (flags or "") else 0)
        if rx.search(m):
            return cat

    return ""


def _normalize_purchase_date_mmddyy(value) -> str:
    return normalize_date_mmddyy(value, default_to_today=True)


def _normalize_amount_token(value) -> str:
    s = str(value or "").strip()
    if not s or s.lower() == "unknown":
        return "unknown"
    try:
        return f"{float(s.replace('$', '').replace(',', '')):.2f}"
    except Exception:
        return "unknown"


def _extract_seq_from_key(tx_id: str) -> int:
    s = str(tx_id or "").strip()
    m = re.search(r"_(\d+)$", s)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def _extract_amount_token_from_key(tx_id: str) -> str:
    s = str(tx_id or "").strip()
    m = re.match(r"^\d+_\d{6}_([^_]+)_\d+$", s)
    if not m:
        return "unknown"
    token = str(m.group(1) or "").strip()
    if re.match(r"^-?\d+(?:\.\d{2})$", token) or token == "unknown":
        return token
    return "unknown"


def _is_normalized_email_key(tx_id: str, account_id: int, amount, purchase_date: str) -> bool:
    s = str(tx_id or "").strip()
    m = re.match(r"^(\d+)_(\d{6})_(-?\d+\.\d{2}|unknown)_(\d+)$", s)
    if not m:
        return False
    if int(m.group(1)) != int(account_id):
        return False
    date_token = normalize_date_mmddyy(purchase_date, default_to_today=False).replace("/", "")
    if not date_token:
        return False
    if m.group(2) != date_token:
        return False
    if amount is None:
        return True
    return m.group(3) == _normalize_amount_token(amount)


def repair_email_transaction_keys(
    *,
    table: str = "transactions",
    dry_run: bool = True,
    limit: int | None = None,
):
    target_table = str(table or "").strip()
    if target_table not in _ALLOWED_TX_TABLES:
        raise ValueError(f"Unsupported table: {target_table}")

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            (target_table,),
        )
        columns = {str((r or {}).get("column_name") or "").strip().lower() for r in (cur.fetchall() or [])}
        has_tenant_id = "tenant_id" in columns

        params = []
        tenant_expr = "tenant_id" if has_tenant_id else "NULL::integer AS tenant_id"
        sql = f"""
            SELECT id, account_id, amount, purchasedate, {tenant_expr}
            FROM {target_table}
            WHERE lower(coalesce(source, '')) = 'email'
            ORDER BY id
        """
        if isinstance(limit, int) and limit > 0:
            sql += " LIMIT %s"
            params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        cur.execute(f"SELECT id FROM {target_table}")
        existing_ids = {str((r or {}).get("id") or "") for r in (cur.fetchall() or [])}
        updates: list[tuple[str, str, str, int | None]] = []
        tenants_touched: set[int] = set()

        for row in rows:
            old_id = str(row.get("id") or "").strip()
            if not old_id:
                continue
            account_id = int(row.get("account_id") or 0)
            if account_id <= 0:
                continue

            normalized_date = normalize_date_mmddyy(row.get("purchasedate"), default_to_today=False)
            if not normalized_date:
                continue

            already_ok = _is_normalized_email_key(
                tx_id=old_id,
                account_id=account_id,
                amount=row.get("amount"),
                purchase_date=normalized_date,
            )
            purchase_date_changed = str(row.get("purchasedate") or "").strip() != normalized_date
            if already_ok and not purchase_date_changed:
                continue

            seq = _extract_seq_from_key(old_id)
            amount_for_key = row.get("amount")
            if amount_for_key is None:
                amount_for_key = _extract_amount_token_from_key(old_id)
            new_id = makeKey(amount_for_key, normalized_date, account_id=account_id, seq=seq)
            while new_id != old_id and new_id in existing_ids:
                seq += 1
                new_id = makeKey(amount_for_key, normalized_date, account_id=account_id, seq=seq)

            updates.append((old_id, new_id, normalized_date, row.get("tenant_id")))
            existing_ids.discard(old_id)
            existing_ids.add(new_id)
            try:
                tenant_raw = row.get("tenant_id")
                if tenant_raw is not None:
                    tenants_touched.add(int(tenant_raw))
            except Exception:
                pass

        if dry_run:
            return {
                "table": target_table,
                "dry_run": True,
                "total_email_rows": len(rows),
                "rows_to_fix": len(updates),
                "sample": [{"old_id": o, "new_id": n, "purchasedate": d} for (o, n, d, _) in updates[:25]],
            }

        fixed = 0
        for old_id, new_id, normalized_date, _tenant_id in updates:
            cur.execute(
                f"""
                UPDATE {target_table}
                SET id = %s, purchasedate = %s
                WHERE id = %s
                """,
                (new_id, normalized_date, old_id),
            )
            fixed += int(cur.rowcount or 0)

        conn.commit()

    try:
        from app.routers.page_payloads import touch_widget_cache_for_tenant

        for tid in sorted(tenants_touched):
            touch_widget_cache_for_tenant(tid)
    except Exception:
        pass

    return {
        "table": target_table,
        "dry_run": False,
        "total_email_rows": len(rows),
        "rows_to_fix": len(updates),
        "rows_fixed": fixed,
    }


def insert_transaction(
    key: str,
    bank: str,
    card: str,
    accountType: str,
    cost,
    where: str,
    purchaseDate: str,
    time: str,
    source: str,
    postedDate: str = "unknown",
    use_test_table: bool = False,
):
    # Normalize amount before DB insert (prevents "$3.00" issues)
    cost_str = str(cost).replace("$", "").replace(",", "").strip()
    purchaseDate = _normalize_purchase_date_mmddyy(purchaseDate)

    pending = "Pending" if source == "email" else "Posted"
    table = "transactions_test" if use_test_table else "transactions"

    with with_db_cursor() as (conn, cur):
        auto_cat = assign_category(cur, where)

        cur.execute(
            f"""
            INSERT INTO {table} (
              id, status, purchasedate, posteddate, amount, merchant, time, source, account_id, category, tenant_id
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s,
              COALESCE(
                (
                  SELECT id
                  FROM accounts
                  WHERE institution = %s AND name = %s AND LOWER(accounttype) = LOWER(%s)
                  LIMIT 1
                ),
                0
              ),
              %s,
              COALESCE(
                (
                  SELECT tenant_id
                  FROM accounts
                  WHERE institution = %s AND name = %s AND LOWER(accounttype) = LOWER(%s)
                  LIMIT 1
                ),
                0
              )
            )
            ON CONFLICT (id) DO UPDATE SET
              status       = EXCLUDED.status,
              purchasedate = EXCLUDED.purchasedate,
              posteddate   = EXCLUDED.posteddate,
              amount       = EXCLUDED.amount,
              merchant     = EXCLUDED.merchant,
              time         = CASE
                               WHEN {table}.time IS NULL OR {table}.time = 'unknown'
                               THEN EXCLUDED.time
                               ELSE {table}.time
                             END,
              source       = EXCLUDED.source,
              account_id   = EXCLUDED.account_id,
              tenant_id    = COALESCE({table}.tenant_id, EXCLUDED.tenant_id),
              category     = CASE
                               WHEN {table}.category IS NULL OR btrim({table}.category) = ''
                               THEN EXCLUDED.category
                               ELSE {table}.category
                             END
            RETURNING
              id AS tx_id,
              account_id,
              tenant_id,
              (xmax = 0) AS inserted
            """,
            (
                key,
                pending,
                purchaseDate,
                postedDate,
                cost_str,
                where,
                time,
                source,
                bank,
                card,
                accountType,
                auto_cat,
                bank,
                card,
                accountType,
            ),
        )

        row = cur.fetchone()
        conn.commit()
        try:
            from app.routers.page_payloads import touch_widget_cache_for_tenant

            tenant_id = row["tenant_id"] if isinstance(row, dict) else row[2]
            touch_widget_cache_for_tenant(int(tenant_id) if tenant_id is not None else None)
        except Exception:
            pass

        # row always exists for INSERT or UPDATE in this statement
        # inserted=True means brand new row was created
        return {
            "tx_id": row["tx_id"] if isinstance(row, dict) else row[0],
            "account_id": row["account_id"] if isinstance(row, dict) else row[1],
            "tenant_id": row["tenant_id"] if isinstance(row, dict) else row[2],
            "inserted": row["inserted"] if isinstance(row, dict) else row[3],

            # add these so pushover is always accurate
            "merchant": where,
            "amount": float(cost_str) if cost_str not in ("", "unknown") else None,
            "purchaseDate": purchaseDate,
            "time": time,
        }


def import_hysa_csv(csv_path: str):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)

        for row_num, row in enumerate(reader, start=1):
            if not row or len(row) < 3:
                continue

            raw_date = row[0].strip()
            raw_amount = row[2].strip()

            if not raw_date or not raw_amount:
                continue

            try:
                d = datetime.strptime(raw_date, "%m/%d/%Y").date()
            except ValueError:
                print(f"[HYSA] Bad date on row {row_num}: {raw_date}")
                continue

            mmddyy = d.strftime("%m/%d/%y")

            cleaned = raw_amount.replace(",", "").replace("$", "")
            try:
                amount = float(cleaned)
            except ValueError:
                print(f"[HYSA] Bad amount on row {row_num}: {raw_amount}")
                continue

            merchant = "deposit" if amount > 0 else "withdrawal"

            AMEX_HYSA_ID = 1
            key = makeKey(f"{amount:.2f}", mmddyy, account_id=AMEX_HYSA_ID)

            insert_transaction(
                key=key,
                bank="American Express",
                card="",  # should match accounts.name if you use it
                accountType="savings",
                cost=amount,
                where=merchant,  # this is what category rules match against
                purchaseDate=mmddyy,
                time="unknown",
                source="csv",
                postedDate=mmddyy,
            )


if __name__ == "__main__":
    # NOTE: for scripts, ensure your db pool is configured via env (DATABASE_URL).
    import_hysa_csv("downloads/HYSA.csv")
