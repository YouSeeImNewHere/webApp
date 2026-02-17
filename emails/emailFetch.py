import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import os
import time
from pathlib import Path
from dotenv import load_dotenv
import re
import html
import requests, json, hashlib

from .email_handlers import *  # handlers + account constants (still used for inserts)
from db import with_db_cursor, query_db, open_pool, close_pool

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WEBAPP_URL = os.getenv("WEBAPP_URL") or ""
NOTIF_SECRET = os.getenv("NOTIF_SECRET") or ""
DEBUG = (os.getenv("EMAILFETCH_DEBUG") or "").lower() in ("1", "true", "yes")
BATCH_SIZE = 200
PUSHOVER_USER = ""
PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""
MAILBOXES = ["INBOX"]


def _lookup_pushover_user_key_from_db(email_addr: str) -> str:
    e = (email_addr or "").strip().lower()
    if not e:
        return ""
    try:
        with with_db_cursor() as (_, cur):
            cur.execute(
                """
                SELECT pushover_user_key
                FROM users
                WHERE lower(email) = lower(%s)
                LIMIT 1
                """,
                (e,),
            )
            row = cur.fetchone() or {}
            return ((row.get("pushover_user_key") or "").strip())
    except Exception:
        return ""

def in_allowed_window():
    tz = ZoneInfo("America/Los_Angeles")
    now = datetime.now(tz)

    # 0=Mon ... 5=Sat, 6=Sun
    if now.weekday() in (5, 6):
        return True  # ✅ stay awake all weekend

    hour = now.hour

    # Allowed windows (24h clock)
    in_morning = 5 <= hour < 7
    in_midday = 10 <= hour < 12
    in_evening = 16 <= hour < 23

    return in_morning or in_midday or in_evening

def wake_web_app():
    url = os.getenv("WEBAPP_URL")  # set in Render env vars
    try:
        requests.get(f"{url}/health", timeout=30)
        print("Web app wake ping sent")
    except Exception as e:
        print("Wake ping failed:", e)


# ============================================================
# DEBUG
# ============================================================

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[emailFetch {ts}] {msg}", flush=True)
def dbg(msg: str):
    if DEBUG:
        log(msg)
def dbg_header(imap_id, subject, sender, date, key):
    if not DEBUG:
        return
    dbg("--------------------------------------------------")
    dbg(f"📧 EMAIL FOUND")
    dbg(f"IMAP ID: {imap_id}")
    dbg(f"Subject: {subject}")
    dbg(f"From: {sender}")
    dbg(f"Date: {date}")
    dbg(f"Dedupe key: {key}")
def dbg_notify_status(subject, rule_name, inserted, fp=None, reason=""):
    if not DEBUG:
        return
    dbg("🔔 NOTIFY STATUS")
    dbg(f"  subject: {subject}")
    dbg(f"  rule: {rule_name}")
    dbg(f"  inserted: {inserted}")
    if fp:
        dbg(f"  fp: {fp}")
    if reason:
        dbg(f"  reason: {reason}")
def dbg_dump_body_on_no_rule(subject: str, sender: str, imap_id: str, body: str, limit: int = 6000):
    """
    If subject matched but no RULES matched, dump body (truncated).
    """
    if not DEBUG:
        return

    b = (body or "").strip()
    if not b:
        dbg(f"🧾 BODY DUMP (empty) | imap_id={imap_id} | subject={subject} | from={sender}")
        return

    if len(b) > limit:
        dbg(f"🧾 BODY DUMP (truncated to {limit} chars) | imap_id={imap_id} | subject={subject} | from={sender}")
        dbg("----- BODY START -----")
        dbg(b[:limit])
        dbg("----- BODY END (TRUNCATED) -----")
    else:
        dbg(f"🧾 BODY DUMP | imap_id={imap_id} | subject={subject} | from={sender}")
        dbg("----- BODY START -----")
        dbg(b)
        dbg("----- BODY END -----")

def dbg_rule_attempt(rule_name):
    if DEBUG:
        dbg(f"🔎 Testing rule: {rule_name}")
def dbg_rule_match(rule_name):
    if DEBUG:
        dbg(f"✅ RULE MATCHED: {rule_name}")
def dbg_rule_no_match(rule_name):
    if DEBUG:
        dbg(f"❌ Rule did not match: {rule_name}")
def dbg_handler_result(result):
    if not DEBUG:
        return
    if not result:
        dbg("⚠️ Handler returned None")
        return
    dbg(f"🧾 Handler result: inserted={result.get('inserted')} account={result.get('account_id')} merchant={result.get('merchant')} amount={result.get('amount')}")
def dbg_notification_decision(reason):
    if DEBUG:
        dbg(f"🔔 Notification decision: {reason}")

class Timer:
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.t0 = time.perf_counter()

    def __exit__(self, *_):
        dt = (time.perf_counter() - self.t0) * 1000
        dbg(f"{self.label} took {dt:.1f} ms")

# ============================================================
# PUSHOVER (centralized)
# Triggers only when a NEW email matches a rule AND handler succeeds.
# ============================================================

def pushover_enabled() -> bool:
    return bool(PUSHOVER_USER.strip()) and bool(PUSHOVER_TOKEN.strip())

def send_pushover(title: str, message: str):
    """
    Sends a Pushover notification. Never raises (logs failures instead).
    """
    global PUSHOVER_USER
    if not PUSHOVER_USER:
        PUSHOVER_USER = _lookup_pushover_user_key_from_db(os.getenv("GMAIL_ADDRESS") or "")

    if not pushover_enabled():
        log("⚠️ Pushover not configured (missing users.pushover_user_key or PUSHOVER_API_TOKEN)")
        return

    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_TOKEN,
                "user": PUSHOVER_USER,
                "title": title[:250],
                "message": message[:1024],
            },
            timeout=10,
        )
        if r.status_code != 200:
            log(f"⚠️ Pushover failed: HTTP {r.status_code} | {r.text[:200]}")
        else:
            dbg("✅ Pushover sent")
    except Exception as e:
        log(f"⚠️ Pushover exception: {e}")

def push_error(kind: str, subject: str, body: str):
    sig = _stable_err_sig(kind, subject, body)
    dedupe_key = f"emailFetch:{kind}:{sig}"

    inserted = push_db_notification(kind=kind, subject=subject, body=body, dedupe_key=dedupe_key)

    if inserted:
        send_pushover(
            title="⚠️ emailFetch error",
            message=f"{subject}\n\n{(body or '')[:700]}",
        )
    else:
        dbg("🔕 Error deduped → skipping pushover")


# --- DB notifications (write directly to notifications table) ---
def ensure_notifications_table_pg():
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

def push_db_notification(kind: str, subject: str, body: str, dedupe_key: str, sender: str = "emailFetch"):
    try:
        ensure_notifications_table_pg()
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO notifications (kind, dedupe_key, subject, sender, body, is_read, dismissed)
                VALUES (%s, %s, %s, %s, %s, FALSE, FALSE)
                ON CONFLICT (dedupe_key) DO NOTHING
                RETURNING id
                """,
                (kind, dedupe_key, subject[:250], sender[:250], (body or "")[:8000]),
            )
            row = cur.fetchone()
            conn.commit()
            return bool(row)  # True only if inserted
    except Exception:
        return False


# ============================================================
# SUBJECT FILTER (ORIGINAL)
# ============================================================
SUBJECTS = [
    "Transaction Notification",
    "Withdrawal Notification",
    "Large Purchase Approved",
    "Debit Card Purchase",
    "A new transaction was charged to your account",
    "Transaction Alert",
    "Deposit Notification",
    "We processed your payment",
    "We've received your payment",
    "Your payment to",
]

def subject_matches(subject: str) -> bool:
    if not subject:
        return False
    lower = subject.lower()
    return any(keyword.lower() in lower for keyword in SUBJECTS)

def debug_subject(subject: str, matched: bool):
    """
    Debug logging for subject filtering.
    Shows every subject and whether it matched our SUBJECTS list.
    """
    if not DEBUG:
        return

    if matched:
        dbg(f"📨 SUBJECT MATCHED: {subject}")
    else:
        dbg(f"📭 SUBJECT SKIPPED: {subject}")

# ============================================================
# ORIGINAL REGEXES (DO NOT MODIFY GROUPS)
# ============================================================
navyFedRegex = re.compile(
    r"The transaction for (\$[\d,]+\.\d{2}) was approved for your (credit|debit) card ending in \d{4} "
    r"at (.*) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{3} "
    r"on ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2})"
)

navyFedWithdrawalRegex = re.compile(
    r"(\$[\d,]+\.\d{2}) was withdrawn from your Active Duty Checking account ending in \d{4}. "
    r"As of ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2}) "
    r"at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{2}"
)

navyFedDepositRegex = re.compile(
    r"(\$[\d,]+\.\d{2}) .* of (\d\d\/\d\d\/\d\d) at (\d\d:\d\d \w+)"
)

navyFedCreditHoldRegex = re.compile(
    r"at (.*) at (\d\d:\d\d \w+) .* on (\d\d\/\d\d\/\d\d)"
)

americanExpressRegex = re.compile(
    r"(?s)Account Ending:\s*\(?(\d+)\)?"
    r".*?\s([A-Z0-9][A-Z0-9 &'.,\-*/]+?)\s+"
    r"\$([\d,]+\.\d{2})\*?\s+"
    r"(?:[A-Za-z]{3},\s*)?([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
)

capitalOneDebitRegex = re.compile(
    r"Amount: (\$[\d,]+\.\d{2})\r?\n.* - (.*)\r?\n"
    r"Date: ((?:January|February|March|April|May|June|July|August|September|October|November|December) "
    r"\d{1,2}, \d{4})"
)

capitalOneCreditRegex = re.compile(
    r"As requested, we're notifying you that on "
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December) "
    r"\d{1,2}, \d{4}), at (.*), .* of (\$[\d,]+\.\d{2})"
)

discoveryRegex = re.compile(
    r"Transaction Date:: "
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December) "
    r"\d{1,2}, \d{4})\s*"
    r"Merchant: (.*)\s*"
    r"Amount: (\$[\d,]+\.\d{2})"
)
discoverAlertRegex = re.compile(
    r"(?si)"
    r"Merchant:\s*(.*?)\s*"
    r"Date:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\s*"
    r"Amount:\s*\$([\d,]+\.\d{2})"
)


amexPaymentRegex = re.compile(
    r"(?s)Account Ending:\s*\(?(\d+)\)?"
    r".*?Payment amount:\s*\(?\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})\)?"
    r".*?Processed on:\s*\(?([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\)?"
)

discoverPaymentRegex = re.compile(
    r"Your Payment of\s*\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})\s*"
    r"posted to your account on\s*"
    r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"
)

capOnePaymentRegex = re.compile(
    r"(?s)Payment amount:\s*\(?\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})\)?\s*.*?"
    r"Posted date:\s*\(?([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\)?"
)

navyFedZelleRegex = re.compile(
    r"(?s)Amount\s*\$([\d,]+\.\d{2}).*?"
    r"To\s*([A-Za-z][A-Za-z\s'.-]+)\s*\([^)]+\).*?"
    r"As of\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"
)

# ============================================================
# RULES — EXACT HANDLER COMPATIBILITY
# ============================================================
RULES = [
    {"name": "navy credit", "regex": navyFedRegex, "handler": navyFedCard},
    {"name": "navy withdrawal", "regex": navyFedWithdrawalRegex, "handler": navyFedWithdrawal},
    {"name": "navy deposit", "regex": navyFedDepositRegex, "handler": navyFedDeposit},
    {"name": "navy credit hold", "regex": navyFedCreditHoldRegex, "handler": navyFedCreditHold},

    {"name": "american express", "regex": americanExpressRegex, "handler": americanExpress},

    {"name": "capital one debit", "regex": capitalOneDebitRegex, "handler": capitalOneDebit},
    {"name": "capital one credit", "regex": capitalOneCreditRegex, "handler": capitalOneCredit},

    {"name": "discovery credit", "regex": discoveryRegex, "handler": discovery},
    {"name": "discover alert", "regex": discoverAlertRegex, "handler": discoverAlert},


    {"name": "amex payment", "regex": amexPaymentRegex, "handler": amexPayment},
    {"name": "discover payment", "regex": discoverPaymentRegex, "handler": discoverPayment},
    {"name": "capital one payment", "regex": capOnePaymentRegex, "handler": capitalOnePayment},

    {"name": "navy federal zelle", "regex": navyFedZelleRegex, "handler": navyFedZelle},
]


# ============================================================
# DB
# ============================================================
def pending_exists(pending_table: str, k: str) -> bool:
    if not k:
        return False
    rows = query_db(f"SELECT 1 FROM {pending_table} WHERE k=%s LIMIT 1", (k,))
    return bool(rows)

def try_resolve_pending_and_notify(pending_table: str, fp: str, account_id: int, merchant: str, amt, date_str: str, time_str: str):
    """
    If a pending 'unknown merchant' exists for this fp, and we now have a real merchant,
    send pushover + mark_notified + delete pending.
    """
    if not fp:
        return False
    if not pushover_enabled():
        return False
    if already_notified(fp):
        return False
    if not pending_exists(pending_table, fp):
        return False

    m = (merchant or "").strip()
    if not m or m.lower() in ("unknown", "unknown merchant"):
        return False

    bank, card = get_bank_card_by_account_id(int(account_id))
    amt_str = f"${float(amt):.2f}" if amt is not None else "an unknown amount"

    title = "Transaction alert"
    message = f"{bank} {card} was used at {m} for {amt_str} on {date_str} at {time_str}"

    dbg_notification_decision("Resolved pending → sending pushover now")
    send_pushover(title, message)

    mark_notified(fp)
    delete_pending(pending_table, fp)
    return True

def delete_pending(pending_table: str, k: str):
    if not k:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute(f"DELETE FROM {pending_table} WHERE k=%s", (k,))
        conn.commit()

def get_bank_card_by_account_id(account_id: int):
    rows = query_db(
        "SELECT institution AS bank, name AS card FROM accounts WHERE id = %s LIMIT 1",
        (int(account_id),)
    )
    if not rows:
        return ("Your bank", "Card")
    return (rows[0]["bank"], rows[0]["card"])

def get_bank_card_for_transaction(cur, extracted: dict):
    """
    Returns (bank, card) using the most recent transaction matching extracted data.
    """
    if not extracted or not extracted.get("cost"):
        return ("Your bank", "Card")

    cur.execute(
        """
        SELECT a.institution AS bank, a.name AS card
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.amount = %s
        ORDER BY t.id DESC
        LIMIT 1
        """,
        (extracted["cost"],)
    )
    row = cur.fetchone()
    if not row:
        return ("Your bank", "Card")

    return (row["bank"], row["card"])

def ensure_notified_table(name="notified_transactions"):
    with with_db_cursor() as (conn, cur):
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {name} (
                k TEXT PRIMARY KEY,
                notified_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        conn.commit()
def ensure_pending_table(name="pushover_pending"):
    with with_db_cursor() as (conn, cur):
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {name} (
                k TEXT PRIMARY KEY,                 -- tx_fingerprint
                account_id INTEGER NOT NULL,
                amount NUMERIC,
                purchase_date TEXT,
                purchase_time TEXT,
                rule_name TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        conn.commit()

def upsert_pending(name: str, k: str, account_id: int, amount, purchase_date: str, purchase_time: str, rule_name: str):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            INSERT INTO {name} (k, account_id, amount, purchase_date, purchase_time, rule_name)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (k) DO UPDATE SET
              last_seen_at = now(),
              account_id = EXCLUDED.account_id,
              amount = EXCLUDED.amount,
              purchase_date = EXCLUDED.purchase_date,
              purchase_time = EXCLUDED.purchase_time,
              rule_name = EXCLUDED.rule_name
            """,
            (k, int(account_id), amount, purchase_date, purchase_time, rule_name),
        )
        conn.commit()

def _stable_err_sig(kind: str, subject: str, body: str) -> str:
    """
    Turn a noisy error body into a stable signature so repeated failures dedupe.
    Strips changing bits like imap_id, timestamps, numbers.
    """
    s = (body or "")

    # remove obvious run-to-run noise
    s = re.sub(r"imap_id=\d+", "imap_id=?", s)
    s = re.sub(r"\b\d{2}:\d{2}:\d{2}\b", "hh:mm:ss", s)
    s = re.sub(r"\b\d+\b", "N", s)  # numbers → N (aggressive but effective)

    # keep it short and stable
    s = (s.strip()[:500]).lower()

    base = f"{kind}|{subject.lower().strip()}|{s}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]

# ============================================================
# HELPERS
# ============================================================
def decode_hdr(v):
    if not v:
        return ""
    out = []
    for chunk, enc in decode_header(v):
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(str(chunk))
    return "".join(out)

def _html_to_text(s: str) -> str:
    """
    Very lightweight HTML → text:
    - strips scripts/styles
    - removes tags
    - decodes entities
    - normalizes whitespace
    """
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</p\s*>", "\n", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()

def extract_body(msg):
    """
    Prefer text/plain. If only HTML exists, convert HTML to readable text.
    """
    # multipart: choose best part
    if msg.is_multipart():
        plain = None
        html_part = None

        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            try:
                text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                text = payload.decode(errors="ignore")

            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html_part:
                html_part = text

        if plain:
            # If plain is a template with blank fields (Discover does this), use HTML instead.
            if (
                    "Merchant:" in plain and re.search(r"Merchant:\s*\n\s*Date:\s*\n\s*Amount:\s*\n", plain)
                    and html_part
            ):
                return _html_to_text(html_part)
            return plain

        if html_part:
            return _html_to_text(html_part)
        return ""

    # singlepart
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""

    try:
        text = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
    except Exception:
        text = payload.decode(errors="ignore")

    ctype = (msg.get_content_type() or "").lower()
    if ctype == "text/html":
        return _html_to_text(text)
    return text

def dedupe_key(hdr, sender, subject, date, imap_id):
    mid = (hdr.get("Message-ID") or "").lower().strip()
    if mid:
        return mid
    return f"{sender}|{subject}|{date}|{imap_id}".lower()

def parse_money(v):
    if not v:
        return None
    try:
        return float(v.replace("$", "").replace(",", ""))
    except Exception:
        return None

def _norm_amount_for_key(v) -> str:
    """
    Normalize amount so Decimal/float/int all produce a stable string.
    """
    if v is None:
        return ""
    try:
        # Handles Decimal nicely too
        return f"{float(v):.2f}"
    except Exception:
        return str(v).strip()

def tx_fingerprint(account_id: int, amount, purchase_date: str, purchase_time: str) -> str:
    """
    Stable key tying together:
      - Navy withdrawal email (often Unknown merchant)
      - Navy Transaction Notification email (has merchant)
    So we can dedupe notifications at the transaction-level.
    """
    a = int(account_id) if account_id is not None else 0
    amt = _norm_amount_for_key(amount)
    d = (purchase_date or "").strip().lower()
    t = (purchase_time or "").strip().lower()
    base = f"{a}|{amt}|{d}|{t}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:24]

def already_notified(k: str) -> bool:
    if not k:
        return False
    rows = query_db("SELECT 1 FROM notified_transactions WHERE k=%s LIMIT 1", (k,))
    return bool(rows)

def mark_notified(k: str):
    if not k:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "INSERT INTO notified_transactions (k) VALUES (%s) ON CONFLICT (k) DO NOTHING",
            (k,),
        )
        conn.commit()

def flush_pending_notifications(pending_table: str, ttl_minutes: int = 30):
    """
    Resolve any pending "unknown merchant" withdrawals.
    - If a real merchant transaction exists now: notify once and mark_notified
    - If already_notified: delete pending
    - If too old: send fallback Unknown merchant notification once
    """
    # Nothing to do if pushover isn't configured
    if not pushover_enabled():
        return

    tz = ZoneInfo("America/Los_Angeles")
    now = datetime.now(tz)

    with with_db_cursor() as (conn, cur):
        cur.execute(f"""
            SELECT k, account_id, amount, purchase_date, purchase_time, rule_name, created_at
            FROM {pending_table}
            ORDER BY created_at ASC
        """)
        pendings = cur.fetchall() or []

        for p in pendings:
            k = p["k"]

            # If something else already notified this tx, just clear pending.
            if already_notified(k):
                cur.execute(f"DELETE FROM {pending_table} WHERE k=%s", (k,))
                conn.commit()
                continue

            account_id = int(p["account_id"])
            amt = p["amount"]
            d = p["purchase_date"] or ""
            t = p["purchase_time"] or ""

            # Try to find a now-known merchant for this same transaction.
            # Assumes transactions has: account_id, amount, merchant, purchase_date, time, id
            cur.execute(
                """
                SELECT merchant, amount, purchasedate, time
                FROM transactions
                WHERE account_id = %s
                  AND amount = %s
                  AND purchasedate = %s
                  AND time = %s
                  AND merchant IS NOT NULL
                  AND lower(merchant) NOT IN ('unknown', 'unknown merchant', '')
                ORDER BY id DESC
                LIMIT 1
                """,
                (account_id, amt, d, t),
            )
            row = cur.fetchone()

            if row:
                bank, card = get_bank_card_by_account_id(account_id)
                merchant = (row["merchant"] or "").strip()
                amt_val = row["amount"]
                amt_str = f"${float(amt_val):.2f}" if amt_val is not None else "an unknown amount"
                date_str = row.get("purchase_date") or d or "unknown date"
                time_str = row.get("time") or t or "unknown time"

                title = "Transaction alert"
                message = f"{bank} {card} was used at {merchant} for {amt_str} on {date_str} at {time_str}"

                send_pushover(title, message)
                mark_notified(k)

                cur.execute(f"DELETE FROM {pending_table} WHERE k=%s", (k,))
                conn.commit()
                continue

            # No resolved merchant yet — maybe send fallback if TTL exceeded
            created_at = p["created_at"]
            try:
                created_local = created_at.astimezone(tz)
            except Exception:
                created_local = now

            age_minutes = (now - created_local).total_seconds() / 60.0

            if age_minutes >= ttl_minutes:
                bank, card = get_bank_card_by_account_id(account_id)
                amt_str = f"${float(amt):.2f}" if amt is not None else "an unknown amount"
                date_str = d or "unknown date"
                time_str = t or "unknown time"

                title = "Transaction alert"
                message = f"{bank} {card} was used at Unknown merchant for {amt_str} on {date_str} at {time_str}"

                send_pushover(title, message)
                mark_notified(k)

                cur.execute(f"DELETE FROM {pending_table} WHERE k=%s", (k,))
                conn.commit()

# ============================================================
# FIELD EXTRACTION (FIXED)
# ============================================================
def extract_fields(rule_name: str, m) -> dict:
    out = {}

    if rule_name == "navy credit":
        out["cost"] = parse_money(m.group(1))
        out["merchant"] = m.group(3)
        out["time"] = m.group(4)
        out["date"] = m.group(5)
        out["card"] = "Debit" if "debit" in m.group(2).lower() else "Credit"
        return out

    if rule_name == "capital one credit":
        out["date"] = m.group(1)
        out["merchant"] = m.group(2)
        out["cost"] = parse_money(m.group(3))
        out["card"] = "Credit"
        return out

    if rule_name == "discover credit":
        out["date"] = m.group(1)
        out["merchant"] = m.group(2)
        out["cost"] = parse_money(m.group(3))
        out["card"] = "Credit"
        return out
    if rule_name == "discover alert":
        out["merchant"] = m.group(1)
        out["date"] = m.group(2)
        out["cost"] = parse_money(m.group(3))
        out["card"] = "Credit"
        return out

    return out

def format_pushover_message(bank: str, extracted: dict) -> tuple[str, str]:
    """
    <Bank> <Card> was used at <Merchant> for <Cost> on <Date> at <Time>
    """
    card = extracted.get("card", "Card")
    merchant = extracted.get("merchant", "Unknown merchant")
    cost = extracted.get("cost")
    date = extracted.get("date", "unknown date")
    time = extracted.get("time", "unknown time")

    cost_str = f"${cost:.2f}" if isinstance(cost, (int, float)) else "an unknown amount"

    title = "Transaction alert"
    message = (
        f"{bank} {card} was used at {merchant} "
        f"for {cost_str} on {date} at {time}"
    )

    return title, message

# ============================================================
# IMAP
# ============================================================

def get_imap_ids(mail, include_processed: bool = False):
    ids = []
    # Primary mailbox + Gmail archive views so recently-archived emails are still discoverable.
    mailbox_candidates = list(MAILBOXES) + ["[Gmail]/All Mail", "[Google Mail]/All Mail"]
    since_2d = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%d-%b-%Y")
    for box in mailbox_candidates:
        try:
            sel_status, _ = mail.select(box)
            if sel_status != "OK":
                continue
        except Exception:
            continue
        # Gmail's newer_than uses d/m/y units; use a 1-day prefilter and do exact minute filtering in Python.
        # X-GM-RAW parsing can vary by IMAP client/server; try common compatible forms.
        status, data = "BAD", []
        gm_raw = "newer_than:1d" if include_processed else "newer_than:1d -label:ProcessedNew"
        search_attempts = [
            (None, f'X-GM-RAW "{gm_raw}"'),
            (None, "X-GM-RAW", gm_raw),
            ("UTF-8", f'X-GM-RAW "{gm_raw}"'),
            (None, "SINCE", since_2d),
            (None, "ALL"),
        ]
        for args in search_attempts:
            try:
                status, data = mail.search(*args)
                if status == "OK":
                    break
            except imaplib.IMAP4.error:
                continue
        if status == "OK" and data and data[0]:
            for x in data[0].split():
                ids.append(x.decode() if isinstance(x, (bytes, bytearray)) else str(x))
    return list(dict.fromkeys(ids))


def is_within_minutes_window(date_header: str, cutoff_utc: datetime) -> bool:
    if not date_header:
        return False
    try:
        dt = parsedate_to_datetime(date_header)
        if dt is None:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc) >= cutoff_utc
    except Exception:
        return False

# ============================================================
# MAIN
# ============================================================
TEST_MODE = False

def run(include_processed: bool = False):
    # Load .env from project root reliably (webApp/.env)
    project_root = Path(__file__).resolve().parents[1]  # .../webApp
    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    init_account_ids()

    # Refresh pushover creds after dotenv load
    global PUSHOVER_USER, PUSHOVER_TOKEN
    PUSHOVER_USER = _lookup_pushover_user_key_from_db(os.getenv("GMAIL_ADDRESS") or "")
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""

    EMAIL = os.getenv("GMAIL_ADDRESS")
    PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

    if not EMAIL or not PASSWORD:
        raise RuntimeError("Missing Gmail credentials")

    pending_table = "pushover_pending_test" if TEST_MODE else "pushover_pending"
    ensure_pending_table(pending_table)
    ensure_notified_table("notified_transactions")
    # Hardcoded lookback for manual recovery/debugging.
    window_minutes = 24 * 60
    cutoff_utc = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    # 20–30 minutes is what you wanted; default 30, configurable
    PENDING_TTL_MINUTES = int(os.getenv("PUSHOVER_PENDING_TTL_MINUTES") or "30")

    log("Connecting to Gmail…")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)

    try:
        all_ids = get_imap_ids(mail, include_processed=include_processed)
        log(f"Found {len(all_ids)} emails in 1-day prefilter; applying {window_minutes}m window")
        did_work = False

        if DEBUG:
            dbg(f"IMAP IDS: {all_ids}")

        for i in range(0, len(all_ids), BATCH_SIZE):
            batch = all_ids[i:i + BATCH_SIZE]
            dbg(f"Batch {i // BATCH_SIZE + 1} ({len(batch)})")

            res, hdrs = mail.fetch(
                ",".join(batch),
                "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM DATE)])"
            )
            if res != "OK":
                continue

            headers = [email.message_from_bytes(p[1]) for p in hdrs if isinstance(p, tuple)]

            keys = []
            meta = []
            for idx, h in enumerate(headers):
                imap_id = batch[min(idx, len(batch) - 1)]
                subj = decode_hdr(h.get("Subject"))
                sndr = decode_hdr(h.get("From"))
                date = h.get("Date") or ""
                if not is_within_minutes_window(date, cutoff_utc):
                    continue
                k = dedupe_key(h, sndr, subj, date, imap_id)
                keys.append(k)
                meta.append((imap_id, subj, sndr, date, h))
                dbg_header(imap_id, subj, sndr, date, k)

            for (imap_id, subject, sender, date, hdr), key in zip(meta, keys):
                # ------------------------------------------------------------
                # SUBJECT DEBUGGING (NEW)
                # ------------------------------------------------------------
                matched_subject = subject_matches(subject)
                debug_subject(subject, matched_subject)

                if not matched_subject:
                    continue

                did_work = True

                _, data = mail.fetch(imap_id, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                body = extract_body(msg)

                matched = False

                for rule in RULES:
                    dbg_rule_attempt(rule["name"])
                    m = rule["regex"].search(body)

                    if not m:
                        dbg_rule_no_match(rule["name"])
                        continue

                    dbg_rule_match(rule["name"])

                    # ✅ Matched a rule. Now run handler (inserts to DB), then send pushover.
                    matched = True
                    extracted = extract_fields(rule["name"], m)

                    try:
                        result = rule["handler"](mail, imap_id, m, "", use_test_table=TEST_MODE)
                        dbg_handler_result(result)

                        # ✅ Only notify if a NEW row was inserted
                        # ✅ Only notify if a NEW row was inserted
                        if not result or not result.get("inserted"):
                            reason = "handler returned None" if not result else "inserted=False (already in DB / deduped)"

                            # NEW: even if inserted=False, a Transaction Notification might be the merchant-resolver
                            # for a pending withdrawal. Try to resolve pending and notify.
                            if result and rule["name"] == "navy credit":
                                account_id = int(result.get("account_id") or 0)
                                merchant = (result.get("merchant") or "").strip()
                                amt = result.get("amount")
                                date_str = result.get("purchaseDate") or "unknown date"
                                time_str = result.get("time") or "unknown time"
                                fp = tx_fingerprint(account_id, amt, date_str, time_str)
                                dbg(f"Computed fp (inserted=False path): {fp}")

                                resolved = try_resolve_pending_and_notify(
                                    pending_table=pending_table,
                                    fp=fp,
                                    account_id=account_id,
                                    merchant=merchant,
                                    amt=amt,
                                    date_str=date_str,
                                    time_str=time_str,
                                )

                                if resolved:
                                    reason = "inserted=False but resolved pending withdrawal → notified"

                            dbg_notify_status(subject, rule["name"], inserted=(result or {}).get("inserted"),
                                              reason=reason)
                            break

                        account_id = int(result["account_id"])
                        bank, card = get_bank_card_by_account_id(account_id)

                        merchant = (result.get("merchant") or "Unknown").strip()
                        amt = result.get("amount")
                        date_str = result.get("purchaseDate") or "unknown date"
                        time_str = result.get("time") or "unknown time"

                        # ✅ transaction-level fingerprint (dedupe across multiple emails)
                        fp = tx_fingerprint(account_id, amt, date_str, time_str)

                        # ✅ If we already sent a notification for this transaction, never send again
                        dbg(f"Computed fp: {fp}")

                        if already_notified(fp):
                            dbg_notification_decision("Already notified → skipping")
                            dbg_notify_status(subject, rule["name"], inserted=True, fp=fp,
                                              reason="already_notified(fp)=True → skipping")
                            break

                        is_unknown = (merchant.lower() in ("unknown", "unknown merchant", ""))
                        if rule["name"] == "navy withdrawal" and is_unknown:
                            dbg_notification_decision("Withdrawal unknown → stored pending")

                            upsert_pending(
                                pending_table,
                                fp,
                                account_id,
                                amt,
                                date_str,
                                time_str,
                                rule["name"],
                            )
                            break

                        amt_str = f"${float(amt):.2f}" if amt is not None else "an unknown amount"

                        title = "Transaction alert"
                        message = f"{bank} {card} was used at {merchant} for {amt_str} on {date_str} at {time_str}"
                        dbg_notification_decision("Sending pushover now")
                        dbg_notify_status(subject, rule["name"], inserted=True, fp=fp, reason="sending pushover")

                        send_pushover(title, message)
                        mark_notified(fp)
                        break



                    except Exception as e:
                        msg = f"rule={rule['name']} imap_id={imap_id}\n{type(e).__name__}: {e}"
                        log(f"⚠️ handler failed {msg}")
                        push_error(subject=f"emailFetch handler FAILED: {rule['name']}", body=msg, kind="handler_error")

                    break

                if not matched:
                    # If it passed the SUBJECT filter but none of the regex rules matched,
                    # dump body so we can build a regex for this email type.
                    if matched_subject:
                        dbg_dump_body_on_no_rule(subject, sender, imap_id, body)

        if did_work:
            dbg("Flushing pending notifications…")
            try:
                flush_pending_notifications(pending_table, ttl_minutes=PENDING_TTL_MINUTES)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                log(f"⚠️ flush_pending_notifications failed: {msg}")
                push_error(
                    kind="cron_error",
                    subject="emailFetch: flush_pending_notifications FAILED",
                    body=msg,
                )

        log("DONE")

    finally:
        mail.logout()


if __name__ == "__main__":
    open_pool()
    try:
        try:
            run()
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            push_error(kind="cron_error", subject="emailFetch crashed", body=msg)
            raise
    finally:
        close_pool()
