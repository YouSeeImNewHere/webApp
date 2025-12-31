from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Use your existing DB_PATH
from transactionHandler import DB_PATH, makeKey

# ============================================================
# CONFIG
# ============================================================

# IMPORTANT: set this to your real table
TABLE_NAME = "transactions"

# Run only one job at a time
ACTIVE_JOB = "capitalone_1047_deposit"

IMPORT_JOBS = [
    {"name": "amex_72008", "csv": Path("downloads/amexCredit_72008.csv"), "account_id": 2},
    {"name": "amex_hysa_3912", "csv": Path("downloads/amexHYSA_3912.csv"), "account_id": 1},
    {"name": "amex_51007", "csv": Path("downloads/amexCredit_51007.csv"), "account_id": 8},

    {"name": "capitalone_9691", "csv": Path("downloads/capitalOne_9691.csv"), "account_id": 4},
    {"name": "capitalone_1047_deposit", "csv": Path("downloads/capitalOne_1047.csv"), "account_id": 9},
    {"name": "capitalone_8424_cc", "csv": Path("downloads/capitalOne_8424.csv"), "account_id": 5},

    {"name": "main",  "csv": Path("downloads/navyfcu_main_9338.csv"),  "account_id": 3},
    {"name": "bills", "csv": Path("downloads/navyfcu_bills_7613.csv"), "account_id": 6},

    {"name": "discover_cc", "csv": Path("downloads/discovery.csv"), "account_id": 7},
]

DEFAULTS = {
    "status": "Posted",
    "time": "unknown",
    "source": "CSV",
}

PHONE_RX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

TIP_MAX_ABS = 50.0
TIP_PCT_SMALL = 0.75   # < $20 purchases can jump more (bars/coffee/food)
TIP_PCT_MED   = 0.50   # $20–$60
TIP_PCT_LARGE = 0.35   # >= $60

TARGET_YEAR = 2025  # keep consistent with your navy importer behavior


# ============================================================
# WITHDRAWAL KEY CLEANUP (when CSV overrides email pending)
# ============================================================

WITHDRAWAL_KEYS_FILE = Path("withdrawalKey_test.json")


def load_withdrawal_keys() -> dict:
    if WITHDRAWAL_KEYS_FILE.exists():
        try:
            return json.loads(WITHDRAWAL_KEYS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_withdrawal_keys(data: dict) -> None:
    WITHDRAWAL_KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def delete_withdrawal_key(key: str) -> bool:
    data = load_withdrawal_keys()
    if key in data:
        del data[key]
        save_withdrawal_keys(data)
        return True
    return False


# ============================================================
# DATE / AMOUNT HELPERS
# ============================================================

def parse_mmddyyyy(s: str):
    if not s:
        return None
    s = str(s).strip()
    if not s or s.lower() == "unknown":
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def to_mmddyy(s: str) -> str:
    d = parse_mmddyyyy(s)
    return d.strftime("%m/%d/%y") if d else "unknown"


def mmddyy(date_str: str) -> str:
    d = parse_mmddyyyy(date_str)
    if not d:
        raise ValueError(f"Bad date for mmddyy(): {date_str!r}")
    return d.strftime("%m%d%y")


def normalize_amount_navy(amount_str: str, indicator: str) -> float:
    """
    Navy Federal semantics in your DB:
      - purchases/spend = POSITIVE
      - credits/refunds = NEGATIVE
    """
    amt = float((amount_str or "0").strip())
    if (indicator or "").strip().lower() == "credit":
        return -abs(amt)
    return abs(amt)


def normalize_amount_capitalone_bank(amount_str: str, tx_type: str) -> float:
    """
    Capital One BANK semantics:
      - Credit = money IN (deposit)  -> positive
      - Debit  = money OUT           -> negative
    """
    amt = float((amount_str or "0").strip())
    t = (tx_type or "").strip().lower()
    if t == "credit":
        return abs(amt)
    return -abs(amt)


def normalize_amount_creditcard(amount_str: str, tx_type: str) -> float:
    """
    Credit card semantics:
      - Debit  = charge  -> positive
      - Credit = payment/refund -> negative
    """
    amt = float((amount_str or "0").strip())
    t = (tx_type or "").strip().lower()
    if t == "credit":
        return -abs(amt)
    return abs(amt)


def amount_id_component(amount: float) -> str:
    return f"{abs(amount):.2f}"


def delete_stale_pending_email(cur, table: str, account_id: int, reference_date, days: int = 5) -> int:
    """
    Deletes Pending+email rows for THIS account whose purchaseDate is older than
    (reference_date - days). reference_date should be the latest date found in the CSV file.
    """
    cutoff = (reference_date - timedelta(days=days)).strftime("%Y-%m-%d")

    sql = f"""
    DELETE FROM {table}
    WHERE account_id = ?
      AND status = 'Pending'
      AND source = 'email'
      AND (
        TRIM(COALESCE(purchaseDate,'')) = '' OR LOWER(TRIM(purchaseDate)) = 'unknown'
        OR
        date(
          CASE
            WHEN TRIM(purchaseDate) GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              '20' || substr(TRIM(purchaseDate), 7, 2) || '-' ||
                     substr(TRIM(purchaseDate), 1, 2) || '-' ||
                     substr(TRIM(purchaseDate), 4, 2)
            WHEN TRIM(purchaseDate) GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              substr(TRIM(purchaseDate), 7, 4) || '-' ||
              substr(TRIM(purchaseDate), 1, 2) || '-' ||
              substr(TRIM(purchaseDate), 4, 2)
            ELSE NULL
          END
        ) <= date(?)
      );
    """
    cur.execute(sql, (account_id, cutoff))
    return cur.rowcount


# ============================================================
# DB / CATEGORY HELPERS
# ============================================================

def get_table_columns(cur: sqlite3.Cursor, table: str) -> List[str]:
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def load_category_rules(cur: sqlite3.Cursor) -> List[Tuple[str, re.Pattern]]:
    rules: List[Tuple[str, re.Pattern]] = []
    try:
        rows = cur.execute("""
            SELECT TRIM(category) AS category, pattern, COALESCE(flags,'') AS flags
            FROM CategoryRules
            WHERE COALESCE(is_active, 1) = 1
              AND category IS NOT NULL AND TRIM(category) <> ''
              AND pattern  IS NOT NULL AND TRIM(pattern)  <> ''
        """).fetchall()
    except sqlite3.Error:
        return rules

    for category, pattern, flags in rows:
        re_flags = re.IGNORECASE if "i" in (flags or "").lower() else 0
        try:
            rx = re.compile(pattern, re_flags)
            rules.append((category, rx))
        except re.error:
            continue

    return rules


def categorize(merchant: str, rules: List[Tuple[str, re.Pattern]]) -> str:
    m = merchant or ""
    for cat, rx in rules:
        if rx.search(m):
            return cat
    return ""


def next_id_for_base(cur: sqlite3.Cursor, table: str, base: str) -> str:
    like = f"{base}_%"
    rows = cur.execute(f"SELECT id FROM {table} WHERE id LIKE ?", (like,)).fetchall()
    max_n = 0
    for (existing_id,) in rows:
        if not existing_id:
            continue
        try:
            n = int(str(existing_id).rsplit("_", 1)[-1])
            max_n = max(max_n, n)
        except ValueError:
            continue
    return f"{base}_{max_n + 1}"


# ============================================================
# MERCHANT CLEANUP / SIMILARITY
# ============================================================

STOP_TOKENS = {
    "debit", "dc", "credit", "pos", "purchase", "card", "visa", "mastercard",
    "auth", "pending", "ach", "transaction"
}


def clean_spaces(s: str) -> str:
    s = (s or "").strip()
    s = PHONE_RX.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" -")


def clean_amex_merchant(raw_desc: str, city_state_field: str) -> str:
    """
    Based on your older amex importer behavior:
    - normalize whitespace
    - strip phone numbers
    - try removing city/state suffix using City/State column
    """
    s = (raw_desc or "").strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = PHONE_RX.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()

    city = ""
    st = ""
    if city_state_field:
        parts = [p.strip() for p in str(city_state_field).splitlines() if p.strip()]
        if len(parts) >= 2:
            city, st = parts[0], parts[1]
        elif len(parts) == 1:
            m = re.match(r"^(.*)\s+([A-Z]{2})$", parts[0].strip())
            if m:
                city, st = m.group(1).strip(), m.group(2).strip()

    if st:
        s = re.sub(rf"(?i)\b{re.escape(st)}\b$", "", s).strip()
    if city:
        s = re.sub(rf"(?i){re.escape(city)}$", "", s).strip()
        s = re.sub(rf"(?i)\b{re.escape(city)}\b$", "", s).strip()

    s = re.sub(r"\s+", " ", s).strip(" -")
    return s


def merchant_tokens(s: str) -> List[str]:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)

    toks: List[str] = []
    for t in s.split():
        if t in STOP_TOKENS:
            continue
        if len(t) < 2:
            continue
        if t.isdigit():
            continue
        toks.append(t)
    return toks


def merchants_similar(a: str, b: str, min_overlap: float = 0.6) -> bool:
    A = set(merchant_tokens(a))
    B = set(merchant_tokens(b))
    if not A or not B:
        return False

    shared = len(A & B)

    if shared < 2:
        if shared == 1 and (len(A) <= 2 or len(B) <= 2) and (len(A) <= 6 and len(B) <= 6):
            return True
        return False

    overlap = shared / min(len(A), len(B))
    return overlap >= min_overlap


# ============================================================
# MATCHING LOGIC
# ============================================================

def find_existing_match_pending_email(cur: sqlite3.Cursor,table: str,account_id: int,amount: float,purchase_d,merchant: str,window_days: int = 4,):
    """
    Pending/email exact-amount match (your original behavior):
      - same account_id
      - exact amount
      - purchaseDate within ±window_days
      - status=Pending AND source=email
      - merchant similarity required
    """
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y")
             for delta in range(-window_days, window_days + 1)]
    qmarks = ",".join(["?"] * len(dates))

    candidates = cur.execute(
        f"""
        SELECT id, postedDate, purchaseDate, amount, merchant
        FROM {table}
        WHERE account_id = ?
          AND amount = ?
          AND TRIM(purchaseDate) IN ({qmarks})
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        """,
        [account_id, float(amount), *dates],
    ).fetchall()

    if not candidates:
        return None

    best = None
    for row in candidates:
        db_merch = row[4] if len(row) > 4 else ""
        if merchants_similar(db_merch or "", merchant or ""):
            if best is None:
                best = row
            else:
                best_posted = (best[1] or "unknown").strip().lower()
                row_posted  = (row[1] or "unknown").strip().lower()
                if best_posted != "unknown" and row_posted == "unknown":
                    best = row
            return best

    return None


def find_tip_adjust_match_pending_email(cur: sqlite3.Cursor,table: str,account_id: int,csv_amount: float,csv_merchant: str,purchase_d,window_days: int = 4,):
    """
    Tip-adjust fallback for Pending/email rows:
      - purchaseDate within ±window_days
      - merchant similar
      - csv_amount >= db_amount
      - diff looks like a tip (bounded by abs + tiered pct)
    """
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y")
             for delta in range(-window_days, window_days + 1)]
    qmarks = ",".join(["?"] * len(dates))

    candidates = cur.execute(
        f"""
        SELECT id, amount, merchant, postedDate, purchaseDate
        FROM {table}
        WHERE account_id = ?
          AND TRIM(purchaseDate) IN ({qmarks})
          AND amount IS NOT NULL
          AND amount != 'unknown'
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        """,
        [account_id, *dates],
    ).fetchall()

    try:
        csv_amt_f = float(csv_amount)
    except (TypeError, ValueError):
        return None

    best = None
    best_diff = None

    for (tx_id, db_amt, db_merch, postedDate, db_purchase) in candidates:
        try:
            db_amt_f = float(db_amt)
        except (TypeError, ValueError):
            continue

        # Same sign (purchase vs refund)
        if (db_amt_f >= 0) != (csv_amt_f >= 0):
            continue

        # Tip adds to total: CSV should be >= DB
        if csv_amt_f < db_amt_f:
            continue

        diff = csv_amt_f - db_amt_f
        if diff <= 0:
            continue

        if diff > TIP_MAX_ABS:
            continue

        base = abs(db_amt_f)
        if base < 20:
            pct_cap = TIP_PCT_SMALL
        elif base < 60:
            pct_cap = TIP_PCT_MED
        else:
            pct_cap = TIP_PCT_LARGE

        if base > 0 and diff > base * pct_cap:
            continue

        if not merchants_similar(db_merch or "", csv_merchant or ""):
            continue

        if best is None or diff < best_diff:
            best = (tx_id, postedDate, db_amt_f, db_merch, db_purchase)
            best_diff = diff

    return best


def find_any_match_any_status(cur: sqlite3.Cursor,table: str,account_id: int,amount: float,purchase_d,merchant: str,window_days: int = 4,):
    """
    Broader "override" match:
      - same account_id
      - exact amount
      - purchaseDate within ±window_days
    Preference order:
      1) Pending/email
      2) merchant-similar rows
      3) postedDate unknown
    """
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y")
             for delta in range(-window_days, window_days + 1)]
    qmarks = ",".join(["?"] * len(dates))

    rows = cur.execute(
        f"""
        SELECT id, status, source, postedDate, purchaseDate, amount, merchant
        FROM {table}
        WHERE account_id = ?
          AND amount = ?
          AND TRIM(purchaseDate) IN ({qmarks})
        """,
        [account_id, float(amount), *dates],
    ).fetchall()

    if not rows:
        return None

    def score(r):
        # higher is better
        _id, status, source, postedDate, purchaseDate, amt, merch = r
        s = 0
        if (status or "") == "Pending" and (source or "") == "email":
            s += 1000
        if merchants_similar(merch or "", merchant or ""):
            s += 200
        if (postedDate or "unknown").strip().lower() == "unknown":
            s += 50
        return s

    best = max(rows, key=score)
    # Require at least SOME similarity unless it's pending/email
    if (best[1] or "") == "Pending" and (best[2] or "") == "email":
        return best
    if score(best) >= 200:  # merchant-similar or better
        return best
    return None


# ============================================================
# CORE UPSERT (shared by all importers)
# ============================================================

def upsert_csv_row(
    cur: sqlite3.Cursor,
    tx_cols: set,
    rules: List[Tuple[str, re.Pattern]],
    account_id: int,
    purchase_d,
    purchase: str,
    posted: str,
    amount: float,
    merchant: str,
    allow_tip_adjust: bool,
    allow_broad_override: bool,
) -> Tuple[str, Optional[str]]:
    """
    Returns: ("updated"/"inserted"/"skipped", matched_id_or_none)
    """
    if not merchant or purchase == "unknown":
        return ("skipped", None)

    # 1) Pending/email exact match first
    match = find_existing_match_pending_email(cur, TABLE_NAME, account_id, amount, purchase_d, merchant, window_days=4)
    tip_adjust = False

    # 2) Tip-adjust match (only when allowed)
    if not match and allow_tip_adjust:
        match = find_tip_adjust_match_pending_email(
            cur,
            TABLE_NAME,
            account_id=account_id,
            csv_amount=amount,
            csv_merchant=merchant,
            purchase_d=purchase_d,
            window_days=4
        )
        tip_adjust = True if match else False

    # 3) If still no match, do broader override match (any status/source)
    if not match and allow_broad_override:
        match = find_any_match_any_status(cur, TABLE_NAME, account_id, amount, purchase_d, merchant, window_days=4)
        tip_adjust = False

    cat = categorize(merchant, rules)

    # If matched, UPDATE/OVERRIDE
    if match:
        existing_id = match[0]

        # Tip-adjust: also update amount (final CSV total)
        if tip_adjust:
            if posted != "unknown":
                cur.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET postedDate = ?,
                        purchaseDate = ?,
                        status = ?,
                        merchant = ?,
                        source = ?,
                        amount = ?,
                        category = ?
                    WHERE id = ?
                    """,
                    (posted, purchase, "Posted", merchant, "CSV", float(amount), cat, existing_id),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET purchaseDate = ?,
                        status = ?,
                        merchant = ?,
                        source = ?,
                        amount = ?,
                        category = ?
                    WHERE id = ?
                    """,
                    (purchase, "Posted", merchant, "CSV", float(amount), cat, existing_id),
                )
        else:
            # Exact/override: update with CSV info (always override key fields)
            cur.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET postedDate = ?,
                    purchaseDate = ?,
                    status = ?,
                    merchant = ?,
                    source = ?,
                    category = ?
                WHERE id = ?
                """,
                (posted, purchase, "Posted", merchant, "CSV", cat, existing_id),
            )

        # If we upgraded/overrode a Pending/email row, remove the pending email key
        delete_withdrawal_key(existing_id)
        return ("updated", existing_id)

    # Otherwise: INSERT new row
    # canonical base id (account-aware, signed)
    base = makeKey(f"{amount:.2f}", purchase, account_id=account_id, seq=0)

    # if already exists, bump seq
    tx_id = base
    n = 0
    while cur.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE id = ?", (tx_id,)).fetchone():
        n += 1
        tx_id = makeKey(f"{amount:.2f}", purchase, account_id=account_id, seq=n)

    payload = {
        "id": tx_id,
        "status": "Posted",
        "purchaseDate": purchase,
        "postedDate": posted,
        "amount": float(amount),
        "merchant": merchant,
        "time": DEFAULTS["time"],
        "source": "CSV",
        "account_id": account_id,
        "category": cat,
    }

    insert_keys = [k for k in payload.keys() if k in tx_cols]
    if not insert_keys:
        raise RuntimeError(f"No matching columns found in {TABLE_NAME} table.")

    cols_sql = ", ".join(insert_keys)
    qmarks = ", ".join(["?"] * len(insert_keys))
    values = [payload[k] for k in insert_keys]

    try:
        cur.execute(f"INSERT INTO {TABLE_NAME} ({cols_sql}) VALUES ({qmarks})", values)
    except sqlite3.IntegrityError:
        payload["id"] = next_id_for_base(cur, TABLE_NAME, base)
        values = [payload[k] for k in insert_keys]
        cur.execute(f"INSERT INTO {TABLE_NAME} ({cols_sql}) VALUES ({qmarks})", values)

    return ("inserted", payload["id"])


# ============================================================
# IMPORTERS
# ============================================================

def import_navy_csv(
    csv_path: Path,
    account_id: int,
    *,
    allow_tip_adjust: bool,
    allow_broad_override: bool,
) -> Dict[str, int]:

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tx_cols = set(get_table_columns(cur, TABLE_NAME))
    rules = load_category_rules(cur)

    inserted = 0
    updated = 0
    skipped = 0

    latest_file_date = None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            posted_raw = (row.get("Posting Date") or "").strip()
            purchase_raw = (row.get("Transaction Date") or "").strip()

            purchase_d = parse_mmddyyyy(purchase_raw)
            posted_d = parse_mmddyyyy(posted_raw)

            for d in (purchase_d, posted_d):
                if d:
                    latest_file_date = d if latest_file_date is None else max(latest_file_date, d)
            # ✅ keep rows relevant by EITHER date
            if not purchase_d and not posted_d:
                skipped += 1
                continue

            if not ((purchase_d and purchase_d.year == TARGET_YEAR) or (posted_d and posted_d.year == TARGET_YEAR)):
                skipped += 1
                continue

            posted = to_mmddyy(posted_raw)  # can be "unknown"
            purchase = (purchase_d or posted_d).strftime("%m/%d/%y")

            merchant = (row.get("Description") or row.get("Transaction Description") or "").strip()
            indicator = (row.get("Credit Debit Indicator") or "").strip()

            try:
                amt = normalize_amount_navy(row.get("Amount") or "0", indicator)
            except ValueError:
                skipped += 1
                continue

            if not merchant:
                skipped += 1
                continue

            action, _ = upsert_csv_row(
                cur=cur,
                tx_cols=tx_cols,
                rules=rules,
                account_id=account_id,
                purchase_d=purchase_d or posted_d,
                purchase=purchase,
                posted=posted,
                amount=amt,
                merchant=merchant,
                allow_tip_adjust=allow_tip_adjust,
                allow_broad_override=allow_broad_override,

            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    print("NAVY latest_file_date =", latest_file_date)
    deleted = 0
    if latest_file_date:
        deleted = delete_stale_pending_email(cur, TABLE_NAME, account_id, reference_date=latest_file_date)
    print(f"Deleted stale pending email rows: {deleted}")

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def import_amex_csv(csv_path: Path, account_id: int) -> Dict[str, int]:
    """
    Follows your older Amex parsing:
      - Date column is the transaction date (use as purchase + posted)
      - Amount already signed in the export
      - Clean merchant using City/State column
    Then applies SAME match/override logic as navy.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tx_cols = set(get_table_columns(cur, TABLE_NAME))
    rules = load_category_rules(cur)

    inserted = 0
    updated = 0
    skipped = 0
    latest_file_date = None

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            date_raw = (row.get("Date") or "").strip()
            d = parse_mmddyyyy(date_raw)
            latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            if not d:
                skipped += 1
                continue
            if d.year != TARGET_YEAR:
                skipped += 1
                continue

            purchase_d = d
            purchase = d.strftime("%m/%d/%y")
            posted = purchase  # older behavior

            # Amount already signed
            try:
                amt = float(str(row.get("Amount") or "0").strip())
            except ValueError:
                skipped += 1
                continue

            raw_desc = (row.get("Description") or "").strip()
            city_state = row.get("City/State") or ""
            merchant = clean_amex_merchant(raw_desc, str(city_state))

            if not merchant:
                skipped += 1
                continue

            # Tip adjust: generally not needed for CC exports (they already include final amount)
            action, _ = upsert_csv_row(
                cur=cur,
                tx_cols=tx_cols,
                rules=rules,
                account_id=account_id,
                purchase_d=purchase_d,
                purchase=purchase,
                posted=posted,
                amount=amt,
                merchant=merchant,
                allow_tip_adjust=False,
                allow_broad_override=False,
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
    print("AMEX latest_file_date =", latest_file_date)

    if latest_file_date:
        deleted = delete_stale_pending_email(cur, TABLE_NAME, account_id, reference_date=latest_file_date)
        print(f"Deleted stale pending email rows: {deleted}")

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def import_capitalone_csv(csv_path: Path, account_id: int) -> Dict[str, int]:
    """
    Amex-style behavior:
      - Track latest_file_date from dates in the CSV file
      - Use purchase date as primary date
      - If posted date missing, posted defaults to purchase (Amex-style)
      - Uses same upsert matching logic but WITHOUT broad override (prevents collapsing repeats)
      - Deletes stale pending-email rows based on latest_file_date
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tx_cols = set(get_table_columns(cur, TABLE_NAME))
    rules = load_category_rules(cur)

    inserted = 0
    updated = 0
    skipped = 0
    latest_file_date = None

    is_cc_job = "cc" in csv_path.stem.lower() or "cc" in str(csv_path).lower()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            purchase_raw = (row.get("Transaction Date") or "").strip()
            posted_raw = (row.get("Posted Date") or "").strip()

            purchase_d = parse_mmddyyyy(purchase_raw)
            posted_d = parse_mmddyyyy(posted_raw) if posted_raw else None

            if not purchase_d and not posted_d:
                skipped += 1
                continue

            # Track latest date seen in FILE (Amex-style)
            for d in (purchase_d, posted_d):
                if d:
                    latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            # Keep only target year based on either date
            if not ((purchase_d and purchase_d.year == TARGET_YEAR) or (posted_d and posted_d.year == TARGET_YEAR)):
                skipped += 1
                continue

            effective_purchase_d = purchase_d or posted_d
            if not effective_purchase_d:
                skipped += 1
                continue

            purchase = effective_purchase_d.strftime("%m/%d/%y")

            # ✅ Amex-style: if posted is missing, default posted=purchase
            if posted_d:
                posted = posted_d.strftime("%m/%d/%y")
            else:
                posted = purchase

            merchant_raw = (row.get("Description") or row.get("Transaction Description") or "").strip()
            merchant = clean_spaces(merchant_raw)
            if not merchant:
                skipped += 1
                continue

            # Amount parsing (two formats)
            # Amount parsing (two formats)
            # Capital One rule:
            # Credit => negative
            # everything else => positive

            amt_str = (row.get("Transaction Amount") or "0").strip()
            tx_type = (row.get("Transaction Type") or "").strip().lower()

            try:
                amt = abs(float(amt_str))
            except ValueError:
                skipped += 1
                continue

            if tx_type == "credit":
                amt = -amt
            # else: keep positive

            action, _ = upsert_csv_row(
                cur=cur,
                tx_cols=tx_cols,
                rules=rules,
                account_id=account_id,
                purchase_d=effective_purchase_d,
                purchase=purchase,
                posted=posted,
                amount=amt,
                merchant=merchant,
                allow_tip_adjust=False,
                allow_broad_override=False,  # ✅ prevents collapsing repeats
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    print("CAPITALONE latest_file_date =", latest_file_date)
    deleted = 0
    if latest_file_date:
        deleted = delete_stale_pending_email(cur, TABLE_NAME, account_id, reference_date=latest_file_date)
    print(f"Deleted stale pending email rows: {deleted}")

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def import_discover_csv(csv_path: Path, account_id: int) -> Dict[str, int]:
    """
    Amex-style behavior:
      - Track latest_file_date from dates in the CSV file
      - Amount already signed
      - If post date missing, posted defaults to purchase (Amex-style)
      - Uses same upsert matching logic but WITHOUT broad override
      - Deletes stale pending-email rows based on latest_file_date
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tx_cols = set(get_table_columns(cur, TABLE_NAME))
    rules = load_category_rules(cur)

    inserted = 0
    updated = 0
    skipped = 0
    latest_file_date = None

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            trans_raw = (row.get("Trans. Date") or "").strip()
            post_raw = (row.get("Post Date") or "").strip()
            desc_raw = (row.get("Description") or "").strip()
            amt_raw = (row.get("Amount") or "").strip()

            trans_d = parse_mmddyyyy(trans_raw)
            post_d = parse_mmddyyyy(post_raw) if post_raw else None

            if not trans_d and not post_d:
                skipped += 1
                continue

            # Track latest date seen in FILE (Amex-style)
            for d in (trans_d, post_d):
                if d:
                    latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            if not ((trans_d and trans_d.year == TARGET_YEAR) or (post_d and post_d.year == TARGET_YEAR)):
                skipped += 1
                continue

            purchase_d = trans_d or post_d
            if not purchase_d or not desc_raw:
                skipped += 1
                continue

            purchase = purchase_d.strftime("%m/%d/%y")

            # ✅ Amex-style: if posted is missing, default posted=purchase
            posted = (post_d.strftime("%m/%d/%y") if post_d else purchase)

            merchant = clean_spaces(desc_raw)
            if not merchant:
                skipped += 1
                continue

            try:
                amt = float(amt_raw)
            except ValueError:
                skipped += 1
                continue

            action, _ = upsert_csv_row(
                cur=cur,
                tx_cols=tx_cols,
                rules=rules,
                account_id=account_id,
                purchase_d=purchase_d,
                purchase=purchase,
                posted=posted,
                amount=amt,
                merchant=merchant,
                allow_tip_adjust=False,
                allow_broad_override=False,  # ✅ prevents collapsing repeats
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    print("DISCOVER latest_file_date =", latest_file_date)
    deleted = 0
    if latest_file_date:
        deleted = delete_stale_pending_email(cur, TABLE_NAME, account_id, reference_date=latest_file_date)
    print(f"Deleted stale pending email rows: {deleted}")

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def parse_yyyy_mm_dd(s: str):
    if not s:
        return None
    s = str(s).strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def import_amex_hysa_csv(csv_path: Path, account_id: int) -> Dict[str, int]:
    """
    Keeps your older HYSA format:
      row: [YYYY-MM-DD, Description, Amount]
    Then applies SAME match/override logic as navy.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tx_cols = set(get_table_columns(cur, TABLE_NAME))
    rules = load_category_rules(cur)

    inserted = 0
    updated = 0
    skipped = 0
    latest_file_date = None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)

        for row in reader:
            if not row or len(row) < 3:
                skipped += 1
                continue

            date_raw = (row[0] or "").strip()
            desc_raw = (row[1] or "").strip()
            amt_raw = (row[2] or "").strip()

            d = parse_yyyy_mm_dd(date_raw)
            latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            if not d:
                skipped += 1
                continue
            if d.year != TARGET_YEAR:
                skipped += 1
                continue

            purchase_d = d
            purchase = d.strftime("%m/%d/%y")
            posted = purchase

            try:
                amt = -float(amt_raw)
            except ValueError:
                skipped += 1
                continue

            merchant = clean_spaces(desc_raw)
            if not merchant:
                skipped += 1
                continue

            action, _ = upsert_csv_row(
                cur=cur,
                tx_cols=tx_cols,
                rules=rules,
                account_id=account_id,
                purchase_d=purchase_d,
                purchase=purchase,
                posted=posted,
                amount=amt,
                merchant=merchant,
                allow_tip_adjust=False,
                allow_broad_override=False,  # ✅ add this
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    deleted = 0
    if latest_file_date:
        deleted = delete_stale_pending_email(
            cur,
            TABLE_NAME,
            account_id,
            reference_date=latest_file_date
        )
    print(f"Deleted stale pending email rows: {deleted}")

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    for job in IMPORT_JOBS:
        name = job["name"].lower()
        csv_path: Path = job["csv"]
        account_id: int = job["account_id"]

        if not csv_path.exists():
            print(f"SKIP {job['name']}: CSV not found -> {csv_path}")
            continue

        print(f"\n=== RUNNING JOB: {job['name']} ===")

        if name.startswith("amex_hysa"):
            out = import_amex_hysa_csv(csv_path, account_id)

        elif name.startswith("amex"):
            out = import_amex_csv(csv_path, account_id)

        elif name.startswith("capitalone"):
            out = import_capitalone_csv(csv_path, account_id)

        elif name.startswith("discover"):
            out = import_discover_csv(csv_path, account_id)

        else:
            # navyfcu main / bills
            if name == "main":
                out = import_navy_csv(
                    csv_path,
                    account_id,
                    allow_tip_adjust=True,
                    allow_broad_override=False,
                )
            else:  # bills
                out = import_navy_csv(
                    csv_path,
                    account_id,
                    allow_tip_adjust=False,
                    allow_broad_override=False,
                )

        print(f"JOB={job['name']} FILE={csv_path} account_id={account_id}")
        print(out)


if __name__ == "__main__":
    main()
