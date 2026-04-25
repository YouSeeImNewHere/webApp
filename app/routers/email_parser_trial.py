from __future__ import annotations

import base64
import json
import os
import re
import threading
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
import tempfile
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import _refresh_google_access_token_if_needed, get_connected_google_email
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from db import with_db_cursor

router = APIRouter()
_SCHEMA_INIT_LOCK = threading.Lock()
_SCHEMA_READY = False
_ACCOUNTS_EMAIL_COLUMN_READY = False
_SAMPLES_CACHE_LOCK = threading.Lock()
_SAMPLES_CACHE_MAX = 1000


def _cache_key(tenant_id: int | None, user_email: str) -> tuple[int, str]:
    return (int(tenant_id or 0), str(user_email or "").strip().lower())


def _sample_store_dir() -> Path:
    p = Path(tempfile.gettempdir()) / "webapp_email_parser_samples"
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(p, 0o700)
    except Exception:
        pass
    return p


def _sample_store_file(tenant_id: int | None, user_email: str) -> Path:
    tid, email = _cache_key(tenant_id, user_email)
    safe_email = re.sub(r"[^a-z0-9_.@-]+", "_", email.lower())
    return _sample_store_dir() / f"t{tid}_{safe_email}.json"


def _read_sample_bucket(tenant_id: int | None, user_email: str) -> dict[str, dict[str, Any]]:
    f = _sample_store_file(tenant_id, user_email)
    if not f.exists():
        return {}
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        sid = str(k or "").strip()
        if not sid or not isinstance(v, dict):
            continue
        out[sid] = dict(v)
    return out


def _write_sample_bucket(tenant_id: int | None, user_email: str, bucket: dict[str, dict[str, Any]]) -> None:
    f = _sample_store_file(tenant_id, user_email)
    payload = json.dumps(bucket, ensure_ascii=False)
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(f.parent),
            prefix=f".{f.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            try:
                os.chmod(tmp_name, 0o600)
            except Exception:
                pass
            tmp.write(payload)
            tmp.flush()
        os.replace(tmp_name, f)
        try:
            os.chmod(f, 0o600)
        except Exception:
            pass
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass


def _cache_trial_samples(tenant_id: int | None, user_email: str, items: list[dict[str, Any]]) -> None:
    with _SAMPLES_CACHE_LOCK:
        bucket = _read_sample_bucket(tenant_id, user_email)
        for item in items:
            sid = str(item.get("sample_id") or "").strip()
            if not sid:
                continue
            bucket[sid] = {
                "sample_id": sid,
                "sender": str(item.get("sender") or ""),
                "subject": str(item.get("subject") or ""),
                "received_at": str(item.get("received_at") or ""),
                "snippet": str(item.get("snippet") or ""),
                "body": str(item.get("body") or ""),
                "account_id": int(item.get("account_id") or 0),
                "_cached_at": datetime.utcnow().isoformat() + "Z",
            }
        if len(bucket) > _SAMPLES_CACHE_MAX:
            # Drop oldest cached samples first to bound process memory.
            ordered = sorted(
                bucket.items(),
                key=lambda kv: str((kv[1] or {}).get("_cached_at") or ""),
            )
            drop_n = len(bucket) - _SAMPLES_CACHE_MAX
            for sid, _ in ordered[:drop_n]:
                bucket.pop(sid, None)
        _write_sample_bucket(tenant_id, user_email, bucket)


def _get_cached_trial_samples(tenant_id: int | None, user_email: str, sample_ids: list[str]) -> list[dict[str, Any]]:
    with _SAMPLES_CACHE_LOCK:
        bucket = _read_sample_bucket(tenant_id, user_email)
        out: list[dict[str, Any]] = []
        for sid in sample_ids:
            row = bucket.get(str(sid).strip())
            if row:
                out.append(dict(row))
        return out


def _get_recent_cached_trial_samples(tenant_id: int | None, user_email: str, limit: int = 40) -> list[dict[str, Any]]:
    with _SAMPLES_CACHE_LOCK:
        bucket = _read_sample_bucket(tenant_id, user_email)
        rows = [dict(v) for v in bucket.values() if isinstance(v, dict)]
        rows.sort(key=lambda r: str(r.get("_cached_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 40), 100))]


def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


def _require_session_email(request: Request) -> str:
    e = (request.session.get("google_email") or "").strip().lower()
    if not e:
        raise HTTPException(status_code=401, detail="google_auth_required")
    return e


def _normalize_parser_slot(value: Any, default: str = "parser_1") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    compact = re.sub(r"[\s\-]+", "_", raw)
    aliases = {
        "primary": "parser_1",
        "backup": "parser_2",
        "secondary": "parser_2",
        "parser1": "parser_1",
        "parser_1": "parser_1",
        "parser2": "parser_2",
        "parser_2": "parser_2",
        "parser3": "parser_3",
        "parser_3": "parser_3",
    }
    if compact in aliases:
        return aliases[compact]
    m = re.fullmatch(r"parser_?(\d+)", compact)
    if m:
        n = max(1, int(m.group(1)))
        return f"parser_{n}"
    m = re.fullmatch(r"(\d+)", compact)
    if m:
        n = max(1, int(m.group(1)))
        return f"parser_{n}"
    return default


def _parser_slot_query_candidates(slot: Any) -> list[str]:
    s = _normalize_parser_slot(slot, default="parser_1")
    if s == "parser_1":
        return ["parser_1", "primary"]
    if s == "parser_2":
        return ["parser_2", "backup", "secondary"]
    return [s]


def _parser_slot_rank(slot: Any) -> int:
    s = _normalize_parser_slot(slot, default="parser_1")
    m = re.fullmatch(r"parser_(\d+)", s)
    if not m:
        return 999
    return int(m.group(1))


def _ensure_trial_tables(cur) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_INIT_LOCK:
        if _SCHEMA_READY:
            return
        # Serialize first-time DDL across concurrent workers/processes.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (8612401901,))
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_parser_trial_drafts (
                id BIGSERIAL PRIMARY KEY,
                tenant_id BIGINT NOT NULL DEFAULT 0,
                user_email TEXT NOT NULL,
                name TEXT NOT NULL,
                account_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'trial_inactive',
                draft_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        _SCHEMA_READY = True


def _ensure_accounts_email_columns(cur) -> None:
    global _ACCOUNTS_EMAIL_COLUMN_READY
    if _ACCOUNTS_EMAIL_COLUMN_READY:
        return
    with _SCHEMA_INIT_LOCK:
        if _ACCOUNTS_EMAIL_COLUMN_READY:
            return
        # Serialize first-time DDL across concurrent workers/processes.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (8612401902,))
        cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS receives_emails BOOLEAN NOT NULL DEFAULT TRUE")
        _ACCOUNTS_EMAIL_COLUMN_READY = True


def _to_text_from_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</p\s*>", "\n", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def _decode_b64url(data: str | None) -> str:
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data.encode("utf-8"))
    except Exception:
        return ""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _looks_like_blank_label_template(s: str) -> bool:
    t = str(s or "")
    if "Merchant:" not in t:
        return False
    return bool(
        re.search(
            r"Merchant:\s*(?:\r?\n)\s*Date:\s*(?:\r?\n)\s*Amount:\s*(?:\r?\n|$)",
            t,
            flags=re.IGNORECASE,
        )
    )


def _extract_gmail_body(payload: dict[str, Any], *, try_html_on_missing_fields: bool = False) -> str:
    if not payload:
        return ""

    stack = [payload]
    plain = ""
    html = ""
    fallback = ""

    while stack:
        part = stack.pop()
        if not isinstance(part, dict):
            continue
        mime = str(part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = _decode_b64url(body.get("data"))
        if data and not fallback:
            fallback = data
        if mime == "text/plain" and data:
            plain = data
            break
        if mime == "text/html" and data and not html:
            html = data
        for child in (part.get("parts") or []):
            stack.append(child)

    if plain:
        if try_html_on_missing_fields and html and _looks_like_blank_label_template(plain):
            return _to_text_from_html(html)
        return plain.strip()
    if html:
        return _to_text_from_html(html)
    return _to_text_from_html(fallback)


def _gmail_list_messages(
    access_token: str,
    *,
    sender_query: str,
    subject_query: str,
    lookback_days: int,
    limit: int,
) -> list[str]:
    terms: list[str] = []
    sender = (sender_query or "").strip()
    subject = (subject_query or "").strip()
    if sender:
        terms.append(f"from:{sender}")
    if subject:
        safe_subject = subject.replace('"', "").strip()
        if safe_subject:
            terms.append(f'subject:"{safe_subject}"')
    if lookback_days > 0:
        terms.append(f"newer_than:{int(lookback_days)}d")
    q = " ".join(terms).strip()

    out: list[str] = []
    wanted = max(1, min(int(limit), 1000))
    page_token: str | None = None
    while len(out) < wanted:
        params: dict[str, Any] = {
            "q": q,
            "maxResults": min(100, wanted - len(out)),
        }
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=25,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"gmail_list_failed_http_{r.status_code}")
        data = r.json() or {}
        for m in (data.get("messages") or []):
            mid = str((m or {}).get("id") or "").strip()
            if mid:
                out.append(mid)
                if len(out) >= wanted:
                    break
        page_token = str(data.get("nextPageToken") or "").strip() or None
        if not page_token:
            break
    return out


def _gmail_get_message(access_token: str, message_id: str) -> dict[str, Any]:
    r = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "full"},
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"gmail_get_failed_http_{r.status_code}")
    return r.json() or {}


def _headers_map(msg: dict[str, Any]) -> dict[str, str]:
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    out: dict[str, str] = {}
    for h in headers:
        k = str((h or {}).get("name") or "").strip().lower()
        v = str((h or {}).get("value") or "").strip()
        if k and v:
            out[k] = v
    return out


def _to_regex_flags(flag_str: str) -> int:
    f = 0
    s = (flag_str or "").lower()
    if "i" in s:
        f |= re.IGNORECASE
    if "s" in s:
        f |= re.DOTALL
    if "m" in s:
        f |= re.MULTILINE
    return f


def _extract_group(match: re.Match[str], group_no: int) -> str:
    if int(group_no or 0) <= 0:
        return ""
    try:
        return str(match.group(int(group_no)) or "").strip()
    except Exception:
        return ""


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _time_from_received_at(received_at: str) -> str:
    s = str(received_at or "").strip()
    if not s:
        return ""
    try:
        dt = parsedate_to_datetime(s)
    except Exception:
        return ""
    if not dt:
        return ""
    tz = (dt.tzname() or "").strip()
    base = dt.strftime("%I:%M %p")
    return f"{base} {tz}".strip()


class TrialSamplesBody(BaseModel):
    account_id: int
    sender_query: str | None = None
    subject_query: str | None = None
    try_html_on_missing_fields: bool = False
    lookback_days: int = 30
    limit: int = 40


class TrialPreviewBody(BaseModel):
    name: str | None = None
    parser_mode: str | None = None
    parsing_method: str | None = None
    account_id: int
    sender_pattern: str | None = None
    subject_contains: str | None = None
    body_regex: str
    flags: str | None = "i"
    field_map: dict[str, Any] = {}
    guided: dict[str, Any] | None = None
    sample_ids: list[str] = []
    parser_slot: str | None = "parser_1"
    override_on_primary: bool = False
    backup_assume_unknown: bool = False
    invert_amount_sign: bool = False
    pending_ttl_minutes: int | None = 30


class TrialSaveBody(BaseModel):
    name: str
    parser_mode: str | None = None
    parsing_method: str | None = None
    account_id: int
    sender_pattern: str | None = None
    subject_contains: str | None = None
    body_regex: str | None = None
    flags: str | None = "i"
    field_map: dict[str, Any] = {}
    guided: dict[str, Any] | None = None
    status: str | None = "trial_inactive"
    sample_ids: list[str] = []
    parser_slot: str | None = "parser_1"
    override_on_primary: bool = False
    backup_assume_unknown: bool = False
    invert_amount_sign: bool = False
    pending_ttl_minutes: int | None = 30


class CorrelationPreviewBody(BaseModel):
    account_id: int
    primary_draft_id: int
    secondary_draft_id: int
    sample_ids: list[str]


class TrialDraftResetBody(BaseModel):
    account_id: int | None = None


class TrialDeleteOneBody(BaseModel):
    account_id: int
    parser_slot: str = "parser_1"


class TrialTestRunBody(BaseModel):
    account_id: int | None = None
    sender_query: str | None = None
    subject_query: str | None = None
    try_html_on_missing_fields: bool = False
    lookback_days: int = 30
    limit: int = 40


def _normalize_amount_str(v: str) -> str:
    s = str(v or "").strip().replace("$", "").replace(",", "")
    if not s:
        return ""
    try:
        return f"{float(s):.2f}"
    except Exception:
        return s


def _normalize_date_str(v: str) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%m/%d/%y")
        except Exception:
            continue
    return s.lower()


def _normalize_time_str(v: str, received_at: str) -> str:
    s = str(v or "").strip()
    if s:
        return s.lower()
    return _time_from_received_at(received_at).lower()


def _maybe_invert_amount_str(amount_norm: str, invert_amount_sign: bool) -> str:
    s = str(amount_norm or "").strip()
    if not s:
        return ""
    if not bool(invert_amount_sign):
        return s
    try:
        return f"{(-1.0 * float(s)):.2f}"
    except Exception:
        return s


def _trial_corr_key(account_id: int, amount: str, date_s: str, time_s: str) -> str:
    a = int(account_id or 0)
    amt = _normalize_amount_str(amount)
    d = _normalize_date_str(date_s)
    t = _normalize_time_str(time_s, "")
    return f"{a}|{amt}|{d}|{t}"


def _extract_from_match(m: re.Match[str], field_map: dict[str, Any], received_at: str) -> dict[str, str]:
    amount_g = int((field_map or {}).get("amount_group") or 0)
    merchant_g = int((field_map or {}).get("merchant_group") or 0)
    date_g = int((field_map or {}).get("date_group") or 0)
    time_g = int((field_map or {}).get("time_group") or 0)
    time_val = _extract_group(m, time_g)
    if not time_val:
        time_val = _time_from_received_at(received_at)
    merchant_val = _extract_group(m, merchant_g)
    merchant_val = re.sub(r"^[\s,.:;|\-]+|[\s,.:;|\-]+$", "", str(merchant_val or "").strip())
    merchant_val = re.sub(r"\s{2,}", " ", merchant_val).strip()
    if not merchant_val or len(merchant_val) < 2 or not re.search(r"[A-Za-z0-9]", merchant_val):
        merchant_val = "Unknown"
    return {
        "amount": _extract_group(m, amount_g),
        "merchant": merchant_val,
        "date": _extract_group(m, date_g),
        "time": time_val,
    }


def _boundary_label_pattern(v: str) -> str:
    parts = [re.escape(p) for p in str(v or "").strip().split() if p]
    if not parts:
        return ""
    sep = r"\s+"
    return rf"(?<!\w){sep.join(parts)}(?!\w)"


def _guided_amount_present(text: str, guided: dict[str, Any]) -> bool:
    body = str(text or "")
    amount_core = r"\$?[-]?[\d,]+\.\d{2}"
    label = str((guided or {}).get("amount_label") or "").strip()
    if label:
        lpat = _boundary_label_pattern(label)
        if lpat:
            return bool(re.search(rf"{lpat}\s*[:\-]?\s*{amount_core}", body, re.IGNORECASE))
    return bool(re.search(amount_core, body, re.IGNORECASE))


def _guided_extract_line_or_label(text: str, label: str, value_pattern: str, from_idx: int) -> tuple[str, int] | None:
    t = str(text or "")
    start = max(0, int(from_idx or 0))
    sub = t[start:]
    if label:
        lpat = _boundary_label_pattern(label)
        rx = re.compile(rf"{lpat}\s*[:\-]?\s*{value_pattern}", re.IGNORECASE)
        m = rx.search(sub)
        if not m:
            m = rx.search(t)
            if not m:
                return None
            return str(m.group(1) or "").strip(), m.end()
        return str(m.group(1) or "").strip(), start + m.end()
    rx_line = re.compile(rf"(?:^|\r?\n)\s*{value_pattern}", re.IGNORECASE)
    m = rx_line.search(sub)
    if not m:
        m = rx_line.search(t)
        if not m:
            return None
        return str(m.group(1) or "").strip(), m.end()
    return str(m.group(1) or "").strip(), start + m.end()


def _guided_extract_anywhere(text: str, value_pattern: str, from_idx: int) -> tuple[str, int] | None:
    t = str(text or "")
    start = max(0, int(from_idx or 0))
    sub = t[start:]
    rx = re.compile(value_pattern, re.IGNORECASE)
    m = rx.search(sub)
    if m:
        return str(m.group(1) or "").strip(), start + m.end()
    m = rx.search(t)
    if not m:
        return None
    return str(m.group(1) or "").strip(), m.end()


def _guided_extract_merchant(text: str, label: str, end_mode: str, end_text: str, from_idx: int) -> tuple[str, int] | None:
    t = str(text or "")
    start = max(0, int(from_idx or 0))
    sub = t[start:]
    start_pos = -1
    if label:
        lpat = _boundary_label_pattern(label)
        m = re.search(rf"{lpat}\s*[:\-]?\s*", sub, re.IGNORECASE)
        if not m:
            m0 = re.search(rf"{lpat}\s*[:\-]?\s*", t, re.IGNORECASE)
            if not m0:
                return None
            start_pos = m0.end()
        else:
            start_pos = start + m.end()
    else:
        m = re.search(r"(?:^|\r?\n)\s*([A-Za-z0-9][^\r\n]{1,140})", sub)
        if not m:
            m0 = re.search(r"(?:^|\r?\n)\s*([A-Za-z0-9][^\r\n]{1,140})", t)
            if not m0:
                return None
            start_pos = m0.start(1)
        else:
            start_pos = start + m.start(1)

    after = t[start_pos:]
    mode = str(end_mode or "auto").strip().lower()
    end = -1
    if mode in ("comma", "auto"):
        m = re.search(r"\s*,", after)
        end = m.start() if m else -1
    if end < 0 and mode == "period":
        m = re.search(r"\s*\.", after)
        end = m.start() if m else -1
    if end < 0 and mode == "newline":
        m = re.search(r"\r?\n", after)
        end = m.start() if m else -1
    if end < 0 and mode == "sentence_end":
        m = re.search(r"[.!?]", after)
        end = m.start() if m else -1
    if end < 0 and mode == "text":
        needle = str(end_text or "").strip()
        if needle:
            idx = after.lower().find(needle.lower())
            if idx >= 0:
                end = idx
    if end < 0 and mode == "auto":
        m = re.search(r"\s+(?:in\s+the\s+amount\s+of|amount\s+of|on\s+\d{1,2}/\d{1,2}/\d{2,4}|on\s+[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", after, re.IGNORECASE)
        end = m.start() if m else -1
    if end < 0:
        end = min(len(after), 160)
    raw = str(after[:end]).strip()
    clean = re.sub(r"^[\s,.:;|\-]+|[\s,.:;|\-]+$", "", raw)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    if not clean or len(clean) < 2 or not re.search(r"[A-Za-z0-9]", clean):
        return None
    return clean, start_pos + end


def _extract_from_guided(body: str, guided: dict[str, Any], received_at: str) -> dict[str, str] | None:
    text = str(body or "")
    g = guided or {}
    ord_map = {
        "amount": int(g.get("amount_order") or 0),
        "merchant": int(g.get("merchant_order") or 0),
        "date": int(g.get("date_order") or 0),
        "time": int(g.get("time_order") or 0),
    }
    if ord_map["amount"] <= 0 and _guided_amount_present(text, g):
        return None
    ordered = [k for k in ("amount", "merchant", "date", "time") if int(ord_map.get(k) or 0) > 0]
    ordered.sort(key=lambda k: int(ord_map.get(k) or 0))
    if not ordered:
        return None

    acct_before = str(g.get("account_before") or "").strip()
    acct_exact = str(g.get("account_exact") or "").strip()
    if acct_before and acct_exact:
        bpat = _boundary_label_pattern(acct_before)
        epat = re.escape(acct_exact)
        if not re.search(rf"{bpat}\s*[:\-]?\s*[^\r\n]*?{epat}", text, re.IGNORECASE):
            return None

    amount_re = r"(\$?[-]?[\d,]+\.\d{2})"
    date_re = r"([A-Za-z]{3},?\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
    time_re = r"([0-1]?\d:[0-5]\d\s*(?:AM|PM)(?:\s*[A-Z]{2,4})?)"
    out = {"amount": "", "merchant": "Unknown", "date": "", "time": ""}
    cursor = 0
    for field in ordered:
        if field == "amount":
            label = str(g.get("amount_label") or "").strip()
            got = _guided_extract_line_or_label(text, label, amount_re, cursor)
            if not got and label:
                got = _guided_extract_line_or_label(text, "", amount_re, cursor)
            if not got:
                got = _guided_extract_anywhere(text, amount_re, cursor)
            if not got:
                return None
            out["amount"], cursor = got
        elif field == "date":
            label = str(g.get("date_label") or "").strip()
            got = _guided_extract_line_or_label(text, label, date_re, cursor)
            if not got and label:
                got = _guided_extract_line_or_label(text, "", date_re, cursor)
            if not got:
                got = _guided_extract_anywhere(text, date_re, cursor)
            if not got:
                return None
            out["date"], cursor = got
        elif field == "time":
            label = str(g.get("time_label") or "").strip()
            got = _guided_extract_line_or_label(text, label, time_re, cursor)
            if not got and label:
                got = _guided_extract_line_or_label(text, "", time_re, cursor)
            if not got:
                got = _guided_extract_anywhere(text, time_re, cursor)
            if got:
                out["time"], cursor = got
        elif field == "merchant":
            got = _guided_extract_merchant(
                text,
                str(g.get("merchant_label") or "").strip(),
                str(g.get("merchant_end") or "auto").strip().lower(),
                str(g.get("merchant_end_text") or "").strip(),
                cursor,
            )
            if not got:
                return None
            merchant_val, cursor = got
            label = str(g.get("merchant_label") or "")
            if re.search(r"description:?", label, re.IGNORECASE) and re.search(r"\s-\s", merchant_val):
                parts = [x.strip() for x in re.split(r"\s-\s", merchant_val) if x.strip()]
                if parts:
                    merchant_val = parts[-1]
            out["merchant"] = merchant_val

    if not out["time"]:
        out["time"] = _time_from_received_at(received_at)
    return out


def _scope_match(cfg: dict[str, Any], sender: str, subject: str) -> bool:
    sp = str(cfg.get("sender_pattern") or "").strip().lower()
    sc = str(cfg.get("subject_contains") or "").strip().lower()
    snd = str(sender or "").strip().lower()
    sub = str(subject or "").strip().lower()
    if sp and sp not in snd:
        return False
    if sc and sc not in sub:
        return False
    return True


def _subject_scoped_parsers(parsers: list[dict[str, Any]], subject: str) -> list[dict[str, Any]]:
    sub = str(subject or "").strip().lower()
    specific = [
        p for p in parsers
        if str(p.get("subject_contains") or "").strip()
        and str(p.get("subject_contains") or "").strip().lower() in sub
    ]
    if specific:
        return specific
    blank = [p for p in parsers if not str(p.get("subject_contains") or "").strip()]
    return blank


def _load_saved_parsers(cur, tenant_id: int, user_email: str, account_id: int | None = None) -> list[dict[str, Any]]:
    if account_id is None:
        cur.execute(
            """
            SELECT d.id, d.name, d.account_id, d.draft_json, d.updated_at,
                   a.institution, a.name AS account_name
            FROM email_parser_trial_drafts d
            LEFT JOIN accounts a ON a.id = d.account_id
            WHERE d.tenant_id = %s
              AND d.user_email = %s
            ORDER BY d.updated_at DESC, d.id DESC
            """,
            (int(tenant_id), user_email),
        )
    else:
        cur.execute(
            """
            SELECT d.id, d.name, d.account_id, d.draft_json, d.updated_at,
                   a.institution, a.name AS account_name
            FROM email_parser_trial_drafts d
            LEFT JOIN accounts a ON a.id = d.account_id
            WHERE d.tenant_id = %s
              AND d.user_email = %s
              AND d.account_id = %s
            ORDER BY d.updated_at DESC, d.id DESC
            """,
            (int(tenant_id), user_email, int(account_id)),
        )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    parsers: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for r in rows:
        rid = int(r.get("id") or 0)
        cfg_raw = r.get("draft_json")
        cfg: dict[str, Any] = {}
        if isinstance(cfg_raw, str):
            try:
                cfg = json.loads(cfg_raw) or {}
            except Exception:
                cfg = {}
        elif isinstance(cfg_raw, dict):
            cfg = cfg_raw
        body_regex = str(cfg.get("body_regex") or "").strip()
        if not body_regex:
            continue
        flags = str(cfg.get("flags") or "i").strip() or "i"
        try:
            rx = re.compile(body_regex, _to_regex_flags(flags))
        except re.error:
            continue
        slot = _normalize_parser_slot(cfg.get("parser_slot"), default="parser_1")
        sender_pattern = str(cfg.get("sender_pattern") or "").strip()
        subject_contains = str(cfg.get("subject_contains") or "").strip()
        parser_account_id = int(cfg.get("account_id") or r.get("account_id") or 0)
        dedupe_key = f"{parser_account_id}|{slot}"
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        parsers.append(
            {
                "draft_id": rid,
                "name": str(cfg.get("name") or r.get("name") or "").strip(),
                "account_id": parser_account_id,
                "account_label": (
                    f"{str(r.get('institution') or '').strip()} {str(r.get('account_name') or '').strip()}".strip()
                ),
                "parser_slot": slot,
                "override_on_primary": bool(cfg.get("override_on_primary")),
                "backup_assume_unknown": bool(cfg.get("backup_assume_unknown")),
                "invert_amount_sign": bool(cfg.get("invert_amount_sign")),
                "sender_pattern": sender_pattern,
                "subject_contains": subject_contains,
                "field_map": cfg.get("field_map") if isinstance(cfg.get("field_map"), dict) else {},
                "rx": rx,
            }
        )
    parsers.sort(key=lambda p: (_parser_slot_rank(p.get("parser_slot")), int(p.get("draft_id") or 0)))
    return parsers


@router.get("/email-parser/trial/accounts")
def trial_accounts(request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        _ensure_accounts_email_columns(cur)
        if tid:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.institution,
                    a.name,
                    LOWER(a.accounttype) AS accounttype,
                    COALESCE(a.receives_emails, TRUE) AS receives_emails,
                    EXISTS (
                      SELECT 1
                      FROM email_parser_trial_drafts d
                      WHERE d.tenant_id = %s
                        AND d.user_email = %s
                        AND d.account_id = a.id
                    ) AS has_parser_setting
                FROM accounts a
                WHERE a.tenant_id = %s
                  AND COALESCE(a.receives_emails, TRUE) = TRUE
                ORDER BY institution ASC, name ASC, id ASC
                """,
                (int(tid), session_email, int(tid)),
            )
        else:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.institution,
                    a.name,
                    LOWER(a.accounttype) AS accounttype,
                    COALESCE(a.receives_emails, TRUE) AS receives_emails,
                    EXISTS (
                      SELECT 1
                      FROM email_parser_trial_drafts d
                      WHERE d.tenant_id = 0
                        AND d.user_email = %s
                        AND d.account_id = a.id
                    ) AS has_parser_setting
                FROM accounts a
                WHERE COALESCE(a.receives_emails, TRUE) = TRUE
                ORDER BY institution ASC, name ASC, id ASC
                """,
                (session_email,),
            )
        rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()
    return {"ok": True, "accounts": rows}


@router.post("/email-parser/trial/samples")
def trial_samples(body: TrialSamplesBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    oauth_email = get_connected_google_email(session_email)
    if oauth_email and oauth_email != session_email:
        raise HTTPException(
            status_code=409,
            detail=f"gmail_oauth_account_mismatch:connected={oauth_email}:session={session_email}",
        )

    sender_query = (body.sender_query or "").strip()
    subject_query = (body.subject_query or "").strip()
    if not sender_query:
        raise HTTPException(status_code=422, detail="sender_query_required")

    access_token, err, _ = _refresh_google_access_token_if_needed(session_email)
    if not access_token:
        raise HTTPException(status_code=401, detail=f"gmail_not_connected:{err or 'unknown'}")

    limit_n = max(1, min(int(body.limit or 40), 100))
    lookback_n = max(1, min(int(body.lookback_days or 30), 365))
    try:
        message_ids = _gmail_list_messages(
            access_token,
            sender_query=sender_query,
            subject_query=subject_query,
            lookback_days=lookback_n,
            limit=limit_n,
        )
    except HTTPException as e:
        if int(getattr(e, "status_code", 0) or 0) == 502:
            cached = _get_recent_cached_trial_samples(tid, session_email, limit=limit_n)
            return {
                "ok": True,
                "items": cached,
                "count": len(cached),
                "stale": True,
                "warning": str(getattr(e, "detail", "gmail_upstream_unavailable")),
            }
        raise
    # Deterministic lock/update order across concurrent requests reduces deadlock risk.
    message_ids = sorted(dict.fromkeys(message_ids))

    items: list[dict[str, Any]] = []
    fetch_errors: list[str] = []
    for mid in message_ids:
        try:
            msg = _gmail_get_message(access_token, mid)
        except HTTPException as e:
            if int(getattr(e, "status_code", 0) or 0) == 502:
                fetch_errors.append(str(getattr(e, "detail", "gmail_get_failed")))
                continue
            raise
        h = _headers_map(msg)
        body_text = _extract_gmail_body(
            msg.get("payload") or {},
            try_html_on_missing_fields=bool(body.try_html_on_missing_fields),
        )
        snippet = str(msg.get("snippet") or "")[:600]
        item = {
            "sample_id": mid,
            "sender": h.get("from", ""),
            "subject": h.get("subject", ""),
            "received_at": h.get("date", ""),
            "snippet": snippet,
            "body": body_text,
            "account_id": int(body.account_id),
        }
        items.append(item)
    if items:
        _cache_trial_samples(tid, session_email, items)

    if not items and fetch_errors:
        cached = _get_recent_cached_trial_samples(tid, session_email, limit=limit_n)
        return {
            "ok": True,
            "items": cached,
            "count": len(cached),
            "stale": True,
            "warning": fetch_errors[0],
        }

    out = {"ok": True, "items": items, "count": len(items)}
    if fetch_errors:
        out["warning"] = f"partial_fetch_errors:{len(fetch_errors)}"
    return out


@router.get("/email-parser/trial/account-settings/{account_id}")
def trial_account_settings(account_id: int, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        cur.execute(
            """
            SELECT id, name, draft_json, updated_at
            FROM email_parser_trial_drafts
            WHERE tenant_id = %s
              AND user_email = %s
              AND account_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (int(tid or 0), session_email, int(account_id)),
        )
        rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()

    settings: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for r in rows:
        raw = r.get("draft_json")
        cfg: dict[str, Any] = {}
        if isinstance(raw, str):
            try:
                cfg = json.loads(raw) or {}
            except Exception:
                cfg = {}
        elif isinstance(raw, dict):
            cfg = raw

        subject = str(cfg.get("subject_contains") or "").strip()
        sender = str(cfg.get("sender_pattern") or "").strip()
        slot = _normalize_parser_slot(cfg.get("parser_slot"), default="parser_1")
        key = slot
        if key in seen_keys:
            continue
        seen_keys.add(key)
        settings.append(
            {
                "draft_id": int(r.get("id") or 0),
                "name": str(cfg.get("name") or r.get("name") or "").strip(),
                "subject_contains": subject,
                "sender_pattern": sender,
                "parser_mode": str(cfg.get("parser_mode") or "").strip(),
                "parsing_method": str(cfg.get("parsing_method") or "").strip(),
                "parser_slot": slot,
                "override_on_primary": bool(cfg.get("override_on_primary")),
                "backup_assume_unknown": bool(cfg.get("backup_assume_unknown")),
                "invert_amount_sign": bool(cfg.get("invert_amount_sign")),
                "pending_ttl_minutes": max(1, min(_safe_int(cfg.get("pending_ttl_minutes"), 30), 24 * 60)),
                "body_regex": str(cfg.get("body_regex") or "").strip(),
                "flags": str(cfg.get("flags") or "i").strip() or "i",
                "field_map": cfg.get("field_map") if isinstance(cfg.get("field_map"), dict) else {},
                "guided": cfg.get("guided") if isinstance(cfg.get("guided"), dict) else {},
            }
        )
    return {"ok": True, "account_id": int(account_id), "settings": settings}


@router.post("/email-parser/trial/preview")
def trial_preview(body: TrialPreviewBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    ids = [str(x).strip() for x in (body.sample_ids or []) if str(x).strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="sample_ids_required")
    parser_mode = str(body.parser_mode or "advanced").strip().lower()
    rx = None
    if parser_mode != "guided":
        rx_txt = (body.body_regex or "").strip()
        if not rx_txt:
            raise HTTPException(status_code=422, detail="body_regex_required")
        try:
            rx = re.compile(rx_txt, _to_regex_flags(body.flags or "i"))
        except re.error as e:
            raise HTTPException(status_code=422, detail=f"invalid_regex:{e}")

    rows = _get_cached_trial_samples(tid, session_email, ids)

    by_id = {
        str(r.get("sample_id") or ""): {
            "body": str(r.get("body") or ""),
            "received_at": str(r.get("received_at") or ""),
        }
        for r in rows
    }
    fm = body.field_map or {}

    out: list[dict[str, Any]] = []
    for sid in ids:
        row = by_id.get(sid) or {}
        btxt = str(row.get("body") or "")
        received_at = str(row.get("received_at") or "")
        if not btxt:
            out.append({"sample_id": sid, "matched": False, "extracted": None, "error": "sample_not_found"})
            continue
        if parser_mode == "guided":
            ext = _extract_from_guided(btxt, body.guided or {}, received_at)
            if not ext:
                out.append({"sample_id": sid, "matched": False, "extracted": None, "error": "No guided match"})
                continue
            out.append({"sample_id": sid, "matched": True, "extracted": ext})
            continue

        amount_g = int(fm.get("amount_group") or 0)
        merchant_g = int(fm.get("merchant_group") or 0)
        date_g = int(fm.get("date_group") or 0)
        time_g = int(fm.get("time_group") or 0)
        m = rx.search(btxt) if rx else None
        if not m:
            out.append({"sample_id": sid, "matched": False, "extracted": None, "error": "No regex match"})
            continue
        out.append({"sample_id": sid, "matched": True, "extracted": _extract_from_match(m, fm, received_at)})

    return {"ok": True, "rows": out, "matched": sum(1 for r in out if r.get("matched"))}


@router.post("/email-parser/trial/save")
def trial_save(body: TrialSaveBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name_required")

    parser_slot = _normalize_parser_slot(body.parser_slot, default="parser_1")
    parser_slot_candidates = _parser_slot_query_candidates(parser_slot)
    draft_json = {
        "name": name,
        "parser_mode": (body.parser_mode or "").strip().lower(),
        "parsing_method": (body.parsing_method or "anchor").strip().lower(),
        "parser_slot": parser_slot,
        "override_on_primary": bool(body.override_on_primary),
        "backup_assume_unknown": bool(body.backup_assume_unknown),
        "invert_amount_sign": bool(body.invert_amount_sign),
        "pending_ttl_minutes": max(1, min(int(body.pending_ttl_minutes or 30), 24 * 60)),
        "account_id": int(body.account_id),
        "sender_pattern": (body.sender_pattern or "").strip(),
        "subject_contains": (body.subject_contains or "").strip(),
        "body_regex": (body.body_regex or "").strip(),
        "flags": (body.flags or "i").strip() or "i",
        "field_map": body.field_map or {},
        "guided": body.guided or {},
        "sample_ids": [str(x).strip() for x in (body.sample_ids or []) if str(x).strip()],
        "status": (body.status or "trial_inactive").strip().lower(),
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }

    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        tid0 = int(tid or 0)
        # Upsert behavior for parser slots at account-level:
        # one parser per slot per account.
        cur.execute(
            """
            SELECT id
            FROM email_parser_trial_drafts
            WHERE tenant_id = %s
              AND user_email = %s
              AND account_id = %s
              AND lower(COALESCE((draft_json::jsonb->>'parser_slot'), 'primary')) = ANY(%s)
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (
                tid0,
                session_email,
                int(body.account_id),
                parser_slot_candidates,
            ),
        )
        existing = cur.fetchone() or {}
        existing_id = int(existing.get("id") or 0)
        if existing_id > 0:
            cur.execute(
                """
                UPDATE email_parser_trial_drafts
                SET name = %s,
                    status = %s,
                    draft_json = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (
                    name,
                    (body.status or "trial_inactive").strip().lower(),
                    json.dumps(draft_json),
                    existing_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO email_parser_trial_drafts
                    (tenant_id, user_email, name, account_id, status, draft_json, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, now())
                RETURNING id
                """,
                (
                    tid0,
                    session_email,
                    name,
                    int(body.account_id),
                    (body.status or "trial_inactive").strip().lower(),
                    json.dumps(draft_json),
                ),
            )
        row = cur.fetchone() or {}
        saved_id = int(row.get("id") or 0)
        if saved_id > 0:
            cur.execute(
                """
                DELETE FROM email_parser_trial_drafts
                WHERE tenant_id = %s
                  AND user_email = %s
                  AND account_id = %s
                  AND lower(COALESCE((draft_json::jsonb->>'parser_slot'), 'primary')) = ANY(%s)
                  AND id <> %s
                """,
                (tid0, session_email, int(body.account_id), parser_slot_candidates, saved_id),
            )
        conn.commit()
    return {"ok": True, "draft_id": int(row.get("id") or 0)}


@router.post("/email-parser/trial/correlation-preview")
def trial_correlation_preview(body: CorrelationPreviewBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    ids = [str(x).strip() for x in (body.sample_ids or []) if str(x).strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="sample_ids_required")

    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        tid0 = int(tid or 0)

        cur.execute(
            """
            SELECT id, draft_json
            FROM email_parser_trial_drafts
            WHERE tenant_id = %s
              AND user_email = %s
              AND account_id = %s
              AND id IN (%s, %s)
            """,
            (tid0, session_email, int(body.account_id), int(body.primary_draft_id), int(body.secondary_draft_id)),
        )
        draft_rows = [dict(r) for r in (cur.fetchall() or [])]
        by_did: dict[int, dict[str, Any]] = {}
        for r in draft_rows:
            did = int(r.get("id") or 0)
            cfg_raw = r.get("draft_json")
            cfg = {}
            if isinstance(cfg_raw, str):
                try:
                    cfg = json.loads(cfg_raw) or {}
                except Exception:
                    cfg = {}
            by_did[did] = cfg

        primary_cfg = by_did.get(int(body.primary_draft_id))
        secondary_cfg = by_did.get(int(body.secondary_draft_id))
        if not primary_cfg or not secondary_cfg:
            raise HTTPException(status_code=404, detail="draft_not_found_for_account")

        try:
            primary_rx = re.compile(
                str(primary_cfg.get("body_regex") or "").strip(),
                _to_regex_flags(str(primary_cfg.get("flags") or "i")),
            )
            secondary_rx = re.compile(
                str(secondary_cfg.get("body_regex") or "").strip(),
                _to_regex_flags(str(secondary_cfg.get("flags") or "i")),
            )
        except re.error as e:
            raise HTTPException(status_code=422, detail=f"invalid_regex:{e}")

        conn.commit()
    sample_rows = _get_cached_trial_samples(tid, session_email, ids)

    def _sort_key(r: dict[str, Any]):
        d = str(r.get("received_at") or "").strip()
        try:
            dt = parsedate_to_datetime(d)
            if dt:
                return dt.isoformat()
        except Exception:
            pass
        return d

    samples = sorted(sample_rows, key=_sort_key)
    sample_by_id = {str(s.get("sample_id") or ""): s for s in samples}

    pending: dict[str, dict[str, Any]] = {}
    notified: set[str] = set()
    seen_tx: set[str] = set()
    out_rows: list[dict[str, Any]] = []
    summary = {
        "no_match": 0,
        "pending": 0,
        "resolved": 0,
        "notify_immediate": 0,
        "skip_already_notified": 0,
        "insert_trial": 0,
        "merge_existing": 0,
    }

    for sid in ids:
        s = sample_by_id.get(sid)
        if not s:
            out_rows.append({"sample_id": sid, "action": "sample_not_found", "notify": False})
            continue
        body_txt = str(s.get("body") or "")
        received_at = str(s.get("received_at") or "")

        pm = primary_rx.search(body_txt)
        sm = None if pm else secondary_rx.search(body_txt)
        if not pm and not sm:
            summary["no_match"] += 1
            out_rows.append(
                {
                    "sample_id": sid,
                    "subject": s.get("subject"),
                    "sender": s.get("sender"),
                    "matched_rule": "none",
                    "action": "no_match",
                    "notify": False,
                }
            )
            continue

        matched_rule = "primary" if pm else "secondary"
        cfg = primary_cfg if pm else secondary_cfg
        m = pm or sm
        extracted = _extract_from_match(m, cfg.get("field_map") if isinstance(cfg.get("field_map"), dict) else {}, received_at)
        extracted["amount"] = _maybe_invert_amount_str(
            _normalize_amount_str(str(extracted.get("amount") or "")),
            bool(cfg.get("invert_amount_sign")),
        )
        key = _trial_corr_key(
            int(body.account_id),
            extracted.get("amount") or "",
            extracted.get("date") or "",
            extracted.get("time") or "",
        )

        tx_action = "merge_existing" if key in seen_tx else "insert_trial"
        seen_tx.add(key)
        summary[tx_action] += 1

        merchant = str(extracted.get("merchant") or "").strip().lower()
        unknown_merchant = merchant in ("", "unknown", "unknown merchant")

        action = ""
        notify = False
        if key in notified:
            action = "skip_already_notified"
            summary["skip_already_notified"] += 1
        elif matched_rule == "primary":
            if key in pending:
                pending.pop(key, None)
                action = "resolve_pending_notify"
                notify = True
                notified.add(key)
                summary["resolved"] += 1
            else:
                action = "notify_immediate"
                notify = True
                notified.add(key)
                summary["notify_immediate"] += 1
        else:
            if unknown_merchant:
                pending[key] = {"sample_id": sid}
                action = "pending_upsert"
                summary["pending"] += 1
            else:
                action = "notify_immediate"
                notify = True
                notified.add(key)
                summary["notify_immediate"] += 1

        out_rows.append(
            {
                "sample_id": sid,
                "subject": s.get("subject"),
                "sender": s.get("sender"),
                "received_at": s.get("received_at"),
                "matched_rule": matched_rule,
                "action": action,
                "tx_action": tx_action,
                "notify": notify,
                "key": key,
                "extracted": extracted,
            }
        )

    return {
        "ok": True,
        "summary": summary,
        "pending_count": len(pending),
        "rows": out_rows,
    }


@router.post("/email-parser/trial/drafts/reset")
def trial_reset_drafts(body: TrialDraftResetBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        tid0 = int(tid or 0)
        if body.account_id is not None:
            cur.execute(
                """
                DELETE FROM email_parser_trial_drafts
                WHERE tenant_id = %s
                  AND user_email = %s
                  AND account_id = %s
                """,
                (tid0, session_email, int(body.account_id)),
            )
        else:
            cur.execute(
                """
                DELETE FROM email_parser_trial_drafts
                WHERE tenant_id = %s
                  AND user_email = %s
                """,
                (tid0, session_email),
            )
        deleted = int(cur.rowcount or 0)
        conn.commit()
    return {"ok": True, "deleted": deleted}


@router.post("/email-parser/trial/draft/delete-one")
def trial_delete_one_draft(body: TrialDeleteOneBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    slot = _normalize_parser_slot(body.parser_slot, default="parser_1")
    slot_candidates = _parser_slot_query_candidates(slot)
    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        tid0 = int(tid or 0)
        cur.execute(
            """
            DELETE FROM email_parser_trial_drafts
            WHERE tenant_id = %s
              AND user_email = %s
              AND account_id = %s
              AND lower(COALESCE((draft_json::jsonb->>'parser_slot'), 'primary')) = ANY(%s)
            """,
            (tid0, session_email, int(body.account_id), slot_candidates),
        )
        deleted = int(cur.rowcount or 0)
        conn.commit()
    return {"ok": True, "deleted": deleted, "account_id": int(body.account_id), "parser_slot": slot}


@router.post("/email-parser/trial/test-run")
def trial_test_run(body: TrialTestRunBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    sender_query = (body.sender_query or "").strip()
    subject_query = (body.subject_query or "").strip()

    access_token, err, _ = _refresh_google_access_token_if_needed(session_email)
    if not access_token:
        raise HTTPException(status_code=401, detail=f"gmail_not_connected:{err or 'unknown'}")

    message_ids = _gmail_list_messages(
        access_token,
        sender_query=sender_query,
        subject_query=subject_query,
        lookback_days=max(1, min(int(body.lookback_days or 30), 365)),
        limit=max(1, min(int(body.limit or 40), 100)),
    )

    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        parsers = _load_saved_parsers(cur, int(tid or 0), session_email, None)
        conn.commit()

    rows: list[dict[str, Any]] = []
    summary = {
        "fetched": len(message_ids),
        "parsers": len(parsers),
        "matched": 0,
        "skipped": 0,
        "would_insert": 0,
        "would_skip_insert": 0,
    }
    if not parsers:
        return {"ok": True, "summary": summary, "rows": rows, "detail": "no_parsers_for_account"}

    for mid in message_ids:
        msg = _gmail_get_message(access_token, mid)
        h = _headers_map(msg)
        sender = h.get("from", "")
        subject = h.get("subject", "")
        received_at = h.get("date", "")
        body_text = _extract_gmail_body(
            msg.get("payload") or {},
            try_html_on_missing_fields=bool(body.try_html_on_missing_fields),
        )
        scoped_parsers = _subject_scoped_parsers(parsers, subject)
        matched_row = None
        parser_fail_reasons: list[str] = []
        if not scoped_parsers:
            summary["skipped"] += 1
            summary["would_skip_insert"] += 1
            rows.append(
                {
                    "sample_id": mid,
                    "subject": subject,
                    "sender": sender,
                    "received_at": received_at,
                    "matched": False,
                    "skip_reason": "no_subject_parser",
                    "would_insert": False,
                    "extracted": None,
                    "would_db_row": None,
                    "parser": None,
                }
            )
            continue
        for p in scoped_parsers:
            # Subject already scoped candidates; sender is optional additional scope.
            if str(p.get("sender_pattern") or "").strip() and not _scope_match(p, sender, subject):
                continue
            m = p["rx"].search(body_text or "")
            if not m:
                continue
            ext = _extract_from_match(m, p.get("field_map") if isinstance(p.get("field_map"), dict) else {}, received_at)
            amt_raw = str(ext.get("amount") or "").strip()
            amt_norm = _normalize_amount_str(amt_raw)
            amt_norm = _maybe_invert_amount_str(amt_norm, bool(p.get("invert_amount_sign")))
            merchant = str(ext.get("merchant") or "").strip() or "Unknown"
            if p.get("backup_assume_unknown") and _normalize_parser_slot(p.get("parser_slot"), default="parser_1") == "parser_2":
                merchant = "Unknown"
            date_norm = _normalize_date_str(str(ext.get("date") or "").strip())
            time_norm = _normalize_time_str(str(ext.get("time") or "").strip(), received_at)
            would_insert = bool(amt_norm)
            if not would_insert:
                parser_fail_reasons.append(
                    f"{str(p.get('name') or '(unnamed)')}#{int(p.get('draft_id') or 0)}:amount_missing_or_invalid"
                )
                continue
            summary["would_insert"] += 1
            matched_row = {
                "sample_id": mid,
                "subject": subject,
                "sender": sender,
                "received_at": received_at,
                "matched": True,
                "parser": {
                    "draft_id": int(p.get("draft_id") or 0),
                    "name": str(p.get("name") or "").strip(),
                    "account_id": int(p.get("account_id") or 0),
                    "account_label": str(p.get("account_label") or "").strip(),
                    "slot": str(p.get("parser_slot") or "").strip(),
                    "override_on_primary": bool(p.get("override_on_primary")),
                    "backup_assume_unknown": bool(p.get("backup_assume_unknown")),
                    "invert_amount_sign": bool(p.get("invert_amount_sign")),
                },
                "would_insert": would_insert,
                "skip_reason": "" if would_insert else "amount_missing_or_invalid",
                "extracted": {
                    "amount": amt_norm,
                    "merchant": merchant,
                    "date": date_norm,
                    "time": time_norm,
                },
                "would_db_row": (
                    {
                        "account_id": int(p.get("account_id") or 0),
                        "amount": amt_norm,
                        "merchant": merchant,
                        "purchasedate": date_norm,
                        "time": time_norm,
                        "source": "email",
                    }
                    if would_insert
                    else None
                ),
            }
            break
        if matched_row:
            summary["matched"] += 1
            rows.append(matched_row)
        else:
            summary["skipped"] += 1
            summary["would_skip_insert"] += 1
            reason = "no_parser_match_for_subject"
            if parser_fail_reasons:
                reason = "parser_matched_but_invalid_amount"
            rows.append(
                {
                    "sample_id": mid,
                    "subject": subject,
                    "sender": sender,
                    "received_at": received_at,
                    "matched": False,
                    "skip_reason": reason,
                    "attempted_parsers": parser_fail_reasons,
                    "would_insert": False,
                    "extracted": None,
                    "would_db_row": None,
                    "parser": None,
                }
            )

    return {"ok": True, "summary": summary, "rows": rows}
