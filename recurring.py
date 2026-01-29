# recurring_pg.py
import re
from collections import defaultdict, Counter
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple

from db import query_db  # your Postgres helper

# -----------------------------
# Helpers (same behavior as sqlite version)
# -----------------------------

def _cadence_days(cadence: str):
    return {
        "weekly": 7,
        "biweekly": 14,
        "monthly": 30,
        "quarterly": 90,
    }.get(cadence)


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
    s = re.sub(r"\b[A-Z]{2}\s+[A-Z]{2}\b$", "", s)  # "SEATTLE WA"
    s = re.sub(r"\bXX\s+[A-Z]{2}\b$", "", s)        # "XX PA"
    s = re.sub(r"\b[A-Z]{2}\b$", "", s)             # trailing "WA"

    # Remove trailing website-ish tokens
    s = re.sub(r"\s+(COM|WWW|ONLINE)$", "", s)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_date_raw(x: Optional[str]) -> Optional[date]:
    """
    Robust parse:
      - MM/DD/YY
      - MM/DD/YYYY
      - YYYY-MM-DD
    Returns date or None.
    """
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() == "unknown":
        return None

    try:
        if len(s) == 8:   # MM/DD/YY
            return datetime.strptime(s, "%m/%d/%y").date()
        if len(s) == 10 and "/" in s:  # MM/DD/YYYY
            return datetime.strptime(s, "%m/%d/%Y").date()
        if len(s) == 10 and "-" in s:  # YYYY-MM-DD
            return datetime.fromisoformat(s).date()
    except Exception:
        return None

    return None


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

    med = ds[len(ds) // 2]

    def within(v, lo, hi):
        return lo <= v <= hi

    weekly = sum(1 for d in ds if within(d, 6, 8))
    biweekly = sum(1 for d in ds if within(d, 13, 16))
    monthly = sum(1 for d in ds if within(d, 27, 35))
    quarterly = sum(1 for d in ds if within(d, 85, 95))

    n = len(ds)

    monthly_missed = sum(1 for d in ds if within(d, 54, 70))   # ~2 months
    biweekly_missed = sum(1 for d in ds if within(d, 26, 33))  # ~4 weeks

    if weekly >= max(2, n // 2 + 1):
        return "weekly"
    if biweekly + biweekly_missed >= max(2, n // 2 + 1) and (biweekly >= 1):
        return "biweekly"
    if monthly + monthly_missed >= max(2, n // 2 + 1) and (monthly >= 1):
        return "monthly"
    if quarterly >= max(2, n // 2 + 1):
        return "quarterly"

    if within(med, 6, 8):
        return "weekly"
    if within(med, 13, 16):
        return "biweekly"
    if within(med, 27, 35):
        return "monthly"
    if within(med, 85, 95):
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
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _amount_bucket(a: float) -> float:
    a = abs(a)
    if a < 5:
        return round(a, 2)
    if a < 50:
        return round(a / 1.0)
    if a < 500:
        return round(a / 5.0) * 5
    return round(a / 25.0) * 25


def _max_date_in_db() -> Optional[date]:
    """
    Postgres version of _max_date_in_db:
    Uses the same date field used for recurring detection:
      COALESCE(purchaseDate, postedDate) (after trimming/unknown handling)

    We normalize via SQL (to_date) then MAX().
    """
    rows = query_db(
        """
        WITH base AS (
          SELECT
            COALESCE(
              NULLIF(TRIM(purchaseDate),'unknown'),
              NULLIF(TRIM(postedDate),'unknown')
            ) AS raw_date
          FROM transactions
        ),
        norm AS (
          SELECT
            CASE
              WHEN raw_date IS NULL THEN NULL
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 AND position('/' in raw_date)>0 THEN to_date(raw_date, 'MM/DD/YYYY')
              WHEN length(raw_date)=10 AND position('-' in raw_date)>0 THEN raw_date::date
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT MAX(d) AS max_d
        FROM norm
        """
    )
    if not rows:
        return None
    md = rows[0].get("max_d")
    if md is None:
        return None
    return md if isinstance(md, date) else _parse_date_raw(str(md))


# =============================================================================
# Main API (Postgres)
# =============================================================================

def get_recurring(min_occ: int = 3, include_stale: bool = False):
    # 1) Load ignore lists + aliases + overrides (all Postgres)
    ignored_merchants = {
        (r["merchant"] or "").upper().strip()
        for r in query_db("SELECT merchant FROM recurring_ignore_merchants")
    }

    alias_map: Dict[str, str] = {}
    for r in query_db("SELECT alias, canonical FROM merchant_aliases"):
        a = (r.get("alias") or "").upper().strip()
        c = (r.get("canonical") or "").upper().strip()
        if a and c:
            alias_map[a] = c

    ignored_categories = {
        (r["category"] or "").upper().strip()
        for r in query_db("SELECT category FROM recurring_ignore_categories")
    }

    ignored_patterns = set()
    for r in query_db(
        """
        SELECT merchant_norm, amount_bucket, sign, account_id
        FROM recurring_ignore_patterns
        """
    ):
        ignored_patterns.add((
            (r.get("merchant_norm") or "").upper(),
            float(r.get("amount_bucket") or 0.0),
            int(r.get("sign") or 0),
            int(r.get("account_id") or -1),
        ))

    cadence_overrides: Dict[Tuple[str, float, int, int], str] = {}
    for r in query_db(
        """
        SELECT merchant_norm, amount_bucket, sign, account_id, cadence
        FROM recurring_cadence_overrides
        """
    ):
        cadence_overrides[(
            (r.get("merchant_norm") or "").upper(),
            float(r.get("amount_bucket") or 0.0),
            int(r.get("sign") or 0),
            int(r.get("account_id") or -1),
        )] = (r.get("cadence") or "").lower().strip()

    # 2) Pull transactions (same filter semantics as sqlite version)
    tx_rows = query_db(
        """
        SELECT
          id,
          account_id,
          merchant,
          amount,
          category,
          COALESCE(
            NULLIF(TRIM(purchaseDate),'unknown'),
            NULLIF(TRIM(postedDate),'unknown')
          ) AS d
        FROM transactions
        WHERE COALESCE(
            NULLIF(TRIM(purchaseDate),'unknown'),
            NULLIF(TRIM(postedDate),'unknown')
          ) IS NOT NULL
          AND merchant IS NOT NULL
          AND TRIM(merchant) <> ''
          AND amount IS NOT NULL
        """
    )

    as_of = _max_date_in_db()

    groups = defaultdict(list)

    for r in tx_rows:
        merchant_raw = r.get("merchant") or ""
        amt = _to_float(r.get("amount"))
        if amt is None:
            continue

        dt = _parse_date_raw(r.get("d"))
        if dt is None:
            continue

        merchant_norm = _norm_merchant(merchant_raw)
        merchant_norm = alias_map.get(merchant_norm, merchant_norm)

        category = (r.get("category") or "").upper().strip()

        if merchant_norm in ignored_merchants:
            continue
        if category and category in ignored_categories:
            continue

        bucket = _amount_bucket(float(amt))
        sign = 1 if float(amt) >= 0 else -1
        key = (merchant_norm, bucket, sign)

        aid = int(r.get("account_id") or -1)
        k_exact = (merchant_norm.upper(), float(bucket), int(sign), aid)
        k_all = (merchant_norm.upper(), float(bucket), int(sign), -1)
        if k_exact in ignored_patterns or k_all in ignored_patterns:
            continue

        groups[key].append({
            "id": r.get("id"),
            "date": dt,
            "amount": float(amt),
            "merchant": merchant_raw,
            "account_id": aid,
            "category": r.get("category") or "",
        })

    # 3) Build patterns
    out = []
    for (m_norm, amt_bucket, sign), items in groups.items():
        if len(items) < int(min_occ):
            continue

        items.sort(key=lambda x: x["date"])
        dates = [x["date"] for x in items]
        deltas = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        cadence = _cadence_label_robust(deltas)

        acct_ids = {int(it.get("account_id") or -1) for it in items}
        override_aid = next(iter(acct_ids)) if len(acct_ids) == 1 else -1

        ok_exact = (m_norm.upper(), float(amt_bucket), int(sign), int(override_aid))
        ok_all = (m_norm.upper(), float(amt_bucket), int(sign), -1)
        if ok_exact in cadence_overrides:
            cadence = cadence_overrides[ok_exact]
        elif ok_all in cadence_overrides:
            cadence = cadence_overrides[ok_all]

        avg_gap = int(round(sum(deltas) / len(deltas))) if deltas else None
        cycle_days = avg_gap or {
            "weekly": 7,
            "biweekly": 14,
            "monthly": 31,
            "quarterly": 92,
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

        common_gap = Counter(deltas).most_common(1)[0][0] if deltas else None
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

    out.sort(key=lambda x: (
        not x.get("active", True),
        x["cadence"] not in ("monthly", "biweekly", "weekly", "quarterly"),
        -x["occurrences"],
        abs(x["amount"]),
    ))

    # 4) Group patterns by merchant (same as sqlite)
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
            abs(x["amount"]),
        ))

        grouped.append({
            "merchant": m,
            "last_seen": last_seen,
            "active": active_any,
            "patterns": patterns,
        })

    grouped.sort(key=lambda g: (not g.get("active", True), g["merchant"]))

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
    (Same as sqlite behavior.)
    """
    ignored_merchants = {
        (r["merchant"] or "").upper().strip()
        for r in query_db("SELECT merchant FROM recurring_ignore_merchants")
    }

    ignored_categories = {
        (r["category"] or "").upper().strip()
        for r in query_db("SELECT category FROM recurring_ignore_categories")
    }

    ignored_patterns = set()
    for r in query_db(
        """
        SELECT merchant_norm, amount_bucket, sign, account_id
        FROM recurring_ignore_patterns
        """
    ):
        ignored_patterns.add((
            (r.get("merchant_norm") or "").upper(),
            float(r.get("amount_bucket") or 0.0),
            int(r.get("sign") or 0),
            int(r.get("account_id") or -1),
        ))

    cadence_overrides: Dict[Tuple[str, float, int, int], str] = {}
    for r in query_db(
        """
        SELECT merchant_norm, amount_bucket, sign, account_id, cadence
        FROM recurring_cadence_overrides
        """
    ):
        cadence_overrides[(
            (r.get("merchant_norm") or "").upper(),
            float(r.get("amount_bucket") or 0.0),
            int(r.get("sign") or 0),
            int(r.get("account_id") or -1),
        )] = (r.get("cadence") or "").lower().strip()

    tx_rows = query_db(
        """
        SELECT
          id,
          account_id,
          merchant,
          amount,
          category,
          COALESCE(
            NULLIF(TRIM(purchaseDate),'unknown'),
            NULLIF(TRIM(postedDate),'unknown')
          ) AS d
        FROM transactions
        WHERE COALESCE(
            NULLIF(TRIM(purchaseDate),'unknown'),
            NULLIF(TRIM(postedDate),'unknown')
          ) IS NOT NULL
          AND merchant IS NOT NULL
          AND TRIM(merchant) <> ''
          AND amount IS NOT NULL
        """
    )

    as_of = _max_date_in_db()
    groups = defaultdict(list)

    for r in tx_rows:
        amt = _to_float(r.get("amount"))
        if amt is None:
            continue

        dt = _parse_date_raw(r.get("d"))
        if dt is None:
            continue

        merchant_raw = r.get("merchant") or ""
        merchant_norm = _norm_merchant(merchant_raw)
        category = (r.get("category") or "").upper().strip()

        # Only show merchants currently ignored
        if merchant_norm not in ignored_merchants:
            continue

        if category and category in ignored_categories:
            continue

        bucket = _amount_bucket(float(amt))
        sign = 1 if float(amt) >= 0 else -1
        key = (merchant_norm, bucket, sign)

        aid = int(r.get("account_id") or -1)
        k_exact = (merchant_norm.upper(), float(bucket), int(sign), aid)
        k_all = (merchant_norm.upper(), float(bucket), int(sign), -1)
        if k_exact in ignored_patterns or k_all in ignored_patterns:
            continue

        groups[key].append({
            "id": r.get("id"),
            "date": dt,
            "amount": float(amt),
            "merchant": merchant_raw,
            "account_id": aid,
            "category": r.get("category") or "",
        })

    out = []
    for (m_norm, amt_bucket, sign), items in groups.items():
        if len(items) < int(min_occ):
            continue

        items.sort(key=lambda x: x["date"])
        dates = [x["date"] for x in items]
        deltas = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        cadence = _cadence_label_robust(deltas)

        acct_ids = {int(it.get("account_id") or -1) for it in items}
        override_aid = next(iter(acct_ids)) if len(acct_ids) == 1 else -1

        ok_exact = (m_norm.upper(), float(amt_bucket), int(sign), int(override_aid))
        ok_all = (m_norm.upper(), float(amt_bucket), int(sign), -1)
        if ok_exact in cadence_overrides:
            cadence = cadence_overrides[ok_exact]
        elif ok_all in cadence_overrides:
            cadence = cadence_overrides[ok_all]

        avg_gap = int(round(sum(deltas) / len(deltas))) if deltas else None
        cycle_days = avg_gap or {"weekly": 7, "biweekly": 14, "monthly": 31, "quarterly": 92}.get(cadence)

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
