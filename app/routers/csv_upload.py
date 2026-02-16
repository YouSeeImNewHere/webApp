from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from db import with_db_cursor

router = APIRouter()

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
PHONE_RX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
STOP_TOKENS = {
    "debit", "dc", "credit", "pos", "purchase", "card", "visa", "mastercard",
    "auth", "pending", "ach", "transaction",
}
PAYMENT_GENERIC_TOKENS = {
    "payment", "pay", "thank", "thanks", "thankyou", "you",
    "mobile", "autopay", "online", "electronic", "transfer",
}
TIP_MAX_ABS = 50.0
TIP_PCT_SMALL = 0.75
TIP_PCT_MED = 0.50
TIP_PCT_LARGE = 0.35


def _safe_target_filename(name: str) -> str:
    """
    Enforce a simple safe filename rule; also force .csv extension.
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing target name")
    if not SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid target name: {name}")
    if not name.lower().endswith(".csv"):
        name = f"{name}.csv"
    return name


def _read_upload_text(uf: UploadFile) -> str:
    raw = uf.file.read()
    if not raw:
        return ""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _detect_delimiter(text: str, preferred: str = "auto") -> str:
    if preferred and preferred != "auto":
        return preferred
    sample = "\n".join(text.splitlines()[:20]) or text[:2000]
    if not sample.strip():
        return ","
    try:
        sniff = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return sniff.delimiter or ","
    except Exception:
        pass
    candidates = [",", ";", "\t", "|"]
    counts = {d: sample.count(d) for d in candidates}
    return max(counts, key=counts.get) if counts else ","


def _parse_csv_rows(text: str, delimiter: str) -> list[list[str]]:
    f = io.StringIO(text)
    reader = csv.reader(f, delimiter=delimiter)
    out: list[list[str]] = []
    for row in reader:
        out.append([(c or "").strip() for c in row])
    return out


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if not s:
        return default
    return s in {"1", "true", "yes", "on"}


def _col_value(row: list[str], idx: int | None) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _parse_date(v: str) -> datetime.date | None:
    s = (v or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def _parse_amount(v: str) -> float | None:
    s = (v or "").strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").strip()
    if s.endswith("-"):
        neg = True
        s = s[:-1].strip()
    try:
        val = float(s)
    except Exception:
        return None
    return -val if neg else val


def _clean_spaces(s: str) -> str:
    s = (s or "").strip()
    s = PHONE_RX.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" -")


def _merchant_tokens(s: str) -> list[str]:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    toks: list[str] = []
    for t in s.split():
        if t in STOP_TOKENS:
            continue
        if len(t) < 2:
            continue
        if t.isdigit():
            continue
        toks.append(t)
    return toks


def _merchants_similar(a: str, b: str, min_overlap: float = 0.6) -> bool:
    A = set(_merchant_tokens(a))
    B = set(_merchant_tokens(b))
    if not A or not B:
        return False
    shared = len(A & B)
    if shared < 2:
        if shared == 1 and (len(A) <= 2 or len(B) <= 2) and (len(A) <= 6 and len(B) <= 6):
            return True
        return False
    overlap = shared / min(len(A), len(B))
    return overlap >= min_overlap


def _is_generic_payment_merchant(s: str) -> bool:
    s = _clean_spaces(s).lower()
    if not s or s == "unknown":
        return True
    s = s.replace("thank you", "thankyou").replace("thanks", "thank")
    toks = set(_merchant_tokens(s))
    return bool(toks) and (toks <= PAYMENT_GENERIC_TOKENS)


def _date_from_text_expr(colname: str) -> str:
    c = f"NULLIF(TRIM(COALESCE({colname}, '')), '')"
    return f"""
    CASE
      WHEN {c} IS NULL THEN NULL
      WHEN LOWER({c}) = 'unknown' THEN NULL
      WHEN length({c}) = 8  THEN to_date({c}, 'MM/DD/YY')
      WHEN length({c}) = 10 THEN to_date({c}, 'MM/DD/YYYY')
      ELSE NULL
    END
    """.strip()


def _latest_posted_cutoff_for_account(
    cur,
    *,
    account_id: int,
    tenant_id: int | None,
    posted_col: str | None,
    purchase_col: str | None,
    status_col: str | None,
    account_col: str | None,
    tenant_col: str | None,
):
    if not account_col or not purchase_col:
        return None
    posted_expr = _date_from_text_expr(posted_col) if posted_col else "NULL"
    purchase_expr = _date_from_text_expr(purchase_col)
    status_pred = f"AND LOWER(TRIM(COALESCE({status_col}, ''))) = 'posted'" if status_col else ""
    tenant_pred = f"AND {tenant_col} = %s" if (tenant_id and tenant_col) else ""
    params: list[Any] = [int(account_id)]
    if tenant_pred:
        params.append(int(tenant_id))
    cur.execute(
        f"""
        SELECT MAX(COALESCE({posted_expr}, {purchase_expr}))::date AS max_d
        FROM transactions
        WHERE {account_col} = %s
          {status_pred}
          {tenant_pred}
          AND COALESCE({posted_expr}, {purchase_expr}) IS NOT NULL
        """,
        tuple(params),
    )
    row = cur.fetchone() or {}
    return row.get("max_d")


def _find_pending_email_match_by_amount_date(
    cur,
    *,
    account_id: int,
    amount: float,
    purchase_date,
    merchant: str,
    tenant_id: int | None,
    id_col: str | None,
    account_col: str | None,
    amount_col: str | None,
    purchase_col: str | None,
    merchant_col: str | None,
    status_col: str | None,
    source_col: str | None,
    tenant_col: str | None,
    window_days: int = 4,
) -> str | None:
    if not (id_col and account_col and amount_col and purchase_col and merchant_col and status_col and source_col and purchase_date):
        return None
    purchase_expr = _date_from_text_expr(purchase_col)
    start_d = purchase_date - timedelta(days=int(window_days))
    end_d = purchase_date + timedelta(days=int(window_days))
    tenant_pred = f"AND {tenant_col} = %s" if (tenant_id and tenant_col) else ""
    params: list[Any] = [int(account_id), float(amount), start_d, end_d]
    if tenant_pred:
        params.append(int(tenant_id))
    cur.execute(
        f"""
        SELECT
          {id_col} AS id,
          {merchant_col} AS merchant,
          {purchase_col} AS purchase_raw,
          {purchase_expr} AS purchase_d
        FROM transactions
        WHERE {account_col} = %s
          AND {amount_col} = %s
          AND COALESCE({status_col}, '') = 'Pending'
          AND COALESCE({source_col}, '') = 'email'
          AND {purchase_expr} BETWEEN %s::date AND %s::date
          {tenant_pred}
        ORDER BY {purchase_expr} DESC NULLS LAST, {id_col} DESC
        """,
        tuple(params),
    )
    candidates = [dict(r) for r in (cur.fetchall() or [])]
    if len(candidates) == 1:
        return str(candidates[0].get("id") or "")
    if not candidates:
        return None

    csv_clean = _clean_spaces(merchant or "").lower()
    csv_toks = _merchant_tokens(csv_clean)
    csv_is_unknown = csv_clean in ("", "unknown")
    csv_is_weak = len(csv_toks) < 2

    for c in candidates:
        db_clean = _clean_spaces(str(c.get("merchant") or "")).lower()
        db_is_unknown = db_clean in ("", "unknown")
        if (db_is_unknown or _is_generic_payment_merchant(db_clean)) and not csv_is_unknown:
            return str(c.get("id") or "")

        db_toks = _merchant_tokens(db_clean)
        db_is_weak = len(db_toks) < 2
        if db_is_weak and not csv_is_weak:
            return str(c.get("id") or "")

        if _merchants_similar(db_clean, csv_clean):
            return str(c.get("id") or "")

    return None


def _find_pending_email_candidates_by_date(
    cur,
    *,
    account_id: int,
    purchase_date,
    tenant_id: int | None,
    id_col: str | None,
    account_col: str | None,
    amount_col: str | None,
    purchase_col: str | None,
    merchant_col: str | None,
    status_col: str | None,
    source_col: str | None,
    tenant_col: str | None,
    window_days: int = 4,
) -> list[dict[str, Any]]:
    if not (id_col and account_col and amount_col and purchase_col and merchant_col and status_col and source_col and purchase_date):
        return []
    purchase_expr = _date_from_text_expr(purchase_col)
    start_d = purchase_date - timedelta(days=int(window_days))
    end_d = purchase_date + timedelta(days=int(window_days))
    tenant_pred = f"AND {tenant_col} = %s" if (tenant_id and tenant_col) else ""
    params: list[Any] = [int(account_id), start_d, end_d]
    if tenant_pred:
        params.append(int(tenant_id))
    cur.execute(
        f"""
        SELECT
          {id_col} AS id,
          {amount_col}::double precision AS amount,
          {merchant_col} AS merchant,
          {purchase_col} AS purchase_raw,
          {purchase_expr} AS purchase_d
        FROM transactions
        WHERE {account_col} = %s
          AND COALESCE({status_col}, '') = 'Pending'
          AND COALESCE({source_col}, '') = 'email'
          AND {purchase_expr} BETWEEN %s::date AND %s::date
          {tenant_pred}
        ORDER BY {purchase_expr} DESC NULLS LAST, {id_col} DESC
        """,
        tuple(params),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def _find_tip_adjust_pending_email_match(
    candidates: list[dict[str, Any]],
    *,
    csv_amount: float,
    csv_merchant: str,
) -> str | None:
    try:
        csv_amt_f = float(csv_amount)
    except Exception:
        return None
    best_id = None
    best_diff = None
    csv_clean = _clean_spaces(csv_merchant or "")
    for c in candidates:
        try:
            db_amt_f = float(c.get("amount") or 0.0)
        except Exception:
            continue
        if (db_amt_f >= 0) != (csv_amt_f >= 0):
            continue
        if csv_amt_f < db_amt_f:
            continue
        diff = csv_amt_f - db_amt_f
        if diff <= 0:
            continue
        if diff > TIP_MAX_ABS:
            continue
        base = abs(db_amt_f)
        if base < 20:
            pct_cap = TIP_PCT_SMALL
        elif base < 60:
            pct_cap = TIP_PCT_MED
        else:
            pct_cap = TIP_PCT_LARGE
        if base > 0 and diff > base * pct_cap:
            continue

        db_merch = _clean_spaces(str(c.get("merchant") or ""))
        db_is_unknown = db_merch.lower() in ("", "unknown")
        csv_is_unknown = csv_clean.lower() in ("", "unknown")
        if (db_is_unknown or _is_generic_payment_merchant(db_merch)) and not csv_is_unknown:
            pass
        elif not _merchants_similar(db_merch, csv_clean):
            continue

        if best_id is None or diff < float(best_diff):
            best_id = str(c.get("id") or "")
            best_diff = diff
    return best_id or None


def _pick_pending_update_target(
    cur,
    *,
    account_id: int,
    amount: float,
    purchase_date,
    merchant: str,
    tenant_id: int | None,
    id_col: str | None,
    account_col: str | None,
    amount_col: str | None,
    purchase_col: str | None,
    merchant_col: str | None,
    status_col: str | None,
    source_col: str | None,
    tenant_col: str | None,
    window_days: int = 4,
    exclude_ids: set[str] | None = None,
) -> tuple[str | None, str | None]:
    exact_id = _find_pending_email_match_by_amount_date(
        cur,
        account_id=account_id,
        amount=amount,
        purchase_date=purchase_date,
        merchant=merchant,
        tenant_id=tenant_id,
        id_col=id_col,
        account_col=account_col,
        amount_col=amount_col,
        purchase_col=purchase_col,
        merchant_col=merchant_col,
        status_col=status_col,
        source_col=source_col,
        tenant_col=tenant_col,
        window_days=window_days,
    )
    if exact_id and (not exclude_ids or exact_id not in exclude_ids):
        return exact_id, "exact"

    candidates = _find_pending_email_candidates_by_date(
        cur,
        account_id=account_id,
        purchase_date=purchase_date,
        tenant_id=tenant_id,
        id_col=id_col,
        account_col=account_col,
        amount_col=amount_col,
        purchase_col=purchase_col,
        merchant_col=merchant_col,
        status_col=status_col,
        source_col=source_col,
        tenant_col=tenant_col,
        window_days=window_days,
    )
    if exclude_ids:
        candidates = [c for c in candidates if str(c.get("id") or "") not in exclude_ids]
    tip_id = _find_tip_adjust_pending_email_match(
        candidates,
        csv_amount=amount,
        csv_merchant=merchant,
    )
    if tip_id:
        return tip_id, "tip_adjust"
    return None, None


def _list_pending_email_rows(
    cur,
    *,
    account_id: int,
    tenant_id: int | None,
    id_col: str | None,
    account_col: str | None,
    amount_col: str | None,
    purchase_col: str | None,
    merchant_col: str | None,
    status_col: str | None,
    source_col: str | None,
    tenant_col: str | None,
    limit: int = 400,
) -> list[dict[str, Any]]:
    if not (id_col and account_col and amount_col and purchase_col and merchant_col and status_col and source_col):
        return []
    tenant_pred = f"AND {tenant_col} = %s" if (tenant_id and tenant_col) else ""
    purchase_expr = _date_from_text_expr(purchase_col)
    params: list[Any] = [int(account_id)]
    if tenant_pred:
        params.append(int(tenant_id))
    params.append(int(limit))
    cur.execute(
        f"""
        SELECT
          {id_col} AS id,
          {purchase_col} AS purchaseDate,
          {amount_col}::double precision AS amount,
          {merchant_col} AS merchant
        FROM transactions
        WHERE {account_col} = %s
          AND COALESCE({status_col}, '') = 'Pending'
          AND COALESCE({source_col}, '') = 'email'
          {tenant_pred}
        ORDER BY {purchase_expr} DESC NULLS LAST, {id_col} DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def _require_tenant_id_or_none() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


def _account_exists_for_scope(cur, account_id: int, tenant_id: int | None) -> bool:
    if tenant_id:
        cur.execute("SELECT 1 FROM accounts WHERE id = %s AND tenant_id = %s LIMIT 1", (int(account_id), int(tenant_id)))
    else:
        cur.execute("SELECT 1 FROM accounts WHERE id = %s LIMIT 1", (int(account_id),))
    return cur.fetchone() is not None


def _transactions_column_lookup(cur) -> dict[str, str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'transactions'
        """
    )
    cols = [str(r.get("column_name") or "") for r in (cur.fetchall() or [])]
    return {c.lower(): c for c in cols if c}


def _pick_col(colmap: dict[str, str], *names: str) -> str | None:
    for n in names:
        out = colmap.get(n.lower())
        if out:
            return out
    return None


def _make_base_id(account_id: int, purchase_mmddyy: str, amount: float) -> str:
    d = purchase_mmddyy.replace("/", "")
    return f"{int(account_id)}_{d}_{float(amount):.2f}"


def _next_tx_id(cur, base: str) -> str:
    cur.execute("SELECT 1 FROM transactions WHERE id = %s LIMIT 1", (base,))
    if cur.fetchone() is None:
        return base
    cur.execute("SELECT id FROM transactions WHERE id LIKE %s", (base + "_%",))
    rows = cur.fetchall() or []
    max_n = 0
    for r in rows:
        tx_id = str(r.get("id") or "")
        try:
            n = int(tx_id.rsplit("_", 1)[-1])
            max_n = max(max_n, n)
        except Exception:
            continue
    return f"{base}_{max_n + 1}"


def _ensure_csv_presets_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS csv_mapping_presets (
          id BIGSERIAL PRIMARY KEY,
          tenant_id BIGINT,
          account_id BIGINT NOT NULL,
          institution_key TEXT NOT NULL,
          preset_json TEXT NOT NULL DEFAULT '{}',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_csv_mapping_presets_scope
        ON csv_mapping_presets (
          COALESCE(tenant_id, 0),
          account_id,
          lower(institution_key)
        )
        """
    )


def _parse_col_opt(v: str | None) -> int | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    n = int(s)
    return n if n >= 0 else None


def _mapped_row_preview(row: list[str], max_len: int = 180) -> str:
    out = " | ".join((c or "").strip() for c in row[:8])
    if len(out) > max_len:
        return out[: max_len - 1] + "…"
    return out


def _analyze_mapped_rows(
    rows: list[list[str]],
    *,
    start_idx: int,
    purchase_col: int,
    amount_col: int,
    merchant_col: int,
    posted_col: int | None,
    category_col: int | None,
    indicator_col: int | None,
    credit_indicator_value: str,
    invert_amount: bool,
):
    valid_rows: list[dict[str, Any]] = []
    sample_errors: list[dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0

    for row_no, row in enumerate(rows[start_idx:], start=start_idx + 1):
        p_raw = _col_value(row, purchase_col)
        m_raw = _col_value(row, merchant_col)
        a_raw = _col_value(row, amount_col)

        p_date = _parse_date(p_raw)
        if not p_date:
            invalid_count += 1
            if len(sample_errors) < 25:
                sample_errors.append({"row_number": row_no, "error": "invalid_transaction_date", "raw": _mapped_row_preview(row)})
            continue

        posted_raw = _col_value(row, posted_col) if posted_col is not None else ""
        posted_date = _parse_date(posted_raw) or p_date

        amount = _parse_amount(a_raw)
        if amount is None:
            invalid_count += 1
            if len(sample_errors) < 25:
                sample_errors.append({"row_number": row_no, "error": "invalid_amount", "raw": _mapped_row_preview(row)})
            continue

        if indicator_col is not None:
            ind = _col_value(row, indicator_col).lower()
            if ind and ind == (credit_indicator_value or "").strip().lower():
                amount = -amount
        if invert_amount:
            amount = -amount

        merchant = m_raw.strip()
        if not merchant:
            invalid_count += 1
            if len(sample_errors) < 25:
                sample_errors.append({"row_number": row_no, "error": "missing_merchant", "raw": _mapped_row_preview(row)})
            continue

        valid_count += 1
        category = _col_value(row, category_col) if category_col is not None else ""
        valid_rows.append(
            {
                "row_number": row_no,
                "purchase_date": p_date,
                "posted_date": posted_date,
                "amount": float(amount),
                "merchant": merchant,
                "category": category,
            }
        )

    return {
        "valid_rows": valid_rows,
        "summary": {
            "total_rows": max(0, len(rows) - start_idx),
            "valid_rows": valid_count,
            "invalid_rows": invalid_count,
            "sample_errors": sample_errors,
        },
    }


class CsvPresetBody(BaseModel):
    account_id: int
    institution_key: str
    preset: dict[str, Any]


@router.get("/csv/mapping-presets")
def get_csv_mapping_preset(
    account_id: int = Query(...),
    institution_key: str = Query(...),
):
    tid = _require_tenant_id_or_none()
    institution = (institution_key or "").strip().lower()
    if not institution:
        raise HTTPException(status_code=400, detail="institution_key required")

    with with_db_cursor() as (conn, cur):
        _ensure_csv_presets_table(cur)
        cur.execute(
            """
            SELECT preset_json, updated_at
            FROM csv_mapping_presets
            WHERE COALESCE(tenant_id, 0) = %s
              AND account_id = %s
              AND lower(institution_key) = lower(%s)
            LIMIT 1
            """,
            (int(tid or 0), int(account_id), institution),
        )
        row = cur.fetchone()
        conn.commit()

    if not row:
        return {"ok": True, "found": False}
    try:
        preset = json.loads(row.get("preset_json") or "{}")
    except Exception:
        preset = {}
    return {"ok": True, "found": True, "preset": preset, "updated_at": row.get("updated_at")}


@router.get("/csv/mapping-presets/keys")
def list_csv_mapping_preset_keys(
    account_id: int | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50),
):
    tid = _require_tenant_id_or_none()
    limit = max(1, min(int(limit or 50), 200))
    q_norm = (q or "").strip().lower()

    with with_db_cursor() as (conn, cur):
        _ensure_csv_presets_table(cur)
        if account_id is not None and not _account_exists_for_scope(cur, int(account_id), tid):
            conn.commit()
            return {"ok": True, "keys": [], "items": []}

        params: list[Any] = [int(tid or 0)]
        account_pred = ""
        if account_id is not None:
            account_pred = "AND account_id = %s"
            params.append(int(account_id))

        key_pred = ""
        if q_norm:
            key_pred = "AND lower(institution_key) LIKE %s"
            params.append(f"%{q_norm}%")

        params.append(limit)
        cur.execute(
            f"""
            SELECT lower(institution_key) AS institution_key, MAX(updated_at) AS updated_at
            FROM csv_mapping_presets
            WHERE COALESCE(tenant_id, 0) = %s
              {account_pred}
              {key_pred}
            GROUP BY lower(institution_key)
            ORDER BY MAX(updated_at) DESC, lower(institution_key) ASC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()

    keys = [str(r.get("institution_key") or "").strip() for r in rows if str(r.get("institution_key") or "").strip()]
    return {"ok": True, "keys": keys, "items": rows}


@router.post("/csv/mapping-presets")
def save_csv_mapping_preset(body: CsvPresetBody):
    tid = _require_tenant_id_or_none()
    institution = (body.institution_key or "").strip().lower()
    if not institution:
        raise HTTPException(status_code=400, detail="institution_key required")

    with with_db_cursor() as (conn, cur):
        _ensure_csv_presets_table(cur)
        if not _account_exists_for_scope(cur, int(body.account_id), tid):
            raise HTTPException(status_code=404, detail="Account not found for current workspace")

        # Use update-then-insert so we can key on an expression-based unique index.
        cur.execute(
            """
            UPDATE csv_mapping_presets
            SET preset_json = %s,
                updated_at = now()
            WHERE COALESCE(tenant_id, 0) = %s
              AND account_id = %s
              AND lower(institution_key) = lower(%s)
            """,
            (json.dumps(body.preset or {}), int(tid or 0), int(body.account_id), institution),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO csv_mapping_presets (tenant_id, account_id, institution_key, preset_json, updated_at)
                VALUES (%s, %s, %s, %s, now())
                """,
                (tid, int(body.account_id), institution, json.dumps(body.preset or {})),
            )

        conn.commit()

    return {"ok": True}


@router.post("/csv/ingest-mapped/dry-run")
async def ingest_csv_mapped_dry_run(
    file: UploadFile = File(...),
    account_id: str | None = Form(None),
    purchase_col: int = Form(...),
    amount_col: int = Form(...),
    merchant_col: int = Form(...),
    posted_col: str | None = Form(None),
    category_col: str | None = Form(None),
    indicator_col: str | None = Form(None),
    credit_indicator_value: str = Form("credit"),
    delimiter: str = Form("auto"),
    has_header: str = Form("true"),
    header_row: int = Form(1),
    data_start_row: int = Form(2),
    invert_amount: str = Form("false"),
):
    text = _read_upload_text(file)
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    used_delim = _detect_delimiter(text, delimiter)
    rows = _parse_csv_rows(text, used_delim)
    if not rows:
        raise HTTPException(status_code=400, detail="No rows found in CSV")

    has_header_b = _to_bool(has_header, default=True)
    invert_amount_b = _to_bool(invert_amount, default=False)
    header_idx = max(0, int(header_row) - 1)
    start_idx = max(0, int(data_start_row) - 1)
    if has_header_b:
        start_idx = max(start_idx, header_idx + 1)

    try:
        posted_idx = _parse_col_opt(posted_col)
        category_idx = _parse_col_opt(category_col)
        indicator_idx = _parse_col_opt(indicator_col)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid optional column mapping")

    mapped = _analyze_mapped_rows(
        rows,
        start_idx=start_idx,
        purchase_col=int(purchase_col),
        amount_col=int(amount_col),
        merchant_col=int(merchant_col),
        posted_col=posted_idx,
        category_col=category_idx,
        indicator_col=indicator_idx,
        credit_indicator_value=credit_indicator_value,
        invert_amount=invert_amount_b,
    )
    summary = mapped["summary"]
    compare: dict[str, Any] | None = None

    acc_id: int | None = None
    try:
        if account_id is not None and str(account_id).strip():
            acc_id = int(str(account_id).strip())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid account_id")

    if acc_id:
        tid = _require_tenant_id_or_none()
        with with_db_cursor() as (conn, cur):
            if not _account_exists_for_scope(cur, int(acc_id), tid):
                raise HTTPException(status_code=404, detail="Account not found for current workspace")

            colmap = _transactions_column_lookup(cur)
            tx_id_col = _pick_col(colmap, "id")
            posted_col_name = _pick_col(colmap, "posteddate", "postedDate")
            purchase_col_name = _pick_col(colmap, "purchasedate", "purchaseDate")
            amount_col_name = _pick_col(colmap, "amount")
            merchant_col_name = _pick_col(colmap, "merchant")
            status_col_name = _pick_col(colmap, "status")
            source_col_name = _pick_col(colmap, "source")
            account_col_name = _pick_col(colmap, "account_id")
            tenant_col_name = _pick_col(colmap, "tenant_id")

            last_posted = _latest_posted_cutoff_for_account(
                cur,
                account_id=int(acc_id),
                tenant_id=tid,
                posted_col=posted_col_name,
                purchase_col=purchase_col_name,
                status_col=status_col_name,
                account_col=account_col_name,
                tenant_col=tenant_col_name,
            )
            start_after_last_posted = (last_posted + timedelta(days=1)) if last_posted else None
            end_date = datetime.now().date() - timedelta(days=1)

            would_update_exact: list[dict[str, Any]] = []
            would_update_tip: list[dict[str, Any]] = []
            would_insert: list[dict[str, Any]] = []
            skipped_before_start = 0
            skipped_after_end = 0
            reserved_pending_ids: set[str] = set()

            for entry in mapped["valid_rows"]:
                row_effective_date = entry.get("posted_date") or entry.get("purchase_date")
                if start_after_last_posted and row_effective_date and row_effective_date < start_after_last_posted:
                    skipped_before_start += 1
                    continue
                if row_effective_date and row_effective_date > end_date:
                    skipped_after_end += 1
                    continue

                amount = float(entry["amount"])
                merchant = str(entry["merchant"])
                purchase_dt = entry.get("purchase_date")
                match_id, match_kind = _pick_pending_update_target(
                    cur,
                    account_id=int(acc_id),
                    amount=amount,
                    purchase_date=purchase_dt,
                    merchant=merchant,
                    tenant_id=tid,
                    id_col=tx_id_col,
                    account_col=account_col_name,
                    amount_col=amount_col_name,
                    purchase_col=purchase_col_name,
                    merchant_col=merchant_col_name,
                    status_col=status_col_name,
                    source_col=source_col_name,
                    tenant_col=tenant_col_name,
                    window_days=4,
                    exclude_ids=reserved_pending_ids,
                )
                row_out = {
                    "row_number": int(entry.get("row_number") or 0),
                    "purchaseDate": (purchase_dt.strftime("%m/%d/%y") if purchase_dt else ""),
                    "postedDate": entry.get("posted_date").strftime("%m/%d/%y") if entry.get("posted_date") else "",
                    "amount": amount,
                    "merchant": merchant,
                }
                if match_id:
                    row_out["match_id"] = match_id
                    reserved_pending_ids.add(str(match_id))
                    if match_kind == "tip_adjust":
                        would_update_tip.append(row_out)
                    else:
                        would_update_exact.append(row_out)
                else:
                    would_insert.append(row_out)

            pending_rows = _list_pending_email_rows(
                cur,
                account_id=int(acc_id),
                tenant_id=tid,
                id_col=tx_id_col,
                account_col=account_col_name,
                amount_col=amount_col_name,
                purchase_col=purchase_col_name,
                merchant_col=merchant_col_name,
                status_col=status_col_name,
                source_col=source_col_name,
                tenant_col=tenant_col_name,
                limit=500,
            )
            conn.commit()

        compare = {
            "account_id": int(acc_id),
            "last_posted_cutoff": (last_posted.isoformat() if last_posted else None),
            "import_start_date": (start_after_last_posted.isoformat() if start_after_last_posted else None),
            "import_end_date": end_date.isoformat(),
            "skipped_before_start": int(skipped_before_start),
            "skipped_after_end": int(skipped_after_end),
            "would_update_exact_count": int(len(would_update_exact)),
            "would_update_tip_count": int(len(would_update_tip)),
            "would_insert_count": int(len(would_insert)),
            "pending_count": int(len(pending_rows)),
            "would_update_exact": would_update_exact,
            "would_update_tip": would_update_tip,
            "would_insert": would_insert,
            "pending": pending_rows,
        }

    return {
        "ok": True,
        "delimiter": used_delim,
        "summary": summary,
        "compare": compare,
    }


@router.post("/csv/preview")
async def preview_csv(
    file: UploadFile = File(...),
    delimiter: str = Form("auto"),
    has_header: str = Form("true"),
    header_row: int = Form(1),
    data_start_row: int = Form(2),
    max_rows: int = Form(12),
):
    text = _read_upload_text(file)
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    used_delim = _detect_delimiter(text, delimiter)
    rows = _parse_csv_rows(text, used_delim)
    if not rows:
        raise HTTPException(status_code=400, detail="No rows found in CSV")

    has_header_b = _to_bool(has_header, default=True)
    header_idx = max(0, int(header_row) - 1)
    start_idx = max(0, int(data_start_row) - 1)
    if has_header_b:
        start_idx = max(start_idx, header_idx + 1)

    if header_idx >= len(rows):
        raise HTTPException(status_code=400, detail="header_row is past end of file")

    width = max(len(r) for r in rows[: max(start_idx + max_rows, 20)])
    raw_headers = rows[header_idx] if has_header_b else []
    columns: list[dict[str, Any]] = []
    for i in range(width):
        h = raw_headers[i] if i < len(raw_headers) else ""
        label = h.strip() if h and h.strip() else f"Column {i + 1}"
        columns.append({"index": i, "label": label})

    preview_slice = rows[start_idx : start_idx + max(1, int(max_rows))]
    preview_rows = []
    for ridx, row in enumerate(preview_slice, start=start_idx + 1):
        cells = [row[i] if i < len(row) else "" for i in range(width)]
        preview_rows.append({"row_number": ridx, "cells": cells})

    return {
        "ok": True,
        "delimiter": used_delim,
        "row_count": len(rows),
        "column_count": width,
        "columns": columns,
        "preview_rows": preview_rows,
    }


@router.post("/csv/ingest-mapped")
async def ingest_csv_mapped(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    purchase_col: int = Form(...),
    amount_col: int = Form(...),
    merchant_col: int = Form(...),
    posted_col: str | None = Form(None),
    category_col: str | None = Form(None),
    indicator_col: str | None = Form(None),
    credit_indicator_value: str = Form("credit"),
    delimiter: str = Form("auto"),
    has_header: str = Form("true"),
    header_row: int = Form(1),
    data_start_row: int = Form(2),
    invert_amount: str = Form("false"),
):
    text = _read_upload_text(file)
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    used_delim = _detect_delimiter(text, delimiter)
    rows = _parse_csv_rows(text, used_delim)
    if not rows:
        raise HTTPException(status_code=400, detail="No rows found in CSV")

    has_header_b = _to_bool(has_header, default=True)
    invert_amount_b = _to_bool(invert_amount, default=False)
    header_idx = max(0, int(header_row) - 1)
    start_idx = max(0, int(data_start_row) - 1)
    if has_header_b:
        start_idx = max(start_idx, header_idx + 1)

    required_cols = [int(purchase_col), int(amount_col), int(merchant_col)]
    if min(required_cols) < 0:
        raise HTTPException(status_code=400, detail="Column indexes must be >= 0")

    try:
        posted_idx = _parse_col_opt(posted_col)
        category_idx = _parse_col_opt(category_col)
        indicator_idx = _parse_col_opt(indicator_col)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid optional column mapping")

    mapped = _analyze_mapped_rows(
        rows,
        start_idx=start_idx,
        purchase_col=int(purchase_col),
        amount_col=int(amount_col),
        merchant_col=int(merchant_col),
        posted_col=posted_idx,
        category_col=category_idx,
        indicator_col=indicator_idx,
        credit_indicator_value=credit_indicator_value,
        invert_amount=invert_amount_b,
    )

    tid = _require_tenant_id_or_none()
    inserted = 0
    updated = 0
    errors: list[dict[str, Any]] = list(mapped["summary"]["sample_errors"])

    with with_db_cursor() as (conn, cur):
        if not _account_exists_for_scope(cur, int(account_id), tid):
            raise HTTPException(status_code=404, detail="Account not found for current workspace")

        colmap = _transactions_column_lookup(cur)
        tx_id_col = _pick_col(colmap, "id")
        posted_col_name = _pick_col(colmap, "posteddate", "postedDate")
        purchase_col_name = _pick_col(colmap, "purchasedate", "purchaseDate")
        amount_col_name = _pick_col(colmap, "amount")
        merchant_col_name = _pick_col(colmap, "merchant")
        status_col_name = _pick_col(colmap, "status")
        source_col_name = _pick_col(colmap, "source")
        time_col_name = _pick_col(colmap, "time")
        account_col_name = _pick_col(colmap, "account_id")
        category_col_name = _pick_col(colmap, "category")
        tenant_col_name = _pick_col(colmap, "tenant_id")

        required_db = [tx_id_col, posted_col_name, purchase_col_name, amount_col_name, merchant_col_name, account_col_name]
        if any(x is None for x in required_db):
            raise HTTPException(status_code=500, detail="transactions schema missing required columns")

        last_posted = _latest_posted_cutoff_for_account(
            cur,
            account_id=int(account_id),
            tenant_id=tid,
            posted_col=posted_col_name,
            purchase_col=purchase_col_name,
            status_col=status_col_name,
            account_col=account_col_name,
            tenant_col=tenant_col_name,
        )
        start_after_last_posted = (last_posted + timedelta(days=1)) if last_posted else None
        end_date = datetime.now().date() - timedelta(days=1)

        for entry in mapped["valid_rows"]:
            row_no = int(entry["row_number"])
            row_effective_date = entry.get("posted_date") or entry.get("purchase_date")
            if start_after_last_posted and row_effective_date and row_effective_date < start_after_last_posted:
                continue
            if row_effective_date and row_effective_date > end_date:
                continue

            purchase_mmddyy = entry["purchase_date"].strftime("%m/%d/%y")
            posted_mmddyy = entry["posted_date"].strftime("%m/%d/%y")
            amount = float(entry["amount"])
            merchant = str(entry["merchant"])
            category = str(entry.get("category") or "")

            pending_match_id, _match_kind = _pick_pending_update_target(
                cur,
                account_id=int(account_id),
                amount=amount,
                purchase_date=entry.get("purchase_date"),
                merchant=merchant,
                tenant_id=tid,
                id_col=tx_id_col,
                account_col=account_col_name,
                amount_col=amount_col_name,
                purchase_col=purchase_col_name,
                merchant_col=merchant_col_name,
                status_col=status_col_name,
                source_col=source_col_name,
                tenant_col=tenant_col_name,
                window_days=4,
            )
            if pending_match_id:
                set_parts: list[str] = []
                set_vals: list[Any] = []
                if status_col_name:
                    set_parts.append(f"{status_col_name} = %s")
                    set_vals.append("Posted")
                if posted_col_name:
                    set_parts.append(f"{posted_col_name} = %s")
                    set_vals.append(posted_mmddyy)
                if purchase_col_name:
                    set_parts.append(f"{purchase_col_name} = %s")
                    set_vals.append(purchase_mmddyy)
                if amount_col_name:
                    set_parts.append(f"{amount_col_name} = %s")
                    set_vals.append(amount)
                if merchant_col_name:
                    set_parts.append(f"{merchant_col_name} = %s")
                    set_vals.append(merchant)
                if source_col_name:
                    set_parts.append(f"{source_col_name} = %s")
                    set_vals.append("CSV")
                if category_col_name and category:
                    set_parts.append(f"{category_col_name} = %s")
                    set_vals.append(category)
                if time_col_name:
                    set_parts.append(f"{time_col_name} = %s")
                    set_vals.append("unknown")
                if set_parts:
                    where = [f"{tx_id_col} = %s"]
                    where_vals: list[Any] = [pending_match_id]
                    if tid and tenant_col_name:
                        where.append(f"{tenant_col_name} = %s")
                        where_vals.append(int(tid))
                    cur.execute(
                        f"UPDATE transactions SET {', '.join(set_parts)} WHERE {' AND '.join(where)}",
                        tuple(set_vals + where_vals),
                    )
                    updated += 1
                continue

            base = _make_base_id(int(account_id), purchase_mmddyy, amount)
            tx_id = _next_tx_id(cur, base)

            payload: dict[str, Any] = {
                str(tx_id_col): tx_id,
                str(status_col_name): "Posted" if status_col_name else None,
                str(purchase_col_name): purchase_mmddyy,
                str(posted_col_name): posted_mmddyy,
                str(amount_col_name): amount,
                str(merchant_col_name): merchant,
                str(source_col_name): "CSV" if source_col_name else None,
                str(time_col_name): "unknown" if time_col_name else None,
                str(account_col_name): int(account_id),
                str(category_col_name): category if (category and category_col_name) else None,
                str(tenant_col_name): int(tid) if (tid and tenant_col_name) else None,
            }
            insert_payload = {k: v for k, v in payload.items() if k and v is not None}
            cols = list(insert_payload.keys())
            vals = [insert_payload[c] for c in cols]
            ph = ", ".join(["%s"] * len(cols))
            sql = f"INSERT INTO transactions ({', '.join(cols)}) VALUES ({ph})"
            try:
                cur.execute(sql, vals)
                inserted += 1
            except Exception as e:
                if len(errors) < 25:
                    errors.append({"row_number": row_no, "error": str(e)})

        conn.commit()

    skipped = int(mapped["summary"]["invalid_rows"]) + max(0, int(mapped["summary"]["valid_rows"]) - inserted - updated)
    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "delimiter": used_delim,
        "account_id": int(account_id),
        "last_posted_cutoff": (last_posted.isoformat() if last_posted else None),
        "import_start_date": (start_after_last_posted.isoformat() if start_after_last_posted else None),
        "import_end_date": end_date.isoformat(),
        "summary": mapped["summary"],
    }


@router.post("/csv/ingest")
async def ingest_csvs(
    target_names: List[str] = Form(...),
    files: List[UploadFile] = File(...),
):
    if len(target_names) != len(files):
        raise HTTPException(status_code=400, detail="target_names/files length mismatch")

    # repo_root = .../webApp
    repo_root = Path(__file__).resolve().parents[2]

    script_path = repo_root / "emails" / "postedDownload.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Missing script: {script_path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="csv_ingest_"))
    saved_paths: List[Path] = []

    try:
        # Save each upload into temp_dir using the user-provided *target* name
        for target, uf in zip(target_names, files):
            target_fname = _safe_target_filename(target)
            out_path = temp_dir / target_fname

            # Stream-write upload to disk
            try:
                with out_path.open("wb") as f:
                    while True:
                        chunk = await uf.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
            finally:
                try:
                    await uf.close()
                except Exception:
                    pass

            saved_paths.append(out_path)

        # Run your importer against the temp dir
        cmd = [sys.executable, str(script_path), "--input-dir", str(temp_dir)]
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "postedDownload.py failed",
                    "returncode": proc.returncode,
                    "processed": [p.name for p in saved_paths],
                    "stdout": (proc.stdout or "")[-4000:],
                    "stderr": (proc.stderr or "")[-4000:],
                },
            )

        return JSONResponse(
            {
                "ok": True,
                "processed": [p.name for p in saved_paths],
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-4000:],
            }
        )

    finally:
        # Always delete temp workspace so nothing is stored permanently
        shutil.rmtree(temp_dir, ignore_errors=True)
