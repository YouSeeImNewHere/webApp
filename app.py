from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sqlite3
from datetime import datetime, timedelta
import re
from pydantic import BaseModel
from typing import List, Optional

from transactionHandler import DB_PATH

app = FastAPI()


# =============================================================================
# App + Static Frontend
# =============================================================================

@app.get("/__ping")
def ping():
    return {"ok": True, "file": __file__}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return FileResponse("static/index.html")


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
def recurring(min_occ: int = 3):
    return get_recurring(min_occ=min_occ)



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
        cards_abs = 0.0

        for aid, bal in current_totals.items():
            t = (acct_types.get(aid) or "other").lower()
            if t == "savings":
                savings += bal
            elif t == "credit":
                # balances are negative for debt, but we want a positive card-balance number here
                cards_abs += abs(bal)
            else:
                # checking + investment + other => "banks"
                banks += bal

        net = banks + savings - cards_abs

        results.append({
            "date": day.isoformat(),
            "value": float(net),
            "banks": float(banks),
            "savings": float(savings),
            "cards": float(cards_abs),
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
      SELECT id, raw_date AS postedDate, merchant, amount, bank, card, accountType
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

    # Fetch all tx for category with a real date column (d)
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

    # Convert to python dates
    daily = []
    for r in rows:
        if not r["d"]:
            continue
        daily.append({
            "date": r["d"],                 # already YYYY-MM-DD from sqlite date()
            "amount": float(r["total"] or 0)
        })

    if not daily:
        return {"category": category, "period": period, "series": []}

    # Period filtering (done in python)
    end = datetime.today().date()

    def months_ago(months: int):
        y, m = end.year, end.month - months
        while m <= 0:
            m += 12
            y -= 1
        # clamp day so dates always valid
        d = min(end.day, 28)
        return datetime(y, m, d).date()

    if period == "all":
        start = datetime.strptime(daily[0]["date"], "%Y-%m-%d").date()
    elif period == "1y":
        start = months_ago(12)
    elif period == "6m":
        start = months_ago(6)
    elif period == "3m":
        start = months_ago(3)
    else:  # default 1m
        start = months_ago(1)

    filtered = [
        p for p in daily
        if datetime.strptime(p["date"], "%Y-%m-%d").date() >= start
    ]

    return {"category": category, "period": period, "series": filtered}


@app.get("/category-transactions")
def category_transactions(category: str, limit: int = 500):
    sql = """
      WITH tx AS (
        SELECT
          t.id,
          t.postedDate,
          t.merchant,
          t.amount,
          TRIM(t.category) AS category,

          a.institution AS bank,
          a.name        AS card,
          LOWER(a.accountType) AS accountType,

          date(
            '20' || substr(t.postedDate, 7, 2) || '-' ||
            substr(t.postedDate, 1, 2) || '-' ||
            substr(t.postedDate, 4, 2)
          ) AS d
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE TRIM(t.category) = TRIM(?)
      )
      SELECT id, postedDate, merchant, amount, category, bank, card, accountType
      FROM tx
      ORDER BY d DESC, id DESC
      LIMIT ?
    """
    return query_db(sql, (category, limit))


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

        display_val = abs(bal) if acc_type == "credit" else bal
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
    rows = cur.execute("""
      WITH base AS (
        SELECT
          id,
          merchant,
          amount,
          COALESCE(NULLIF(postedDate,'unknown'), NULLIF(purchaseDate,'unknown')) AS raw_date
        FROM transactions
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
        raw_date AS effectiveDate,   -- posted if known else purchase
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
