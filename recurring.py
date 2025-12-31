# recurring.py
import re
import sqlite3
from collections import defaultdict, Counter
from datetime import datetime

from transactionHandler import DB_PATH


def _cadence_days(cadence: str):
    return {
        "weekly": 7,
        "biweekly": 14,
        "monthly": 30,
        "quarterly": 90,
    }.get(cadence)


def _max_date_in_db(cur):
    # Uses the same date field you use for recurring detection
    r = cur.execute("""
      SELECT MAX(
        CASE
          WHEN COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown')) IS NULL THEN NULL
          ELSE COALESCE(NULLIF(TRIM(postedDate),'unknown'), NULLIF(TRIM(purchaseDate),'unknown'))
        END
      ) AS max_d
      FROM transactions
    """).fetchone()

    max_d = (r[0] if r else None)
    if not max_d or max_d == "unknown":
        return None
    try:
        return _parse_mmddyy(max_d)
    except Exception:
        return None


def _norm_merchant(s: str) -> str:
    s = (s or "").upper().strip()

    # Common leading noise/prefixes from banks
    s = re.sub(r"^(DEBIT\s+DC\s+)", "", s)
    s = re.sub(r"^(DEBIT\s+)", "", s)
    s = re.sub(r"^(ACH\s+(ORIG\s+)?(DEBIT|CREDIT)\s+)", "", s)
    s = re.sub(r"^(PAYMENT\s+TO\s+)", "", s)
    s = re.sub(r"^(TRANSFER\s+TO\s+)", "", s)
    s = re.sub(r"^(DEPOSIT\s+FROM\s+)", "", s)

    # Remove obvious self-identifiers (your name appears in a bunch)
    s = re.sub(r"\bJARED\b|\bTREVINO\b|\bJARED\s+C\b", "", s)

    # Remove digits and separators
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"[\*\-_/]", " ", s)

    # Remove trailing state/city tokens (best-effort)
    # examples: "SEATTLE WA", "XX PA", "TROY MI"
    s = re.sub(r"\b[A-Z]{2}\s+[A-Z]{2}\b$", "", s)  # "SEATTLE WA"
    s = re.sub(r"\bXX\s+[A-Z]{2}\b$", "", s)        # "XX PA"
    s = re.sub(r"\b[A-Z]{2}\b$", "", s)             # trailing "WA"

    # Remove trailing website-ish tokens
    s = re.sub(r"\s+(COM|WWW|ONLINE)$", "", s)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_mmddyy(s: str):
    # your DB commonly stores mm/dd/yy
    return datetime.strptime(s, "%m/%d/%y").date()


def _cadence_label(deltas):
    if not deltas:
        return "unknown"
    avg = sum(deltas) / len(deltas)
    if 6 <= avg <= 8:
        return "weekly"
    if 13 <= avg <= 16:
        return "biweekly"
    if 27 <= avg <= 33:
        return "monthly"
    if 85 <= avg <= 95:
        return "quarterly"
    return "irregular"


def _to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().lower()
    if not s or s == "unknown":
        return None
    # allow "$1,234.56"
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except:
        return None


def _amount_bucket(a: float) -> float:
    a = abs(a)
    if a < 5:
        return round(a, 2)       # tiny stuff keep exact
    if a < 50:
        return round(a / 1.0)    # $1 buckets
    if a < 500:
        return round(a / 5.0) * 5  # $5 buckets
    return round(a / 25.0) * 25    # big payments: $25 buckets


def get_recurring(min_occ: int = 3):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    ignored_merchants = {
        r[0].upper()
        for r in cur.execute("SELECT merchant FROM recurring_ignore_merchants")
    }

    ignored_categories = {
        r[0].upper()
        for r in cur.execute("SELECT category FROM recurring_ignore_categories")
    }

    # Use postedDate, fallback purchaseDate
    rows = cur.execute("""
      SELECT
        id,
        account_id,
        merchant,
        amount,
        category,
        COALESCE(NULLIF(TRIM(postedDate),'unknown'),
                 NULLIF(TRIM(purchaseDate),'unknown')) AS d
      FROM transactions
      WHERE d IS NOT NULL
        AND d != 'unknown'
        AND merchant IS NOT NULL
        AND TRIM(merchant) != ''
        AND amount IS NOT NULL
        AND TRIM(amount) != ''
        AND TRIM(amount) != 'unknown'
    """).fetchall()

    as_of = _max_date_in_db(cur)
    conn.close()

    groups = defaultdict(list)

    for r in rows:
        merchant = r["merchant"]
        amt = _to_float(r["amount"])
        if amt is None:
            continue

        d = r["d"]
        # only handle mm/dd/yy here for now
        try:
            dt = _parse_mmddyy(d)
        except Exception:
            continue

        merchant_raw = r["merchant"]
        merchant_norm = _norm_merchant(merchant_raw)
        category = (r["category"] or "").upper().strip()

        if merchant_norm in ignored_merchants:
            continue

        if category and category in ignored_categories:
            continue

        key = (merchant_norm, _amount_bucket(amt), 1 if amt >= 0 else -1)
        groups[key].append({
            "id": r["id"],
            "date": dt,  # python date
            "amount": float(amt),
            "merchant": merchant_raw,
            "account_id": r["account_id"],
            "category": r["category"] or "",
        })

    out = []
    for (m_norm, amt_bucket, sign), items in groups.items():
        if len(items) < min_occ:
            continue

        items.sort(key=lambda x: x["date"])
        dates = [x["date"] for x in items]

        deltas = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
        cadence = _cadence_label(deltas)

        # choose cadence length from observed gaps when possible
        avg_gap = int(round(sum(deltas) / len(deltas))) if deltas else None

        # default cycle days
        cycle_days = avg_gap or {
            "weekly": 7,
            "biweekly": 14,
            "monthly": 31,  # better than 30
            "quarterly": 92,  # better than 90
        }.get(cadence)

        ref = as_of or dates[-1]
        days_since = (ref - dates[-1]).days

        # looseness knobs
        cycles_allowed = 3  # <-- was 2
        grace_days = 14  # <-- extra slack

        active = True
        if cadence in ("unknown", "irregular") or cycle_days is None:
            # don't drop it; just mark inactive by default unless it has many occurrences
            active = (len(items) >= 6)  # optional heuristic
        else:
            if days_since > (cycles_allowed * cycle_days + grace_days):
                active = False

        # dominant gap (mode-ish)
        if deltas:
            common_gap = Counter(deltas).most_common(1)[0][0]
        else:
            common_gap = None

        kind = "paycheck" if sign > 0 and cadence in ("weekly", "biweekly") else "recurring"

        tx_list = [{
            "id": it.get("id"),
            "date": it["date"].isoformat() if it.get("date") else None,
            "amount": float(it.get("amount") or 0.0),
            "merchant": it.get("merchant") or "",
            "account_id": it.get("account_id"),
            "category": it.get("category") or "",
        } for it in items]

        out.append({
            "merchant": m_norm,
            "merchant_norm": m_norm,
            "amount": float(amt_bucket) * (1 if sign > 0 else -1),
            "cadence": cadence,
            "occurrences": len(items),
            "first_seen": dates[0].isoformat(),
            "last_seen": dates[-1].isoformat(),
            "common_gap_days": common_gap,
            "kind": kind,
            "active": active,
            "days_since_last": int(days_since),
            "cycle_days": int(cycle_days) if cycle_days else None,
            "tx": tx_list,
        })

    # show strongest signals first
    out.sort(key=lambda x: (
        not x.get("active", True),  # active first
        x["cadence"] not in ("monthly", "biweekly", "weekly", "quarterly"),
        -x["occurrences"],
        abs(x["amount"])
    ))

    # Group patterns by merchant
    # Group patterns by merchant
    by_merchant = defaultdict(list)
    for p in out:
        by_merchant[p["merchant_norm"]].append(p)

    grouped = []
    for m, patterns in by_merchant.items():
        last_seen = max(p["last_seen"] for p in patterns)
        active_any = any(p.get("active", True) for p in patterns)

        patterns.sort(key=lambda x: (
            not x.get("active", True),
            x["cadence"] not in ("monthly", "biweekly", "weekly", "quarterly"),
            -x["occurrences"],
            abs(x["amount"])
        ))

        grouped.append({
            "merchant": m,
            "last_seen": last_seen,
            "active": active_any,
            "patterns": patterns,
        })

    grouped.sort(key=lambda g: (
        not g.get("active", True),
        g["merchant"],
    ))

    return grouped

