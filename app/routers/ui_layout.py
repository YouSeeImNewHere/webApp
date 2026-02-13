from __future__ import annotations

import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.settings import _ensure_ui_layout_table_pg, SaveLayoutBody
from db import with_db_cursor, query_db

router = APIRouter()

# =============================================================================
# UI Layout (ui_layout)
# =============================================================================

@router.get("/ui-layout")
def get_ui_layout(key: str):
    _ensure_ui_layout_table_pg()

    rows = query_db(
        "SELECT layout_json FROM ui_layout WHERE key = %s LIMIT 1",
        (key,),
    )
    if not rows:
        return {"key": key, "layout": {}}

    try:
        layout = json.loads(rows[0]["layout_json"] or "{}")
    except Exception:
        layout = {}

    return {"key": key, "layout": layout}

@router.post("/ui-layout")
def save_ui_layout(body: SaveLayoutBody):
    _ensure_ui_layout_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO ui_layout(key, layout_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET layout_json = EXCLUDED.layout_json,
                          updated_at = now()
            """,
            (body.key, json.dumps(body.layout)),
        )
        conn.commit()

    return {"key": body.key, "layout": body.layout}

