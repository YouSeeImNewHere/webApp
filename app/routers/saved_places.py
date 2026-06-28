from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.tenancy import current_tenant_id
from db import get_conn

router = APIRouter()


def ensure_saved_places_tables():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_place_lists (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    emoji TEXT DEFAULT '📍',
                    color TEXT DEFAULT '#5856D6',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_places (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    list_id INTEGER NOT NULL REFERENCES saved_place_lists(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    address TEXT DEFAULT '',
                    latitude DECIMAL(10,7),
                    longitude DECIMAL(10,7),
                    notes TEXT DEFAULT '',
                    saved_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()


class PlaceListIn(BaseModel):
    name: str
    emoji: Optional[str] = "📍"
    color: Optional[str] = "#5856D6"


class PlaceIn(BaseModel):
    list_id: int
    name: str
    address: Optional[str] = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = ""


@router.get("/saved-places/lists")
def get_lists():
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.id, l.name, l.emoji, l.color, l.created_at,
                       COUNT(p.id) AS place_count
                FROM saved_place_lists l
                LEFT JOIN saved_places p ON p.list_id = l.id AND p.tenant_id = l.tenant_id
                WHERE l.tenant_id = %s
                GROUP BY l.id
                ORDER BY l.created_at ASC
            """, (tid,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        v = r.get("created_at")
        if v and not isinstance(v, str):
            r["created_at"] = v.isoformat()
    return rows


@router.post("/saved-places/lists")
def create_list(body: PlaceListIn):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO saved_place_lists (tenant_id, name, emoji, color)
                VALUES (%s, %s, %s, %s) RETURNING id, name, emoji, color, created_at
            """, (tid, body.name, body.emoji, body.color))
            row = cur.fetchone()
        conn.commit()
    created = row["created_at"]
    return {"id": row["id"], "name": row["name"], "emoji": row["emoji"], "color": row["color"],
            "created_at": created if isinstance(created, str) else created.isoformat(),
            "place_count": 0}


@router.patch("/saved-places/lists/{list_id}")
def update_list(list_id: int, body: PlaceListIn):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE saved_place_lists SET name=%s, emoji=%s, color=%s, updated_at=NOW()
                WHERE id=%s AND tenant_id=%s
            """, (body.name, body.emoji, body.color, list_id, tid))
        conn.commit()
    return {"ok": True}


@router.delete("/saved-places/lists/{list_id}")
def delete_list(list_id: int):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM saved_place_lists WHERE id=%s AND tenant_id=%s", (list_id, tid))
        conn.commit()
    return {"ok": True}


@router.get("/saved-places/lists/{list_id}/places")
def get_places(list_id: int):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, address, latitude, longitude, notes, saved_at
                FROM saved_places WHERE list_id=%s AND tenant_id=%s ORDER BY saved_at DESC
            """, (list_id, tid))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        v = r.get("saved_at")
        if v and not isinstance(v, str):
            r["saved_at"] = v.isoformat()
        r["list_id"] = list_id
    return rows


@router.post("/saved-places/places")
def save_place(body: PlaceIn):
    tid = current_tenant_id()
    # Verify list belongs to tenant
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM saved_place_lists WHERE id=%s AND tenant_id=%s", (body.list_id, tid))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="List not found")
            cur.execute("""
                INSERT INTO saved_places (tenant_id, list_id, name, address, latitude, longitude, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, address, latitude, longitude, notes, saved_at
            """, (tid, body.list_id, body.name, body.address, body.latitude, body.longitude, body.notes))
            row = cur.fetchone()
        conn.commit()
    saved = row["saved_at"]
    return {
        "id": row["id"], "list_id": body.list_id, "name": row["name"], "address": row["address"],
        "latitude": float(row["latitude"]) if row["latitude"] else None,
        "longitude": float(row["longitude"]) if row["longitude"] else None,
        "notes": row["notes"],
        "saved_at": saved if isinstance(saved, str) else saved.isoformat()
    }


@router.delete("/saved-places/places/{place_id}")
def delete_place(place_id: int):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM saved_places WHERE id=%s AND tenant_id=%s", (place_id, tid))
        conn.commit()
    return {"ok": True}
