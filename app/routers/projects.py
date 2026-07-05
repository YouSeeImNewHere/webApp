from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.tenancy import current_tenant_id
from db import query_db, with_db_cursor

router = APIRouter()

_tables_ready = False


def ensure_projects_tables():
    global _tables_ready
    if _tables_ready:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'generic',
                description TEXT DEFAULT '',
                sections JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_quick_notes (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                title TEXT DEFAULT '',
                text TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_checklists (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                title TEXT NOT NULL,
                items JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        conn.commit()
    _tables_ready = True


class ProjectIn(BaseModel):
    client_id: str
    name: str
    type: str = "generic"
    description: Optional[str] = ""
    sections: List[dict] = []


class QuickNoteIn(BaseModel):
    client_id: str
    title: Optional[str] = ""
    text: str


class ChecklistIn(BaseModel):
    client_id: str
    title: str
    items: List[dict] = []


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects")
def list_projects():
    ensure_projects_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM projects WHERE tenant_id = %s ORDER BY updated_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/projects")
def upsert_project(body: ProjectIn):
    ensure_projects_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO projects (tenant_id, client_id, name, type, description, sections, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,NOW())
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                description = EXCLUDED.description,
                sections = EXCLUDED.sections,
                updated_at = NOW()
            RETURNING *
            """,
            (tid, body.client_id, body.name, body.type, body.description, json.dumps(body.sections)),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/projects/{record_id}")
def delete_project(record_id: int):
    ensure_projects_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM projects WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Quick notes
# ---------------------------------------------------------------------------

@router.get("/projects/quick-notes")
def list_quick_notes():
    ensure_projects_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM project_quick_notes WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/projects/quick-notes")
def upsert_quick_note(body: QuickNoteIn):
    ensure_projects_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO project_quick_notes (tenant_id, client_id, title, text)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                text = EXCLUDED.text
            RETURNING *
            """,
            (tid, body.client_id, body.title, body.text),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/projects/quick-notes/{record_id}")
def delete_quick_note(record_id: int):
    ensure_projects_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM project_quick_notes WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------

@router.get("/projects/checklists")
def list_checklists():
    ensure_projects_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM project_checklists WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/projects/checklists")
def upsert_checklist(body: ChecklistIn):
    ensure_projects_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO project_checklists (tenant_id, client_id, title, items)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                items = EXCLUDED.items
            RETURNING *
            """,
            (tid, body.client_id, body.title, json.dumps(body.items)),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/projects/checklists/{record_id}")
def delete_checklist(record_id: int):
    ensure_projects_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM project_checklists WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(row: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif k in ("sections", "items") and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        else:
            out[k] = v
    return out
