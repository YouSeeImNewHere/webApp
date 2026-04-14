from __future__ import annotations

import json
import threading
from typing import Any

from db import query_db, with_db_cursor

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def ensure_email_parse_events_table_pg() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with with_db_cursor() as (conn, cur):
            # Serialize first-time DDL across workers.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (8612401903,))
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS email_parse_events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    tenant_id BIGINT NULL,
                    user_email TEXT NULL,
                    run_source TEXT NOT NULL DEFAULT 'cron',
                    imap_id TEXT NULL,
                    sender TEXT NULL,
                    subject TEXT NULL,
                    received_at TEXT NULL,
                    matched BOOLEAN NOT NULL DEFAULT FALSE,
                    status TEXT NULL,
                    reason TEXT NULL,
                    inserted BOOLEAN NOT NULL DEFAULT FALSE,
                    notified BOOLEAN NOT NULL DEFAULT FALSE,
                    parser_draft_id BIGINT NULL,
                    parser_slot TEXT NULL,
                    account_id BIGINT NULL,
                    account_label TEXT NULL,
                    amount NUMERIC NULL,
                    merchant TEXT NULL,
                    context_json JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_parse_events_created_desc
                ON email_parse_events (created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_parse_events_tenant_created
                ON email_parse_events (tenant_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_parse_events_email_created
                ON email_parse_events ((lower(user_email)), created_at DESC)
                """
            )
            conn.commit()
        _SCHEMA_READY = True


def log_email_parse_event(
    *,
    tenant_id: int | None,
    user_email: str | None,
    run_source: str,
    imap_id: str | None,
    sender: str | None,
    subject: str | None,
    received_at: str | None,
    matched: bool,
    status: str | None,
    reason: str | None,
    inserted: bool,
    notified: bool,
    parser_draft_id: int | None = None,
    parser_slot: str | None = None,
    account_id: int | None = None,
    account_label: str | None = None,
    amount: float | int | None = None,
    merchant: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    ensure_email_parse_events_table_pg()
    ctx = context if isinstance(context, dict) else {}
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO email_parse_events (
                tenant_id, user_email, run_source, imap_id, sender, subject, received_at,
                matched, status, reason, inserted, notified,
                parser_draft_id, parser_slot, account_id, account_label, amount, merchant,
                context_json
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s::jsonb
            )
            """,
            (
                (int(tenant_id) if tenant_id is not None else None),
                (str(user_email or "").strip().lower() or None),
                (str(run_source or "").strip().lower() or "cron"),
                (str(imap_id or "").strip() or None),
                (str(sender or "").strip() or None),
                (str(subject or "").strip() or None),
                (str(received_at or "").strip() or None),
                bool(matched),
                (str(status or "").strip() or None),
                (str(reason or "").strip() or None),
                bool(inserted),
                bool(notified),
                (int(parser_draft_id) if parser_draft_id else None),
                (str(parser_slot or "").strip() or None),
                (int(account_id) if account_id else None),
                (str(account_label or "").strip() or None),
                amount,
                (str(merchant or "").strip() or None),
                json.dumps(ctx, ensure_ascii=False),
            ),
        )
        conn.commit()


def list_email_parse_events(
    *,
    limit: int = 200,
    tenant_id: int | None = None,
    user_email: str | None = None,
) -> list[dict[str, Any]]:
    ensure_email_parse_events_table_pg()
    n = max(1, min(int(limit or 200), 1000))
    params: list[Any] = []
    where: list[str] = []
    if tenant_id is not None:
        where.append("tenant_id = %s")
        params.append(int(tenant_id))
    email = str(user_email or "").strip().lower()
    if email:
        where.append("lower(user_email) = lower(%s)")
        params.append(email)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = query_db(
        f"""
        SELECT
          id, created_at, tenant_id, user_email, run_source,
          imap_id, sender, subject, received_at,
          matched, status, reason, inserted, notified,
          parser_draft_id, parser_slot, account_id, account_label,
          amount, merchant, context_json
        FROM email_parse_events
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT {n}
        """,
        tuple(params),
    )
    return [dict(r) for r in (rows or [])]


def clear_email_parse_events(*, tenant_id: int | None = None, user_email: str | None = None) -> int:
    ensure_email_parse_events_table_pg()
    params: list[Any] = []
    where: list[str] = []
    if tenant_id is not None:
        where.append("tenant_id = %s")
        params.append(int(tenant_id))
    email = str(user_email or "").strip().lower()
    if email:
        where.append("lower(user_email) = lower(%s)")
        params.append(email)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with with_db_cursor() as (conn, cur):
        cur.execute(f"DELETE FROM email_parse_events {where_sql}", tuple(params))
        deleted = int(cur.rowcount or 0)
        conn.commit()
    return deleted


def log_email_parse_server_line(
    *,
    message: str,
    tenant_id: int | None = None,
    user_email: str | None = None,
    run_source: str = "server",
    context: dict[str, Any] | None = None,
) -> None:
    log_email_parse_event(
        tenant_id=tenant_id,
        user_email=user_email,
        run_source=run_source,
        imap_id=None,
        sender=None,
        subject=None,
        received_at=None,
        matched=False,
        status="server_log",
        reason=str(message or "").strip()[:4000],
        inserted=False,
        notified=False,
        parser_draft_id=None,
        parser_slot=None,
        account_id=None,
        account_label=None,
        amount=None,
        merchant=None,
        context=(context or {}),
    )
