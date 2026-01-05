import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from emails.email_handlers import *
from dotenv import load_dotenv
import os
import json
from pathlib import Path
from datetime import datetime, timezone

load_dotenv()

EMAIL = os.getenv("GMAIL_ADDRESS")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# -----------------------------
# De-dupe: processed Message-IDs
# -----------------------------
SEEN_IDS_FILE = Path(__file__).resolve().parent / "seen_ids.json"
SEEN_IDS_TEST_FILE = Path(__file__).resolve().parent / "seen_ids_test.json"

# Toggle: when True, reads seen_ids.json but writes ONLY to seen_ids_test.json and inserts into transactions_test
TEST_MODE = True


def load_seen_ids(path: Path) -> dict:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # If file is corrupt for any reason, start fresh rather than crash
            return {}
    return {}

    return {}

def save_seen_ids(path: Path, seen: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


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
        status, data = mail.search(None, "ALL")
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


def test():
    # In TEST_MODE:
    #   - skip anything already in seen_ids.json (prod)
    #   - ALSO skip anything already in seen_ids_test.json (so re-runs don't duplicate)
    #   - write new processed IDs ONLY to seen_ids_test.json
    #   - insert into transactions_test via handlers (use_test_table=True)
    if TEST_MODE:
        seen_prod = load_seen_ids(SEEN_IDS_FILE)
        seen_test = load_seen_ids(SEEN_IDS_TEST_FILE)
        seen_skip = set(seen_prod.keys()) | set(seen_test.keys())
        seen_write_path = SEEN_IDS_TEST_FILE
        seen_write = seen_test
        use_test_table = True
    else:
        seen_prod = load_seen_ids(SEEN_IDS_FILE)
        seen_skip = set(seen_prod.keys())
        seen_write_path = SEEN_IDS_FILE
        seen_write = seen_prod
        use_test_table = False

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)

    for msg_id_str in iter_message_ids(mail):

        # ✅ Skip if already processed
        if msg_id_str in seen_skip:
            continue

        res, msg_data = mail.fetch(msg_id_str, "(RFC822)")

        for response in msg_data:
            if not isinstance(response, tuple):
                continue

            msg = email.message_from_bytes(response[1])
            date_header = msg["Date"]
            sent_dt = parsedate_to_datetime(date_header)
            timeEmail = sent_dt.strftime("%I:%M %p")

            raw_subject, encoding = decode_header(msg["Subject"])[0]
            subject = raw_subject.decode(encoding) if isinstance(raw_subject, bytes) else raw_subject

            if not subject_matches(subject):
                continue

            raw_from, enc_from = decode_header(msg.get("From"))[0]
            sender = raw_from.decode(enc_from) if isinstance(raw_from, bytes) else raw_from

            body = extract_email_body(msg)

            print("Subject:", subject)
            print("From:", sender)

            matched_any = False
            for rule in RULES:
                if not sender_matches(rule, sender):
                    continue

                match = rule["regex"].search(body)
                if match:
                    print(f"Matched rule: {rule['name']}")

                    # ✅ handler does DB insert; we pass use_test_table down
                    rule["handler"](mail, msg_id_str, match, timeEmail, use_test_table=use_test_table)

                    # Optional: label processed in Gmail too
                    mail.store(msg_id_str, '+X-GM-LABELS', '(PROCESSED)')
                    mail.store(msg_id_str, '-X-GM-LABELS', r'(\Processed)')
                    # ✅ Archive: remove from Inbox
                    mail.store(msg_id_str, "-X-GM-LABELS", r"(\Inbox)")

                    # ✅ Mark as processed in the appropriate JSON (prod OR test)
                    mark_seen(seen_write_path, seen_write, msg_id_str, subject)
                    matched_any = True
                    break

            if not matched_any:
                print("No rule matched this email.")
                if re.search("declined", body, re.IGNORECASE):
                    print("Declined")
                    mail.store(msg_id_str, '+X-GM-LABELS', '(DECLINED)')
                    mail.store(msg_id_str, '-X-GM-LABELS', r'(\Processed)')
                    # ✅ don’t keep re-checking declined emails forever
                    mark_seen(seen_write_path, seen_write, msg_id_str, subject)
                print(body)

            print("=" * 80)

    mail.logout()


if __name__ == '__main__':
    test()
