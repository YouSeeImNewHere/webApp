# email_handlers.py (Postgres)

from __future__ import annotations

from datetime import datetime, timedelta

from db import query_db
#from transactionHandler import *  # provides makeKey/checkKey/find_matching_key/insert_transaction/etc.
from .transactionHandler import *
# =============================================================================
# Shared helper (ONE place to change print/labels/insert behavior)
# =============================================================================

NAVY_DEBIT_ID = 3
NAVY_CASHREWARDS_ID = 6
AMEX_PLATINUM_ID = 2
AMEX_BCP_ID = 8
CAPONE_DEBIT_ID = 4
CAPONE_SAVOR_ID = 5
DISCOVER_IT_ID = 7

BCP_ACCOUNT_NUMBER = "51007"
PLAT_ACCOUNT_NUMBER = "72008"


def _parse_money_to_float(cost: str) -> float:
    # "$1,234.56" -> 1234.56
    return float(cost.replace("$", "").replace(",", ""))


def find_existing_tx_key_by_amount_time_near_date(
    cost: str,
    date_mmddyy: str,
    time_str: str,
    *,
    account_id: int,
    use_test_table: bool = False,
) -> str | None:
    table = "transactions_test" if use_test_table else "transactions"
    amt = _parse_money_to_float(cost)

    base = datetime.strptime(date_mmddyy, "%m/%d/%y").date()
    candidates = [(base + timedelta(days=d)).strftime("%m/%d/%y") for d in (-1, 0, 1)]

    # try with time match first
    rows = query_db(
        f"""
        SELECT id
        FROM {table}
        WHERE account_id = %s
          AND abs(amount - %s) < 0.005
          AND purchasedate = ANY(%s)
          AND time = %s
        LIMIT 1
        """,
        (int(account_id), float(amt), candidates, str(time_str)),
    )
    if rows:
        return rows[0]["id"]

    # fallback: match without time
    rows = query_db(
        f"""
        SELECT id
        FROM {table}
        WHERE account_id = %s
          AND abs(amount - %s) < 0.005
          AND purchasedate = ANY(%s)
        LIMIT 1
        """,
        (int(account_id), float(amt), candidates),
    )
    return rows[0]["id"] if rows else None


def transaction_exists(key: str, *, use_test_table: bool = False) -> bool:
    table = "transactions_test" if use_test_table else "transactions"
    rows = query_db(f"SELECT 1 FROM {table} WHERE id = %s LIMIT 1", (str(key),))
    return bool(rows)


def finalize_transaction(
    mail,
    msg_id_str: str,
    *,
    cost: str,
    card: str,
    where: str,
    time: str,
    date: str,
    key: str,
    bank: str,
    accountType: str,
    source: str = "email",
    use_test_table: bool = False,
    labels_add=(),
    labels_remove=(r"\Inbox \Important",),
):
    # ---- print ----
    print("Cost:", cost)
    print("Card:", card)
    print("Where:", where)
    print("Time:", time)
    print("Date:", date)

    # ---- labels ----
    for lab in labels_add:
        mail.store(msg_id_str, "+X-GM-LABELS", f"({lab})")

    for lab in labels_remove:
        typ, resp = mail.store(msg_id_str, "-X-GM-LABELS", f"({lab})")
        print("REMOVE LABEL:", lab, "->", typ, resp)

    # Always mark processed here (single place to change)
    mail.store(msg_id_str, "+X-GM-LABELS", "(ProcessedNew)")

    # ---- insert ----
    insert_transaction(
        key,
        bank,
        card,
        accountType,
        cost,
        where,
        date,
        time,
        source,
        use_test_table=use_test_table,
    )

# =============================================================================
# Handlers (unchanged below)
# =============================================================================
# =============================================================================
# Handlers
# =============================================================================
def navyFedCard(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)
    where = match.group(3)
    time = match.group(4)
    date = match.group(5)

    card_kind = match.group(2)
    if card_kind == "credit":
        card = "cashRewards"
        accountType = "credit"
        account_id = NAVY_CASHREWARDS_ID
    else:
        card = "Debit"
        accountType = "checking"
        account_id = NAVY_DEBIT_ID

    # default key from this email's date
    key = makeKey(cost, date, account_id=account_id)

    # try fuzzy match against stored withdrawal keys (same amount, same time, date +/- 1 day)
    matched_key = find_matching_key(cost, date, time, account_id=account_id)

    if matched_key:
        checkKey(mail, matched_key)
        key = matched_key
    else:
        checkKey(mail, key)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card=card, where=where, time=time, date=date,
        key=key, bank="Navy Federal", accountType=accountType,
        labels_add=("NavyFedPurchase",),
    )


def navyFedWithdrawal(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)
    date = match.group(2)
    time = match.group(3)

    key = makeKey(cost, date, account_id=NAVY_DEBIT_ID)

    # 1) exact key exists → nothing to do
    if transaction_exists(key, use_test_table=use_test_table):
        return

    # 2) NEW: if a tx already exists under a slightly different key, don’t insert a duplicate
    existing_key = find_existing_tx_key_by_amount_time_near_date(
        cost, date, time,
        account_id=NAVY_DEBIT_ID,
        use_test_table=use_test_table
    )
    if existing_key:
        # optional: label this email as “matched”
        mail.store(msg_id_str, "+X-GM-LABELS", "(NavyFedWithdrawalMatched)")
        return

    # 3) otherwise it truly is unmatched → keep current behavior
    add_key(cost, date, time, msg_id_str, account_id=NAVY_DEBIT_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Debit", where="unknown", time=time, date=date,
        key=key, bank="Navy Federal", accountType="checking",
        labels_add=("NavyFedPurchase",),
    )


def navyFedDeposit(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)
    date = match.group(2)
    time = match.group(3)

    # ✅ Force deposits to be negative
    # cost is like "$1,234.56"
    amt = float(cost.replace("$", "").replace(",", ""))
    cost = f"-{amt:.2f}"   # "-1234.56"

    key = makeKey(cost, date, account_id=NAVY_DEBIT_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Debit", where="unknown", time=time, date=date,
        key=key, bank="Navy Federal", accountType="checking",
        labels_add=("NavyFedDeposit",),
    )


def navyFedCreditHold(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    where = match.group(1)
    time = match.group(2)
    date = match.group(3)
    cost = ""

    key = makeKey(cost, date, account_id=NAVY_CASHREWARDS_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="cashRewards", where=where, time=time, date=date,
        key=key, bank="Navy Federal", accountType="credit",
        labels_add=("NavyFedPurchase",),
    )


def americanExpress(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    account = match.group(1)
    where = match.group(2)
    cost = match.group(3)

    date = match.group(4)
    date = datetime.strptime(date, "%b %d, %Y").strftime("%m/%d/%y")

    if account == PLAT_ACCOUNT_NUMBER:
        card = "Platinum"
        account_id = AMEX_PLATINUM_ID
    elif account == BCP_ACCOUNT_NUMBER:
        card = "Blue Cash Preferred"
        account_id = AMEX_BCP_ID
    else:
        raise ValueError(f"Unknown AMEX account ending: {account}")

    key = makeKey(cost, date, account_id=account_id)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card=card, where=where, time=timeEmail, date=date,
        key=key, bank="American Express", accountType="credit",
        labels_add=("AmexPurchase",),
    )


def capitalOneDebit(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)
    where = match.group(2)

    date = match.group(3)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date, account_id=CAPONE_DEBIT_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Debit", where=where, time=timeEmail, date=date,
        key=key, bank="Capital One", accountType="checking",
        labels_add=("CapitalOne",),
    )


def capitalOneCredit(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    where = match.group(2)
    cost = match.group(3)

    date = match.group(1)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date, account_id=CAPONE_SAVOR_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Savor", where=where, time=timeEmail, date=date,
        key=key, bank="Capital One", accountType="credit",
        labels_add=("CapitalOne",),
    )


def discovery(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    where = match.group(2)
    cost = match.group(3)

    date = match.group(1)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date, account_id=DISCOVER_IT_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Discover It", where=where, time=timeEmail, date=date,
        key=key, bank="Discovery", accountType="credit",
        labels_add=("Discovery",),
    )

def amexPayment(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    where = "Thanks for your payment"

    account = match.group(1)
    cost = match.group(2)
    cost = f"-{cost.lstrip('-')}"

    date = match.group(3)
    date = datetime.strptime(date, "%b %d, %Y").strftime("%m/%d/%y")

    # ---- Account → card mapping ----
    if PLAT_ACCOUNT_NUMBER in account:
        card = "Platinum"
        account_id = AMEX_PLATINUM_ID
    elif BCP_ACCOUNT_NUMBER in account:
        card = "Blue Cash Preferred"
        account_id = AMEX_BCP_ID
    else:
        raise ValueError(f"Unknown AMEX account ending: {account}")

    key = makeKey(cost, date, account_id=account_id)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost,
        card=card,
        where=where,
        time=timeEmail,
        date=date,
        key=key,
        bank="American Express",
        accountType="credit",
        labels_add=("AmexPurchase",),
    )

def discoverPayment(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)
    cost = f"-{cost.lstrip('-')}"

    where = "Thanks for your payment"

    date = match.group(2)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date, account_id=DISCOVER_IT_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Discover It", where=where, time=timeEmail, date=date,
        key=key, bank="Discovery", accountType="credit",
        labels_add=("Discovery",),
    )

def capitalOnePayment(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)
    cost = f"-{cost.lstrip('-')}"

    where = "Thanks for your payment"

    date = match.group(2)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date, account_id=CAPONE_SAVOR_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Savor", where=where, time=timeEmail, date=date,
        key=key, bank="Capital One", accountType="credit",
        labels_add=("CapitalOne",),
    )

def navyFedZelle(mail, msg_id_str, match, timeEmail, use_test_table: bool = False):
    cost = match.group(1)

    where = f"Zelle - {match.group(2)}"

    date = match.group(3)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date, account_id=NAVY_DEBIT_ID)

    finalize_transaction(
        mail, msg_id_str,
        use_test_table=use_test_table,
        cost=cost, card="Debit", where=where, time=timeEmail, date=date,
        key=key, bank="Navy Federal", accountType="checking",
        labels_add=("NavyFedPurchase",),
    )

