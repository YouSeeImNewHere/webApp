import imaplib
import email
from email.header import decode_header
import os
import time
from dotenv import load_dotenv
import requests
import re
import html
import requests, json, hashlib

from .email_handlers import *  # handlers + account constants (still used for inserts)
from db import with_db_cursor, query_db, open_pool, close_pool

from datetime import datetime
from zoneinfo import ZoneInfo

WEBAPP_URL = os.getenv("WEBAPP_URL") or ""
NOTIF_SECRET = os.getenv("NOTIF_SECRET") or ""
DEBUG = (os.getenv("EMAILFETCH_DEBUG") or "").lower() in ("1", "true", "yes")
BATCH_SIZE = 200
PUSHOVER_USER = os.getenv("PUSHOVER_USER_KEY") or ""
PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""
MAILBOXES = ["INBOX"]

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

if in_allowed_window():
    wake_web_app()
else:
    print("Outside allowed window → letting Render sleep")
    raise SystemExit(0)  # stops cron job early to save free minutes

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
def dbg_seen_check(key, is_seen):
    if not DEBUG:
        return
    if is_seen:
        dbg(f"🔁 ALREADY PROCESSED → skipping")
    else:
        dbg(f"🆕 NEW EMAIL → processing")
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
    if not pushover_enabled():
        log("⚠️ Pushover not configured (missing PUSHOVER_USER/PUSHOVER_TOKEN)")
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

def push_notif(subject: str, body: str, kind: str = "system"):
    if not WEBAPP_URL or not NOTIF_SECRET:
        return
    try:
        # stable-ish dedupe for repeated same error in short time
        h = hashlib.sha1((subject + "\n" + body).encode("utf-8", "ignore")).hexdigest()[:12]
        dedupe_key = f"emailFetch:{kind}:{h}:{int(time.time())}"

        requests.post(
            f"{WEBAPP_URL}/notifications/push",
            headers={"Content-Type": "application/json", "X-Notif-Secret": NOTIF_SECRET},
            json={
                "kind": kind,
                "dedupe_key": dedupe_key,
                "subject": subject[:250],
                "sender": "emailFetch",
                "body": body[:8000],
            },
            timeout=10,
        )
    except Exception:
        pass

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
    r"Merchant:\s*([A-Z0-9][A-Z0-9 &'.,\-*/]+?)\s*"
    r"Date:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\s*"
    r"Amount:\s*\$([\d,]+\.\d{2})",
    re.IGNORECASE
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
    {"name": "discover alert", "regex": discoverAlertRegex, "handler": discovery},

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

def ensure_seen_table(name="email_seen_ids"):
    with with_db_cursor() as (conn, cur):
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {name} (
                message_id TEXT PRIMARY KEY,
                subject TEXT,
                sender TEXT,
                email_date TEXT,
                imap_id INTEGER,
                matched BOOLEAN NOT NULL DEFAULT FALSE,
                matched_rule TEXT,
                note TEXT,
                processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                extracted JSONB
            );
        """)
        conn.commit()
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

def seen_keys(keys, table):
    if not keys:
        return set()
    rows = query_db(
        f"SELECT message_id FROM {table} WHERE message_id = ANY(%s)",
        (keys,)
    )
    return {r["message_id"] for r in rows}

def write_seen(rows, table):
    if not rows:
        return
    with with_db_cursor() as (conn, cur):
        cur.executemany(f"""
            INSERT INTO {table}
            (message_id, subject, sender, email_date, imap_id,
             matched, matched_rule, note, processed_at, extracted)
            VALUES
            (%(message_id)s,%(subject)s,%(sender)s,%(email_date)s,%(imap_id)s,
             %(matched)s,%(matched_rule)s,%(note)s,now(),%(extracted)s)
            ON CONFLICT (message_id) DO UPDATE SET
              matched=EXCLUDED.matched,
              matched_rule=EXCLUDED.matched_rule,
              note=EXCLUDED.note,
              processed_at=now(),
              extracted=EXCLUDED.extracted
        """, rows)
        conn.commit()

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
                SELECT merchant, amount, purchase_date, time
                FROM transactions
                WHERE account_id = %s
                  AND amount = %s
                  AND purchase_date = %s
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

def get_imap_ids(mail):
    ids = []
    for box in MAILBOXES:
        mail.select(box)
        status, data = mail.search(None, "X-GM-RAW", "newer_than:4d")
        if status == "OK" and data and data[0]:
            ids.extend(x.decode() for x in data[0].split())
    return list(dict.fromkeys(ids))

# ============================================================
# MAIN
# ============================================================
TEST_MODE = False

def run():
    # Load .env from project root reliably (webApp/.env)
    project_root = Path(__file__).resolve().parents[1]  # .../webApp
    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)

    # Refresh pushover creds after dotenv load
    global PUSHOVER_USER, PUSHOVER_TOKEN
    PUSHOVER_USER = os.getenv("PUSHOVER_USER_KEY") or ""
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or ""

    EMAIL = os.getenv("GMAIL_ADDRESS")
    PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

    if not EMAIL or not PASSWORD:
        raise RuntimeError("Missing Gmail credentials")

    seen_table = "email_seen_ids_test" if TEST_MODE else "email_seen_ids"
    ensure_seen_table(seen_table)
    pending_table = "pushover_pending_test" if TEST_MODE else "pushover_pending"
    ensure_pending_table(pending_table)
    ensure_notified_table("notified_transactions")

    # 20–30 minutes is what you wanted; default 30, configurable
    PENDING_TTL_MINUTES = int(os.getenv("PUSHOVER_PENDING_TTL_MINUTES") or "30")

    log("Connecting to Gmail…")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)

    try:
        all_ids = get_imap_ids(mail)
        log(f"Found {len(all_ids)} emails")

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
                k = dedupe_key(h, sndr, subj, date, imap_id)
                keys.append(k)
                meta.append((imap_id, subj, sndr, date, h))
                dbg_header(imap_id, subj, sndr, date, k)

            seen = seen_keys(keys, seen_table)
            dbg(f"Seen keys from DB: {len(seen)}")

            rows = []

            for (imap_id, subject, sender, date, hdr), key in zip(meta, keys):
                # ✅ Deduping means this is a "new" email for our pipeline
                already_seen = key in seen
                dbg_seen_check(key, already_seen)

                if already_seen:
                    continue

                # ------------------------------------------------------------
                # SUBJECT DEBUGGING (NEW)
                # ------------------------------------------------------------
                matched_subject = subject_matches(subject)
                debug_subject(subject, matched_subject)

                if not matched_subject:
                    rows.append({
                        "message_id": key,
                        "subject": subject,
                        "sender": sender,
                        "email_date": date,
                        "imap_id": int(imap_id),
                        "matched": False,
                        "matched_rule": "",
                        "note": "subject_skip",
                        "extracted": None,
                    })
                    continue

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

                            rows.append({
                                "message_id": key,
                                "subject": subject,
                                "sender": sender,
                                "email_date": date,
                                "imap_id": int(imap_id),
                                "matched": True,
                                "matched_rule": rule["name"],
                                "note": "matched_no_insert" if result else "matched_handler_skip",
                                "extracted": json.dumps(extracted) if extracted else None,
                            })
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

                            rows.append({
                                "message_id": key,
                                "subject": subject,
                                "sender": sender,
                                "email_date": date,
                                "imap_id": int(imap_id),
                                "matched": True,
                                "matched_rule": rule["name"],
                                "note": "inserted_but_already_notified",
                                "extracted": json.dumps(extracted) if extracted else None,
                            })
                            break

                        # ✅ Suppress the noisy Navy withdrawal “Unknown merchant” notification.
                        # The matching “Transaction Notification” email will arrive shortly and send the real merchant.
                        # ✅ Suppress the noisy Navy withdrawal “Unknown merchant” notification.
                        # Store pending so we can notify later if merchant never arrives.
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

                            rows.append({
                                "message_id": key,
                                "subject": subject,
                                "sender": sender,
                                "email_date": date,
                                "imap_id": int(imap_id),
                                "matched": True,
                                "matched_rule": rule["name"],
                                "note": "inserted_withdrawal_unknown_pending",
                                "extracted": json.dumps(extracted) if extracted else None,
                            })
                            break

                        amt_str = f"${float(amt):.2f}" if amt is not None else "an unknown amount"

                        title = "Transaction alert"
                        message = f"{bank} {card} was used at {merchant} for {amt_str} on {date_str} at {time_str}"
                        dbg_notification_decision("Sending pushover now")
                        dbg_notify_status(subject, rule["name"], inserted=True, fp=fp, reason="sending pushover")

                        send_pushover(title, message)
                        mark_notified(fp)

                        rows.append({
                            "message_id": key,
                            "subject": subject,
                            "sender": sender,
                            "email_date": date,
                            "imap_id": int(imap_id),
                            "matched": True,
                            "matched_rule": rule["name"],
                            "note": "inserted_and_notified",
                            "extracted": json.dumps(extracted) if extracted else None,
                        })
                        break

                        break



                    except Exception as e:
                        msg = f"rule={rule['name']} imap_id={imap_id}\n{type(e).__name__}: {e}"
                        log(f"⚠️ handler failed {msg}")
                        push_notif(subject=f"emailFetch handler FAILED: {rule['name']}", body=msg, kind="handler_error")
                        rows.append({
                            "message_id": key,
                            "subject": subject,
                            "sender": sender,
                            "email_date": date,
                            "imap_id": int(imap_id),
                            "matched": False,
                            "matched_rule": rule["name"],
                            "note": f"handler_error: {type(e).__name__}",
                            "extracted": json.dumps(extracted) if extracted else None,
                        })

                    break

                if not matched:
                    # If it passed the SUBJECT filter but none of the regex rules matched,
                    # dump body so we can build a regex for this email type.
                    if matched_subject:
                        dbg_dump_body_on_no_rule(subject, sender, imap_id, body)

                    rows.append({
                        "message_id": key,
                        "subject": subject,
                        "sender": sender,
                        "email_date": date,
                        "imap_id": int(imap_id),
                        "matched": False,
                        "matched_rule": "",
                        "note": "no_rule",
                        "extracted": None,
                    })

            dbg(f"Writing {len(rows)} rows to {seen_table}")
            dbg("Flushing pending notifications…")
            flush_pending_notifications(pending_table, ttl_minutes=PENDING_TTL_MINUTES)
            write_seen(rows, seen_table)

        log("DONE")

    finally:
        mail.logout()


if __name__ == "__main__":
    open_pool()
    try:
        run()
    finally:
        close_pool()