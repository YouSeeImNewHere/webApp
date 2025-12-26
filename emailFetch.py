import imaplib
import email
from email.header import decode_header
import re
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from email_handlers import *
from dotenv import load_dotenv
import os

load_dotenv()

EMAIL = os.getenv("GMAIL_ADDRESS")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

SUBJECTS = [
    "Transaction Notification",
    "Withdrawal Notification",
    "Large Purchase Approved",
    "Debit Card Purchase",
    "A new transaction was charged to your account",
    "Transaction Alert",
    "Deposit Notification"
]

navyFedRegex = re.compile(r"The transaction for (\$[\d,]+\.\d{2}) was approved for your (credit|debit) card ending in \d{4} at (.*) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{3} on ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2})")
navyFedWithdrawalRegex = re.compile(r"(\$[\d,]+\.\d{2}) was withdrawn from your Active Duty Checking account ending in \d{4}. As of ((?:0[1-9]|1[0-2])\/(?:[0-2][0-9]|3[01])\/\d{2}) at ((?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)) [A-Z]{2}")
navyFedDepositRegex = re.compile(r"(\$[\d,]+\.\d{2}) .* of (\d\d\/\d\d\/\d\d) at (\d\d:\d\d \w+) ")
navyFedCreditHoldRegex = re.compile(r"at (.*) at (\d\d:\d\d \w+) .* on (\d\d\/\d\d\/\d\d)")
americanExpressRegex = re.compile(r"online.\n(.*)\n(\$[\d,]+\.\d{2})\*\n([A-Za-z]{3},\s[A-Za-z]{3}\s\d{1,2},\s\d{4})")
capitalOneDebitRegex = re.compile(r"Amount: (\$[\d,]+\.\d{2})\r?\n.* - (.*)\r?\nDate: ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})")
capitalOneCreditRegex = re.compile(r"As requested, we're notifying you that on ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}), at (.*), .* of (\$[\d,]+\.\d{2})")
discoveryRegex = re.compile(r"Transaction Date:: ((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})\s*Merchant: (.*)\s*Amount: (\$[\d,]+\.\d{2})")

def subject_matches(subject: str) -> bool:
    if not subject:
        return False
    lower = subject.lower()
    return any(keyword.lower() in lower for keyword in SUBJECTS)

RULES = [
    {
        "name": "navy credit",
        "regex": navyFedRegex,
        "handler": navyFedCard
    },
    {
        "name": "navy withdrawal",
        "regex": navyFedWithdrawalRegex,
        "handler": navyFedWithdrawal
    },
    {
        "name": "navy deposit",
        "regex": navyFedDepositRegex,
        "handler": navyFedDeposit
    },
    {
        "name": "navy credit hold",
        "regex": navyFedCreditHoldRegex,
        "handler": navyFedCreditHold
    },
    {
        "name": "american express",
        "regex": americanExpressRegex,
        "handler": americanExpress
    },
    {
        "name": "capital one debit",
        "regex": capitalOneDebitRegex,
        "handler": capitalOneDebit
    },
    {
        "name": "capital one credit",
        "regex": capitalOneCreditRegex,
        "handler": capitalOneCredit
    },
    {
        "name": "discovery credit",
        "regex": discoveryRegex,
        "handler": discovery
    }
]

def extract_email_body(msg) -> str:
    """
    Returns the best-effort text body from an email.message.Message.
    Prefers text/plain, falls back to text/html (converted to text).
    """
    # 1) If multipart, walk parts
    if msg.is_multipart():
        plain_text = None
        html_text = None

        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_text = part.get_payload(decode=True).decode(errors="ignore")
                break  # we found what we want
            elif content_type == "text/html" and html_text is None:
                html_text = part.get_payload(decode=True).decode(errors="ignore")

        if plain_text is not None:
            return plain_text.strip()

        if html_text is not None:
            # convert HTML → text
            soup = BeautifulSoup(html_text, "html.parser")
            return soup.get_text(separator="\n").strip()

        return ""

    # 2) Not multipart: single-part message
    content_type = msg.get_content_type()
    payload = msg.get_payload(decode=True).decode(errors="ignore")

    if content_type == "text/plain":
        return payload.strip()

    if content_type == "text/html":
        soup = BeautifulSoup(payload, "html.parser")
        return soup.get_text(separator="\n").strip()

    return payload.strip()

def test():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)

    mail.select("NavyFedPurchase")

    status, data = mail.search(None, "ALL")
    message_ids = data[0].split()

    for msg_id in reversed(message_ids):
        msg_id_str = msg_id.decode()   # MUST be string, not bytes

        res, msg_data = mail.fetch(msg_id_str, "(RFC822)")
        for response in msg_data:
            if not isinstance(response, tuple):
                continue

            msg = email.message_from_bytes(response[1])
            date_header = msg["Date"]
            sent_dt = parsedate_to_datetime(date_header)
            timeEmail = sent_dt.strftime("%I:%M %p")

            # decode subject
            raw_subject, encoding = decode_header(msg["Subject"])[0]
            subject = raw_subject.decode(encoding) if isinstance(raw_subject, bytes) else raw_subject

            if not subject_matches(subject):
                continue

            raw_from, enc_from = decode_header(msg.get("From"))[0]
            sender = raw_from.decode(enc_from) if isinstance(raw_from, bytes) else raw_from

            # extract body
            body = extract_email_body(msg)

            print("Subject:", subject)
            print("From:", sender)

            matched_any = False
            for rule in RULES:
                match = rule["regex"].search(body)
                if match:
                    print(f"Matched rule: {rule['name']}")
                    rule["handler"](mail, msg_id_str, match, timeEmail)
                    matched_any = True
                    break  # stop after first match

            if not matched_any:
                print("No rule matched this email.")
                if re.search("declined", body, re.IGNORECASE):
                    print("Declined")
                    mail.store(msg_id_str, '+X-GM-LABELS', '(DECLINED)')
                    mail.store(msg_id_str, '-X-GM-LABELS', r'(\Processed)')
                print(body)

            print("=" * 80)

    mail.logout()

if __name__ == '__main__':
    test()
