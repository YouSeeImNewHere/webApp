# email_handlers.py
from transactionHandler import *
from datetime import datetime


# =============================================================================
# Shared helper (ONE place to change print/labels/insert behavior)
# =============================================================================


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
    labels_add=(),
    labels_remove=(r"(\Inbox)",),
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
        mail.store(msg_id_str, "-X-GM-LABELS", lab)

    # Always mark processed here (single place to change)
    mail.store(msg_id_str, "+X-GM-LABELS", "(ProcessedNew)")

    # ---- insert ----
    insert_transaction(key, bank, card, accountType, cost, where, date, time, source)


# =============================================================================
# Handlers
# =============================================================================
def navyFedCard(mail, msg_id_str, match, timeEmail):
    cost = match.group(1)
    where = match.group(3)
    time = match.group(4)
    date = match.group(5)

    key = makeKey(cost, date)
    checkKey(key)

    card_kind = match.group(2)
    if card_kind == "credit":
        card = "cashRewards"
        accountType = "credit"
    else:
        card = "Debit"
        accountType = "checking"

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card=card, where=where, time=time, date=date,
        key=key, bank="Navy Federal", accountType=accountType,
        labels_add=("NavyFedPurchase",),
    )


def navyFedWithdrawal(mail, msg_id_str, match, timeEmail):
    cost = match.group(1)
    date = match.group(2)
    time = match.group(3)

    key = makeKey(cost, date)
    add_key(key, cost, date, time)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="Debit", where="unknown", time=time, date=date,
        key=key, bank="Navy Federal", accountType="checking",
        labels_add=("NavyFedPurchase",),
    )


def navyFedDeposit(mail, msg_id_str, match, timeEmail):
    cost = match.group(1)
    date = match.group(2)
    time = match.group(3)

    key = makeKey(cost, date)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="Debit", where="unknown", time=time, date=date,
        key=key, bank="Navy Federal", accountType="checking",
        labels_add=("NavyFedDeposit",),
    )


def navyFedCreditHold(mail, msg_id_str, match, timeEmail):
    where = match.group(1)
    time = match.group(2)
    date = match.group(3)
    cost = "unknown"

    key = makeKey(cost, date)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="cashRewards", where=where, time=time, date=date,
        key=key, bank="Navy Federal", accountType="credit",
        labels_add=("NavyFedPurchase",),
    )


def americanExpress(mail, msg_id_str, match, timeEmail):
    where = match.group(1)
    cost = match.group(2)

    date = match.group(3)
    date = datetime.strptime(date, "%a, %b %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="Platinum", where=where, time=timeEmail, date=date,
        key=key, bank="American Express", accountType="credit",
        labels_add=("AmexPurchase",),
    )


def capitalOneDebit(mail, msg_id_str, match, timeEmail):
    cost = match.group(1)
    where = match.group(2)

    date = match.group(3)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="Debit", where=where, time=timeEmail, date=date,
        key=key, bank="Capital One", accountType="checking",
        labels_add=("CapitalOne",),
    )


def capitalOneCredit(mail, msg_id_str, match, timeEmail):
    where = match.group(2)
    cost = match.group(3)

    date = match.group(1)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="Savor", where=where, time=timeEmail, date=date,
        key=key, bank="Capital One", accountType="credit",
        labels_add=("CapitalOne",),
    )


def discovery(mail, msg_id_str, match, timeEmail):
    where = match.group(2)
    cost = match.group(3)

    date = match.group(1)
    date = datetime.strptime(date, "%B %d, %Y").strftime("%m/%d/%y")

    key = makeKey(cost, date)

    finalize_transaction(
        mail, msg_id_str,
        cost=cost, card="Discover It", where=where, time=timeEmail, date=date,
        key=key, bank="Discovery", accountType="credit",
        labels_add=("Discovery",),
    )
