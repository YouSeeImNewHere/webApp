from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Optional .env support
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Postgres
import psycopg2
from psycopg2.extras import RealDictCursor
import argparse

# You said: .env "DATABASE_URL=<database>"
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL. Put DATABASE_URL=<your postgres url> in .env")

# ============================================================
# CONFIG (kept from your SQLite file)
# ============================================================

# IMPORTANT: set these to your real tables if needed
WRITE_TABLE = "transactions"
LOOKUP_TABLE = "transactions"

IMPORT_JOBS = [
    {"name": "amex_72008", "csv": Path("../downloads/amexCredit_72008.csv"), "account_id": 2},
    {"name": "amex_hysa_3912", "csv": Path("../downloads/amexHYSA_3912.csv"), "account_id": 1},
    {"name": "amex_51007", "csv": Path("../downloads/amexCredit_51007.csv"), "account_id": 8},

    {"name": "capitalone_9691", "csv": Path("../downloads/capitalOne_9691.csv"), "account_id": 4},
    {"name": "capitalone_1047_deposit", "csv": Path("../downloads/capitalOne_1047.csv"), "account_id": 9},
    {"name": "capitalone_8424_cc", "csv": Path("../downloads/capitalOne_8424.csv"), "account_id": 5},

    {"name": "main",  "csv": Path("../downloads/navyfcu_main_9338.csv"), "account_id": 3},
    {"name": "bills", "csv": Path("../downloads/navyfcu_bills_7613.csv"), "account_id": 6},

    {"name": "discover_cc", "csv": Path("../downloads/discovery.csv"), "account_id": 7},
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

WITHDRAWAL_KEYS_FILE = Path("withdrawalKey_test.json")

PAYMENT_GENERIC_TOKENS = {
    "payment", "pay", "thank", "thanks", "thankyou", "you",
    "mobile", "autopay", "online", "electronic", "transfer"
}


def build_jobs(input_dir: Optional[str] = None):
    if not input_dir:
        return IMPORT_JOBS

    base = Path(input_dir)
    # Use the SAME expected filenames, but inside the temp upload dir.
    jobs = []
    for j in IMPORT_JOBS:
        fname = Path(j["csv"]).name  # e.g. "amexCredit_72008.csv"
        jobs.append({**j, "csv": base / fname})
    return jobs


# If you used transactionHandler.makeKey before, keep the same key strategy here:
# This replicates your previous “base + seq” behavior but WITHOUT importing sqlite DB_PATH.
def make_base_id(amount: float, purchase_mmddyy: str, account_id: int) -> str:
    # base: 3_012626_7.25   (NO suffix)
    d = purchase_mmddyy.replace("/", "")
    return f"{account_id}_{d}_{amount:.2f}"

def next_seq_id(cur, table: str, base: str) -> str:
    """
    If base doesn't exist, return base.
    If base exists, return base_1, base_2, ...
    """
    # exact base
    cur.execute(f"SELECT 1 FROM {table} WHERE id = %s LIMIT 1", (base,))
    if cur.fetchone() is None:
        return base

    # any base_N
    like = base + r"\_%"
    cur.execute(f"SELECT id FROM {table} WHERE id LIKE %s", (base + "_%",))
    rows = cur.fetchall()

    max_n = 0
    for (existing_id,) in rows:
        try:
            n = int(str(existing_id).rsplit("_", 1)[-1])
            max_n = max(max_n, n)
        except ValueError:
            continue

    return f"{base}_{max_n + 1}"

def find_pending_email_by_base(cur, table: str, base: str) -> Optional[str]:
    """
    Only returns an ID if it's Pending+email for base or base_*.
    Otherwise returns None (so duplicates will INSERT instead of UPDATE).
    """
    cur.execute(
        f"""
        SELECT id
        FROM {table}
        WHERE (id = %s OR id LIKE %s)
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        ORDER BY CASE WHEN id = %s THEN 0 ELSE 1 END, id
        LIMIT 1
        """,
        (base, base + "_%", base),
    )
    row = cur.fetchone()
    return row[0] if row else None

# ============================================================
# Postgres connection helpers
# ============================================================

def get_conn():
    # autocommit off; commit in import functions
    return psycopg2.connect(DATABASE_URL)

def qmarks(n: int) -> str:
    return ", ".join(["%s"] * n)

def table_columns(cur, table: str) -> List[str]:
    # Assumes public schema; adjust if you use something else
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]

def date_from_text_expr(colname: str) -> str:
    """
    Convert text date ('MM/DD/YY' or 'MM/DD/YYYY' or 'unknown'/blank) -> DATE (or NULL).
    Mirrors your earlier logic but in Postgres.
    """
    c = f"NULLIF(TRIM(COALESCE({colname}, '')), '')"
    # treat 'unknown' as NULL too
    c2 = f"NULLIF(NULLIF(LOWER({c}), 'unknown'), '')"
    # we need original casing for to_date, so use c but gate on lower() check
    return f"""
    CASE
      WHEN {c} IS NULL THEN NULL
      WHEN LOWER({c}) = 'unknown' THEN NULL
      WHEN length({c}) = 8  THEN to_date({c}, 'MM/DD/YY')
      WHEN length({c}) = 10 THEN to_date({c}, 'MM/DD/YYYY')
      ELSE NULL
    END
    """.strip()


# ============================================================
# Withdrawal key cleanup (unchanged)
# ============================================================

def clean_spaces(s: str) -> str:
    s = (s or "").strip()
    s = PHONE_RX.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" -")

STOP_TOKENS = {
    "debit", "dc", "credit", "pos", "purchase", "card", "visa", "mastercard",
    "auth", "pending", "ach", "transaction"
}

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

def is_generic_payment_merchant(s: str) -> bool:
    s = clean_spaces(s).lower()
    if not s or s in ("unknown",):
        return True
    s = s.replace("thank you", "thankyou").replace("thanks", "thank")
    toks = set(merchant_tokens(s))
    return bool(toks) and (toks <= PAYMENT_GENERIC_TOKENS)

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
# Date helpers (unchanged behavior)
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

def _row_effective_date(*ds):
    ds2 = [d for d in ds if d]
    return max(ds2) if ds2 else None

def get_latest_posted_cutoff(cur, account_id: int) -> Optional[datetime.date]:
    """
    Latest transaction date among rows with status 'Posted' for THIS account in LOOKUP_TABLE.
    Uses postedDate when valid; falls back to purchaseDate when postedDate is unknown/blank.
    """
    posted_d = date_from_text_expr("postedDate")
    purchase_d = date_from_text_expr("purchaseDate")

    sql = f"""
      SELECT MAX(COALESCE({posted_d}, {purchase_d}))::date AS max_d
      FROM {LOOKUP_TABLE}
      WHERE LOWER(TRIM(COALESCE(status,''))) = 'posted'
        AND account_id = %s
        AND COALESCE({posted_d}, {purchase_d}) IS NOT NULL
    """
    cur.execute(sql, (account_id,))
    row = cur.fetchone()
    return row[0] if row and row[0] else None

def get_import_window(cur, account_id: int, today: Optional[datetime.date] = None):
    if today is None:
        today = datetime.now().date()
    end_date = today - timedelta(days=1)
    last_posted = get_latest_posted_cutoff(cur, account_id)
    start_date = (last_posted + timedelta(days=1)) if last_posted else None
    return start_date, end_date, last_posted

def date_in_window(d, start_date, end_date) -> bool:
    if not d:
        return False
    if start_date and d < start_date:
        return False
    if d > end_date:
        return False
    return True

# ============================================================
# Category rules (same schema assumptions)
# ============================================================

def load_category_rules(cur):
    rules = []
    try:
        cur.execute("""
            SELECT TRIM(category) AS category, pattern, COALESCE(flags,'') AS flags
            FROM categoryrules
            WHERE COALESCE(is_active, TRUE) = TRUE
              AND category IS NOT NULL AND TRIM(category) <> ''
              AND pattern  IS NOT NULL AND TRIM(pattern)  <> ''
        """)
        rows = cur.fetchall()
    except Exception as e:
        # IMPORTANT for Postgres: clear aborted transaction state
        try:
            cur.connection.rollback()
        except Exception:
            pass
        print("⚠️ CategoryRules query failed:", repr(e))
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

# ============================================================
# DB row existence / copying (testing mode parity)
# ============================================================

def _id_exists(cur, table: str, tx_id: str) -> bool:
    cur.execute(f"SELECT 1 FROM {table} WHERE id = %s LIMIT 1", (tx_id,))
    return cur.fetchone() is not None

def _id_exists_any(cur, tx_id: str) -> bool:
    if _id_exists(cur, LOOKUP_TABLE, tx_id):
        return True
    if WRITE_TABLE != LOOKUP_TABLE and _id_exists(cur, WRITE_TABLE, tx_id):
        return True
    return False

def _copy_row_from_lookup_if_missing(cur, tx_id: str) -> None:
    """
    If a row exists in LOOKUP_TABLE but not in WRITE_TABLE, copy it over (testing mode).
    """
    if _id_exists(cur, WRITE_TABLE, tx_id):
        return

    cur.execute(f"SELECT * FROM {LOOKUP_TABLE} WHERE id = %s LIMIT 1", (tx_id,))
    row = cur.fetchone()
    if row is None:
        return

    # fetch columns in lookup in the same order as SELECT *
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (LOOKUP_TABLE,),
    )
    cols = [r[0] for r in cur.fetchall()]
    if not cols:
        return

    write_cols = set(table_columns(cur, WRITE_TABLE))
    keep_cols = [c for c in cols if c in write_cols]
    if not keep_cols:
        return

    # row is a sequence aligned to cols
    idx = {c: i for i, c in enumerate(cols)}
    values = [row[idx[c]] for c in keep_cols]

    col_sql = ", ".join(keep_cols)
    ph = qmarks(len(keep_cols))
    cur.execute(f"INSERT INTO {WRITE_TABLE} ({col_sql}) VALUES ({ph})", values)

def next_id_for_base(cur, table: str, base: str) -> str:
    like = f"{base}_%"
    cur.execute(f"SELECT id FROM {table} WHERE id LIKE %s", (like,))
    rows = cur.fetchall()
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
# Pending email cleanup (Postgres rewrite)
# ============================================================

def delete_stale_pending_email(cur, table: str, account_id: int, reference_date, days: int = 5) -> int:
    """
    Deletes Pending+email rows for THIS account whose purchaseDate is older than
    (reference_date - days). purchaseDate stored as mm/dd/yy or mm/dd/yyyy or unknown.
    """
    cutoff_date = (reference_date - timedelta(days=days))

    purchase_d = date_from_text_expr("purchaseDate")

    sql = f"""
    DELETE FROM {table}
    WHERE account_id = %s
      AND status = 'Pending'
      AND source = 'email'
      AND (
        {purchase_d} IS NULL
        OR {purchase_d} <= %s::date
      )
    """
    cur.execute(sql, (account_id, cutoff_date))
    return cur.rowcount


# ============================================================
# Matching logic (placeholder changes only)
# ============================================================

def find_existing_match_pending_email(cur, table: str, account_id: int, amount: float, purchase_d, merchant: str, window_days: int = 4):
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y")
             for delta in range(-window_days, window_days + 1)]
    ph = qmarks(len(dates))

    cur.execute(
        f"""
        SELECT id, postedDate, purchaseDate, amount, merchant
        FROM {table}
        WHERE account_id = %s
          AND amount = %s
          AND TRIM(purchaseDate) IN ({ph})
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        """,
        [account_id, float(amount), *dates],
    )
    candidates = cur.fetchall()

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None

    for row in candidates:
        db_merch = (row[4] if len(row) > 4 else "") or ""
        db_clean = clean_spaces(db_merch).lower()
        csv_clean = clean_spaces(merchant or "").lower()

        db_is_unknown = db_clean in ("", "unknown")
        csv_is_unknown = csv_clean in ("", "unknown")

        if (db_is_unknown or is_generic_payment_merchant(db_clean)) and not csv_is_unknown:
            return row

        db_toks = merchant_tokens(db_clean)
        csv_toks = merchant_tokens(csv_clean)

        db_is_weak = (len(db_toks) < 2)
        csv_is_weak = (len(csv_toks) < 2)

        if db_is_weak and not csv_is_weak:
            return row

        if merchants_similar(db_clean, csv_clean):
            return row

    return None


def find_tip_adjust_match_pending_email(cur, table: str, account_id: int, csv_amount: float, csv_merchant: str, purchase_d, window_days: int = 4):
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y")
             for delta in range(-window_days, window_days + 1)]
    ph = qmarks(len(dates))

    cur.execute(
        f"""
        SELECT id, amount, merchant, postedDate, purchaseDate
        FROM {table}
        WHERE account_id = %s
          AND TRIM(purchaseDate) IN ({ph})
          AND amount IS NOT NULL
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        """,
        [account_id, *dates],
    )
    candidates = cur.fetchall()

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

        if (db_amt_f >= 0) != (csv_amt_f >= 0):
            continue
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


def find_any_match_any_status(cur, table: str, account_id: int, amount: float, purchase_d, merchant: str, window_days: int = 4):
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y")
             for delta in range(-window_days, window_days + 1)]
    ph = qmarks(len(dates))

    cur.execute(
        f"""
        SELECT id, status, source, postedDate, purchaseDate, amount, merchant
        FROM {table}
        WHERE account_id = %s
          AND amount = %s
          AND TRIM(purchaseDate) IN ({ph})
        """,
        [account_id, float(amount), *dates],
    )
    rows = cur.fetchall()

    if not rows:
        return None

    def score(r):
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

    if (best[1] or "") == "Pending" and (best[2] or "") == "email":
        return best
    if score(best) >= 200:
        return best
    return None


# ============================================================
# CORE UPSERT (logic maintained; SQL placeholders changed)
# ============================================================

def upsert_csv_row(
    cur,
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
    if not merchant or purchase == "unknown":
        return ("skipped", None)

    cat = categorize(merchant, rules)
    base = make_base_id(float(amount), purchase, account_id)

    # 1) Only override a Pending+email row if the BASE id matches
    pending_id = find_pending_email_by_base(cur, LOOKUP_TABLE, base)
    if pending_id:
        _copy_row_from_lookup_if_missing(cur, pending_id)
        cur.execute(
            f"""
            UPDATE {WRITE_TABLE}
            SET postedDate   = %s,
                purchaseDate = %s,
                status       = %s,
                merchant     = %s,
                source       = %s,
                amount       = %s,
                category     = %s
            WHERE id = %s
            """,
            (posted, purchase, "Posted", merchant, "CSV", float(amount), cat, pending_id),
        )
        delete_withdrawal_key(pending_id)
        return ("updated", pending_id)

    # 2) Fuzzy pending-email match: same account + amount, purchaseDate within +/- 4 days.
    pending_match = find_existing_match_pending_email(
        cur,
        LOOKUP_TABLE,
        account_id=account_id,
        amount=float(amount),
        purchase_d=purchase_d,
        merchant=merchant,
        window_days=4,
    )
    if pending_match:
        existing_id = pending_match[0]
        _copy_row_from_lookup_if_missing(cur, existing_id)
        cur.execute(
            f"""
            UPDATE {WRITE_TABLE}
            SET postedDate   = %s,
                purchaseDate = %s,
                status       = %s,
                merchant     = %s,
                source       = %s,
                amount       = %s,
                category     = %s
            WHERE id = %s
            """,
            (posted, purchase, "Posted", merchant, "CSV", float(amount), cat, existing_id),
        )
        delete_withdrawal_key(existing_id)
        return ("updated", existing_id)

    # 3) Tip adjust: update only Pending+email rows (amount increases)
    if allow_tip_adjust:
        tip_match = find_tip_adjust_match_pending_email(
            cur,
            LOOKUP_TABLE,
            account_id=account_id,
            csv_amount=float(amount),
            csv_merchant=merchant,
            purchase_d=purchase_d,
            window_days=4
        )
        if tip_match:
            existing_id = tip_match[0]
            _copy_row_from_lookup_if_missing(cur, existing_id)
            cur.execute(
                f"""
                UPDATE {WRITE_TABLE}
                SET posteddate   = %s,
                    purchasedate = %s,
                    status       = %s,
                    merchant     = %s,
                    source       = %s,
                    amount       = %s,
                    category     = %s
                WHERE id = %s
                """,
                (posted, purchase, "Posted", merchant, "CSV", float(amount), cat, existing_id),
            )
            delete_withdrawal_key(existing_id)
            return ("updated", existing_id)

    # 4) ALWAYS INSERT (duplicates become _1, _2, ...)
    tx_id = next_seq_id(cur, WRITE_TABLE, base)

    payload = {
        "id": tx_id,
        "status": "Posted",
        "purchasedate": purchase,
        "posteddate": posted,
        "amount": float(amount),
        "merchant": merchant,
        "time": DEFAULTS["time"],
        "source": "CSV",
        "account_id": account_id,
        "category": cat,
    }

    insert_keys = [k for k in payload.keys() if k in tx_cols]
    if not insert_keys:
        raise RuntimeError(f"No matching columns found in {WRITE_TABLE} table.")

    cols_sql = ", ".join(insert_keys)
    ph = qmarks(len(insert_keys))
    values = [payload[k] for k in insert_keys]
    if "steam" in (merchant or "").lower():
        print("STEAM ACTION:", "insert", "id=", tx_id, "base=", base, "purchase=", purchase, "amount=", amount)
    if payload["id"] == "3_012626_21.64":
        print("INSERT PAYLOAD:", payload)
        cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port()")
        print("DB TARGET:", cur.fetchone())

    try:
        cur.execute(f"INSERT INTO {WRITE_TABLE} ({cols_sql}) VALUES ({ph})", values)
    except Exception:
        # collision fallback
        payload["id"] = next_id_for_base(cur, WRITE_TABLE, base)
        values = [payload[k] for k in insert_keys]
        cur.execute(f"INSERT INTO {WRITE_TABLE} ({cols_sql}) VALUES ({ph})", values)

    return ("inserted", payload["id"])


# ============================================================
# Per-bank importers (same logic; DB connect swapped)
# ============================================================

def clean_amex_merchant(raw_desc: str, city_state_field: str) -> str:
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

def _to_float(s: str) -> float:
    return float(str(s or "0").replace(",", "").strip())

def inverse_if(flag: bool, amt: float) -> float:
    return (-amt) if flag else amt

def normalize_amount_navy(amount_str: str, indicator: str) -> float:
    """
    navyfcu_bills_7613 / navyfcu_main_9338:
      - if indicator is Credit => inverse value
      - else => same value
    """
    amt = _to_float(amount_str)
    is_credit = (indicator or "").strip().lower() == "credit"
    return inverse_if(is_credit, amt)

def import_amex_csv(conn, csv_path: Path, account_id: int) -> Dict[str, int]:
    cur = conn.cursor()

    start_date, end_date, last_posted = get_import_window(cur, account_id)
    print("IMPORT WINDOW =", start_date, "to", end_date, "| last_posted =", last_posted)

    tx_cols = set(table_columns(cur, WRITE_TABLE))
    rules = load_category_rules(cur)

    inserted = updated = skipped = 0
    latest_file_date = None

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_raw = (row.get("Date") or "").strip()
            d = parse_mmddyyyy(date_raw)
            if d:
                latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            if not date_in_window(d, start_date, end_date):
                skipped += 1
                continue
            if not d:
                skipped += 1
                continue

            purchase_d = d
            purchase = d.strftime("%m/%d/%y")
            posted = purchase

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
        deleted = delete_stale_pending_email(cur, WRITE_TABLE, account_id, reference_date=min(latest_file_date, end_date))
        print(f"Deleted stale pending email rows: {deleted}")

    return {"inserted": inserted, "updated": updated, "skipped": skipped}

def import_capitalone_csv(conn, csv_path: Path, account_id: int, job_name: str) -> Dict[str, int]:
    cur = conn.cursor()

    start_date, end_date, last_posted = get_import_window(cur, account_id)
    print("IMPORT WINDOW =", start_date, "to", end_date, "| last_posted =", last_posted)

    tx_cols = set(table_columns(cur, WRITE_TABLE))
    rules = load_category_rules(cur)

    inserted = updated = skipped = 0
    latest_file_date = None

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

            for d in (purchase_d, posted_d):
                if d:
                    latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            eff_d = _row_effective_date(purchase_d, posted_d)
            if not date_in_window(eff_d, start_date, end_date):
                skipped += 1
                continue

            effective_purchase_d = purchase_d or posted_d
            if not effective_purchase_d:
                skipped += 1
                continue

            purchase = effective_purchase_d.strftime("%m/%d/%y")
            posted = (posted_d.strftime("%m/%d/%y") if posted_d else purchase)  # keep your “amex-style fallback”

            merchant_raw = (row.get("Description") or row.get("Transaction Description") or "").strip()
            merchant = clean_spaces(merchant_raw)
            if not merchant:
                skipped += 1
                continue

            amt_str = (row.get("Transaction Amount") or "0").strip()
            tx_type = (row.get("Transaction Type") or "").strip().lower()

            try:
                amt = _to_float(amt_str)  # SAME value by default
            except ValueError:
                skipped += 1
                continue

            # Per your rules:
            # - capitalOne_9691 -> same value (no inversion at all)
            # - capitalOne_1047 -> if Transaction Type is Credit, inverse
            # - capitalOne_8424 -> debit same, credit inverse
            name = (job_name or "").lower()

            if "capitalone_9691" in name:
                pass  # same value always
            elif "capitalone_1047" in name or "capitalone_8424" in name:
                amt = inverse_if(tx_type == "credit", amt)
            else:
                # safe default for other Capital One files (keeps your old behavior but via inverse)
                amt = inverse_if(tx_type == "credit", amt)

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
                allow_broad_override=False,
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    print("CAPITALONE latest_file_date =", latest_file_date)
    if latest_file_date:
        deleted = delete_stale_pending_email(cur, WRITE_TABLE, account_id, reference_date=min(latest_file_date, end_date))
        print(f"Deleted stale pending email rows: {deleted}")

    return {"inserted": inserted, "updated": updated, "skipped": skipped}

def import_discover_csv(conn, csv_path: Path, account_id: int) -> Dict[str, int]:
    cur = conn.cursor()

    start_date, end_date, last_posted = get_import_window(cur, account_id)
    print("IMPORT WINDOW =", start_date, "to", end_date, "| last_posted =", last_posted)

    tx_cols = set(table_columns(cur, WRITE_TABLE))
    rules = load_category_rules(cur)

    inserted = updated = skipped = 0
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

            for d in (trans_d, post_d):
                if d:
                    latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            eff_d = _row_effective_date(trans_d, post_d)
            if not date_in_window(eff_d, start_date, end_date):
                skipped += 1
                continue

            purchase_d = trans_d or post_d
            if not purchase_d or not desc_raw:
                skipped += 1
                continue

            purchase = purchase_d.strftime("%m/%d/%y")
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
                allow_broad_override=False,
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    print("DISCOVER latest_file_date =", latest_file_date)
    if latest_file_date:
        deleted = delete_stale_pending_email(cur, WRITE_TABLE, account_id, reference_date=min(latest_file_date, end_date))
        print(f"Deleted stale pending email rows: {deleted}")

    return {"inserted": inserted, "updated": updated, "skipped": skipped}

def import_amex_hysa_csv(conn, csv_path: Path, account_id: int) -> Dict[str, int]:
    cur = conn.cursor()

    start_date, end_date, last_posted = get_import_window(cur, account_id)
    print("IMPORT WINDOW =", start_date, "to", end_date, "| last_posted =", last_posted)

    tx_cols = set(table_columns(cur, WRITE_TABLE))
    rules = load_category_rules(cur)

    inserted = updated = skipped = 0
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

            d = parse_mmddyyyy(date_raw)
            if d:
                latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            if not date_in_window(d, start_date, end_date):
                skipped += 1
                continue
            if not d:
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
                allow_broad_override=False,
            )

            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    if latest_file_date:
        deleted = delete_stale_pending_email(cur, WRITE_TABLE, account_id, reference_date=min(latest_file_date, end_date))
        print(f"Deleted stale pending email rows: {deleted}")

    return {"inserted": inserted, "updated": updated, "skipped": skipped}

def import_navy_csv(conn, csv_path: Path, account_id: int, allow_tip_adjust: bool, allow_broad_override: bool) -> Dict[str, int]:
    cur = conn.cursor()

    start_date, end_date, last_posted = get_import_window(cur, account_id)
    print("IMPORT WINDOW =", start_date, "to", end_date, "| last_posted =", last_posted)

    tx_cols = set(table_columns(cur, WRITE_TABLE))
    rules = load_category_rules(cur)

    inserted = updated = skipped = 0
    latest_file_date = None

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        print("NAVY HEADERS:", reader.fieldnames)

        for row in reader:
            purchase_raw = (
                row.get("Transaction Date")
                or row.get("TransactionDate")
                or row.get("Date")
                or row.get("Trans Date")
                or row.get("Posted Date")
                or ""
            ).strip()

            posted_raw = (
                row.get("Posted Date")
                or row.get("Post Date")
                or row.get("Posting Date")
                or row.get("PostedDate")
                or ""
            ).strip()

            purchase_d = parse_mmddyyyy(purchase_raw)
            posted_d = parse_mmddyyyy(posted_raw) if posted_raw else None

            if not purchase_d and not posted_d:
                skipped += 1
                continue

            for d in (purchase_d, posted_d):
                if d:
                    latest_file_date = d if latest_file_date is None else max(latest_file_date, d)

            eff_d = _row_effective_date(purchase_d, posted_d)
            if not date_in_window(eff_d, start_date, end_date):
                skipped += 1
                continue

            effective_purchase_d = purchase_d or posted_d
            if not effective_purchase_d:
                skipped += 1
                continue

            purchase = effective_purchase_d.strftime("%m/%d/%y")
            posted = posted_d.strftime("%m/%d/%y") if posted_d else "unknown"

            merchant_raw = (
                row.get("Description")
                or row.get("Transaction Description")
                or row.get("Merchant")
                or row.get("Payee")
                or ""
            ).strip()
            merchant = clean_spaces(merchant_raw)
            if "steam" in (merchant or "").lower():
                print("STEAM CSV:", posted_raw, purchase_raw, "=>", posted, purchase, "amt_str=", amt_str, "indicator=",
                      indicator, "amt=", amt)

            # show any row that mentions TRIDENT (regardless of which column it's in)
            joined = " | ".join([str(v) for v in row.values() if v is not None])
            if "TRIDENT" in joined.upper():
                print("TRIDENT ROW RAW DICT:", row)

            # show why it was skipped (merchant/date)
            if not merchant:
                if "TRIDENT" in joined.upper():
                    print("TRIDENT SKIPPED: merchant not found by header mapping")

            if not merchant:
                skipped += 1
                continue

            amt_str = (
                row.get("Amount")
                or row.get("Transaction Amount")
                or row.get("TransactionAmount")
                or "0"
            )
            indicator = (
                row.get("Credit/Debit Indicator")
                or row.get("Credit Debit Indicator")
                or row.get("Credit/Debit")
                or row.get("Type")
                or ""
            )

            try:
                amt = normalize_amount_navy(str(amt_str).strip(), str(indicator).strip())
            except Exception:
                skipped += 1
                continue

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
    if latest_file_date:
        deleted = delete_stale_pending_email(cur, WRITE_TABLE, account_id, reference_date=min(latest_file_date, end_date))
        print(f"Deleted stale pending email rows: {deleted}")

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# ============================================================
# MAIN (press Run, no args)
# ============================================================

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default=None, help="Directory containing uploaded CSVs renamed to expected filenames")
    args = ap.parse_args()

    jobs = build_jobs(args.input_dir)

    conn = get_conn()
    try:
        for job in jobs:
            name = job["name"].lower()
            csv_path: Path = job["csv"]
            account_id: int = job["account_id"]

            if not csv_path.exists():
                print(f"SKIP {job['name']}: CSV not found -> {csv_path}")
                continue

            print(f"\n=== RUNNING JOB: {job['name']} ===")

            if name.startswith("amex_hysa"):
                try:
                    out = import_amex_hysa_csv(conn, csv_path, account_id)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print("\n❌ JOB FAILED:", csv_path)
                    print("   ERROR:", repr(e))
                    raise


            elif name.startswith("amex"):
                out = import_amex_csv(conn, csv_path, account_id)

            elif name.startswith("capitalone"):
                out = import_capitalone_csv(conn, csv_path, account_id, job_name=job["name"])

            elif name.startswith("discover"):
                out = import_discover_csv(conn, csv_path, account_id)

            else:
                if name == "main":
                    out = import_navy_csv(conn, csv_path, account_id, allow_tip_adjust=True, allow_broad_override=False)
                else:
                    out = import_navy_csv(conn, csv_path, account_id, allow_tip_adjust=False, allow_broad_override=False)

            conn.commit()
            print(f"JOB={job['name']} FILE={csv_path} account_id={account_id}")
            print(out)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
