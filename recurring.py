# recurring.py
import re
import sqlite3
from collections import defaultdict, Counter
from datetime import datetime

from emails.transactionHandler import DB_PATH


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
            WHEN COALESCE(NULLIF(TRIM(purchaseDate),'unknown'),
                          NULLIF(TRIM(postedDate),'unknown')) IS NULL THEN NULL
            ELSE COALESCE(NULLIF(TRIM(purchaseDate),'unknown'),
                          NULLIF(TRIM(postedDate),'unknown'))
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


def _cadence_label_robust(deltas):
    """
    Robust cadence detection:
    - Use median (not mean) so one missed month doesn't break classification
    - Allow "missed cycles": e.g., a 60–66 day gap still counts as monthly-ish
    """
    if not deltas:
        return "unknown"

    ds = sorted(int(x) for x in deltas if x is not None)
    if not ds:
        return "unknown"

    med = ds[len(ds)//2]

    def within(x, lo, hi):
        return lo <= x <= hi

    # Count how many deltas match each cadence window
    weekly = sum(1 for d in ds if within(d, 6, 8))
    biweekly = sum(1 for d in ds if within(d, 13, 16))
    monthly = sum(1 for d in ds if within(d, 27, 35))  # widen a bit
    quarterly = sum(1 for d in ds if within(d, 85, 95))

    n = len(ds)

    # Also count "missed one cycle" gaps (about 2x)
    monthly_missed = sum(1 for d in ds if within(d, 54, 70))      # ~2 months
    biweekly_missed = sum(1 for d in ds if within(d, 26, 33))     # ~4 weeks

    # Majority vote with missed-cycle support
    if weekly >= max(2, n // 2 + 1):
        return "weekly"
    if biweekly + biweekly_missed >= max(2, n // 2 + 1) and (biweekly >= 1):
        return "biweekly"
    if monthly + monthly_missed >= max(2, n // 2 + 1) and (monthly >= 1):
        return "monthly"
    if quarterly >= max(2, n // 2 + 1):
        return "quarterly"

    # Fallback: median-based
    if within(med, 6, 8): return "weekly"
    if within(med, 13, 16): return "biweekly"
    if within(med, 27, 35): return "monthly"
    if within(med, 85, 95): return "quarterly"
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


def get_recurring(min_occ: int = 3, include_stale: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    ignored_merchants = {
        r[0].upper()
        for r in cur.execute("SELECT merchant FROM recurring_ignore_merchants")
    }

    # Merchant alias map (merge merchants)
    alias_map = {}
    for r in cur.execute("SELECT alias, canonical FROM merchant_aliases").fetchall():
        a = (r[0] or "").upper().strip()
        c = (r[1] or "").upper().strip()
        if a and c:
            alias_map[a] = c


    ignored_categories = {
        r[0].upper()
        for r in cur.execute("SELECT category FROM recurring_ignore_categories")
    }

    ignored_patterns = set()
    for r in cur.execute("""
        SELECT merchant_norm, amount_bucket, sign, account_id
        FROM recurring_ignore_patterns
    """).fetchall():
        ignored_patterns.add((
            (r[0] or "").upper(),
            float(r[1]),
            int(r[2]),
            int(r[3]),
        ))

    cadence_overrides = {}
    for r in cur.execute("""
        SELECT merchant_norm, amount_bucket, sign, account_id, cadence
        FROM recurring_cadence_overrides
    """).fetchall():
        cadence_overrides[(
            (r[0] or "").upper(),
            float(r[1]),
            int(r[2]),
            int(r[3]),
        )] = (r[4] or "").lower().strip()

    # Use postedDate, fallback purchaseDate
    rows = cur.execute("""
      SELECT
        id,
        account_id,
        merchant,
        amount,
        category,
COALESCE(NULLIF(TRIM(purchaseDate),'unknown'),
         NULLIF(TRIM(postedDate),'unknown')) AS d
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

        # Apply merchant alias (merge)
        merchant_norm = alias_map.get(merchant_norm, merchant_norm)

        category = (r["category"] or "").upper().strip()

        if merchant_norm in ignored_merchants:
            continue

        if category and category in ignored_categories:
            continue

        bucket = _amount_bucket(amt)
        sign = 1 if amt >= 0 else -1
        key = (merchant_norm, bucket, sign)

        # pattern-level ignore (account-specific or global)
        aid = int(r["account_id"] or -1)
        k_exact = (merchant_norm.upper(), float(bucket), int(sign), aid)
        k_all = (merchant_norm.upper(), float(bucket), int(sign), -1)

        if k_exact in ignored_patterns or k_all in ignored_patterns:
            continue

        groups[key].append({
            "id": r["id"],
            "date": dt,
            "amount": float(amt),
            "merchant": merchant_raw,
            "account_id": int(aid),
            "category": r["category"] or "",
        })

    out = []
    for (m_norm, amt_bucket, sign), items in groups.items():
        if len(items) < min_occ:
            continue

        items.sort(key=lambda x: x["date"])
        dates = [x["date"] for x in items]

        deltas = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
        cadence = _cadence_label_robust(deltas)

        # cadence override (account-specific or global)
        # pick a representative account_id for override matching:
        # - if all tx are same account_id, use it; otherwise use -1
        acct_ids = {int(it.get("account_id") or -1) for it in items}
        override_aid = acct_ids.pop() if len(acct_ids) == 1 else -1

        ok_exact = (m_norm.upper(), float(amt_bucket), int(sign), override_aid)
        ok_all = (m_norm.upper(), float(amt_bucket), int(sign), -1)

        if ok_exact in cadence_overrides:
            cadence = cadence_overrides[ok_exact]
        elif ok_all in cadence_overrides:
            cadence = cadence_overrides[ok_all]

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
            "account_id": int(override_aid),
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

    # If not including stale, hide inactive patterns and groups
    if not include_stale:
        filtered = []
        for g in grouped:
            pats = [p for p in (g.get("patterns") or []) if p.get("active", True)]
            if not pats:
                continue
            g2 = dict(g)
            g2["patterns"] = pats
            g2["active"] = True
            filtered.append(g2)
        grouped = filtered

    return grouped

def get_ignored_merchants_preview(min_occ: int = 3, include_stale: bool = False):
    """
    Returns recurring groups ONLY for merchants currently ignored.
    These are the items you would have seen if you weren't ignoring the merchant.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    ignored_merchants = {
        (r[0] or "").upper().strip()
        for r in cur.execute("SELECT merchant FROM recurring_ignore_merchants").fetchall()
    }

    ignored_categories = {
        (r[0] or "").upper().strip()
        for r in cur.execute("SELECT category FROM recurring_ignore_categories").fetchall()
    }

    # Load pattern ignores + cadence overrides (keep them respected)
    ignored_patterns = set()
    for r in cur.execute("""
        SELECT merchant_norm, amount_bucket, sign, account_id
        FROM recurring_ignore_patterns
    """).fetchall():
        ignored_patterns.add((
            (r[0] or "").upper(),
            float(r[1]),
            int(r[2]),
            int(r[3]),
        ))

    cadence_overrides = {}
    for r in cur.execute("""
        SELECT merchant_norm, amount_bucket, sign, account_id, cadence
        FROM recurring_cadence_overrides
    """).fetchall():
        cadence_overrides[(
            (r[0] or "").upper(),
            float(r[1]),
            int(r[2]),
            int(r[3]),
        )] = (r[4] or "").lower().strip()

    # Pull tx rows (same as get_recurring)
    rows = cur.execute("""
      SELECT
        id,
        account_id,
        merchant,
        amount,
        category,
        COALESCE(NULLIF(TRIM(purchaseDate),'unknown'),
                 NULLIF(TRIM(postedDate),'unknown')) AS d

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

    # Build groups ONLY for merchants that are ignored
    groups = defaultdict(list)

    for r in rows:
        amt = _to_float(r["amount"])
        if amt is None:
            continue

        try:
            dt = _parse_mmddyy(r["d"])
        except Exception:
            continue

        merchant_raw = r["merchant"]
        merchant_norm = _norm_merchant(merchant_raw)
        category = (r["category"] or "").upper().strip()

        # ✅ Only show merchants currently ignored
        if merchant_norm not in ignored_merchants:
            continue

        # still respect category ignores
        if category and category in ignored_categories:
            continue

        bucket = _amount_bucket(amt)
        sign = 1 if amt >= 0 else -1
        key = (merchant_norm, bucket, sign)

        # still respect pattern-level ignore
        aid = int(r["account_id"] or -1)
        k_exact = (merchant_norm.upper(), float(bucket), int(sign), aid)
        k_all = (merchant_norm.upper(), float(bucket), int(sign), -1)
        if k_exact in ignored_patterns or k_all in ignored_patterns:
            continue

        groups[key].append({
            "id": r["id"],
            "date": dt,
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
        cadence = _cadence_label_robust(deltas)

        acct_ids = {int(it.get("account_id") or -1) for it in items}
        override_aid = acct_ids.pop() if len(acct_ids) == 1 else -1

        ok_exact = (m_norm.upper(), float(amt_bucket), int(sign), override_aid)
        ok_all   = (m_norm.upper(), float(amt_bucket), int(sign), -1)
        if ok_exact in cadence_overrides:
            cadence = cadence_overrides[ok_exact]
        elif ok_all in cadence_overrides:
            cadence = cadence_overrides[ok_all]

        avg_gap = int(round(sum(deltas) / len(deltas))) if deltas else None
        cycle_days = avg_gap or {
            "weekly": 7, "biweekly": 14, "monthly": 31, "quarterly": 92,
        }.get(cadence)

        ref = as_of or dates[-1]
        days_since = (ref - dates[-1]).days

        cycles_allowed = 3
        grace_days = 14

        active = True
        if cadence in ("unknown", "irregular") or cycle_days is None:
            active = (len(items) >= 6)
        else:
            if days_since > (cycles_allowed * cycle_days + grace_days):
                active = False

        tx_list = [{
            "id": it.get("id"),
            "date": it["date"].isoformat(),
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
            "kind": "paycheck" if sign > 0 and cadence in ("weekly", "biweekly") else "recurring",
            "active": active,
            "days_since_last": int(days_since),
            "cycle_days": int(cycle_days) if cycle_days else None,
            "tx": tx_list,
            "account_id": int(override_aid),
        })

    by_merchant = defaultdict(list)
    for p in out:
        by_merchant[p["merchant_norm"]].append(p)

    grouped = []
    for m, patterns in by_merchant.items():
        last_seen = max(p["last_seen"] for p in patterns)
        active_any = any(p.get("active", True) for p in patterns)
        grouped.append({
            "merchant": m,
            "last_seen": last_seen,
            "active": active_any,
            "patterns": patterns,
        })

    grouped.sort(key=lambda g: (not g.get("active", True), g["merchant"]))

    if not include_stale:
        grouped = [
            {**g, "patterns": [p for p in g["patterns"] if p.get("active", True)], "active": True}
            for g in grouped
            if any(p.get("active", True) for p in g["patterns"])
        ]

    return grouped
