from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.tenancy import current_tenant_id
from db import query_db, with_db_cursor

router = APIRouter()

_tables_ready = False


def ensure_bugs_tables():
    global _tables_ready
    if _tables_ready:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bug_reports (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                route TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_bug_reports_tenant_status
                ON bug_reports(tenant_id, status)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bug_notes (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                text TEXT NOT NULL,
                is_resolved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        conn.commit()
    _tables_ready = True


class BugReportIn(BaseModel):
    client_id: str
    title: str
    description: Optional[str] = ""
    status: str = "open"
    route: Optional[str] = ""


class BugNoteIn(BaseModel):
    client_id: str
    text: str
    is_resolved: bool = False


@router.get("/bugs/reports")
def list_bug_reports():
    ensure_bugs_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM bug_reports WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/bugs/reports")
def upsert_bug_report(body: BugReportIn):
    ensure_bugs_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO bug_reports (tenant_id, client_id, title, description, status, route, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                route = EXCLUDED.route,
                updated_at = NOW()
            RETURNING *
            """,
            (tid, body.client_id, body.title, body.description, body.status, body.route),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/bugs/reports/{record_id}")
def delete_bug_report(record_id: int):
    ensure_bugs_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM bug_reports WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


@router.get("/bugs/notes")
def list_bug_notes():
    ensure_bugs_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM bug_notes WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/bugs/notes")
def upsert_bug_note(body: BugNoteIn):
    ensure_bugs_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO bug_notes (tenant_id, client_id, text, is_resolved)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                text = EXCLUDED.text,
                is_resolved = EXCLUDED.is_resolved
            RETURNING *
            """,
            (tid, body.client_id, body.text, body.is_resolved),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/bugs/notes/{record_id}")
def delete_bug_note(record_id: int):
    ensure_bugs_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM bug_notes WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


def _serialize(row: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out
