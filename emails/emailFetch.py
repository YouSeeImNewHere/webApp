import email
import base64
from email.header import decode_header
from email.utils import parsedate_to_datetime
import os
import time
from pathlib import Path
from dotenv import load_dotenv
import re
import html
import requests, json, hashlib

# Legacy handler import kept for backward compatibility of helper symbols in this module.
from .email_handlers import *
from .transactionHandler import insert_transaction, makeKey
from db import with_db_cursor, query_db, open_pool, close_pool

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WEBAPP_URL = os.getenv("WEBAPP_URL") or ""
NOTIF_SECRET = os.getenv("NOTIF_SECRET") or ""
DEBUG = (os.getenv("EMAILFETCH_DEBUG") or "").lower() in ("1", "true", "yes")
BATCH_SIZE = 200
PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""
MAILBOXES = ["INBOX"]
# Wizard pipeline is now the only supported email parser pipeline.
USE_LEGACY_PIPELINE = False
_GMAIL_LABEL_CACHE: dict[str, str] = {}


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

def _resolve_pushover_db_key(recipient_email: str | None = None) -> str:
    target_email = str(recipient_email or "").strip().lower()
    if not target_email:
        return ""
    return _lookup_pushover_user_key_from_db(target_email)


def pushover_enabled(*, recipient_email: str | None = None) -> bool:
    return bool(_resolve_pushover_db_key(recipient_email)) and bool(PUSHOVER_TOKEN.strip())

def send_pushover(title: str, message: str, *, recipient_email: str | None = None):
    """
    Sends a Pushover notification. Never raises (logs failures instead).
    """
    target_user = _resolve_pushover_db_key(recipient_email)

    if not (bool(target_user) and bool(PUSHOVER_TOKEN.strip())):
        log('Pushover not configured (missing users.pushover_user_key or PUSHOVER_API_TOKEN)')
        return

    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_TOKEN,
                "user": target_user,
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
        dbg("✅ Error notification inserted")
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
        from app.core.tenancy import get_owner_tenant_id
        from app.routers.notifications import create_notification
        tid = get_owner_tenant_id()
        return bool(
            create_notification(
                kind=str(kind or "").strip() or "system",
                dedupe_key=str(dedupe_key or "").strip(),
                subject=(subject or "")[:250],
                sender=(sender or "emailFetch")[:250],
                body=(body or "")[:8000],
                tenant_id=(int(tid) if tid else None),
            )
        )
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

def try_resolve_pending_and_notify(
    pending_table: str,
    fp: str,
    account_id: int,
    merchant: str,
    amt,
    date_str: str,
    time_str: str,
    *,
    recipient_email: str | None = None,
):
    """
    If a pending 'unknown merchant' exists for this fp, and we now have a real merchant,
    send pushover + mark_notified + delete pending.
    """
    if not fp:
        return False
    if not pushover_enabled(recipient_email=recipient_email):
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
    send_pushover(title, message, recipient_email=recipient_email)

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

def flush_pending_notifications(
    pending_table: str,
    ttl_minutes: int = 30,
    *,
    recipient_email: str | None = None,
):
    """
    Resolve any pending "unknown merchant" withdrawals.
    - If a real merchant transaction exists now: notify once and mark_notified
    - If already_notified: delete pending
    - If too old: send fallback Unknown merchant notification once
    """
    # Nothing to do if pushover isn't configured
    if not pushover_enabled(recipient_email=recipient_email):
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

                send_pushover(title, message, recipient_email=recipient_email)
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

                send_pushover(title, message, recipient_email=recipient_email)
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

def get_recent_gmail_ids(access_token: str, *, include_processed: bool = False, lookback_days: int = 1, limit: int = 5000):
    return _gmail_api_list_ids(
        access_token,
        lookback_days=max(1, int(lookback_days or 1)),
        include_processed=bool(include_processed),
        limit=max(1, int(limit or 5000)),
    )


def _decode_b64url(data: str | None) -> str:
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data.encode("utf-8"))
    except Exception:
        return ""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _to_text_from_html(s: str) -> str:
    if not s:
        return ""
    x = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    x = re.sub(r"(?is)<br\s*/?>", "\n", x)
    x = re.sub(r"(?is)</p\s*>", "\n", x)
    x = re.sub(r"(?is)<[^>]+>", " ", x)
    x = re.sub(r"[ \t]+", " ", x)
    x = re.sub(r"\n\s*\n+", "\n\n", x)
    return html.unescape(x).strip()


def _looks_like_blank_label_template(s: str) -> bool:
    t = str(s or "")
    if "Merchant:" not in t:
        return False
    return bool(
        re.search(
            r"Merchant:\s*(?:\r?\n)\s*Date:\s*(?:\r?\n)\s*Amount:\s*(?:\r?\n|$)",
            t,
            flags=re.IGNORECASE,
        )
    )


def _extract_gmail_body_from_payload(payload: dict, *, try_html_on_missing_fields: bool = True) -> str:
    if not isinstance(payload, dict):
        return ""
    stack = [payload]
    plain = ""
    html_body = ""
    fallback = ""
    while stack:
        part = stack.pop()
        if not isinstance(part, dict):
            continue
        mime = str(part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = _decode_b64url(body.get("data"))
        if data and not fallback:
            fallback = data
        if mime == "text/plain" and data:
            plain = data
            break
        if mime == "text/html" and data and not html_body:
            html_body = data
        for child in (part.get("parts") or []):
            stack.append(child)
    if plain:
        if try_html_on_missing_fields and html_body and _looks_like_blank_label_template(plain):
            return _to_text_from_html(html_body)
        return plain.strip()
    if html_body:
        return _to_text_from_html(html_body)
    return _to_text_from_html(fallback)


def _gmail_headers_map(msg: dict) -> dict[str, str]:
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    out = {}
    for h in headers:
        k = str((h or {}).get("name") or "").strip().lower()
        v = str((h or {}).get("value") or "").strip()
        if k and v:
            out[k] = v
    return out


def _gmail_api_list_ids(access_token: str, *, lookback_days: int, include_processed: bool, limit: int) -> list[str]:
    terms = [f"newer_than:{max(1, int(lookback_days or 1))}d"]
    if not include_processed:
        terms.append("-label:ProcessedNew")
    q = " ".join(terms).strip()
    out: list[str] = []
    page_token = None
    wanted = max(1, int(limit or 100))
    while len(out) < wanted:
        params = {"q": q, "maxResults": min(500, wanted - len(out))}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"gmail_list_failed_http_{r.status_code}")
        data = r.json() or {}
        for m in (data.get("messages") or []):
            mid = str((m or {}).get("id") or "").strip()
            if mid:
                out.append(mid)
                if len(out) >= wanted:
                    break
        page_token = str(data.get("nextPageToken") or "").strip() or None
        if not page_token:
            break
    return list(dict.fromkeys(out))


def _gmail_api_get_message(access_token: str, message_id: str) -> dict:
    r = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "full"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"gmail_get_failed_http_{r.status_code}")
    return r.json() or {}


def _gmail_get_or_create_label_id(access_token: str, label_name: str) -> str | None:
    name = str(label_name or "").strip()
    if not name:
        return None
    cache_key = f"{access_token[:24]}::{name.lower()}"
    cached = _GMAIL_LABEL_CACHE.get(cache_key)
    if cached:
        return cached

    r = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if r.status_code != 200:
        return None
    data = r.json() or {}
    for lbl in (data.get("labels") or []):
        if str((lbl or {}).get("name") or "").strip().lower() == name.lower():
            lid = str((lbl or {}).get("id") or "").strip()
            if lid:
                _GMAIL_LABEL_CACHE[cache_key] = lid
                return lid

    cr = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
        timeout=20,
    )
    if cr.status_code not in (200, 201):
        return None
    lid = str((cr.json() or {}).get("id") or "").strip()
    if lid:
        _GMAIL_LABEL_CACHE[cache_key] = lid
        return lid
    return None


def _gmail_mark_processed(access_token: str, message_id: str, processed_label_id: str | None) -> None:
    if not access_token or not message_id or not processed_label_id:
        return
    try:
        requests.post(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"addLabelIds": [processed_label_id]},
            timeout=20,
        )
    except Exception:
        pass


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


def received_time_from_header(date_header: str) -> str:
    """
    Fallback time when parsed transaction time is blank.
    Uses the email's Date header converted to local timezone.
    """
    if not date_header:
        return "unknown time"
    try:
        dt = parsedate_to_datetime(date_header)
        if dt is None:
            return "unknown time"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%I:%M %p")
    except Exception:
        return "unknown time"


def _to_regex_flags_py(flag_str: str) -> int:
    f = 0
    s = (flag_str or "").lower()
    if "i" in s:
        f |= re.IGNORECASE
    if "s" in s:
        f |= re.DOTALL
    if "m" in s:
        f |= re.MULTILINE
    return f


def _normalize_date_mmddyy(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%m/%d/%y")
        except Exception:
            continue
    return s


def _normalize_amount(v: str):
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return float(s.replace("$", "").replace(",", ""))
    except Exception:
        return None


def _normalize_time(v: str, fallback_header_date: str, date_mmddyy: str) -> str:
    s = str(v or "").strip()
    if not s:
        s = received_time_from_header(fallback_header_date)
    # strip trailing tz token for ET->local conversion helper
    t0 = re.sub(r"\s+[A-Z]{2,4}$", "", s).strip()
    try:
        return et_time_to_local(date_mmddyy, t0)
    except Exception:
        return t0 or "unknown time"


def _extract_group_safe(m: re.Match, idx: int) -> str:
    if int(idx or 0) <= 0:
        return ""
    try:
        return str(m.group(int(idx)) or "").strip()
    except Exception:
        return ""


def _clean_merchant(v: str) -> str:
    s = str(v or "").strip()
    s = re.sub(r"^[\s,.:;|\-]+|[\s,.:;|\-]+$", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if not s or len(s) < 2 or not re.search(r"[A-Za-z0-9]", s):
        return "Unknown"
    return s


def _escape_regex(v: str) -> str:
    return re.escape(str(v or ""))


def _boundary_label_pattern(v: str) -> str:
    parts = [re.escape(p) for p in str(v or "").strip().split() if p]
    if not parts:
        return ""
    core = r"\s+".join(parts)
    return rf"(?<!\w){core}(?!\w)"


def _guided_amount_present(text: str, guided: dict) -> bool:
    body = str(text or "")
    amount_core = r"\$?[-]?[\d,]+\.\d{2}"
    label = str((guided or {}).get("amount_label") or "").strip()
    if label:
        lpat = _boundary_label_pattern(label)
        if lpat:
            return bool(re.search(rf"{lpat}\s*[:\-]?\s*{amount_core}", body, re.IGNORECASE))
    return bool(re.search(amount_core, body, re.IGNORECASE))


def _guided_extract_line_or_label(text: str, label: str, value_pattern: str, from_idx: int) -> tuple[str, int] | None:
    t = str(text or "")
    start = max(0, int(from_idx or 0))
    sub = t[start:]
    if label:
        lpat = _boundary_label_pattern(label)
        rx = re.compile(rf"{lpat}\s*[:\-]?\s*{value_pattern}", re.IGNORECASE)
        m = rx.search(sub)
        if not m:
            m = rx.search(t)
            if not m:
                return None
            return str(m.group(1) or "").strip(), m.end()
        return str(m.group(1) or "").strip(), start + m.end()
    # blank label => own line first
    rx_line = re.compile(rf"(?:^|\r?\n)\s*{value_pattern}", re.IGNORECASE)
    m = rx_line.search(sub)
    if not m:
        m = rx_line.search(t)
        if not m:
            return None
        return str(m.group(1) or "").strip(), m.end()
    return str(m.group(1) or "").strip(), start + m.end()


def _guided_extract_anywhere(text: str, value_pattern: str, from_idx: int) -> tuple[str, int] | None:
    t = str(text or "")
    start = max(0, int(from_idx or 0))
    sub = t[start:]
    rx = re.compile(value_pattern, re.IGNORECASE)
    m = rx.search(sub)
    if m:
        return str(m.group(1) or "").strip(), start + m.end()
    m = rx.search(t)
    if not m:
        return None
    return str(m.group(1) or "").strip(), m.end()


def _guided_extract_merchant(text: str, label: str, end_mode: str, end_text: str, from_idx: int) -> tuple[str, int] | None:
    t = str(text or "")
    start = max(0, int(from_idx or 0))
    sub = t[start:]

    start_pos = -1
    if label:
        lpat = _boundary_label_pattern(label)
        m = re.search(rf"{lpat}\s*[:\-]?\s*", sub, re.IGNORECASE)
        if not m:
            m0 = re.search(rf"{lpat}\s*[:\-]?\s*", t, re.IGNORECASE)
            if not m0:
                return None
            start_pos = m0.end()
        else:
            start_pos = start + m.end()
    else:
        m = re.search(r"(?:^|\r?\n)\s*([A-Za-z0-9][^\r\n]{1,140})", sub)
        if not m:
            m0 = re.search(r"(?:^|\r?\n)\s*([A-Za-z0-9][^\r\n]{1,140})", t)
            if not m0:
                return None
            start_pos = m0.start(1)
        else:
            start_pos = start + m.start(1)

    after = t[start_pos:]
    mode = str(end_mode or "auto").strip().lower()
    end = -1
    if mode in ("comma", "auto"):
        m = re.search(r"\s*,", after)
        end = m.start() if m else -1
    if end < 0 and mode == "period":
        m = re.search(r"\s*\.", after)
        end = m.start() if m else -1
    if end < 0 and mode == "newline":
        m = re.search(r"\r?\n", after)
        end = m.start() if m else -1
    if end < 0 and mode == "sentence_end":
        m = re.search(r"[.!?]", after)
        end = m.start() if m else -1
    if end < 0 and mode == "text":
        needle = str(end_text or "").strip()
        if needle:
            idx = after.lower().find(needle.lower())
            if idx >= 0:
                end = idx
    if end < 0 and mode == "auto":
        m = re.search(r"\s+(?:in\s+the\s+amount\s+of|amount\s+of|on\s+\d{1,2}/\d{1,2}/\d{2,4}|on\s+[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", after, re.IGNORECASE)
        end = m.start() if m else -1
    if end < 0:
        end = min(len(after), 160)
    raw = str(after[:end]).strip()
    clean = re.sub(r"^[\s,.:;|\-]+|[\s,.:;|\-]+$", "", raw)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    if not clean or len(clean) < 2 or not re.search(r"[A-Za-z0-9]", clean):
        return None
    return clean, start_pos + end


def _guided_extract_fields(body: str, guided: dict, header_date: str) -> dict | None:
    text = str(body or "")
    g = guided or {}
    ord_map = {
        "amount": int(g.get("amount_order") or 0),
        "merchant": int(g.get("merchant_order") or 0),
        "date": int(g.get("date_order") or 0),
        "time": int(g.get("time_order") or 0),
    }
    if ord_map["amount"] <= 0 and _guided_amount_present(text, g):
        return None
    ordered = [k for k in ("amount", "merchant", "date", "time") if int(ord_map.get(k) or 0) > 0]
    ordered.sort(key=lambda k: int(ord_map.get(k) or 0))
    if not ordered:
        return None

    acct_before = str(g.get("account_before") or "").strip()
    acct_exact = str(g.get("account_exact") or "").strip()
    if acct_before and acct_exact:
        bpat = _boundary_label_pattern(acct_before)
        epat = _escape_regex(acct_exact)
        guard = re.search(rf"{bpat}\s*[:\-]?\s*[^\r\n]*?{epat}", text, re.IGNORECASE)
        if not guard:
            return None

    amount_re = r"(\$?[-]?[\d,]+\.\d{2})"
    date_re = r"([A-Za-z]{3},?\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
    time_re = r"([0-1]?\d:[0-5]\d\s*(?:AM|PM)(?:\s*[A-Z]{2,4})?)"

    out = {"amount": "", "merchant": "Unknown", "date": "", "time": ""}
    cursor = 0
    for field in ordered:
        if field == "amount":
            label = str(g.get("amount_label") or "").strip()
            got = _guided_extract_line_or_label(text, label, amount_re, cursor)
            if not got and label:
                got = _guided_extract_line_or_label(text, "", amount_re, cursor)
            if not got:
                got = _guided_extract_anywhere(text, amount_re, cursor)
            if not got:
                return None
            out["amount"], cursor = got
        elif field == "date":
            label = str(g.get("date_label") or "").strip()
            got = _guided_extract_line_or_label(text, label, date_re, cursor)
            if not got and label:
                got = _guided_extract_line_or_label(text, "", date_re, cursor)
            if not got:
                got = _guided_extract_anywhere(text, date_re, cursor)
            if not got:
                return None
            out["date"], cursor = got
        elif field == "time":
            label = str(g.get("time_label") or "").strip()
            got = _guided_extract_line_or_label(text, label, time_re, cursor)
            if not got and label:
                got = _guided_extract_line_or_label(text, "", time_re, cursor)
            if not got:
                got = _guided_extract_anywhere(text, time_re, cursor)
            if got:
                out["time"], cursor = got
        elif field == "merchant":
            got = _guided_extract_merchant(
                text,
                str(g.get("merchant_label") or "").strip(),
                str(g.get("merchant_end") or "auto").strip().lower(),
                str(g.get("merchant_end_text") or "").strip(),
                cursor,
            )
            if not got:
                return None
            merchant_val, cursor = got
            label = str(g.get("merchant_label") or "")
            if re.search(r"description:?", label, re.IGNORECASE) and re.search(r"\s-\s", merchant_val):
                parts = [x.strip() for x in re.split(r"\s-\s", merchant_val) if x.strip()]
                if parts:
                    merchant_val = parts[-1]
            out["merchant"] = merchant_val

    if not out["time"]:
        out["time"] = received_time_from_header(header_date)
    return out


def load_wizard_rules(email_addr: str):
    e = (email_addr or "").strip().lower()
    if not e:
        return []
    rows = query_db(
        """
        SELECT id, account_id, draft_json, updated_at
        FROM email_parser_trial_drafts
        WHERE lower(user_email) = lower(%s)
        ORDER BY updated_at DESC, id DESC
        """,
        (e,),
    ) or []
    out = []
    seen_ids = set()
    for r in rows:
        rid = int(r.get("id") or 0)
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        raw = r.get("draft_json")
        cfg = {}
        if isinstance(raw, str):
            try:
                cfg = json.loads(raw) or {}
            except Exception:
                cfg = {}
        elif isinstance(raw, dict):
            cfg = raw
        body_regex = str(cfg.get("body_regex") or "").strip()
        if not body_regex:
            continue
        flags = str(cfg.get("flags") or "i")
        try:
            rx = re.compile(body_regex, _to_regex_flags_py(flags))
        except Exception:
            continue
        slot = str(cfg.get("parser_slot") or "primary").strip().lower()
        if slot not in ("primary", "backup"):
            slot = "primary"
        fm = cfg.get("field_map") if isinstance(cfg.get("field_map"), dict) else {}
        parser_mode = str(cfg.get("parser_mode") or "advanced").strip().lower()
        guided = cfg.get("guided") if isinstance(cfg.get("guided"), dict) else {}
        out.append(
            {
                "draft_id": rid,
                "account_id": int(cfg.get("account_id") or r.get("account_id") or 0),
                "parser_mode": parser_mode if parser_mode in ("guided", "advanced") else "advanced",
                "guided": guided,
                "sender_pattern": str(cfg.get("sender_pattern") or "").strip().lower(),
                "subject_contains": str(cfg.get("subject_contains") or "").strip().lower(),
                "parser_slot": slot,
                "override_on_primary": bool(cfg.get("override_on_primary")),
                "backup_assume_unknown": bool(cfg.get("backup_assume_unknown")),
                "rx": rx,
                "field_map": {
                    "amount_group": int(fm.get("amount_group") or 0),
                    "merchant_group": int(fm.get("merchant_group") or 0),
                    "date_group": int(fm.get("date_group") or 0),
                    "time_group": int(fm.get("time_group") or 0),
                },
            }
        )
    # Keep DB recency order (updated_at DESC) while still prioritizing primary over backup.
    # Python sort is stable, so sorting by slot only preserves relative recency.
    slot_rank = {"primary": 0, "backup": 1}
    out.sort(key=lambda x: slot_rank.get(x["parser_slot"], 9))
    return out


def _rule_scope_match(rule: dict, sender: str, subject: str) -> bool:
    snd = (sender or "").lower()
    sub = (subject or "").lower()
    sp = (rule.get("sender_pattern") or "").strip()
    sc = (rule.get("subject_contains") or "").strip()
    if sp and sp not in snd:
        return False
    if sc and sc not in sub:
        return False
    return True


def _subject_scoped_rules(rules: list[dict], subject: str) -> list[dict]:
    sub = (subject or "").lower()
    specific = [r for r in rules if (r.get("subject_contains") or "").strip() and (r.get("subject_contains") in sub)]
    if specific:
        return specific
    # Fallback: parsers with blank subject act as catch-all.
    blank = [r for r in rules if not (r.get("subject_contains") or "").strip()]
    return blank


def _account_meta_by_id(account_id: int):
    rows = query_db(
        "SELECT institution, name, LOWER(accounttype) AS accounttype FROM accounts WHERE id = %s LIMIT 1",
        (int(account_id),),
    ) or []
    if not rows:
        return None
    r = rows[0]
    return {
        "bank": str(r.get("institution") or "").strip(),
        "card": str(r.get("name") or "").strip(),
        "accounttype": str(r.get("accounttype") or "").strip().lower(),
    }


def _maybe_mark_processed(mail, imap_id: str, *, access_token: str | None = None, processed_label_id: str | None = None):
    # OAuth path (current).
    if access_token:
        _gmail_mark_processed(str(access_token), str(imap_id), processed_label_id)
        return
    # Backward compatibility fallback.
    try:
        if mail is not None:
            mail.store(imap_id, "+X-GM-LABELS", "(ProcessedNew)")
    except Exception:
        pass


def process_wizard_email(
    *,
    mail,
    imap_id: str,
    sender: str,
    subject: str,
    header_date: str,
    body: str,
    rules: list[dict],
    pending_table: str,
    return_detail: bool = False,
    access_token: str | None = None,
    processed_label_id: str | None = None,
    recipient_email: str | None = None,
):
    """
    Returns True if any wizard rule matched and was processed.
    """
    scoped_rules = _subject_scoped_rules(rules, subject)
    if not scoped_rules:
        if return_detail:
            return {
                "matched": False,
                "status": "skipped",
                "reason": "no_subject_parser",
                "parser": None,
                "inserted": False,
                "notified": False,
                "extracted": None,
                "attempted_parsers": [],
            }
        return False

    attempted: list[dict] = []
    for rule in scoped_rules:
        sender_ok = True
        if (rule.get("sender_pattern") or "").strip():
            sender_ok = _rule_scope_match(rule, sender, subject)
        attempted.append(
            {
                "draft_id": int(rule.get("draft_id") or 0),
                "parser_mode": str(rule.get("parser_mode") or "advanced"),
                "subject_contains": str(rule.get("subject_contains") or ""),
                "sender_pattern": str(rule.get("sender_pattern") or ""),
                "sender_matched": bool(sender_ok),
                "regex": str(getattr(rule.get("rx"), "pattern", "") or ""),
            }
        )
        # Subject has already scoped parser candidates; sender is an additional filter.
        if (rule.get("sender_pattern") or "").strip() and not sender_ok:
            continue

        parser_mode = str(rule.get("parser_mode") or "advanced").strip().lower()
        amount_raw = ""
        merchant_raw = ""
        date_raw = ""
        time_raw = ""
        if parser_mode == "guided":
            gx = _guided_extract_fields(body or "", rule.get("guided") if isinstance(rule.get("guided"), dict) else {}, header_date or "")
            if not gx:
                continue
            amount_raw = str(gx.get("amount") or "")
            merchant_raw = str(gx.get("merchant") or "")
            date_raw = str(gx.get("date") or "")
            time_raw = str(gx.get("time") or "")
        else:
            m = rule["rx"].search(body or "")
            if not m:
                continue
            fm = rule.get("field_map") or {}
            amount_raw = _extract_group_safe(m, int(fm.get("amount_group") or 0))
            merchant_raw = _extract_group_safe(m, int(fm.get("merchant_group") or 0))
            date_raw = _extract_group_safe(m, int(fm.get("date_group") or 0))
            time_raw = _extract_group_safe(m, int(fm.get("time_group") or 0))

        amount_val = _normalize_amount(amount_raw)
        if amount_val is None:
            dbg(f"Wizard rule {rule.get('draft_id')} matched but amount missing/unparseable; trying next parser")
            continue

        date_mmddyy = _normalize_date_mmddyy(date_raw) or datetime.now().strftime("%m/%d/%y")
        time_local = _normalize_time(time_raw, header_date, date_mmddyy)
        merchant = _clean_merchant(merchant_raw)
        slot = str(rule.get("parser_slot") or "primary").lower()
        allow_primary_override = bool(rule.get("override_on_primary")) and slot == "primary"
        account_id = int(rule.get("account_id") or 0)
        meta = _account_meta_by_id(account_id)
        if not meta:
            dbg(f"Wizard rule {rule.get('draft_id')} account_id={account_id} not found; trying next parser")
            continue

        key = makeKey(f"{amount_val:.2f}", date_mmddyy, account_id=account_id)
        result = insert_transaction(
            key=key,
            bank=meta["bank"],
            card=meta["card"],
            accountType=meta["accounttype"],
            cost=amount_val,
            where=merchant,
            purchaseDate=date_mmddyy,
            time=time_local,
            source="email",
            use_test_table=TEST_MODE,
        )

        fp = tx_fingerprint(account_id, amount_val, date_mmddyy, time_local)
        is_unknown = merchant.lower() in ("unknown", "unknown merchant", "")
        backup_pending_first = bool(rule.get("backup_assume_unknown")) and slot == "backup"
        effective_unknown = is_unknown or backup_pending_first

        notified_key = f"{fp}|primary_override" if allow_primary_override else fp
        did_notify = False
        notify_reason = ""
        if not already_notified(notified_key):
            notify_now = False
            reason = ""
            if slot == "backup" and effective_unknown:
                upsert_pending(
                    pending_table,
                    fp,
                    account_id,
                    amount_val,
                    date_mmddyy,
                    time_local,
                    slot,
                )
                reason = "backup unknown/pending-first -> pending"
            else:
                if slot == "primary":
                    try_resolve_pending_and_notify(
                    pending_table=pending_table,
                    fp=fp,
                    account_id=account_id,
                    merchant=merchant,
                    amt=amount_val,
                    date_str=date_mmddyy,
                    time_str=time_local,
                    recipient_email=recipient_email,
                )
                    if allow_primary_override:
                        reason = "primary override -> notify"
                notify_now = True
                if not reason:
                    reason = "notify now"

            if notify_now:
                amt_str = f"${float(amount_val):.2f}"
                title = "Transaction alert"
                message = f"{meta['bank']} {meta['card']} was used at {merchant} for {amt_str} on {date_mmddyy} at {time_local}"
                send_pushover(title, message, recipient_email=recipient_email)
                mark_notified(notified_key)
                did_notify = True
                notify_reason = reason or "notify now"
            dbg_notify_status(subject, f"wizard:{slot}", inserted=(result or {}).get("inserted"), fp=notified_key, reason=reason)
        else:
            dbg_notify_status(subject, f"wizard:{slot}", inserted=(result or {}).get("inserted"), fp=notified_key, reason="already_notified")

        _maybe_mark_processed(mail, imap_id, access_token=access_token, processed_label_id=processed_label_id)
        if return_detail:
            return {
                "matched": True,
                "status": "matched",
                "reason": notify_reason or ("already_notified" if already_notified(notified_key) else "matched"),
                "parser": {
                    "draft_id": int(rule.get("draft_id") or 0),
                    "slot": slot,
                    "subject_contains": str(rule.get("subject_contains") or ""),
                    "sender_pattern": str(rule.get("sender_pattern") or ""),
                },
                "inserted": bool((result or {}).get("inserted")),
                "notified": bool(did_notify),
                "extracted": {
                    "amount": float(amount_val),
                    "merchant": merchant,
                    "date": date_mmddyy,
                    "time": time_local,
                    "account_id": account_id,
                    "account_label": f"{meta['bank']} {meta['card']}".strip(),
                },
            }
        return True

    if return_detail:
        attempted_modes = {str((a or {}).get("parser_mode") or "").strip().lower() for a in attempted}
        if attempted_modes and attempted_modes == {"guided"}:
            fail_reason = "subject_matched_but_guided_failed"
        elif attempted_modes and attempted_modes == {"advanced"}:
            fail_reason = "subject_matched_but_regex_failed"
        else:
            fail_reason = "subject_matched_but_parser_failed"
        return {
            "matched": False,
            "status": "skipped",
            "reason": fail_reason,
            "parser": None,
            "inserted": False,
            "notified": False,
            "extracted": None,
            "attempted_parsers": attempted,
        }
    return False


def run_manual_wizard_parse(
    *,
    lookback_days: int = 1,
    include_processed: bool = True,
    max_emails: int = 2000,
    rules_user_email: str | None = None,
) -> dict:
    """
    Manual parse runner for Settings page.
    Returns summary + per-email rows including skipped and extracted info.
    """
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    init_account_ids()

    global PUSHOVER_TOKEN
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""

    if not str(rules_user_email or "").strip():
        raise RuntimeError("Missing Gmail address")

    rules_owner = str(rules_user_email or "").strip().lower()
    wizard_rules = load_wizard_rules(rules_owner)
    pending_table = "pushover_pending_test" if TEST_MODE else "pushover_pending"
    ensure_pending_table(pending_table)
    ensure_notified_table("notified_transactions")

    days = max(1, int(lookback_days or 1))
    cutoff_utc = datetime.now(timezone.utc) - timedelta(days=days)
    rows: list[dict] = []
    summary = {
        "lookback_days": days,
        "fetched": 0,
        "matched": 0,
        "inserted": 0,
        "notified": 0,
        "skipped": 0,
    }

    from app.core.auth import _refresh_google_access_token_if_needed

    access_token, err = _refresh_google_access_token_if_needed(rules_owner)
    if not access_token:
        raise RuntimeError(f"gmail_oauth_not_connected:{err or 'unknown'}")

    processed_label_id = None
    if not include_processed:
        processed_label_id = _gmail_get_or_create_label_id(access_token, "ProcessedNew")

    message_ids = _gmail_api_list_ids(
        access_token,
        lookback_days=days,
        include_processed=include_processed,
        limit=max_emails,
    )
    summary["fetched"] = len(message_ids)
    for mid in message_ids:
        msg = _gmail_api_get_message(access_token, mid)
        h = _gmail_headers_map(msg)
        subject = h.get("subject", "")
        sender = h.get("from", "")
        date = h.get("date", "")
        if not is_within_minutes_window(date, cutoff_utc):
            continue
        body = _extract_gmail_body_from_payload(msg.get("payload") or {})
        detail = process_wizard_email(
            mail=None,
            imap_id=str(mid),
            sender=sender,
            subject=subject,
            header_date=date,
            body=body,
            rules=wizard_rules,
            pending_table=pending_table,
            return_detail=True,
            access_token=access_token,
            processed_label_id=processed_label_id,
            recipient_email=rules_owner,
        ) or {}
        row = {
            "imap_id": str(mid),
            "subject": str(subject or ""),
            "sender": str(sender or ""),
            "received_at": str(date or ""),
            "matched": bool(detail.get("matched")),
            "status": str(detail.get("status") or "skipped"),
            "reason": str(detail.get("reason") or ""),
            "inserted": bool(detail.get("inserted")),
            "notified": bool(detail.get("notified")),
            "parser": detail.get("parser"),
            "extracted": detail.get("extracted"),
            "attempted_parsers": detail.get("attempted_parsers") or [],
            "body_excerpt": str((body or "")[:6000]),
        }
        if row["matched"]:
            summary["matched"] += 1
        else:
            summary["skipped"] += 1
        if row["inserted"]:
            summary["inserted"] += 1
        if row["notified"]:
            summary["notified"] += 1
        rows.append(row)

    return {"ok": True, "summary": summary, "rows": rows}

# ============================================================
# MAIN
# ============================================================
TEST_MODE = False

def run(include_processed: bool = False, rules_user_email: str | None = None):
    # Load .env from project root reliably (webApp/.env)
    project_root = Path(__file__).resolve().parents[1]  # .../webApp
    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    init_account_ids()

    # Refresh pushover creds after dotenv load
    global PUSHOVER_TOKEN
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""

    from app.core.auth import _refresh_google_access_token_if_needed, _list_connected_google_emails

    targets: list[str]
    requested = str(rules_user_email or "").strip().lower()
    if requested:
        targets = [requested]
    else:
        targets = _list_connected_google_emails()
    if not targets:
        raise RuntimeError("No connected Gmail accounts")

    for rules_owner in targets:
        tenant_id = None
        try:
            from app.core.tenancy import get_user_by_email

            user_row = get_user_by_email(rules_owner)
            tenant_id = int((user_row or {}).get("tenant_id") or 0) or None
        except Exception:
            tenant_id = None
        scope_tag = f"email={rules_owner} tenant_id={tenant_id if tenant_id is not None else '-'}"
        wizard_rules = load_wizard_rules(rules_owner)
        log(f"[{scope_tag}] Wizard pipeline enabled; loaded {len(wizard_rules)} parser rule(s)")
        if not wizard_rules:
            log(f"[{scope_tag}] No parser rules found; emails will be fetched but none will parse until rules are created.")

        pending_table = "pushover_pending_test" if TEST_MODE else "pushover_pending"
        ensure_pending_table(pending_table)
        ensure_notified_table("notified_transactions")
        # Hardcoded lookback for manual recovery/debugging.
        window_minutes = 24 * 60
        cutoff_utc = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        # 20–30 minutes is what you wanted; default 30, configurable
        PENDING_TTL_MINUTES = int(os.getenv("PUSHOVER_PENDING_TTL_MINUTES") or "30")

        access_token, err = _refresh_google_access_token_if_needed(rules_owner)
        if not access_token:
            raise RuntimeError(f"gmail_oauth_not_connected:{err or 'unknown'}")
        processed_label_id = None
        if not include_processed:
            processed_label_id = _gmail_get_or_create_label_id(access_token, "ProcessedNew")

        all_ids = get_recent_gmail_ids(
            access_token,
            include_processed=include_processed,
            lookback_days=1,
            limit=5000,
        )
        log(f"[{scope_tag}] Found {len(all_ids)} emails in 1-day prefilter; applying {window_minutes}m window")
        did_work = False

        if DEBUG:
            dbg(f"GMAIL IDS: {all_ids}")

        for i in range(0, len(all_ids), BATCH_SIZE):
            batch = all_ids[i:i + BATCH_SIZE]
            dbg(f"Batch {i // BATCH_SIZE + 1} ({len(batch)})")

            for mid in batch:
                msg = _gmail_api_get_message(access_token, str(mid))
                hdrs = _gmail_headers_map(msg)
                subject = hdrs.get("subject", "")
                sender = hdrs.get("from", "")
                date = hdrs.get("date", "")
                if not is_within_minutes_window(date, cutoff_utc):
                    continue
                k = dedupe_key({"Message-ID": hdrs.get("message-id", "")}, sender, subject, date, str(mid))
                dbg_header(str(mid), subject, sender, date, k)
                body = _extract_gmail_body_from_payload(msg.get("payload") or {})

                matched = process_wizard_email(
                    mail=None,
                    imap_id=str(mid),
                    sender=sender,
                    subject=subject,
                    header_date=date,
                    body=body,
                    rules=wizard_rules,
                    pending_table=pending_table,
                    access_token=access_token,
                    processed_label_id=processed_label_id,
                    recipient_email=rules_owner,
                )
                if matched:
                    did_work = True
                elif DEBUG:
                    dbg_dump_body_on_no_rule(subject, sender, str(mid), body)

        if did_work:
            dbg("Flushing pending notifications…")
            try:
                flush_pending_notifications(
                    pending_table,
                    ttl_minutes=PENDING_TTL_MINUTES,
                    recipient_email=rules_owner,
                )
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                log(f"⚠️ flush_pending_notifications failed: {msg}")
                push_error(
                    kind="cron_error",
                    subject="emailFetch: flush_pending_notifications FAILED",
                    body=msg,
                )

    log("DONE")


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
