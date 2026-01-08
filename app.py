from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import sqlite3
from datetime import datetime, timedelta
import re
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import calendar

from emails.transactionHandler import DB_PATH
from recurring import get_recurring, get_ignored_merchants_preview

app = FastAPI()

def _last_day_of_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]

def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    # weekday: Mon=0..Sun=6
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))

def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    d = date(year, month, _last_day_of_month(year, month))
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d

def _observed(d: date) -> date:
    # Federal holiday observed rules: if Sat -> Fri, if Sun -> Mon
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d

def _us_federal_holidays_observed(year: int) -> set[date]:
    # Core federal holidays (observed)
    holidays = set()

    # Fixed-date holidays
    holidays.add(_observed(date(year, 1, 1)))    # New Year's Day
    holidays.add(_observed(date(year, 6, 19)))   # Juneteenth
    holidays.add(_observed(date(year, 7, 4)))    # Independence Day
    holidays.add(_observed(date(year, 11, 11)))  # Veterans Day
    holidays.add(_observed(date(year, 12, 25)))  # Christmas Day

    # Weekday-based holidays
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))   # MLK Day: 3rd Mon Jan
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))   # Presidents Day: 3rd Mon Feb
    holidays.add(_last_weekday_of_month(year, 5, 0))     # Memorial Day: last Mon May
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))   # Labor Day: 1st Mon Sep
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))  # Columbus Day: 2nd Mon Oct
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving: 4th Thu Nov

    return holidays

def _previous_workday(d: date, holiday_set: set[date]) -> date:
    while _is_weekend(d) or d in holiday_set:
        d -= timedelta(days=1)
    return d

def _paycheck_dates_for_month(year: int, month: int) -> list[date]:
    """
    Paydays are 1st and 15th, but deposit is day before.
    If that day-before is weekend/holiday -> previous workday.

    IMPORTANT:
    - The deposit for NEXT month’s 1st can land in THIS month
      (ex: Feb 1 payday -> Jan 31 deposit).
    """
    hol_this = _us_federal_holidays_observed(year)

    def deposit_for_target(target: date) -> date:
        # use holidays for the target's year (can differ when target is next year)
        hol = hol_this if target.year == year else _us_federal_holidays_observed(target.year)
        d = target - timedelta(days=1)
        return _previous_workday(d, hol)

    paydays = []

    # 1st and 15th of this month
    paydays.append(deposit_for_target(date(year, month, 1)))
    paydays.append(deposit_for_target(date(year, month, 15)))

    # ALSO: 1st of next month (deposit can fall in this month)
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1

    next_month_deposit = deposit_for_target(date(ny, nm, 1))
    # only include if it lands in the requested month
    if next_month_deposit.year == year and next_month_deposit.month == month:
        paydays.append(next_month_deposit)

    return sorted(set(paydays))


# =============================================================================
# App + Static Frontend
# =============================================================================

@app.get("/__ping")
def ping():
    return {"ok": True, "file": __file__}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return FileResponse("static/home.html")


@app.get("/account")
def account_page():
    return FileResponse("static/account.html")


# =============================================================================
# DB Helpers
# =============================================================================

def query_db(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def with_db_cursor():
    """
    Convenience helper: returns (conn, cur) configured with Row factory.
    Caller is responsible for closing conn.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


# =============================================================================
# Date Parsing Helpers
# =============================================================================

def parse_iso(d: str):
    return datetime.strptime(d, "%Y-%m-%d").date()


def parse_posted_date(s: str):
    if not s:
        return None
    s = str(s).strip()
    if s.lower() == "unknown":
        return None
    return datetime.strptime(s, "%m/%d/%y").date()


# =============================================================================
# Balance / Series Helpers (Net Worth, Savings, Investments, Accounts)
# =============================================================================


def parse_db_date(s):
    if not s:
        return None
    s = str(s).strip().lower()
    if s == "unknown":
        return None
    return datetime.strptime(s, "%m/%d/%y").date()


def apply_transaction(current_totals, account_id, amount, account_type):
    t = (account_type or "other").lower()
    amt = float(amount or 0)

    if t in ("investment"):
        # contributions increase net worth
        delta = amt
    else:
        # checking / credit spending reduces net worth
        delta = -amt

    current_totals[account_id] = current_totals.get(account_id, 0.0) + delta


def load_starting_balances(cur):
    cur.execute("""
      SELECT account_id, SUM(Start) AS total_start
      FROM StartingBalance
      GROUP BY account_id
    """)
    return {int(r["account_id"]): float(r["total_start"] or 0) for r in cur.fetchall()}


def load_account_type_map(cur):
    cur.execute("SELECT id, LOWER(accountType) AS t FROM accounts")
    return {int(r["id"]): (r["t"] or "other") for r in cur.fetchall()}


def load_transactions(cur):
    cur.execute("""
      SELECT
        t.postedDate,
        t.purchaseDate,
        t.account_id,
        t.amount,
        LOWER(a.accountType) AS accountType
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """)
    rows = cur.fetchall()

    tx = []
    for r in rows:
        posted = parse_posted_date(r["postedDate"])
        purchase = parse_posted_date(r["purchaseDate"])

        # RULE: if no posted date, use transaction (purchase) date
        tx_date = posted if posted is not None else purchase

        # Safety: skip totally broken rows
        if tx_date is None:
            continue

        amt_raw = r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            # skip junk like "unknown", "", None
            continue

        tx.append({
            "date": tx_date,
            "account_id": int(r["account_id"]),
            "amount": amt,
            "accountType": r["accountType"] or "other",
        })

    tx.sort(key=lambda t: t["date"])
    return tx


def build_series(start_date, end_date, starting, transactions, value_fn):
    """
    Rolls balances forward, then emits day-by-day values using value_fn(current_totals).
    Returns [{"date": "YYYY-MM-DD", "value": number}, ...]
    """
    current_totals = starting.copy()
    results = []
    tx_index = 0

    # A) roll forward before start_date
    while tx_index < len(transactions) and transactions[tx_index]["date"] < start_date:
        t = transactions[tx_index]
        apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
        tx_index += 1

    # B) day-by-day
    day = start_date
    while day <= end_date:
        while tx_index < len(transactions) and transactions[tx_index]["date"] == day:
            t = transactions[tx_index]
            apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
            tx_index += 1

        results.append({"date": day.isoformat(), "value": float(value_fn(current_totals))})
        day += timedelta(days=1)

    return results


from recurring import get_recurring  # new file you created

@app.get("/recurring")
def recurring(min_occ: int = 3, include_stale: bool = False):
    return get_recurring(min_occ=min_occ, include_stale=include_stale)

# =============================================================================
# Series Endpoints (Net Worth / Savings / Investments)
# =============================================================================

@app.get("/net-worth")
def net_worth(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances(cur)
    transactions = load_transactions(cur)
    acct_types = load_account_type_map(cur)

    conn.close()

    current_totals = starting.copy()
    results = []
    tx_index = 0

    # A) roll forward before start_date
    while tx_index < len(transactions) and transactions[tx_index]["date"] < start_date:
        t = transactions[tx_index]
        apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
        tx_index += 1

    # B) day-by-day
    day = start_date
    while day <= end_date:
        while tx_index < len(transactions) and transactions[tx_index]["date"] == day:
            t = transactions[tx_index]
            apply_transaction(current_totals, t["account_id"], t["amount"], t["accountType"])
            tx_index += 1

        banks = 0.0
        savings = 0.0
        cards_balance = 0.0  # signed: negative = owe, positive = surplus

        for aid, bal in current_totals.items():
            t = (acct_types.get(aid) or "other").lower()
            if t == "savings":
                savings += bal
            elif t == "credit":
                cards_balance += bal
            else:
                # checking + investment + other => "banks"
                banks += bal

        cards_owed = max(0.0, -cards_balance)  # positive debt magnitude for UI
        net = banks + savings + cards_balance  # signed contribution (liability reduces)

        results.append({
            "date": day.isoformat(),
            "value": float(net),
            "banks": float(banks),
            "savings": float(savings),
            "cards": float(cards_owed),  # what your UI expects
            "cards_balance": float(cards_balance)  # optional, handy for later
        })

        day += timedelta(days=1)

    return results


@app.get("/savings")
def savings(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances(cur)
    transactions = load_transactions(cur)
    acct_types = load_account_type_map(cur)  # ✅ before close

    conn.close()

    def savings_only(totals):
        return sum(bal for aid, bal in totals.items() if acct_types.get(aid) == "savings")

    return build_series(start_date, end_date, starting, transactions, value_fn=savings_only)


@app.get("/investments")
def investments(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    starting = load_starting_balances(cur)
    transactions = load_transactions(cur)
    acct_types = load_account_type_map(cur)  # ✅

    conn.close()

    def investments_only(totals):
        return sum(bal for aid, bal in totals.items() if acct_types.get(aid) == "investment")

    return build_series(start_date, end_date, starting, transactions, value_fn=investments_only)


# =============================================================================
# Transactions Feeds (Recent / Per-Account)
# =============================================================================

@app.get("/transactions")
def transactions(limit: int = 15):
    sql = """
      WITH tx AS (
        SELECT
          t.id,
          t.postedDate,
          t.purchaseDate,
          t.merchant,
          t.amount,
          t.status,
          a.institution AS bank,
          a.name        AS card,
          LOWER(a.accountType) AS accountType,

          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,

          CASE
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
              date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
              date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
            ELSE NULL
          END AS d

        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      )
      SELECT id, raw_date AS postedDate, merchant, amount, status, bank, card, accountType
      FROM tx
      ORDER BY d DESC, id DESC
      LIMIT ?
    """

    return query_db(sql, (limit,))


@app.get("/account-transactions")
def account_transactions(account_id: int, limit: int = 200):
    sql = """
      WITH tx AS (
        SELECT
          id,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
          merchant,
          amount,

          CASE
            WHEN length(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown'))) = 8 THEN
              date('20' || substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 7, 2) || '-' ||
                         substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 1, 2) || '-' ||
                         substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 4, 2))
            WHEN length(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown'))) = 10 THEN
              date(substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 7, 4) || '-' ||
                   substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 4, 2))
            ELSE NULL
          END AS d
        FROM transactions
        WHERE account_id = ?
      )
      SELECT id, raw_date AS postedDate, merchant, amount
      FROM tx
      ORDER BY d DESC, id DESC
      LIMIT ?
    """

    return query_db(sql, (account_id, limit))


# =============================================================================
# Bank Totals Sidebar
# =============================================================================

@app.get("/bank-totals")
def bank_totals():
    conn, cur = with_db_cursor()

    accounts = cur.execute("""
      SELECT id, institution, name, LOWER(accountType) AS accountType
      FROM accounts
    """).fetchall()

    starting = {
      int(r["account_id"]): float(r["start_total"] or 0)
      for r in cur.execute("""
        SELECT account_id, SUM(Start) AS start_total
        FROM StartingBalance
        GROUP BY account_id
      """).fetchall()
    }

    tx_totals = {
      int(r["account_id"]): float(r["trans_total"] or 0)
      for r in cur.execute("""
        SELECT account_id, SUM(amount) AS trans_total
        FROM transactions
        GROUP BY account_id
      """).fetchall()
    }

    conn.close()

    by_type = {"checking": [], "savings": [], "investment": [], "credit": [], "other": []}

    for a in accounts:
      aid = int(a["id"])
      acc_type = a["accountType"] or "other"

      start = starting.get(aid, 0.0)
      trans = tx_totals.get(aid, 0.0)

      # savings/investment: start + trans
      # everything else (checking/credit): start - trans
      balance = start - trans

      bucket = acc_type if acc_type in by_type else "other"
      display_name = f'{a["institution"]} — {a["name"]}'
      by_type[bucket].append({"id": aid, "name": display_name, "total": balance})

    for k in by_type:
      by_type[k].sort(key=lambda x: x["total"], reverse=True)

    return {
      k: {"total": sum(x["total"] for x in lst), "accounts": lst}
      for k, lst in by_type.items()
    }


# =============================================================================
# Categories + Rules
# =============================================================================

class RuleCreate(BaseModel):
    category: str
    keywords: List[str] = []     # e.g. ["chick fil a", "chick-fil-a"]
    regex: Optional[str] = None  # advanced override
    apply_now: bool = True


def build_pattern_from_keywords(keywords: List[str]) -> str:
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    if not cleaned:
        raise ValueError("No keywords provided")
    alts = "|".join(re.escape(k) for k in cleaned)
    return alts


def apply_rule_to_existing(cur, category: str, pattern: str, flags: str):
    # SQLite has no REGEXP by default; apply in Python.
    re_flags = re.IGNORECASE if "i" in (flags or "") else 0
    rx = re.compile(pattern, re_flags)

    rows = cur.execute("""
      SELECT id, merchant
      FROM transactions
      WHERE category IS NULL OR TRIM(category) = ''
    """).fetchall()

    matched_ids = []
    for r in rows:
        merchant = (r["merchant"] or "")
        if rx.search(merchant):
            matched_ids.append(r["id"])

    if matched_ids:
        cur.executemany(
            "UPDATE transactions SET category = ? WHERE id = ?",
            [(category, txid) for txid in matched_ids]
        )

    return len(matched_ids)


@app.get("/categories")
def list_categories():
    conn, cur = with_db_cursor()

    rows = cur.execute("""
      SELECT category FROM (
        SELECT TRIM(category) AS category
        FROM transactions
        WHERE category IS NOT NULL AND TRIM(category) <> ''
        UNION
        SELECT TRIM(category) AS category
        FROM CategoryRules
        WHERE category IS NOT NULL AND TRIM(category) <> ''
      )
      ORDER BY category COLLATE NOCASE
    """).fetchall()

    conn.close()
    return [r["category"] for r in rows]


@app.post("/category-rules")
def create_category_rule(payload: RuleCreate):
    category = payload.category.strip()
    if not category:
        return {"ok": False, "error": "Category is required"}

    if payload.regex and payload.regex.strip():
        pattern = payload.regex.strip()
    else:
        try:
            pattern = build_pattern_from_keywords(payload.keywords)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    flags = "i"  # default case-insensitive

    conn, cur = with_db_cursor()

    cur.execute("""
      INSERT INTO CategoryRules (category, pattern, flags, is_active)
      VALUES (?, ?, ?, 1)
    """, (category, pattern, flags))

    applied = 0
    if payload.apply_now:
        applied = apply_rule_to_existing(cur, category, pattern, flags)

    conn.commit()
    conn.close()

    return {"ok": True, "pattern": pattern, "applied": applied}


@app.get("/category-totals-month")
def category_totals_month():
    conn, cur = with_db_cursor()

    today = datetime.today().date()
    first = today.replace(day=1)

    if first.month == 12:
        next_month = datetime(first.year + 1, 1, 1).date()
    else:
        next_month = datetime(first.year, first.month + 1, 1).date()

    unassigned_all_time = cur.execute("""
      SELECT COUNT(*) AS c
      FROM transactions
      WHERE category IS NULL OR TRIM(category) = ''
    """).fetchone()["c"]

    rows = cur.execute("""
      WITH tx AS (
        SELECT
          TRIM(category) AS category,
          amount,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
date(
  '20' || substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 7, 2) || '-' ||
  substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 1, 2) || '-' ||
  substr(COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')), 4, 2)
) AS d

        FROM transactions
        WHERE amount > 0
          AND category IS NOT NULL
          AND TRIM(category) <> ''
      )
      SELECT category, SUM(amount) AS total, COUNT(*) AS tx_count
      FROM tx
      WHERE d >= ? AND d < ?
      GROUP BY category
      ORDER BY total DESC
    """, (first.isoformat(), next_month.isoformat())).fetchall()

    return {
        "unassigned_all_time": int(unassigned_all_time or 0),
        "categories": [
            {
                "category": r["category"],
                "total": float(r["total"] or 0),
                "tx_count": int(r["tx_count"] or 0),
            }
            for r in rows
        ]
    }


@app.get("/unassigned")
def get_unassigned(limit: int = 25, mode: str = "freq"):
    """
    mode:
      - "freq"   => most frequent unassigned merchants
      - "recent" => most recent unassigned transactions
    """
    mode = (mode or "freq").strip().lower()
    conn, cur = with_db_cursor()

    if mode == "recent":
        rows = cur.execute("""
          WITH tx AS (
  SELECT
    t.id,
    COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
    t.merchant,
    t.amount,
    a.institution AS bank,
    a.name        AS card,

    CASE
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
        date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
        date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      ELSE NULL
    END AS d
  FROM transactions t
  JOIN accounts a ON a.id = t.account_id
  WHERE (t.category IS NULL OR TRIM(t.category) = '')
    AND t.merchant IS NOT NULL
    AND TRIM(t.merchant) <> ''
    AND LOWER(TRIM(t.merchant)) <> 'unknown'
)
SELECT id, raw_date AS postedDate, merchant, amount, bank, card
FROM tx
ORDER BY d DESC, id DESC
LIMIT ?

        """, (limit,)).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    # default: freq
    rows = cur.execute("""
      WITH ranked AS (
  SELECT
    t.id,
    t.merchant,
    t.amount,
    a.institution AS bank,
    a.name        AS card,
    COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
    COUNT(*) OVER (PARTITION BY t.merchant) AS usage_count,

    CASE
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
        date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
        date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2))
      ELSE NULL
    END AS d
  FROM transactions t
  JOIN accounts a ON a.id = t.account_id
  WHERE (t.category IS NULL OR TRIM(t.category) = '')
    AND t.merchant IS NOT NULL
    AND TRIM(t.merchant) <> ''
    AND LOWER(TRIM(t.merchant)) <> 'unknown'
)
SELECT
  id,
  raw_date AS postedDate,
  merchant,
  amount,
  bank,
  card,
  usage_count
FROM ranked
ORDER BY usage_count DESC, d DESC, id DESC
LIMIT ?

    """, (limit,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


@app.get("/category-trend")
def category_trend(category: str, period: str = "1m"):
    conn, cur = with_db_cursor()
    cat = (category or "").strip().lower()

    if cat == "unknown merchant":
        rows = cur.execute("""
          WITH tx AS (
            SELECT
              t.amount,
              CASE
                WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
                  date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,2) || '-' ||
                             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                             substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
                WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
                  date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,4) || '-' ||
                       substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                       substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
                ELSE NULL
              END AS d
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE
              t.amount > 0
              AND LOWER(a.accountType) IN ('checking','credit')
              AND LOWER(TRIM(COALESCE(t.merchant,''))) = 'unknown'
              AND LOWER(TRIM(COALESCE(t.category,''))) NOT IN ('card payment','transfer')
          )
          SELECT d, SUM(amount) AS total
          FROM tx
          WHERE d IS NOT NULL
          GROUP BY d
          ORDER BY d ASC
        """).fetchall()
    else:
        rows = cur.execute("""
          WITH tx AS (
            SELECT
              amount,
              date(
                '20' || substr(postedDate, 7, 2) || '-' ||
                substr(postedDate, 1, 2) || '-' ||
                substr(postedDate, 4, 2)
              ) AS d
            FROM transactions
            WHERE TRIM(category) = TRIM(?)
          )
          SELECT d, SUM(amount) AS total
          FROM tx
          WHERE d IS NOT NULL
          GROUP BY d
          ORDER BY d ASC
        """, (category,)).fetchall()

    conn.close()

    daily = [
        {"date": r["d"], "amount": float(r["total"] or 0)}
        for r in rows if r["d"]
    ]

    return {"category": category, "period": period, "series": daily}

@app.get("/category-transactions")
def category_transactions(
    category: str,
    start: str,
    end: str,
    limit: int = 500
):
    sql = """
      WITH tx AS (
        SELECT
          t.id,
          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
          t.merchant,
          t.amount,
          TRIM(t.category) AS category,
          a.institution AS bank,
          a.name AS card,
          CASE
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
              date('20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
              date(substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),7,4) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),1,2) || '-' ||
                   substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')),4,2))
            ELSE NULL
          END AS d
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE TRIM(t.category) = TRIM(?)
      )
      SELECT *
      FROM tx
      WHERE d BETWEEN ? AND ?
      ORDER BY d DESC, id DESC
      LIMIT ?
    """
    return query_db(sql, (category, start, end, limit))

@app.get("/category-totals-lifetime")
def category_totals_lifetime():
    conn, cur = with_db_cursor()

    rows = cur.execute("""
      SELECT
        TRIM(category) AS category,
        SUM(amount) AS total
      FROM transactions
      WHERE category IS NOT NULL
        AND TRIM(category) <> ''
        AND amount > 0
      GROUP BY TRIM(category)
      ORDER BY total DESC
    """).fetchall()

    conn.close()

    return [
      {"category": r["category"], "total": float(r["total"] or 0)}
      for r in rows
    ]

# =============================================================================
# Account Details + Account Series
# =============================================================================

@app.get("/account/{account_id}")
def account_info(account_id: int):
    sql = """
      SELECT id, institution, name, LOWER(accountType) AS accountType
      FROM accounts
      WHERE id = ?
    """
    rows = query_db(sql, (account_id,))
    return rows[0] if rows else {"error": "Account not found"}


@app.get("/account-series")
def account_series(account_id: int, start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    # starting balance for this account
    cur.execute("""
      SELECT SUM(Start) AS s
      FROM StartingBalance
      WHERE account_id = ?
    """, (account_id,))
    bal = float(cur.fetchone()["s"] or 0.0)

    # account type
    cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # IMPORTANT: pull both postedDate and purchaseDate
    rows = cur.execute("""
      SELECT postedDate, purchaseDate, amount
      FROM transactions
      WHERE account_id = ?
    """, (account_id,)).fetchall()

    conn.close()

    tx = []
    for r in rows:
        posted = parse_posted_date(r["postedDate"])
        purchase = parse_posted_date(r["purchaseDate"])

        # RULE: if no posted date, use transaction (purchase) date
        tx_date = posted if posted is not None else purchase

        # skip broken rows (no date at all)
        if tx_date is None:
            continue

        amt_raw = r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            continue

        tx.append({
            "date": tx_date,
            "amount": amt,
        })

    tx.sort(key=lambda x: x["date"])

    i = 0

    # A) roll forward transactions BEFORE the start date
    # A) roll forward transactions BEFORE the start date
    while i < len(tx) and tx[i]["date"] < start_date:
        amt = tx[i]["amount"]
        if acc_type == "investment":
            bal += amt
        else:
            bal -= amt

        i += 1

    # B) day-by-day series
    results = []
    day = start_date
    while day <= end_date:
        while i < len(tx) and tx[i]["date"] == day:
            amt = tx[i]["amount"]
            if acc_type == "investment":
                bal += amt
            else:
                bal -= amt

            i += 1

        display_val = (-bal) if acc_type == "credit" else bal

        results.append({"date": day.isoformat(), "value": float(display_val)})

        day += timedelta(days=1)

    return results


@app.get("/account-transactions-range")
def account_transactions_range(account_id: int, start: str, end: str, limit: int = 500):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start).isoformat()
    end_date   = parse_iso(end).isoformat()

    # account type
    row = cur.execute(
        "SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # sign rule consistent with your series logic:
    # savings/investment: balance += amount
    # checking/credit/etc: balance -= amount
    sign = 1 if acc_type == "investment" else -1

    # starting balance from table
    row = cur.execute("""
        SELECT COALESCE(SUM(Start), 0) AS s
        FROM StartingBalance
        WHERE account_id = ?
    """, (account_id,)).fetchone()
    start_bal = float(row["s"] or 0.0)

    # roll forward all transactions BEFORE start_date
    row = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
          amount
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT COALESCE(SUM(amount), 0) AS s
      FROM norm
      WHERE d IS NOT NULL AND d < ?
    """, (account_id, start_date)).fetchone()

    before_sum = float(row["s"] or 0.0)
    starting_balance_at_range = start_bal + (sign * before_sum)

    # now fetch range tx and compute running balance inside range
    # inside /account-transactions-range, replace the "now fetch range tx..." query with this

    rows = cur.execute("""
      WITH base AS (
        SELECT
          id,
          merchant,
          amount,
          TRIM(category) AS category,
          COALESCE(NULLIF(status,''), 'posted') AS status,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          id,
          merchant,
          amount,
          category,
          status,
          raw_date,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      ),
      in_range AS (
        SELECT *
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN ? AND ?
        ORDER BY d ASC, id ASC
        LIMIT ?
      ),
      with_running AS (
        SELECT
          id,
          merchant,
          amount,
          category,
          status,
          raw_date AS effectiveDate,
          d AS dateISO,
          SUM(amount) OVER (ORDER BY d, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_sum
        FROM in_range
      )
      SELECT
        id,
        effectiveDate,
        dateISO,
        merchant,
        amount,
        category,
        status,
        (? + (? * running_sum)) AS balance_after
      FROM with_running
      ORDER BY dateISO DESC, id DESC
    """, (account_id, start_date, end_date, limit, starting_balance_at_range, sign)).fetchall()

    conn.close()

    tx = [dict(r) for r in rows]
    ending_balance = float(tx[0]["balance_after"]) if tx else float(starting_balance_at_range)

    # ---- DISPLAY NORMALIZATION (credit shows positive debt) ----
    if acc_type == "credit":
        starting_balance_at_range = -float(starting_balance_at_range)
        ending_balance = -float(ending_balance)
        for r in tx:
            r["balance_after"] = -float(r["balance_after"])

    return {
        "account_id": account_id,
        "start": start_date,
        "end": end_date,
        "starting_balance": float(starting_balance_at_range),
        "ending_balance": float(ending_balance),
        "transactions": tx
    }


@app.get("/transactions-all")
def transactions_all(limit: int = 10000, offset: int = 0):
    sql = """
      WITH base AS (
        SELECT
          t.*,
          a.institution AS bank,
          a.name        AS card,
          LOWER(a.accountType) AS accountType,
          COALESCE(
            NULLIF(t.postedDate,'unknown'),
            NULLIF(t.purchaseDate,'unknown')
          ) AS raw_date
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      ),
      tx AS (
        SELECT
          base.*,
          CASE
            -- MM/DD/YY
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))

            -- MM/DD/YYYY
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))

            ELSE NULL
          END AS dateISO
        FROM base
      )
      SELECT *
      FROM tx
      ORDER BY (dateISO IS NULL) ASC, dateISO DESC, id DESC
      LIMIT ? OFFSET ?
    """
    return query_db(sql, (limit, offset))

# TEST METHODS ------------------------------------------------------------------------------------------

from fastapi import Query


@app.get("/transactions-test")
def transactions_test(limit: int = Query(200, ge=1, le=10000), offset: int = Query(0, ge=0)):
    sql = f"""
      WITH tx AS (
        SELECT
          *,
          COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date
        FROM transactions_test
      )
      SELECT *
      FROM tx
      ORDER BY
        CASE
          WHEN raw_date IS NULL THEN 1
          WHEN length(raw_date) = 8 THEN
            date('20' || substr(raw_date,7,2) || '-' || substr(raw_date,1,2) || '-' || substr(raw_date,4,2))
          WHEN length(raw_date) = 10 THEN
            date(substr(raw_date,7,4) || '-' || substr(raw_date,1,2) || '-' || substr(raw_date,4,2))
          ELSE NULL
        END DESC,
        id DESC
      LIMIT ? OFFSET ?;
    """
    return query_db(sql, (limit, offset))


from fastapi.responses import FileResponse


@app.get("/transactions-test-page")
def transactions_test_page():
    return FileResponse("static/transactions_test_account.html")


@app.get("/transactions-test-account")
def transactions_test_account_page():
    return FileResponse("static/transactions_test_account.html")


@app.get("/transactions-test-range")
def transactions_test_range(account_id: int, start: str, end: str, limit: int = 500):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start).isoformat()
    end_date   = parse_iso(end).isoformat()

    # account type (same as prod)
    row = cur.execute(
        "SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # sign rule (same as prod)
    # savings/investment: balance += amount
    # checking/credit/etc: balance -= amount
    sign = 1 if acc_type == "investment" else -1


    # starting balance from table (same as prod)
    row = cur.execute("""
        SELECT COALESCE(SUM(Start), 0) AS s
        FROM StartingBalance
        WHERE account_id = ?
    """, (account_id,)).fetchone()
    start_bal = float(row["s"] or 0.0)

    # roll forward all transactions BEFORE start_date (but from transactions_test)
    row = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date,
          amount
        FROM transactions_test
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT COALESCE(SUM(amount), 0) AS s
      FROM norm
      WHERE d IS NOT NULL AND d < ?
    """, (account_id, start_date)).fetchone()

    before_sum = float(row["s"] or 0.0)
    starting_balance_at_range = start_bal + (sign * before_sum)

    # now fetch range tx and compute running balance inside range (from transactions_test)
    rows = cur.execute("""
      WITH base AS (
        SELECT
          id,
          merchant,
          amount,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date
        FROM transactions_test
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          id,
          merchant,
          amount,
          raw_date,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      ),
      in_range AS (
        SELECT *
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN ? AND ?
        ORDER BY d ASC, id ASC
        LIMIT ?
      ),
      with_running AS (
        SELECT
          id,
          merchant,
          amount,
          raw_date AS effectiveDate,
            d AS dateISO,
          SUM(amount) OVER (ORDER BY d, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_sum
        FROM in_range
      )
      SELECT
        id,
        effectiveDate,
        dateISO,
        merchant,
        amount,
        (? + (? * running_sum)) AS balance_after
      FROM with_running
      ORDER BY dateISO DESC, id DESC
    """, (account_id, start_date, end_date, limit, starting_balance_at_range, sign)).fetchall()

    conn.close()

    tx = [dict(r) for r in rows]
    ending_balance = float(tx[0]["balance_after"]) if tx else float(starting_balance_at_range)

    # ---- DISPLAY NORMALIZATION (credit shows positive debt) ----
    if acc_type == "credit":
        starting_balance_at_range = abs(float(starting_balance_at_range))
        ending_balance = abs(float(ending_balance))
        for r in tx:
            r["balance_after"] = abs(float(r["balance_after"]))

    return {
        "account_id": account_id,
        "start": start_date,
        "end": end_date,
        "starting_balance": float(starting_balance_at_range),
        "ending_balance": float(ending_balance),
        "transactions": tx
    }


@app.get("/transactions-test-series")
def transactions_test_series(account_id: int, start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    # starting balance for this account (same as /account-series)
    cur.execute("""
      SELECT SUM(Start) AS s
      FROM StartingBalance
      WHERE account_id = ?
    """, (account_id,))
    bal = float(cur.fetchone()["s"] or 0.0)

    # account type (same as /account-series)
    cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    acc_type = (row["t"] if row else "other") or "other"

    # pull both postedDate and purchaseDate (BUT from transactions_test)
    rows = cur.execute("""
      SELECT postedDate, purchaseDate, amount
      FROM transactions_test
      WHERE account_id = ?
    """, (account_id,)).fetchall()

    conn.close()

    tx = []
    for r in rows:
        posted = parse_posted_date(r["postedDate"])
        purchase = parse_posted_date(r["purchaseDate"])
        tx_date = posted if posted is not None else purchase
        if tx_date is None:
            continue
        amt_raw = r["amount"]
        try:
            amt = float(amt_raw)
        except (TypeError, ValueError):
            continue
        tx.append({"date": tx_date, "amount": amt})

    tx.sort(key=lambda x: x["date"])

    i = 0

    # A) roll forward transactions BEFORE the start date
    while i < len(tx) and tx[i]["date"] < start_date:
        amt = tx[i]["amount"]
        if acc_type == "investment":
            bal += amt
        else:
            bal -= amt

        i += 1

    # B) day-by-day series
    results = []
    day = start_date
    while day <= end_date:
        while i < len(tx) and tx[i]["date"] == day:
            amt = tx[i]["amount"]
            if acc_type == "investment":
                bal += amt
            else:
                bal -= amt

            i += 1

        display_val = abs(bal) if acc_type == "credit" else bal
        results.append({"date": day.isoformat(), "value": float(display_val)})

        day += timedelta(days=1)

    return results


@app.get("/recurring/ignore")
def get_recurring_ignores():
    conn, cur = with_db_cursor()
    merchants = [r[0] for r in cur.execute("SELECT merchant FROM recurring_ignore_merchants")]
    categories = [r[0] for r in cur.execute("SELECT category FROM recurring_ignore_categories")]
    conn.close()
    return {"merchants": merchants, "categories": categories}


@app.post("/recurring/ignore/merchant")
def ignore_merchant(name: str):
    conn, cur = with_db_cursor()
    cur.execute(
        "INSERT OR IGNORE INTO recurring_ignore_merchants (merchant) VALUES (?)",
        (name.upper(),)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/ignore/category")
def ignore_category(name: str):
    conn, cur = with_db_cursor()
    cur.execute(
        "INSERT OR IGNORE INTO recurring_ignore_categories (category) VALUES (?)",
        (name.upper(),)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/spending")
def spending(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    # Pull transactions with effective date
    rows = cur.execute("""
      SELECT
        COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
        t.amount,
        TRIM(t.category) AS category,
        LOWER(a.accountType) AS accountType
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """).fetchall()

    conn.close()

    # Build date → spending map
    daily = {}

    for r in rows:
        d = parse_posted_date(r["raw_date"])
        if not d or d < start_date or d > end_date:
            continue

        try:
            amt = float(r["amount"])
        except (TypeError, ValueError):
            continue

        category = (r["category"] or "").strip().lower()

        # 🚫 EXCLUSIONS
        if category in ("card payment", "transfer"):
            continue

        # ✅ SPENDING
        if r["accountType"] in ("checking", "credit") and amt > 0:
            daily[d] = daily.get(d, 0.0) + amt

    # Emit full day-by-day series
    results = []
    day = start_date
    while day <= end_date:
        results.append({
            "date": day.isoformat(),
            "value": float(daily.get(day, 0))
        })
        day += timedelta(days=1)

    return results

@app.get("/spending-debug")
def spending_debug(start: str, end: str):
    conn, cur = with_db_cursor()

    start_date = parse_iso(start)
    end_date = parse_iso(end)

    rows = cur.execute("""
      SELECT
        t.id,
        COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date,
        t.amount,
        t.merchant,
        TRIM(t.category) AS category,
        LOWER(a.accountType) AS accountType,
        a.institution AS bank,
        a.name AS account
      FROM transactions t
      JOIN accounts a ON a.id = t.account_id
    """).fetchall()

    conn.close()

    out = []

    for r in rows:
        d = parse_posted_date(r["raw_date"])
        if not d or d < start_date or d > end_date:
            continue

        try:
            amt = float(r["amount"])
        except (TypeError, ValueError):
            continue

        category = (r["category"] or "").strip().lower()

        # 🚫 EXCLUSIONS (same as /spending)
        if category in ("card payment", "transfer"):
            continue

        # ✅ ONLY include real spending
        if r["accountType"] in ("checking", "credit") and amt > 0:
            out.append({
                "date": d.isoformat(),
                "amount": amt,
                "merchant": r["merchant"],
                "category": r["category"],
                "bank": r["bank"],
                "account": r["account"]
            })

    return out

@app.get("/category-totals-range")
def category_totals_range(start: str, end: str):
    conn, cur = with_db_cursor()

    rows = cur.execute("""
      WITH tx AS (
        SELECT
          TRIM(t.category) AS category,
          t.amount,
          CASE
            -- MM/DD/YY
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 8 THEN
              date(
                '20' || substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                         substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2)
              )

            -- MM/DD/YYYY
            WHEN length(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown'))) = 10 THEN
              date(
                substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 7, 4) || '-' ||
                substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 1, 2) || '-' ||
                substr(COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')), 4, 2)
              )
            ELSE NULL
          END AS d
        FROM transactions t
        WHERE t.amount > 0
          AND t.category IS NOT NULL
          AND TRIM(t.category) <> ''
          AND LOWER(TRIM(t.category)) NOT IN ('card payment', 'transfer')

      )
      SELECT category, SUM(amount) AS total
      FROM tx
      WHERE d BETWEEN ? AND ?
      GROUP BY category
      ORDER BY total DESC
    """, (start, end)).fetchall()

    conn.close()

    return [
        {"category": r["category"], "total": float(r["total"] or 0)}
        for r in rows
    ]

from recurring import _norm_merchant, _amount_bucket  # matches your recurring.py helpers

@app.post("/recurring/ignore/pattern")
def ignore_pattern(merchant: str, amount: float, account_id: int = -1):
    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    conn, cur = with_db_cursor()
    cur.execute("""
      INSERT OR IGNORE INTO recurring_ignore_patterns
        (merchant_norm, amount_bucket, sign, account_id)
      VALUES (?, ?, ?, ?)
    """, (m_norm, bucket, sign, int(account_id)))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/recurring/override-cadence")
def override_cadence(merchant: str, amount: float, cadence: str, account_id: int = -1):
    cadence = (cadence or "").strip().lower()
    allowed = {"weekly","biweekly","monthly","quarterly","yearly","irregular"}
    if cadence not in allowed:
        return {"ok": False, "error": f"cadence must be one of {sorted(allowed)}"}

    m_norm = _norm_merchant(merchant).upper()
    amt = float(amount)
    bucket = float(_amount_bucket(amt))
    sign = 1 if amt >= 0 else -1

    conn, cur = with_db_cursor()
    cur.execute("""
      INSERT INTO recurring_cadence_overrides
        (merchant_norm, amount_bucket, sign, account_id, cadence)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(merchant_norm, amount_bucket, sign, account_id)
      DO UPDATE SET cadence = excluded.cadence
    """, (m_norm, bucket, sign, int(account_id), cadence))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/recurring/merchant-alias")
def set_merchant_alias(alias: str, canonical: str):
    a = _norm_merchant(alias).upper()
    c = _norm_merchant(canonical).upper()
    if not a or not c:
        return {"ok": False, "error": "alias and canonical required"}

    conn, cur = with_db_cursor()
    cur.execute("""
      INSERT INTO merchant_aliases (alias, canonical)
      VALUES (?, ?)
      ON CONFLICT(alias) DO UPDATE SET canonical = excluded.canonical
    """, (a, c))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/recurring/merchant-alias/delete")
def delete_merchant_alias(alias: str):
    a = _norm_merchant(alias).upper()
    conn, cur = with_db_cursor()
    cur.execute("DELETE FROM merchant_aliases WHERE alias = ?", (a,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/recurring/unignore/merchant")
def unignore_merchant(name: str):
    conn, cur = with_db_cursor()
    cur.execute("DELETE FROM recurring_ignore_merchants WHERE merchant = ?", (name.upper(),))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/recurring/ignored-preview")
def recurring_ignored_preview(min_occ: int = 3, include_stale: bool = False):
    return get_ignored_merchants_preview(min_occ=min_occ, include_stale=include_stale)

# =========================
# Recurring Calendar
# =========================

def _interest_cycle_window(year: int, month: int, post_day: int | None):
    """
    Returns (start_date, end_date_exclusive) for the interest accrual period
    that pays on post_day in (year, month).

    Example: post_day=18 in Jan => cycle is Dec 19 .. Jan 18 (inclusive)
    """
    post_date = _interest_post_date(year, month, post_day)

    # previous month's posting date
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1

    prev_post = _interest_post_date(py, pm, post_day)

    start = prev_post + timedelta(days=1)
    end_excl = post_date + timedelta(days=1)
    return start, end_excl, post_date

def _interest_post_date(year: int, month: int, post_day: int | None) -> date:
    last_day = calendar.monthrange(year, month)[1]

    if post_day is None:
        return date(year, month, last_day)

    # clamp (e.g. 31 → Feb 28)
    day = min(int(post_day), last_day)
    return date(year, month, day)

def _add_months(d: date, months: int) -> date:
    # month-safe add: keeps "day of month" as close as possible
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _last_day_of_month(y, m))
    return date(y, m, day)

def _project_occurrences_for_month(last_seen: date, cadence: str, anchor_day: int, month_start: date, month_end: date):
    """
    Returns list[date] of projected occurrences within [month_start, month_end]
    using cadence + anchor_day (day-of-month from last_seen for month-based cadences).
    """
    out = []

    cadence = (cadence or "").lower().strip()
    if cadence in ("weekly", "biweekly"):
        step = 7 if cadence == "weekly" else 14

        # find first date >= month_start by stepping forward from last_seen
        d = last_seen
        # push to at least next cycle (don’t re-include last_seen itself)
        d = d + timedelta(days=step)

        # fast forward until we reach this month
        while d < month_start:
            d = d + timedelta(days=step)

        while d <= month_end:
            out.append(d)
            d = d + timedelta(days=step)

        return out

    if cadence in ("monthly", "quarterly", "yearly"):
        step_months = {"monthly": 1, "quarterly": 3, "yearly": 12}[cadence]

        # start from the NEXT cadence “slot” after last_seen
        base = last_seen
        cursor = _add_months(base.replace(day=min(anchor_day, _last_day_of_month(base.year, base.month))), step_months)

        # move forward until we’re in/after month_start
        while cursor < month_start:
            cursor = _add_months(cursor, step_months)

        # now add any occurrences inside the requested month
        while cursor <= month_end:
            out.append(cursor)
            cursor = _add_months(cursor, step_months)

        return out

    # irregular/unknown => no projections
    return out

PAYCHECK_MERCHANT = "SALARY REGULAR INCOME FROM DFAS"

def _find_paycheck_amount(groups) -> float:
    """
    Pull the real paycheck amount from recurring detection.
    Uses median to avoid outliers.
    """
    amounts = []

    for g in (groups or []):
        m = (g.get("merchant") or "").upper().strip()
        if m != PAYCHECK_MERCHANT:
            continue

        for p in (g.get("patterns") or []):
            try:
                amounts.append(abs(float(p.get("amount") or 0)))
            except Exception:
                pass

    if not amounts:
        return 0.0

    amounts.sort()
    return amounts[len(amounts) // 2]


@app.get("/recurring/calendar")
def recurring_calendar(year: int, month: int, min_occ: int = 3, include_stale: bool = False):
    """
    Returns projected recurring WITHDRAWALS for a given month.
    - uses get_recurring() output
    - excludes kind == "paycheck"
    """
    # clamp month
    if month < 1 or month > 12:
        return {"ok": False, "error": "month must be 1..12"}

    month_start = date(year, month, 1)
    month_end = date(year, month, _last_day_of_month(year, month))

    groups = get_recurring(min_occ=min_occ, include_stale=include_stale)

    events = []
    for g in (groups or []):
        merchant = g.get("merchant") or ""
        if merchant.upper().strip() == PAYCHECK_MERCHANT:
            continue
        for p in (g.get("patterns") or []):
            # only “recurring” (withdrawals), not paychecks
            if (p.get("kind") or "").lower() == "paycheck":
                continue

            cadence = (p.get("cadence") or "").lower().strip()
            if cadence in ("unknown", "irregular", ""):
                continue

            # Use last_seen anchor day (day-of-month) for month-based cadences
            last_seen_iso = p.get("last_seen")
            if not last_seen_iso:
                continue

            try:
                last_seen_d = datetime.strptime(last_seen_iso, "%Y-%m-%d").date()
            except Exception:
                continue

            anchor_day = last_seen_d.day

            occs = _project_occurrences_for_month(
                last_seen=last_seen_d,
                cadence=cadence,
                anchor_day=anchor_day,
                month_start=month_start,
                month_end=month_end,
            )

            # amount is already signed in recurring.py output (withdrawals are usually +)
            amt = float(p.get("amount") or 0.0)
            aid = int(p.get("account_id") or -1)
            for d in occs:
                events.append({
                    "date": d.isoformat(),
                    "merchant": merchant,
                    "amount": amt,
                    "cadence": cadence,
                    "account_id": aid,  # ✅ NEW
                })

    # ---- PAYCHECK EVENTS (derived from recurring data) ----
    pay_amt = _find_paycheck_amount(groups)

    # targets: 1st + 15th of this month, plus 1st of next month (if deposit lands in this month)
    targets = [date(year, month, 1), date(year, month, 15)]
    if month == 12:
        targets.append(date(year + 1, 1, 1))
    else:
        targets.append(date(year, month + 1, 1))

    hol_this = _us_federal_holidays_observed(year)

    def deposit_for_target(target: date) -> date:
        hol = hol_this if target.year == year else _us_federal_holidays_observed(target.year)
        d = target - timedelta(days=1)
        return _previous_workday(d, hol)

    for target in targets:
        dep = deposit_for_target(target)

        # Include if:
        # 1) this paycheck's TARGET payday is in the requested month (Jan 1/15),
        #    even if the deposit date is in the previous month (Dec 31)
        # OR
        # 2) the deposit date lands in the requested month (the "early deposit" for next month's 1st)
        include = (
                (target.year == year and target.month == month) or
                (dep.year == year and dep.month == month)
        )
        if not include:
            continue

        events.append({
            "date": dep.isoformat(),  # deposit day shown on calendar grid
            "merchant": PAYCHECK_MERCHANT,
            "amount": pay_amt,
            "cadence": "paycheck",
            "type": "income",
            "account_id": 3,
            "pay_target": target.isoformat(),  # used for totals
            "spillover": not (dep.year == year and dep.month == month),  # optional flag
        })

    # ---- INTEREST EVENTS (estimated) ----
    # Put a single "Estimated Interest" income chip on the LAST day of the month
    conn, cur = with_db_cursor()

    acct_rows = cur.execute("""
      SELECT
        id,
        institution,
        name,
        LOWER(accountType) AS accountType,
        interest_post_day
      FROM accounts
      WHERE LOWER(accountType) IN ('checking', 'savings')
    """).fetchall()

    for a in acct_rows:
        aid = int(a["id"])
        est = _estimate_interest_for_account_month(cur, aid, year, month)

        # optional: ignore tiny pennies so calendar doesn't get noisy
        if abs(est) < 0.01:
            continue

        # show as income (positive number)
        post_date = _interest_post_date(
            year,
            month,
            a["interest_post_day"]
        )

        events.append({
            "date": post_date.isoformat(),
            "merchant": f'INTEREST — {a["institution"]} {a["name"]}',
            "amount": round(est, 2),
            "cadence": "interest",
            "type": "income",
            "account_id": aid,  # ✅ NEW
        })

    conn.close()


    events.sort(key=lambda e: (e["date"], e["merchant"], abs(e["amount"])))
    return {
        "ok": True,
        "year": year,
        "month": month,
        "start": month_start.isoformat(),
        "end": month_end.isoformat(),
        "events": events,
    }

def _month_range(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end  # [start, end)

def _get_rate_rows(cur, account_id: int):
    # return sorted effective-dated APRs
    rows = cur.execute("""
      SELECT effective_date, apr
      FROM interest_rates
      WHERE account_id = ?
      ORDER BY effective_date ASC
    """, (account_id,)).fetchall()
    out = []
    for r in rows:
        try:
            out.append((datetime.strptime(r["effective_date"], "%Y-%m-%d").date(), float(r["apr"])))
        except Exception:
            pass
    return out

def _apr_for_day(rate_rows, d: date) -> float:
    # rate_rows sorted asc by effective_date
    apr = 0.0
    for eff, r in rate_rows:
        if eff <= d:
            apr = r
        else:
            break
    return apr

def _estimate_interest_for_account_month(cur, account_id: int, year: int, month: int) -> float:
    """
    End-of-day balance convention:
      - apply that day's transactions to balance
      - then accrue interest for that day on resulting balance
    """
    row = cur.execute("SELECT interest_post_day FROM accounts WHERE id = ?", (account_id,)).fetchone()
    post_day = row["interest_post_day"] if row else None

    month_start, month_end, _post_date = _interest_cycle_window(year, month, post_day)

    # only do accounts that *should* earn deposit interest
    row = cur.execute("SELECT LOWER(accountType) AS t FROM accounts WHERE id = ?", (account_id,)).fetchone()
    acc_type = (row["t"] if row else "other") or "other"
    if acc_type not in ("checking", "savings"):
        return 0.0

    # must have at least one rate row
    rate_rows = _get_rate_rows(cur, account_id)
    if not rate_rows:
        return 0.0

    # starting balance (sum of StartingBalance)
    row = cur.execute("""
      SELECT COALESCE(SUM(Start), 0) AS s
      FROM StartingBalance
      WHERE account_id = ?
    """, (account_id,)).fetchone()
    start_bal = float(row["s"] or 0.0)

    # sum of amounts BEFORE month_start using your “effective date” logic (posted else purchase)
    # and the same date normalization pattern you use elsewhere.
    row = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
          amount
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT COALESCE(SUM(amount), 0) AS s
      FROM norm
      WHERE d IS NOT NULL AND d < date(?)
    """, (account_id, month_start.isoformat())).fetchone()

    before_sum = float(row["s"] or 0.0)

    # Your balance convention for checking/savings in series:
    #   bal -= amount  (amount positive reduces balance)
    bal = start_bal - before_sum

    # daily net transactions within month grouped by dateISO
    rows = cur.execute("""
      WITH base AS (
        SELECT
          COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) AS raw_date,
          amount
        FROM transactions
        WHERE account_id = ?
      ),
      norm AS (
        SELECT
          amount,
          CASE
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9]' THEN
              date('20' || substr(raw_date, 7, 2) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            WHEN raw_date GLOB '[0-1][0-9]/[0-3][0-9]/[0-9][0-9][0-9][0-9]' THEN
              date(substr(raw_date, 7, 4) || '-' || substr(raw_date, 1, 2) || '-' || substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT d, COALESCE(SUM(amount), 0) AS net
      FROM norm
      WHERE d IS NOT NULL
        AND d >= date(?)
        AND d < date(?)
      GROUP BY d
      ORDER BY d ASC
    """, (account_id, month_start.isoformat(), month_end.isoformat())).fetchall()

    net_by_day = {r["d"]: float(r["net"] or 0.0) for r in rows}

    total_interest = 0.0
    d = month_start
    while d < month_end:
        # apply transactions for the day (end-of-day balance)
        net = net_by_day.get(d.isoformat(), 0.0)
        bal = bal - net

        apr = _apr_for_day(rate_rows, d)
        daily_rate = apr / 365.0
        total_interest += (bal * daily_rate)

        d += timedelta(days=1)

    return float(total_interest)

# =============================================================================
# Unknown merchant (for reconciliation cards)
# =============================================================================

@app.get("/unknown-merchant-total-month")
def unknown_merchant_total_month():
    conn, cur = with_db_cursor()

    today = datetime.today().date()
    first = today.replace(day=1)

    if first.month == 12:
        next_month = datetime(first.year + 1, 1, 1).date()
    else:
        next_month = datetime(first.year, first.month + 1, 1).date()

    row = cur.execute("""
      WITH base AS (
        SELECT
          t.amount,
          t.merchant,
          TRIM(t.category) AS category,
          LOWER(a.accountType) AS accountType,
          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      ),
      norm AS (
        SELECT
          amount,
          merchant,
          category,
          accountType,
          CASE
            WHEN length(raw_date) = 8 THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN length(raw_date) = 10 THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT
        COALESCE(SUM(amount), 0) AS total,
        COALESCE(COUNT(*), 0)    AS tx_count
      FROM norm
      WHERE d IS NOT NULL
        AND d >= ? AND d < ?
        AND amount > 0
        AND accountType IN ('checking','credit')
        AND LOWER(TRIM(COALESCE(merchant,''))) = 'unknown'
        AND LOWER(TRIM(COALESCE(category,''))) NOT IN ('card payment','transfer')
    """, (first.isoformat(), next_month.isoformat())).fetchone()

    conn.close()
    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}


@app.get("/unknown-merchant-total-range")
def unknown_merchant_total_range(start: str, end: str):
    conn, cur = with_db_cursor()

    row = cur.execute("""
      WITH base AS (
        SELECT
          t.amount,
          t.merchant,
          TRIM(t.category) AS category,
          LOWER(a.accountType) AS accountType,
          COALESCE(NULLIF(t.postedDate,'unknown'), NULLIF(t.purchaseDate,'unknown')) AS raw_date
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
      ),
      norm AS (
        SELECT
          amount,
          merchant,
          category,
          accountType,
          CASE
            WHEN length(raw_date) = 8 THEN
              date('20' || substr(raw_date, 7, 2) || '-' ||
                         substr(raw_date, 1, 2) || '-' ||
                         substr(raw_date, 4, 2))
            WHEN length(raw_date) = 10 THEN
              date(substr(raw_date, 7, 4) || '-' ||
                   substr(raw_date, 1, 2) || '-' ||
                   substr(raw_date, 4, 2))
            ELSE NULL
          END AS d
        FROM base
      )
      SELECT
        COALESCE(SUM(amount), 0) AS total,
        COALESCE(COUNT(*), 0)    AS tx_count
      FROM norm
      WHERE d IS NOT NULL
        AND d BETWEEN ? AND ?
        AND amount > 0
        AND accountType IN ('checking','credit')
        AND LOWER(TRIM(COALESCE(merchant,''))) = 'unknown'
        AND LOWER(TRIM(COALESCE(category,''))) NOT IN ('card payment','transfer')
    """, (start, end)).fetchone()

    conn.close()
    return {"total": float(row["total"] or 0), "tx_count": int(row["tx_count"] or 0)}

