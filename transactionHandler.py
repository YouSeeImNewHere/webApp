from pathlib import Path
import json
from datetime import datetime, timedelta, timezone
import sqlite3
import csv
import re

KEYS_FILE = Path("withdrawalKey.json")
DB_PATH = "finance.db"


def add_key(key, cost, date, time):
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    print("\n=== ADDED KEY ===")
    with KEYS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True


def delete_key(key):
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


def checkKey(key):
    if KEYS_FILE.exists():
        with KEYS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    if key in data:
        print("\n=== DELETING KEY ===")
        delete_key(key)


def makeKey(cost, date):
    cost = str(cost).replace("$", "").replace(",", "").replace("-", "")
    date = str(date).replace("/", "")
    return f"{cost}_{date}"


def assign_category(cur, merchant: str):
    rows = cur.execute("""
      SELECT category, pattern, flags
      FROM CategoryRules
      WHERE is_active = 1
    """).fetchall()

    m = merchant or ""
    for r in rows:
        pattern = r["pattern"] if isinstance(r, sqlite3.Row) else r[1]
        flags   = r["flags"]   if isinstance(r, sqlite3.Row) else r[2]
        cat     = r["category"] if isinstance(r, sqlite3.Row) else r[0]

        rx = re.compile(pattern, re.IGNORECASE if "i" in (flags or "") else 0)
        if rx.search(m):
            return cat

    return ""


def insert_transaction(
    key,
    bank,
    card,
    accountType,
    cost,
    where,
    purchaseDate,
    time,
    source,
    postedDate="unknown"
):
    # Normalize amount before DB insert (prevents "$3.00" issues)
    cost_str = str(cost).replace("$", "").replace(",", "").strip()

    pending = "Pending" if source == "email" else "Posted"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ✅ Option A: auto-assign category from rules
    auto_cat = assign_category(cursor, where)

    cursor.execute("""
        INSERT INTO transactions (
            id,
            status,
            purchaseDate,
            postedDate,
            bank,
            card,
            accountType,
            amount,
            merchant,
            time,
            source,
            account_id,
            category
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            COALESCE(
                (SELECT id
                 FROM accounts
                 WHERE institution = ? AND name = ? AND LOWER(accountType) = LOWER(?)
                 LIMIT 1),
                0
            ),
            ?
        )
        ON CONFLICT(id) DO UPDATE SET
            status       = EXCLUDED.status,
            purchaseDate = EXCLUDED.purchaseDate,
            postedDate   = EXCLUDED.postedDate,
            bank         = EXCLUDED.bank,
            card         = EXCLUDED.card,
            accountType  = EXCLUDED.accountType,
            amount       = EXCLUDED.amount,
            merchant     = EXCLUDED.merchant,
            time         = CASE
                               WHEN transactions.time IS NULL
                                    OR transactions.time = 'unknown'
                               THEN EXCLUDED.time
                               ELSE transactions.time
                           END,
            source       = EXCLUDED.source,
            account_id   = EXCLUDED.account_id,
            category     = CASE
                               WHEN transactions.category IS NULL OR TRIM(transactions.category) = ''
                               THEN EXCLUDED.category
                               ELSE transactions.category
                           END
    """, (
        key,
        pending,
        purchaseDate,
        postedDate,
        bank,
        card,
        accountType,
        cost_str,
        where,
        time,
        source,

        # for the subquery lookup (institution, name, accountType)
        bank,
        card,
        accountType,

        # category on insert/update
        auto_cat
    ))

    conn.commit()
    conn.close()


def import_hysa_csv(csv_path):
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

            key = makeKey(f"{abs(amount):.2f}", mmddyy)

            insert_transaction(
                key=key,
                bank="American Express",
                card="",                 # should match accounts.name if you use it
                accountType="savings",
                cost=amount,
                where=merchant,          # this is what category rules match against
                purchaseDate=mmddyy,
                time="unknown",
                source="csv",
                postedDate=mmddyy
            )


if __name__ == "__main__":
    import_hysa_csv("downloads/HYSA.csv")
