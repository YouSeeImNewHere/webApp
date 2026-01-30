import imaplib
import email
from email.header import decode_header
import os
import time
from dotenv import load_dotenv
import requests

from .email_handlers import *   # handlers + account constants (still used for inserts)
from db import with_db_cursor, query_db, open_pool, close_pool


# ============================================================
# DEBUG
# ============================================================
DEBUG = (os.getenv("EMAILFETCH_DEBUG") or "").lower() in ("1", "true", "yes")
BATCH_SIZE = 200

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[emailFetch {ts}] {msg}", flush=True)

def dbg(msg: str):
    if DEBUG:
        log(msg)

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
PUSHOVER_USER = os.getenv("PUSHOVER_USER") or ""
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN") or ""

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
    r".*?\n([A-Z0-9][A-Z0-9 &'.,\-*/]+?)\s*\n"
    r"\$([\d,]+\.\d{2})\*?\s*\n"
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

    {"name": "amex payment", "regex": amexPaymentRegex, "handler": amexPayment},
    {"name": "discover payment", "regex": discoverPaymentRegex, "handler": discoverPayment},
    {"name": "capital one payment", "regex": capOnePaymentRegex, "handler": capitalOnePayment},

    {"name": "navy federal zelle", "regex": navyFedZelleRegex, "handler": navyFedZelle},
]


# ============================================================
# DB
# ============================================================

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

def extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="ignore")
    return msg.get_payload(decode=True).decode(errors="ignore")

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
MAILBOXES = ["INBOX"]

def get_imap_ids(mail):
    ids = []
    for box in MAILBOXES:
        mail.select(box)
        status, data = mail.search(None, "X-GM-RAW", "newer_than:30d")
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

    log("Connecting to Gmail…")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)

    try:
        all_ids = get_imap_ids(mail)
        log(f"Found {len(all_ids)} emails")

        for i in range(0, len(all_ids), BATCH_SIZE):
            batch = all_ids[i:i+BATCH_SIZE]
            dbg(f"Batch {i//BATCH_SIZE + 1} ({len(batch)})")

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
                imap_id = batch[min(idx, len(batch)-1)]
                subj = decode_hdr(h.get("Subject"))
                sndr = decode_hdr(h.get("From"))
                date = h.get("Date") or ""
                k = dedupe_key(h, sndr, subj, date, imap_id)
                keys.append(k)
                meta.append((imap_id, subj, sndr, date, h))

            seen = seen_keys(keys, seen_table)
            rows = []

            for (imap_id, subject, sender, date, hdr), key in zip(meta, keys):
                # ✅ Deduping means this is a "new" email for our pipeline
                if key in seen:
                    continue

                if not subject_matches(subject):
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
                    m = rule["regex"].search(body)
                    if not m:
                        continue

                    # ✅ Matched a rule. Now run handler (inserts to DB), then send pushover.
                    matched = True
                    extracted = extract_fields(rule["name"], m)

                    try:
                        result = rule["handler"](mail, imap_id, m, "", use_test_table=TEST_MODE)

                        # ✅ Only notify if a NEW row was inserted
                        if not result or not result.get("inserted"):
                            # matched email, but it updated existing row OR handler skipped insert
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

                        merchant = result.get("merchant") or "Unknown"
                        amt = result.get("amount")
                        date_str = result.get("purchaseDate") or "unknown date"
                        time_str = result.get("time") or "unknown time"

                        amt_str = f"${amt:.2f}" if isinstance(amt, (int, float)) else "an unknown amount"

                        title = "Transaction alert"
                        message = f"{bank} {card} was used at {merchant} for {amt_str} on {date_str} at {time_str}"

                        send_pushover(title, message)

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


                    except Exception as e:
                        # Handler failed -> don't notify; record failure
                        log(f"⚠️ handler failed rule={rule['name']} imap_id={imap_id}: {e}")
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
