from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import _refresh_google_access_token_if_needed
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from db import with_db_cursor

router = APIRouter()


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


def _ensure_trial_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS email_parser_trial_samples (
            id BIGSERIAL PRIMARY KEY,
            tenant_id BIGINT NOT NULL DEFAULT 0,
            user_email TEXT NOT NULL,
            sample_id TEXT NOT NULL,
            account_id BIGINT,
            sender TEXT,
            subject TEXT,
            received_at TEXT,
            snippet TEXT,
            body TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_email_parser_trial_samples_scope
        ON email_parser_trial_samples (tenant_id, sample_id)
        """
    )
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


def _ensure_accounts_email_columns(cur) -> None:
    cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS receives_emails BOOLEAN NOT NULL DEFAULT TRUE")


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

    r = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": q, "maxResults": max(1, min(int(limit), 100))},
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"gmail_list_failed_http_{r.status_code}")
    data = r.json() or {}
    out: list[str] = []
    for m in (data.get("messages") or []):
        mid = str((m or {}).get("id") or "").strip()
        if mid:
            out.append(mid)
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
    rule_role: str | None = "standard"
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
    rule_role: str | None = "standard"
    pending_ttl_minutes: int | None = 30


class CorrelationPreviewBody(BaseModel):
    account_id: int
    primary_draft_id: int
    secondary_draft_id: int
    sample_ids: list[str]


class TrialDraftResetBody(BaseModel):
    account_id: int | None = None


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
    if not merchant_val:
        merchant_val = "Unknown"
    return {
        "amount": _extract_group(m, amount_g),
        "merchant": merchant_val,
        "date": _extract_group(m, date_g),
        "time": time_val,
    }


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

    sender_query = (body.sender_query or "").strip()
    subject_query = (body.subject_query or "").strip()
    if not sender_query:
        raise HTTPException(status_code=422, detail="sender_query_required")

    access_token, err = _refresh_google_access_token_if_needed()
    if not access_token:
        raise HTTPException(status_code=401, detail=f"gmail_not_connected:{err or 'unknown'}")

    message_ids = _gmail_list_messages(
        access_token,
        sender_query=sender_query,
        subject_query=subject_query,
        lookback_days=max(1, min(int(body.lookback_days or 30), 365)),
        limit=max(1, min(int(body.limit or 40), 100)),
    )

    items: list[dict[str, Any]] = []
    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        tid0 = int(tid or 0)
        for mid in message_ids:
            msg = _gmail_get_message(access_token, mid)
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
            }
            items.append(item)
            cur.execute(
                """
                INSERT INTO email_parser_trial_samples
                    (tenant_id, user_email, sample_id, account_id, sender, subject, received_at, snippet, body, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (tenant_id, sample_id) DO UPDATE SET
                    user_email = EXCLUDED.user_email,
                    account_id = EXCLUDED.account_id,
                    sender = EXCLUDED.sender,
                    subject = EXCLUDED.subject,
                    received_at = EXCLUDED.received_at,
                    snippet = EXCLUDED.snippet,
                    body = EXCLUDED.body,
                    updated_at = now()
                """,
                (
                    tid0,
                    session_email,
                    mid,
                    int(body.account_id),
                    item["sender"],
                    item["subject"],
                    item["received_at"],
                    item["snippet"],
                    item["body"],
                ),
            )
        conn.commit()

    return {"ok": True, "items": items, "count": len(items)}


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
    seen_subjects: set[str] = set()
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
        key = subject.lower()
        if key in seen_subjects:
            continue
        seen_subjects.add(key)
        settings.append(
            {
                "draft_id": int(r.get("id") or 0),
                "name": str(cfg.get("name") or r.get("name") or "").strip(),
                "subject_contains": subject,
                "sender_pattern": str(cfg.get("sender_pattern") or "").strip(),
                "parser_mode": str(cfg.get("parser_mode") or "").strip(),
                "parsing_method": str(cfg.get("parsing_method") or "").strip(),
                "rule_role": str(cfg.get("rule_role") or "standard").strip().lower(),
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
    rx_txt = (body.body_regex or "").strip()
    if not rx_txt:
        raise HTTPException(status_code=422, detail="body_regex_required")

    try:
        rx = re.compile(rx_txt, _to_regex_flags(body.flags or "i"))
    except re.error as e:
        raise HTTPException(status_code=422, detail=f"invalid_regex:{e}")

    with with_db_cursor() as (conn, cur):
        _ensure_trial_tables(cur)
        tid0 = int(tid or 0)
        cur.execute(
            """
            SELECT sample_id, body, received_at
            FROM email_parser_trial_samples
            WHERE tenant_id = %s
              AND user_email = %s
              AND sample_id = ANY(%s)
            """,
            (tid0, session_email, ids),
        )
        rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()

    by_id = {
        str(r.get("sample_id") or ""): {
            "body": str(r.get("body") or ""),
            "received_at": str(r.get("received_at") or ""),
        }
        for r in rows
    }
    fm = body.field_map or {}
    amount_g = int(fm.get("amount_group") or 0)
    merchant_g = int(fm.get("merchant_group") or 0)
    date_g = int(fm.get("date_group") or 0)
    time_g = int(fm.get("time_group") or 0)

    out: list[dict[str, Any]] = []
    for sid in ids:
        row = by_id.get(sid) or {}
        btxt = str(row.get("body") or "")
        received_at = str(row.get("received_at") or "")
        if not btxt:
            out.append({"sample_id": sid, "matched": False, "extracted": None, "error": "sample_not_found"})
            continue
        m = rx.search(btxt)
        if not m:
            out.append({"sample_id": sid, "matched": False, "extracted": None, "error": "No match"})
            continue
        time_val = _extract_group(m, time_g)
        if not time_val:
            time_val = _time_from_received_at(received_at)
        out.append(
            {
                "sample_id": sid,
                "matched": True,
                "extracted": {
                    "amount": _extract_group(m, amount_g),
                    "merchant": _extract_group(m, merchant_g) or "Unknown",
                    "date": _extract_group(m, date_g),
                    "time": time_val,
                },
            }
        )

    return {"ok": True, "rows": out, "matched": sum(1 for r in out if r.get("matched"))}


@router.post("/email-parser/trial/save")
def trial_save(body: TrialSaveBody, request: Request):
    tid = _require_tenant_id()
    session_email = _require_session_email(request)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name_required")

    draft_json = {
        "name": name,
        "parser_mode": (body.parser_mode or "").strip().lower(),
        "parsing_method": (body.parsing_method or "anchor").strip().lower(),
        "rule_role": (body.rule_role or "standard").strip().lower(),
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

        cur.execute(
            """
            SELECT sample_id, subject, sender, received_at, body
            FROM email_parser_trial_samples
            WHERE tenant_id = %s
              AND user_email = %s
              AND sample_id = ANY(%s)
            """,
            (tid0, session_email, ids),
        )
        sample_rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()

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
