from typing import List, Dict, Any, Optional, Callable
from datetime import date as _date, timedelta as _timedelta
from db import query_db


def load_starting_balances_pg() -> Dict[int, float]:
    """
    StartingBalance table -> {account_id: sum(start)}.
    Matches sqlite logic. :contentReference[oaicite:1]{index=1}
    """
    rows = query_db(
        """
        SELECT account_id::int AS account_id, COALESCE(SUM(start), 0)::double precision AS total_start
        FROM startingbalance
        GROUP BY account_id
        """
    )
    return {int(r["account_id"]): float(r["total_start"] or 0.0) for r in rows}

def load_transactions_pg() -> List[Dict[str, Any]]:
    """
    Loads normalized transactions as:
      [{"date": date, "account_id": int, "amount": float, "accountType": str}, ...]
    Rule preserved: use postedDate if present else purchaseDate; skip unknown/broken.
    :contentReference[oaicite:3]{index=3}
    """
    rows = query_db(
        """
        WITH base AS (
          SELECT
            t.account_id::int AS account_id,
            t.amount::double precision AS amount,
            LOWER(a.accountType) AS accountType,
            COALESCE(
              NULLIF(TRIM(t.postedDate), 'unknown'),
              NULLIF(TRIM(t.purchaseDate), 'unknown')
            ) AS raw_date
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
        ),
        norm AS (
          SELECT
            account_id,
            amount,
            accountType,
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date) = 8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date) = 10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT account_id, amount, accountType, d
        FROM norm
        WHERE d IS NOT NULL
        ORDER BY d ASC, account_id ASC
        """
    )

    tx: List[Dict[str, Any]] = []
    for r in rows:
        # Safety: amount can be NULL or non-numeric if data is messy
        try:
            amt = float(r["amount"])
        except Exception:
            continue

        d = r["d"]
        if not d:
            continue

        tx.append({
            "date": d,
            "account_id": int(r["account_id"]),
            "amount": amt,
            "accountType": (r.get("account_type") or "other"),
        })

    # already ordered by SQL, but keep stable:
    tx.sort(key=lambda t: t["date"])
    return tx

def load_account_type_map_pg() -> Dict[int, str]:
    """
    accounts -> {id: lower(accountType)}.
    Matches sqlite logic. :contentReference[oaicite:2]{index=2}
    """
    rows = query_db("SELECT id::int AS id, LOWER(accounttype) AS t FROM accounts")
    return {int(r["id"]): (r["t"] or "other") for r in rows}

def apply_transaction(current_totals: Dict[int, float], account_id: int, amount: float, account_type: Optional[str]) -> None:
    """
    Same rule as sqlite version:
      - investment: contributions increase net worth (delta = +amount)
      - everything else: spending reduces net worth (delta = -amount)
    """
    t = (account_type or "other").lower()
    amt = float(amount or 0.0)

    if t in ("investment",):
        delta = amt
    else:
        delta = -amt

    current_totals[int(account_id)] = float(current_totals.get(int(account_id), 0.0)) + float(delta)

def build_series(
    start_date: _date,
    end_date: _date,
    starting: Dict[int, float],
    transactions: List[Dict[str, Any]],
    value_fn: Callable[[Dict[int, float]], float],
) -> List[Dict[str, Any]]:
    """
    Same behavior as sqlite build_series: roll forward, then emit daily values.
    :contentReference[oaicite:4]{index=4}
    """
    current_totals = dict(starting)
    results: List[Dict[str, Any]] = []
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
        day += _timedelta(days=1)

    return results
