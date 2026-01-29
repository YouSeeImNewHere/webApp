from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from db import with_db_cursor

KEYS_FILE = Path(__file__).resolve().parent / "withdrawalKey_test.json"

# Keep this default aligned with your test-mode workflows
USE_TEST_TABLE = True


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


def makeKey(cost, date, account_id: int, seq: int = 0):
    date = str(date).replace("/", "")

    s = str(cost).strip()
    if not s or s.lower() == "unknown":
        # still unique-ish: account + date + "unknown" + seq
        return f"{account_id}_{date}_unknown_{seq}"

    # normalize amount but KEEP sign
    amt = float(s.replace("$", "").replace(",", ""))
    return f"{account_id}_{date}_{amt:.2f}_{seq}"


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

    NOTE: app_postgres.py uses CATEGORY_RULES_TABLE = "categoryrules".
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

    pending = "Pending" if source == "email" else "Posted"
    table = "transactions_test" if use_test_table else "transactions"

    with with_db_cursor() as (conn, cur):
        # auto-assign category from rules
        auto_cat = assign_category(cur, where)

        cur.execute(
            f"""
            INSERT INTO {table} (
              id, status, purchasedate, posteddate, amount, merchant, time, source, account_id, category
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
              %s
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
              category     = CASE
                               WHEN {table}.category IS NULL OR btrim({table}.category) = ''
                               THEN EXCLUDED.category
                               ELSE {table}.category
                             END
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
            ),
        )
        conn.commit()


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
