import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from emails.email_handlers import *
from dotenv import load_dotenv
import os
import json
from pathlib import Path
from datetime import datetime, timezone
import re
import requests

import sqlite3
from emails.transactionHandler import DB_PATH

# -----------------------------
# Notifications (failed email parse)
# -----------------------------
def ensure_notifications_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            subject TEXT,
            sender TEXT,
            body TEXT,
            created_at TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            dismissed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_dismissed ON notifications(dismissed)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)")
    conn.commit()
    conn.close()


def log_parse_failure(dedupe_key: str, subject: str, sender: str, body: str):
    """Insert one notification per email Message-ID (deduped by dedupe_key)."""
    try:
        ensure_notifications_table()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO notifications (kind, dedupe_key, subject, sender, body, created_at, is_read, dismissed)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                "email_parse_failure",
                dedupe_key,
                subject,
                sender,
                body,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("Failed to log parse failure notification:", e)


def parse_money_to_float(s: str | None):
    if not s:
        return None
    # handles "$1,234.56" and "1234.56" and "-123.45"
    s = s.strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except:
        return None


def extract_fields(rule_name: str, m) -> dict:
    """
    Return best-effort: merchant, cost, date.
    date is returned as whatever format the regex captures (string).
    """
    out = {}

    # NAVY FED CARD: (1) $amount (2) credit/debit (3) merchant (4) time (5) mm/dd/yy
    if rule_name == "navy credit":
        out["cost"] = parse_money_to_float(m.group(1))
        card_kind = (m.group(2) or "").strip().lower()  # credit|debit
        out["merchant"] = (m.group(3) or "").strip()
        out["time"] = (m.group(4) or "").strip()
        out["date"] = (m.group(5) or "").strip()

        # ✅ match handler mapping (navyFedCard)
        out["account_id"] = NAVY_CASHREWARDS_ID if card_kind == "credit" else NAVY_DEBIT_ID
        return out

    # NAVY FED WITHDRAWAL: (1) $amount (2) mm/dd/yy (3) time
    if rule_name == "navy withdrawal":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    # NAVY FED DEPOSIT: (1) $amount (2) mm/dd/yy (3) time
    if rule_name == "navy deposit":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    # NAVY FED CREDIT HOLD: (1) merchant (2) time (3) mm/dd/yy
    if rule_name == "navy credit hold":
        out["merchant"] = (m.group(1) or "").strip()
        out["date"] = (m.group(3) or "").strip()
        return out

    # AMEX CHARGE: (1) acct (2) merchant (3) $amount (4) date
    if rule_name == "american express":
        acct = (m.group(1) or "").strip()
        out["merchant"] = (m.group(2) or "").strip()
        out["cost"] = parse_money_to_float(m.group(3))
        out["date"] = (m.group(4) or "").strip()  # note: handler normalizes format later

        # ✅ same mapping as email_handlers.americanExpress()
        if acct == PLAT_ACCOUNT_NUMBER:
            out["account_id"] = AMEX_PLATINUM_ID
        elif acct == BCP_ACCOUNT_NUMBER:
            out["account_id"] = AMEX_BCP_ID
        return out

    # CAP ONE DEBIT: (1) $amount (2) merchant (3) date
    if rule_name == "capital one debit":
        out["cost"] = parse_money_to_float(m.group(1))
        out["merchant"] = (m.group(2) or "").strip()
        out["date"] = (m.group(3) or "").strip()
        out["account_id"] = CAPONE_DEBIT_ID
        return out

    if rule_name == "capital one credit":
        out["date"] = (m.group(1) or "").strip()
        out["merchant"] = (m.group(2) or "").strip()
        out["cost"] = parse_money_to_float(m.group(3))
        out["account_id"] = CAPONE_SAVOR_ID
        return out

    if rule_name == "discovery credit":
        out["date"] = (m.group(1) or "").strip()
        out["merchant"] = (m.group(2) or "").strip()
        out["cost"] = parse_money_to_float(m.group(3))
        out["account_id"] = DISCOVER_IT_ID
        return out

    # AMEX PAYMENT: (1) acct (2) amount (3) date
    if rule_name == "amex payment":
        out["cost"] = parse_money_to_float(m.group(2))
        out["date"] = (m.group(3) or "").strip()
        return out

    # DISCOVER PAYMENT: (1) amount (2) date
    if rule_name == "discover payment":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    # CAP ONE PAYMENT: (1) amount (2) date
    if rule_name == "capital one payment":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    # NAVY FED ZELLE: (1) amount (2) to person (3) date
    if rule_name == "navy federal zelle":
        out["cost"] = parse_money_to_float(m.group(1))
        out["merchant"] = (m.group(2) or "").strip()
        out["date"] = (m.group(3) or "").strip()
        return out

    # default: no known mapping
    return out


load_dotenv()

# -----------------------------
# Pushover (phone notifications)
# -----------------------------
# -----------------------------
# Pushover (phone notifications)
# -----------------------------
PUSHOVER_API_TOKEN = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
PUSHOVER_USER_KEY  = (os.getenv("PUSHOVER_USER_KEY")  or "").strip()
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

def send_pushover(message: str, title: str = "Finance", priority: int = 0) -> None:
    if not PUSHOVER_API_TOKEN or not PUSHOVER_USER_KEY:
        print("Pushover not configured (missing token/user).")
        return

    # Pushover rejects empty message
    message = (message or "").strip()
    if not message:
        print("Pushover skipped: empty message")
        return

    try:
        r = requests.post(
            PUSHOVER_URL,
            data={
                "token": PUSHOVER_API_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": title[:250],
                "message": message[:1024],
                "priority": priority,
            },
            timeout=10,
        )

        if not r.ok:
            # ✅ This will tell you *exactly* why it’s 400 (bad token/user/etc.)
            print("Pushover error:", r.status_code, r.text)

        r.raise_for_status()

    except Exception as e:
        print("Pushover failed:", e)


EMAIL = os.getenv("GMAIL_ADDRESS")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# -----------------------------

def _first_nonempty(d: dict, keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""

def card_label_from_account_id(account_id: int | None) -> str:
    if not account_id:
        return ""

    # These constants already exist in email_handlers.py (imported via `from emails.email_handlers import *`)
    # :contentReference[oaicite:2]{index=2}
    mapping = {
        NAVY_DEBIT_ID: "Debit",
        NAVY_CASHREWARDS_ID: "cashRewards",
        AMEX_PLATINUM_ID: "Platinum",
        AMEX_BCP_ID: "Blue Cash Preferred",
        CAPONE_DEBIT_ID: "Capital One Debit",
        CAPONE_SAVOR_ID: "Savor",
        DISCOVER_IT_ID: "Discover It",
    }
    return mapping.get(account_id, f"Account {account_id}")

def get_bank_and_card_from_db(account_id: int | None) -> tuple[str, str]:
    """
    Returns (bank, card_name) from accounts table.
    accounts: id, institution, name, ...
    """
    if not account_id:
        return ("", "")

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT institution, name FROM accounts WHERE id = ?", (int(account_id),))
        row = cur.fetchone()
        conn.close()
        if not row:
            return ("", "")
        bank, card = row[0] or "", row[1] or ""
        return (str(bank).strip(), str(card).strip())
    except Exception as e:
        print("Account lookup failed:", e)
        return ("", "")

def _guess_card_label(extracted: dict) -> str:
    # ✅ Prefer account_id mapping
    try:
        acct_id = extracted.get("account_id")
        if acct_id is not None:
            label = card_label_from_account_id(int(acct_id))
            if label:
                return label
    except Exception:
        pass

    # (keep your existing logic)
    label = _first_nonempty(
        extracted,
        ["card_used","card","card_name","account","account_name","payment_method",
         "source","acct","account_last4","acct_last4","card_last4","last4"]
    )
    if label:
        return label

    for k, v in extracted.items():
        lk = str(k).lower()
        if any(tok in lk for tok in ("last4", "card", "account", "acct")):
            s = str(v).strip()
            if s:
                return s
    return ""

def _guess_datetime_label(extracted: dict) -> str:
    # If your parser provides a combined datetime field, prefer that.
    dt = _first_nonempty(extracted, ["datetime", "date_time", "timestamp", "posted_at", "authorized_at"])
    if dt:
        return dt

    date = _first_nonempty(extracted, ["date", "posted_date", "transaction_date"])
    time = _first_nonempty(extracted, ["time", "transaction_time"])
    if date and time:
        return f"{date} {time}"
    return date or time

def format_purchase_pushover(extracted: dict) -> str:
    merchant = _first_nonempty(extracted, ["merchant", "description", "merchant_name"]).strip()

    # cost
    raw_cost = extracted.get("cost", "")
    cost_val = None
    try:
        if isinstance(raw_cost, (int, float)):
            cost_val = float(raw_cost)
        else:
            s = str(raw_cost).replace(",", "")
            s = re.sub(r"[^0-9.\-]", "", s)
            cost_val = float(s) if s else None
    except Exception:
        cost_val = None

    date = _first_nonempty(extracted, ["date", "posted_date", "transaction_date"]).strip()
    time = _first_nonempty(extracted, ["time", "transaction_time"]).strip()

    # ✅ Prefer DB truth via account_id (bank + card)
    bank = ""
    card = ""
    try:
        acct_id = extracted.get("account_id")
        if acct_id is not None:
            bank, card = get_bank_and_card_from_db(int(acct_id))
    except Exception:
        pass

    # fallback if DB lookup didn’t return a label
    if not card:
        card = _guess_card_label(extracted)

    # Build sentence (skip missing parts gracefully)
    cost_txt = f"${cost_val:,.2f}" if cost_val is not None else ""

    subject = " ".join([x for x in [bank, card] if x]).strip()
    if not subject:
        subject = "A card"

    parts = [f"{subject} was used"]
    if merchant:
        parts.append(f"at {merchant}")
    if cost_txt:
        parts.append(f"for {cost_txt}")
    if date:
        parts.append(f"on {date}")
    if time:
        parts.append(f"at {time}")

    return " ".join(parts).strip() + "."

# De-dupe: processed Message-IDs
# -----------------------------
SEEN_IDS_FILE = Path(__file__).resolve().parent / "seen_ids.json"
SEEN_IDS_TEST_FILE = Path(__file__).resolve().parent / "seen_ids_test.json"

# Toggle: when True, reads seen_ids.json but writes ONLY to seen_ids_test.json and inserts into transactions_test
TEST_MODE = False


def load_seen_ids(path: Path) -> dict:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_seen_ids(path: Path, seen: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)

def mark_seen_test(
    seen: dict,
    dedupe_key: str,
    subject: str,
    sender: str,
    date_header: str,
    imap_id: str,
    matched_rule: str,
    matched: bool,
    note: str = "",
    extracted: dict | None = None,
) -> None:
    """
    New JSON format:
      {
        "<message-id>": {
           "subject": "...",
           "sender": "...",
           "date": "...",
           "imap_id": "...",
           "matched": true/false,
           "matched_rule": "rule name or ''",
           "note": "...",
           "processed_at": "...",
           "extracted": { "merchant": "...", "cost": 0.0, "date": "..." }   # optional
        }
      }
    """
    entry = {
        "subject": subject or "",
        "sender": sender or "",
        "date": date_header or "",
        "imap_id": imap_id,
        "matched": bool(matched),
        "matched_rule": matched_rule or "",
        "note": note or "",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    if extracted:
        # only keep non-empty values
        entry["extracted"] = {k: v for k, v in extracted.items() if v not in (None, "", [])}

    seen[dedupe_key] = entry

def decode_hdr(val: str) -> str:
    if not val:
        return ""
    parts = decode_header(val)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(str(chunk))
    return "".join(out)

def get_dedupe_key_from_headers(hdr_msg, sender: str, subject: str, date_header: str, fallback_imap_id: str) -> str:
    msgid = (hdr_msg.get("Message-ID") or "").strip().lower()
    if msgid:
        return msgid
    # Rare fallback if Message-ID missing
    return f"{sender.strip().lower()}|{subject.strip().lower()}|{(date_header or '').strip()}|imap:{fallback_imap_id}"



def mark_seen(path: Path, seen: dict, msg_id_str: str, subject: str) -> None:
    # store minimal metadata (handy for debugging)
    seen[msg_id_str] = {
        "subject": subject,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }
    save_seen_ids(path, seen)

def sender_matches(rule: dict, sender: str) -> bool:
    sender_l = (sender or "").lower()
    needles = rule.get("from_contains")
    if not needles:
        return True  # no constraint => allowed
    return any(n.lower() in sender_l for n in needles)

MAILBOXES = ["INBOX", '"[Gmail]/All Mail"']

def iter_message_ids(mail):
    """
    Yield message IDs from INBOX first, then All Mail (deduped).
    Oldest -> newest within each mailbox.
    """
    seen_local = set()

    for mbox in MAILBOXES:
        mail.select(mbox)
        status, data = mail.search(None, 'X-GM-RAW', 'newer_than:30d')

        if status != "OK" or not data or not data[0]:
            continue

        ids = data[0].split()

        # oldest -> newest
        for msg_id in ids:
            msg_id_str = msg_id.decode()
            if msg_id_str in seen_local:
                continue
            seen_local.add(msg_id_str)
            yield msg_id_str

SUBJECTS = [
    "Transaction Notification",  # navy fed
    "Withdrawal Notification",  # navy fed
    "Large Purchase Approved",  # amex
    "Debit Card Purchase",  # capital one debit
    "A new transaction was charged to your account",  # capital one credit
    "Transaction Alert",  # discovery
    "Deposit Notification",  # navy fed

    "We processed your payment",  # card payment
    "We've received your payment",  # card payment
    "Your payment to"
]

navyFedRegex = re.compile( r"The transaction for (\$[\d,]+\.\d{2}) was approved for your (credit|debit) card ending in \d{4} at (.*) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{3} on ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2})")
navyFedWithdrawalRegex = re.compile(r"(\$[\d,]+\.\d{2}) was withdrawn from your Active Duty Checking account ending in \d{4}. As of ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2}) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{2}")
navyFedDepositRegex = re.compile(r"(\$[\d,]+\.\d{2}) .* of (\d\d\/\d\d\/\d\d) at (\d\d:\d\d \w+) ")
navyFedCreditHoldRegex = re.compile(r"at (.*) at (\d\d:\d\d \w+) .* on (\d\d\/\d\d\/\d\d)")
americanExpressRegex = re.compile(
    r"(?s)Account Ending:\s*\(?(\d+)\)?"
    r".*?\n([A-Z0-9][A-Z0-9 &'.,\-*/]+?)\s*\n"  # merchant (group 2)
    r"\$([\d,]+\.\d{2})\*?\s*\n"  # amount (group 3)
    r"(?:[A-Za-z]{3},\s*)?([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"  # date (group 4)
)
capitalOneDebitRegex = re.compile(r"Amount: (\$[\d,]+\.\d{2})\r?\n.* - (.*)\r?\nDate: ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})")
capitalOneCreditRegex = re.compile(r"As requested, we're notifying you that on ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}), at (.*), .* of (\$[\d,]+\.\d{2})")
discoveryRegex = re.compile(r"Transaction Date:: ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})\s*Merchant: (.*)\s*Amount: (\$[\d,]+\.\d{2})")

amexPaymentRegex = re.compile(
    r"(?s)Account Ending:\s*\(?(\d+)\)?"
    r".*?Payment amount:\s*\(?\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})\)?"
    r".*?Processed on:\s*\(?([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\)?"
)
discoverPaymentRegex = re.compile(r"Your Payment of\s*\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})\s*posted to your account on\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})")
capOnePaymentRegex = re.compile(
    r"(?s)Payment amount:\s*\(?\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})\)?\s*.*?"
    r"Posted date:\s*\(?([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\)?"
)
navyFedZelleRegex = re.compile(
    r"(?s)Amount\s*\$([\d,]+\.\d{2}).*?"
    r"To\s*([A-Za-z][A-Za-z\s'.-]+)\s*\([^)]+\).*?"
    r"As of\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"
)


def subject_matches(subject: str) -> bool:
    if not subject:
        return False
    lower = subject.lower()
    return any(keyword.lower() in lower for keyword in SUBJECTS)


RULES = [
    {"name": "navy credit", "regex": navyFedRegex, "handler": navyFedCard},
    {"name": "navy withdrawal", "regex": navyFedWithdrawalRegex, "handler": navyFedWithdrawal},
    {"name": "navy deposit", "regex": navyFedDepositRegex, "handler": navyFedDeposit},
    {"name": "navy credit hold", "regex": navyFedCreditHoldRegex, "handler": navyFedCreditHold},
    {"name": "american express", "regex": americanExpressRegex, "handler": americanExpress},
    {"name": "capital one debit", "regex": capitalOneDebitRegex, "handler": capitalOneDebit},
    {"name": "capital one credit", "regex": capitalOneCreditRegex, "handler": capitalOneCredit},
    {"name": "discovery credit", "regex": discoveryRegex, "handler": discovery},
    {"name": "amex payment", "regex": amexPaymentRegex, "handler": amexPayment},
    {
        "name": "amex payment",
        "from_contains": ["americanexpress.com", "aexp.com", "american express"],
        "regex": amexPaymentRegex,
        "handler": amexPayment
    },
    {
        "name": "discover payment",
        "from_contains": ["discover.com", "discover@services.discover.com", "discover card"],
        "regex": discoverPaymentRegex,   # make a payment-specific regex if needed
        "handler": discoverPayment
    },
    {
        "name": "capital one payment",
        "from_contains": ["notification.capitalone.com", "capitalone@", "capital one"],
        "regex": capOnePaymentRegex,
        "handler": capitalOnePayment
    },
    {
        "name": "navy federal zelle",
        "from_contains": ["Navy Federal Credit Union"],
        "regex": navyFedZelleRegex,
        "handler": navyFedZelle
    },
]


def extract_email_body(msg) -> str:
    """
    Returns the best-effort text body from an email.message.Message.
    Prefers text/plain, falls back to text/html (converted to text).
    """
    if msg.is_multipart():
        plain_text = None
        html_text = None

        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_text = part.get_payload(decode=True).decode(errors="ignore")
                break
            elif content_type == "text/html" and html_text is None:
                html_text = part.get_payload(decode=True).decode(errors="ignore")

        if plain_text is not None:
            return plain_text.strip()

        if html_text is not None:
            soup = BeautifulSoup(html_text, "html.parser")
            return soup.get_text(separator="\n").strip()

        return ""

    content_type = msg.get_content_type()
    payload = msg.get_payload(decode=True).decode(errors="ignore")

    if content_type == "text/plain":
        return payload.strip()

    if content_type == "text/html":
        soup = BeautifulSoup(payload, "html.parser")
        return soup.get_text(separator="\n").strip()

    return payload.strip()

from email.utils import parsedate_to_datetime

def test():
    # ✅ always test mode for this run
    use_test_table = False
    seen_path = SEEN_IDS_FILE

    # Load existing seen file so we can skip already-processed emails
    seen = load_seen_ids(seen_path)
    seen_keys = set(seen.keys())  # dedupe_key = Message-ID

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)

    for msg_id_str in iter_message_ids(mail):

        # 1) Fetch headers (cheap)
        res, hdr_data = mail.fetch(
            msg_id_str,
            "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM DATE)])"
        )
        if res != "OK":
            continue

        raw_headers = b""
        for part in hdr_data:
            if isinstance(part, tuple):
                raw_headers += part[1]

        hdr_msg = email.message_from_bytes(raw_headers)

        subject = decode_hdr(hdr_msg.get("Subject", ""))
        sender = decode_hdr(hdr_msg.get("From", ""))
        date_header = hdr_msg.get("Date") or ""

        dedupe_key = get_dedupe_key_from_headers(hdr_msg, sender, subject, date_header, msg_id_str)

        # ✅ Skip if already processed
        if dedupe_key in seen_keys:
            continue

        # compute timeEmail for handlers
        sent_dt = None
        try:
            sent_dt = parsedate_to_datetime(date_header) if date_header else None
        except Exception:
            sent_dt = None
        timeEmail = sent_dt.strftime("%I:%M %p") if sent_dt else ""

        # If not a subject we care about, still record it as seen? (you previously did)
        # If you ONLY want to record matched ones, change this to `continue` without mark_seen_test.
        if not subject_matches(subject):
            mark_seen_test(
                seen=seen,
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note="subject_not_matched",
                extracted=None
            )
            save_seen_ids(seen_path, seen)
            seen_keys.add(dedupe_key)
            continue

        # 2) Fetch full message (expensive)
        res, msg_data = mail.fetch(msg_id_str, "(RFC822)")
        if res != "OK":
            mark_seen_test(
                seen=seen,
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note="fetch_rfc822_failed",
                extracted=None
            )
            save_seen_ids(seen_path, seen)
            seen_keys.add(dedupe_key)
            continue

        full_msg = None
        for response in msg_data:
            if isinstance(response, tuple):
                full_msg = email.message_from_bytes(response[1])
                break

        if full_msg is None:
            mark_seen_test(
                seen=seen,
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note="no_message_bytes",
                extracted=None
            )
            save_seen_ids(seen_path, seen)
            seen_keys.add(dedupe_key)
            continue

        # Re-read headers from full message (sometimes cleaner)
        subject = decode_hdr(full_msg.get("Subject", subject))
        sender = decode_hdr(full_msg.get("From", sender))
        date_header = full_msg.get("Date", date_header) or date_header

        body = extract_email_body(full_msg)

        matched = False
        matched_rule = ""
        extracted = None

        # 3) Match rules + INSERT into transactions_test via handler
        for rule in RULES:
            if not sender_matches(rule, sender):
                continue

            m = rule["regex"].search(body or "")
            if not m:
                continue

            matched = True
            matched_rule = rule.get("name", "")
            extracted = extract_fields(matched_rule, m) or None

            # If the regex didn't capture time, use the handler-style fallback
            if extracted is not None and "time" not in extracted:
                extracted["time"] = timeEmail

            # ✅ INSERT to DB test table (via your existing handler)
            try:
                rule["handler"](mail, msg_id_str, m, timeEmail, use_test_table=use_test_table)
            except Exception as e:
                print("Handler failed:", e)
                log_parse_failure(dedupe_key, subject, sender, body)
                # ❌ DO NOT mark seen — retry next run
                continue
            break

        # 4) Record outcome in JSON
        if matched:
            note = "inserted_transactions_test"
            mark_seen_test(
                seen=seen,
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule=matched_rule,
                matched=True,
                note=note,
                extracted=extracted
            )
            save_seen_ids(seen_path, seen)
            seen_keys.add(dedupe_key)

            print("✅ Inserted + seen:", dedupe_key, "|", matched_rule, "|", extracted)

            # ✅ Phone notification for PURCHASES only (no webapp notifications table entry)
            try:
                rule_lower = (matched_rule or "").lower()
                is_non_purchase = any(x in rule_lower for x in ["payment", "deposit", "withdrawal", "transfer", "interest"])
                has_purchase_fields = bool(extracted and extracted.get("merchant") and extracted.get("cost") is not None)
                if (not is_non_purchase) and has_purchase_fields:
                    message = format_purchase_pushover(extracted)
                    send_pushover(
                        title="Purchase Alert",
                        message=message,
                    )
            except Exception as e:
                print("Purchase notification build failed:", e)

        else:
            # If you want unmatched emails to stay un-seen so you can retry later, do NOT write them.
            # Current behavior: still record them to seen file so you don't keep re-parsing noise.
            note = "no_rule_matched"
            if re.search("declined", body or "", re.IGNORECASE):
                note = "no_rule_matched_declined_detected"

            mark_seen_test(
                seen=seen,
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note=note,
                extracted=None
            )
            save_seen_ids(seen_path, seen)
            seen_keys.add(dedupe_key)

            # optional: also log parse failure notification for unmatched (you used to)
            log_parse_failure(dedupe_key, subject, sender, body)

            print("— No match:", dedupe_key, "|", subject)

    mail.logout()


if __name__ == "__main__":
    test()
