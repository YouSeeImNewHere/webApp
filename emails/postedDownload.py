from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from db import with_db_cursor, query_db, open_pool, close_pool
from transactionHandler import makeKey, assign_category

# ============================================================
# CONFIG
# ============================================================

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

DEFAULTS = {"status": "Posted", "time": "unknown", "source": "CSV"}

PHONE_RX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

TIP_MAX_ABS = 50.0
TIP_PCT_SMALL = 0.75   # < $20 purchases can jump more (bars/coffee/food)
TIP_PCT_MED   = 0.50   # $20–$60
TIP_PCT_LARGE = 0.35   # >= $60

TARGET_YEAR = 2025

# ============================================================
# WITHDRAWAL KEY CLEANUP
# ============================================================

WITHDRAWAL_KEYS_FILE = Path("withdrawalKey_test.json")

PAYMENT_GENERIC_TOKENS = {
    "payment", "pay", "thank", "thanks", "thankyou", "you",
    "mobile", "autopay", "online", "electronic", "transfer",
}


def clean_spaces(s: str) -> str:
    s = (s or "").strip()
    s = PHONE_RX.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" -")


STOP_TOKENS = {
    "debit", "dc", "credit", "pos", "purchase", "card", "visa", "mastercard",
    "auth", "pending", "ach", "transaction",
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


def is_generic_payment_merchant(s: str) -> bool:
    s = clean_spaces(s).lower()
    if not s or s in ("unknown",):
        return True
    s = s.replace("thank you", "thankyou").replace("thanks", "thank")
    toks = set(merchant_tokens(s))
    return bool(toks) and (toks <= PAYMENT_GENERIC_TOKENS)


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


def to_mmddyy(date_like: str) -> str:
    d = parse_mmddyyyy(date_like)
    return d.strftime("%m/%d/%y") if d else "unknown"


def _id_exists(table: str, tx_id: str) -> bool:
    rows = query_db(f"SELECT 1 FROM {table} WHERE id = %s LIMIT 1", (tx_id,))
    return bool(rows)


def _pick_pending_match_exact(account_id: int, amount: float, purchase_d, merchant: str, window_days: int = 4) -> Optional[str]:
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y") for delta in range(-window_days, window_days + 1)]

    rows = query_db(
        f"""
        SELECT id, merchant
        FROM {LOOKUP_TABLE}
        WHERE account_id = %s
          AND amount = %s
          AND purchasedate = ANY(%s)
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        """,
        (account_id, float(amount), dates),
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]["id"]

    csv_clean = clean_spaces(merchant or "").lower()
    for r in rows:
        db_clean = clean_spaces((r.get("merchant") or "")).lower()
        db_is_unknown = db_clean in ("", "unknown")
        if db_is_unknown or is_generic_payment_merchant(db_clean):
            return r["id"]
        if merchants_similar(db_clean, csv_clean):
            return r["id"]
    return rows[0]["id"]


def _pick_pending_match_tip(account_id: int, csv_amount: float, purchase_d, csv_merchant: str, window_days: int = 4) -> Optional[str]:
    if not purchase_d:
        return None

    dates = [(purchase_d + timedelta(days=delta)).strftime("%m/%d/%y") for delta in range(-window_days, window_days + 1)]

    rows = query_db(
        f"""
        SELECT id, amount, merchant
        FROM {LOOKUP_TABLE}
        WHERE account_id = %s
          AND purchasedate = ANY(%s)
          AND COALESCE(status,'') = 'Pending'
          AND COALESCE(source,'') = 'email'
        """,
        (account_id, dates),
    )
    if not rows:
        return None

    csv_m = clean_spaces(csv_merchant or "").lower()
    for r in rows:
        try:
            db_amount = float(r.get("amount") or 0.0)
        except Exception:
            continue

        if db_amount <= 0 or csv_amount <= 0:
            continue

        if csv_amount < db_amount:
            continue

        diff = csv_amount - db_amount
        if diff <= 0:
            continue

        # tip-ish thresholds
        if abs(diff) > TIP_MAX_ABS:
            continue

        pct = diff / max(db_amount, 0.01)
        if db_amount < 20 and pct > TIP_PCT_SMALL:
            continue
        if 20 <= db_amount < 60 and pct > TIP_PCT_MED:
            continue
        if db_amount >= 60 and pct > TIP_PCT_LARGE:
            continue

        db_m = clean_spaces((r.get("merchant") or "")).lower()
        if db_m in ("", "unknown") or is_generic_payment_merchant(db_m):
            return r["id"]
        if merchants_similar(db_m, csv_m):
            return r["id"]

    return None


def _ensure_unique_id(base_id: str, table: str) -> str:
    if not _id_exists(table, base_id):
        return base_id
    # bump seq suffix
    # base_id format: "{accountid}_{mmddyyNoSlashes}_{amount}_{seq}"
    for seq in range(1, 500):
        parts = base_id.split("_")
        if len(parts) >= 4:
            parts[-1] = str(seq)
            cand = "_".join(parts)
        else:
            cand = f"{base_id}_{seq}"
        if not _id_exists(table, cand):
            return cand
    return f"{base_id}_{int(datetime.now().timestamp())}"


def upsert_posted_row(
    *,
    tx_id: str,
    account_id: int,
    amount: float,
    merchant: str,
    purchase_mmddyy: str,
    posted_mmddyy: str,
    time: str = "unknown",
    source: str = "CSV",
):
    with with_db_cursor() as (conn, cur):
        category = assign_category(cur, merchant)
        cur.execute(
            f"""
            INSERT INTO {WRITE_TABLE}
              (id, status, purchasedate, posteddate, amount, merchant, time, source, account_id, category)
            VALUES
              (%s, 'Posted', %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              status = 'Posted',
              purchasedate = EXCLUDED.purchasedate,
              posteddate   = EXCLUDED.posteddate,
              amount       = EXCLUDED.amount,
              merchant     = EXCLUDED.merchant,
              time         = CASE
                              WHEN {WRITE_TABLE}.time IS NULL OR {WRITE_TABLE}.time = 'unknown'
                              THEN EXCLUDED.time
                              ELSE {WRITE_TABLE}.time
                             END,
              source       = EXCLUDED.source,
              account_id   = EXCLUDED.account_id,
              category     = CASE
                              WHEN {WRITE_TABLE}.category IS NULL OR btrim({WRITE_TABLE}.category) = ''
                              THEN EXCLUDED.category
                              ELSE {WRITE_TABLE}.category
                             END
            """,
            (tx_id, purchase_mmddyy, posted_mmddyy, float(amount), merchant, time, source, int(account_id), category),
        )
        conn.commit()


def import_generic_csv(job_name: str, csv_path: Path, account_id: int):
    if not csv_path.exists():
        print(f"[{job_name}] missing CSV: {csv_path}")
        return

    # naive generic reader: expects columns: Date, Description, Amount, Type(optional), Posted(optional)
    # If your bank formats differ, keep using your existing parsers and just call upsert_posted_row().
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"[{job_name}] empty CSV")
        return

    for r in rows:
        raw_date = (r.get("Date") or r.get("Transaction Date") or r.get("Posted Date") or "").strip()
        raw_posted = (r.get("Posted Date") or r.get("Post Date") or raw_date).strip()
        raw_desc = (r.get("Description") or r.get("Merchant") or r.get("Name") or "").strip()
        raw_amt = (r.get("Amount") or r.get("Transaction Amount") or "").strip()

        d = parse_mmddyyyy(raw_date)
        pd = parse_mmddyyyy(raw_posted) or d
        if not d or raw_amt == "":
            continue

        try:
            amt = float(str(raw_amt).replace("$", "").replace(",", ""))
        except Exception:
            continue

        purchase_mmddyy = d.strftime("%m/%d/%y")
        posted_mmddyy = pd.strftime("%m/%d/%y") if pd else purchase_mmddyy

        # base ID from date+amount
        base_id = makeKey(f"{amt:.2f}", purchase_mmddyy, account_id=account_id)

        # prefer re-using pending email id if it exists (so CSV 'posts' the pending row)
        pending_id = _pick_pending_match_exact(account_id, amt, d, raw_desc)
        if not pending_id:
            pending_id = _pick_pending_match_tip(account_id, amt, d, raw_desc)

        tx_id = pending_id or _ensure_unique_id(base_id, WRITE_TABLE)

        upsert_posted_row(
            tx_id=tx_id,
            account_id=account_id,
            amount=amt,
            merchant=raw_desc or "unknown",
            purchase_mmddyy=purchase_mmddyy,
            posted_mmddyy=posted_mmddyy,
            time=DEFAULTS["time"],
            source=DEFAULTS["source"],
        )

    print(f"[{job_name}] imported {len(rows)} rows")


def run_all():
    open_pool()
    try:
        for j in IMPORT_JOBS:
            import_generic_csv(j["name"], j["csv"], int(j["account_id"]))
    finally:
        close_pool()


if __name__ == "__main__":
    run_all()
