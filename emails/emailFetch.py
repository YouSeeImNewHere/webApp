import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from .email_handlers import *
from dotenv import load_dotenv
import os
from pathlib import Path
from datetime import datetime, timezone
import re
import requests
import json

from db import with_db_cursor, query_db, open_pool, close_pool

# -----------------------------
# Notifications (failed email parse)
# -----------------------------
def ensure_notifications_table():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                dedupe_key TEXT UNIQUE NOT NULL,
                subject TEXT,
                sender TEXT,
                body TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                dismissed BOOLEAN NOT NULL DEFAULT FALSE
            );
            """
        )
        conn.commit()

def log_parse_failure(dedupe_key: str, subject: str, sender: str, body: str):
    """Insert one notification per email Message-ID (deduped by dedupe_key)."""
    try:
        ensure_notifications_table()
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO notifications (kind, dedupe_key, subject, sender, body)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                ("email_parse_failure", dedupe_key, subject, sender, body),
            )
            conn.commit()
    except Exception as e:
        print("Failed to log parse failure notification:", e)


# -----------------------------
# DB Dedupe: email_seen_ids
# -----------------------------
def ensure_seen_table(table_name: str = "email_seen_ids"):
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
              message_id   TEXT PRIMARY KEY,

              subject      TEXT,
              sender       TEXT,
              email_date   TEXT,
              imap_id      INTEGER,

              matched      BOOLEAN NOT NULL DEFAULT FALSE,
              matched_rule TEXT,
              note         TEXT,

              processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              extracted    JSONB
            );
            """
        )
        # lightweight helpful indexes
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_processed_at ON {table_name} (processed_at DESC);")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_matched ON {table_name} (matched);")
        conn.commit()

def seen_exists(dedupe_key: str, table_name: str = "email_seen_ids") -> bool:
    rows = query_db(f"SELECT 1 FROM {table_name} WHERE message_id = %s LIMIT 1", (dedupe_key,))
    return bool(rows)

def mark_seen_db(
    *,
    dedupe_key: str,
    subject: str,
    sender: str,
    date_header: str,
    imap_id: str,
    matched_rule: str,
    matched: bool,
    note: str = "",
    extracted: dict | None = None,
    table_name: str = "email_seen_ids",
):
    ensure_seen_table(table_name)
    payload = extracted or None
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            INSERT INTO {table_name} (
              message_id, subject, sender, email_date, imap_id,
              matched, matched_rule, note, processed_at, extracted
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now(), %s)
            ON CONFLICT (message_id) DO UPDATE SET
              subject      = EXCLUDED.subject,
              sender       = EXCLUDED.sender,
              email_date   = EXCLUDED.email_date,
              imap_id      = EXCLUDED.imap_id,
              matched      = EXCLUDED.matched,
              matched_rule = EXCLUDED.matched_rule,
              note         = EXCLUDED.note,
              processed_at = now(),
              extracted    = EXCLUDED.extracted
            """,
            (
                dedupe_key,
                subject or "",
                sender or "",
                date_header or "",
                int(imap_id) if str(imap_id).isdigit() else None,
                bool(matched),
                matched_rule or "",
                note or "",
                json.dumps(payload) if payload else None,
            ),
        )
        conn.commit()


def parse_money_to_float(s: str | None):
    if not s:
        return None
    s = s.strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except:
        return None


def extract_fields(rule_name: str, m) -> dict:
    out = {}

    if rule_name == "navy credit":
        out["cost"] = parse_money_to_float(m.group(1))
        card_kind = (m.group(2) or "").strip().lower()
        out["merchant"] = (m.group(3) or "").strip()
        out["time"] = (m.group(4) or "").strip()
        out["date"] = (m.group(5) or "").strip()
        out["account_id"] = NAVY_CASHREWARDS_ID if card_kind == "credit" else NAVY_DEBIT_ID
        return out

    if rule_name == "navy withdrawal":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    if rule_name == "navy deposit":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    if rule_name == "navy credit hold":
        out["merchant"] = (m.group(1) or "").strip()
        out["date"] = (m.group(3) or "").strip()
        return out

    if rule_name == "american express":
        acct = (m.group(1) or "").strip()
        out["merchant"] = (m.group(2) or "").strip()
        out["cost"] = parse_money_to_float(m.group(3))
        out["date"] = (m.group(4) or "").strip()
        if acct == PLAT_ACCOUNT_NUMBER:
            out["account_id"] = AMEX_PLATINUM_ID
        elif acct == BCP_ACCOUNT_NUMBER:
            out["account_id"] = AMEX_BCP_ID
        return out

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

    if rule_name == "amex payment":
        out["cost"] = parse_money_to_float(m.group(2))
        out["date"] = (m.group(3) or "").strip()
        return out

    if rule_name == "discover payment":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    if rule_name == "capital one payment":
        out["cost"] = parse_money_to_float(m.group(1))
        out["date"] = (m.group(2) or "").strip()
        return out

    if rule_name == "navy federal zelle":
        out["cost"] = parse_money_to_float(m.group(1))
        out["merchant"] = (m.group(2) or "").strip()
        out["date"] = (m.group(3) or "").strip()
        return out

    return out


load_dotenv()

# For standalone scripts (not FastAPI startup)
open_pool()

PUSHOVER_API_TOKEN = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
PUSHOVER_USER_KEY  = (os.getenv("PUSHOVER_USER_KEY")  or "").strip()
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

def send_pushover(message: str, title: str = "Finance", priority: int = 0) -> None:
    if not PUSHOVER_API_TOKEN or not PUSHOVER_USER_KEY:
        print("Pushover not configured (missing token/user).")
        return

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
            print("Pushover error:", r.status_code, r.text)
        r.raise_for_status()
    except Exception as e:
        print("Pushover failed:", e)


EMAIL = os.getenv("GMAIL_ADDRESS")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

def _first_nonempty(d: dict, keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""

def _guess_card_label(extracted: dict) -> str:
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

def format_purchase_pushover(extracted: dict) -> str:
    merchant = _first_nonempty(extracted, ["merchant", "description", "merchant_name"]).strip()

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
    card = _guess_card_label(extracted)

    cost_txt = f"${cost_val:,.2f}" if cost_val is not None else ""
    subject = card or "A card"

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
    return f"{sender.strip().lower()}|{subject.strip().lower()}|{(date_header or '').strip()}|imap:{fallback_imap_id}"

def sender_matches(rule: dict, sender: str) -> bool:
    sender_l = (sender or "").lower()
    needles = rule.get("from_contains")
    if not needles:
        return True
    return any(n.lower() in sender_l for n in needles)

MAILBOXES = ["INBOX", '"[Gmail]/All Mail"']

def iter_message_ids(mail):
    seen_local = set()
    for mbox in MAILBOXES:
        mail.select(mbox)
        status, data = mail.search(None, 'X-GM-RAW', 'newer_than:30d')
        if status != "OK" or not data or not data[0]:
            continue
        ids = data[0].split()
        for msg_id in ids:
            msg_id_str = msg_id.decode()
            if msg_id_str in seen_local:
                continue
            seen_local.add(msg_id_str)
            yield msg_id_str

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
    "Your payment to"
]

navyFedRegex = re.compile(r"The transaction for (\$[\d,]+\.\d{2}) was approved for your (credit|debit) card ending in \d{4} at (.*) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{3} on ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2})")
navyFedWithdrawalRegex = re.compile(r"(\$[\d,]+\.\d{2}) was withdrawn from your Active Duty Checking account ending in \d{4}. As of ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2}) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{2}")
navyFedDepositRegex = re.compile(r"(\$[\d,]+\.\d{2}) .* of (\d\d\/\d\d\/\d\d) at (\d\d:\d\d \w+) ")
navyFedCreditHoldRegex = re.compile(r"at (.*) at (\d\d:\d\d \w+) .* on (\d\d\/\d\d\/\d\d)")
americanExpressRegex = re.compile(
    r"(?s)Account Ending:\s*\(?(\d+)\)?"
    r".*?\n([A-Z0-9][A-Z0-9 &'.,\-*/]+?)\s*\n"
    r"\$([\d,]+\.\d{2})\*?\s*\n"
    r"(?:[A-Za-z]{3},\s*)?([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
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
        "regex": discoverPaymentRegex,
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

# Toggle: if True, inserts into transactions_test AND writes to email_seen_ids_test
TEST_MODE = False

def test():
    use_test_table = bool(TEST_MODE)
    seen_table = "email_seen_ids_test" if use_test_table else "email_seen_ids"

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

        # ✅ Skip if already processed (DB)
        if seen_exists(dedupe_key, table_name=seen_table):
            continue

        # compute timeEmail for handlers
        sent_dt = None
        try:
            sent_dt = parsedate_to_datetime(date_header) if date_header else None
        except Exception:
            sent_dt = None
        timeEmail = sent_dt.strftime("%I:%M %p") if sent_dt else ""

        # If not a subject we care about, record as seen (DB)
        if not subject_matches(subject):
            mark_seen_db(
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note="subject_not_matched",
                extracted=None,
                table_name=seen_table,
            )
            continue

        # 2) Fetch full message (expensive)
        res, msg_data = mail.fetch(msg_id_str, "(RFC822)")
        if res != "OK":
            mark_seen_db(
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note="fetch_rfc822_failed",
                extracted=None,
                table_name=seen_table,
            )
            continue

        full_msg = None
        for response in msg_data:
            if isinstance(response, tuple):
                full_msg = email.message_from_bytes(response[1])
                break

        if full_msg is None:
            mark_seen_db(
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note="no_message_bytes",
                extracted=None,
                table_name=seen_table,
            )
            continue

        subject = decode_hdr(full_msg.get("Subject", subject))
        sender = decode_hdr(full_msg.get("From", sender))
        date_header = full_msg.get("Date", date_header) or date_header

        body = extract_email_body(full_msg)

        matched = False
        matched_rule = ""
        extracted = None

        # 3) Match rules + handler insert
        for rule in RULES:
            if not sender_matches(rule, sender):
                continue

            m = rule["regex"].search(body or "")
            if not m:
                continue

            matched = True
            matched_rule = rule.get("name", "")
            extracted = extract_fields(matched_rule, m) or None

            if extracted is not None and "time" not in extracted:
                extracted["time"] = timeEmail

            try:
                rule["handler"](mail, msg_id_str, m, timeEmail, use_test_table=use_test_table)
            except Exception as e:
                print("Handler failed:", e)
                log_parse_failure(dedupe_key, subject, sender, body)
                # ❌ DO NOT mark seen — retry next run
                matched = False
                matched_rule = ""
                extracted = None
                break

            break

        # 4) Record outcome in DB
        if matched:
            mark_seen_db(
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule=matched_rule,
                matched=True,
                note="inserted_transactions_test" if use_test_table else "inserted_transactions",
                extracted=extracted,
                table_name=seen_table,
            )

            print("✅ Inserted + seen:", dedupe_key, "|", matched_rule, "|", extracted)

            # ✅ Phone notification for purchases only
            try:
                rule_lower = (matched_rule or "").lower()
                is_non_purchase = any(x in rule_lower for x in ["payment", "deposit", "withdrawal", "transfer", "interest"])
                has_purchase_fields = bool(extracted and extracted.get("merchant") and extracted.get("cost") is not None)
                if (not is_non_purchase) and has_purchase_fields:
                    message = format_purchase_pushover(extracted)
                    send_pushover(title="Purchase Alert", message=message)
            except Exception as e:
                print("Purchase notification build failed:", e)

        else:
            note = "no_rule_matched"
            if re.search("declined", body or "", re.IGNORECASE):
                note = "no_rule_matched_declined_detected"

            mark_seen_db(
                dedupe_key=dedupe_key,
                subject=subject,
                sender=sender,
                date_header=date_header,
                imap_id=msg_id_str,
                matched_rule="",
                matched=False,
                note=note,
                extracted=None,
                table_name=seen_table,
            )

            log_parse_failure(dedupe_key, subject, sender, body)
            print("— No match:", dedupe_key, "|", subject)

    mail.logout()

if __name__ == "__main__":
    try:
        test()
    finally:
        close_pool()
