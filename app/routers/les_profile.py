from __future__ import annotations

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.settings import _ensure_les_profile_table_pg
from app.core.tenant_keys import scoped_key
from db import with_db_cursor, query_db
import json

router = APIRouter()

# =============================================================================
# LES Profile (les_profile)
# =============================================================================

@router.get("/les-profile")
def get_les_profile(key: str = "default"):
    _ensure_les_profile_table_pg()

    rows = query_db("SELECT profile_json FROM les_profile WHERE key = %s LIMIT 1", (scoped_key(key),))
    if not rows:
        return {"key": key, "profile": {}}

    try:
        profile = json.loads(rows[0]["profile_json"] or "{}")
    except Exception:
        profile = {}

    return {"key": key, "profile": profile}

class SaveLESProfileBody(BaseModel):
    key: str = "default"
    profile: Dict[str, Any]

@router.post("/les-profile")
def save_les_profile(body: SaveLESProfileBody):
    _ensure_les_profile_table_pg()

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO les_profile(key, profile_json, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key)
            DO UPDATE SET profile_json = EXCLUDED.profile_json,
                          updated_at = now()
            """,
            (scoped_key(body.key), json.dumps(body.profile)),
        )
        conn.commit()

    return {"key": body.key, "profile": body.profile}
