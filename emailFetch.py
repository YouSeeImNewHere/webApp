import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from email_handlers import *
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


def load_seen_ids() -> dict:
    if SEEN_IDS_FILE.exists():
        try:
            with SEEN_IDS_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # If file is corrupt for any reason, start fresh rather than crash
            return {}
    return {}


def save_seen_ids(seen: dict) -> None:
    with SEEN_IDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def mark_seen(seen: dict, msg_id_str: str, subject: str) -> None:
    # store minimal metadata (handy for debugging)
    seen[msg_id_str] = {
        "subject": subject,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }
    save_seen_ids(seen)


SUBJECTS = [
    "Transaction Notification",  # navy fed
    "Withdrawal Notification",  # navy fed
    "Large Purchase Approved",  # amex
    "Debit Card Purchase",  # capital one debit
    "A new transaction was charged to your account",  # capital one credit
    "Transaction Alert",  # discovery
    "Deposit Notification"  # navy fed
]

navyFedRegex = re.compile(
    r"The transaction for (\$[\d,]+\.\d{2}) was approved for your (credit|debit) card ending in \d{4} at (.*) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{3} on ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2})")
navyFedWithdrawalRegex = re.compile(
    r"(\$[\d,]+\.\d{2}) was withdrawn from your Active Duty Checking account ending in \d{4}. As of ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2}) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{2}")
navyFedDepositRegex = re.compile(r"(\$[\d,]+\.\d{2}) .* of (\d\d\/\d\d\/\d\d) at (\d\d:\d\d \w+) ")
navyFedCreditHoldRegex = re.compile(r"at (.*) at (\d\d:\d\d \w+) .* on (\d\d\/\d\d\/\d\d)")
americanExpressRegex = re.compile(r"online.\n(.*)\n(\$[\d,]+\.\d{2})\*\n([A-Za-z]{3},\s[A-Za-z]{3}\s\d{1,2},\s\d{4})")
capitalOneDebitRegex = re.compile(
    r"Amount: (\$[\d,]+\.\d{2})\r?\n.* - (.*)\r?\nDate: ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})")
capitalOneCreditRegex = re.compile(
    r"As requested, we're notifying you that on ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}), at (.*), .* of (\$[\d,]+\.\d{2})")
discoveryRegex = re.compile(
    r"Transaction Date:: ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})\s*Merchant: (.*)\s*Amount: (\$[\d,]+\.\d{2})")


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
    seen = load_seen_ids()

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)
    mail.select("INBOX")

    # Keep your existing behavior (scan ALL), but skip ones we've already processed.
    # If you later want speed, we can switch this to Gmail raw query -label:PROCESSED.
    status, data = mail.search(None, "ALL")
    message_ids = data[0].split()[:]

    for msg_id in reversed(message_ids):
        msg_id_str = msg_id.decode()  # MUST be string, not bytes

        # ✅ Skip if already processed
        if msg_id_str in seen:
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
                match = rule["regex"].search(body)
                if match:
                    print(f"Matched rule: {rule['name']}")
                    # ✅ Only mark seen if handler succeeds
                    rule["handler"](mail, msg_id_str, match, timeEmail)

                    # Optional: label processed in Gmail too
                    mail.store(msg_id_str, '+X-GM-LABELS', '(PROCESSED)')
                    mail.store(msg_id_str, '-X-GM-LABELS', r'(\Processed)')

                    mark_seen(seen, msg_id_str, subject)
                    matched_any = True
                    break

            if not matched_any:
                print("No rule matched this email.")
                if re.search("declined", body, re.IGNORECASE):
                    print("Declined")
                    mail.store(msg_id_str, '+X-GM-LABELS', '(DECLINED)')
                    mail.store(msg_id_str, '-X-GM-LABELS', r'(\Processed)')
                    # ✅ don’t keep re-checking declined emails forever
                    mark_seen(seen, msg_id_str, subject)
                print(body)

            print("=" * 80)

    mail.logout()


if __name__ == '__main__':
    test()
