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


def ensure_fitness_tables():
    global _tables_ready
    if _tables_ready:
        return
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_workout_sessions (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                date DATE NOT NULL,
                duration_minutes INTEGER DEFAULT 0,
                bodyweight_kg DECIMAL(6,2),
                notes TEXT DEFAULT '',
                exercises JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fitness_sessions_tenant_date
                ON fitness_workout_sessions(tenant_id, date DESC)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_routines (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                name TEXT NOT NULL,
                exercises JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_goals (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                title TEXT NOT NULL,
                goal_type TEXT NOT NULL,
                target_exercise_id TEXT,
                target_reps INTEGER,
                target_duration_seconds INTEGER,
                target_date DATE,
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_milestones (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                title TEXT NOT NULL,
                date DATE NOT NULL,
                exercise_id TEXT,
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_bodyweight_logs (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                date DATE NOT NULL,
                weight_kg DECIMAL(6,2) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fitness_bodyweight_tenant_date
                ON fitness_bodyweight_logs(tenant_id, date DESC)
        """)
        conn.commit()
    _tables_ready = True


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class WorkoutSessionIn(BaseModel):
    client_id: str
    date: date
    duration_minutes: int = 0
    bodyweight_kg: Optional[float] = None
    notes: Optional[str] = ""
    exercises: List[dict] = []


class RoutineIn(BaseModel):
    client_id: str
    name: str
    exercises: List[dict] = []


class GoalIn(BaseModel):
    client_id: str
    title: str
    goal_type: str
    target_exercise_id: Optional[str] = None
    target_reps: Optional[int] = None
    target_duration_seconds: Optional[int] = None
    target_date: Optional[date] = None
    notes: Optional[str] = ""


class MilestoneIn(BaseModel):
    client_id: str
    title: str
    date: date
    exercise_id: Optional[str] = None
    notes: Optional[str] = ""


class BodyweightIn(BaseModel):
    client_id: str
    date: date
    weight_kg: float


# ---------------------------------------------------------------------------
# Workout sessions
# ---------------------------------------------------------------------------

@router.get("/fitness/sessions")
def list_sessions(limit: int = 200, offset: int = 0):
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        """
        SELECT * FROM fitness_workout_sessions
        WHERE tenant_id = %s
        ORDER BY date DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (tid, limit, offset),
    )
    total = query_db("SELECT COUNT(*) AS n FROM fitness_workout_sessions WHERE tenant_id = %s", (tid,))
    return {"records": [_serialize(r) for r in rows], "total": total[0]["n"]}


@router.post("/fitness/sessions")
def upsert_session(body: WorkoutSessionIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_workout_sessions (
                tenant_id, client_id, date, duration_minutes, bodyweight_kg, notes, exercises
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                date = EXCLUDED.date,
                duration_minutes = EXCLUDED.duration_minutes,
                bodyweight_kg = EXCLUDED.bodyweight_kg,
                notes = EXCLUDED.notes,
                exercises = EXCLUDED.exercises
            RETURNING *
            """,
            (
                tid, body.client_id, body.date, body.duration_minutes, body.bodyweight_kg,
                body.notes, json.dumps(body.exercises),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/fitness/sessions/{record_id}")
def delete_session(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_workout_sessions WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------

@router.get("/fitness/routines")
def list_routines():
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_routines WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/fitness/routines")
def upsert_routine(body: RoutineIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_routines (tenant_id, client_id, name, exercises)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                name = EXCLUDED.name,
                exercises = EXCLUDED.exercises
            RETURNING *
            """,
            (tid, body.client_id, body.name, json.dumps(body.exercises)),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/fitness/routines/{record_id}")
def delete_routine(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_routines WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

@router.get("/fitness/goals")
def list_goals():
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_goals WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/fitness/goals")
def upsert_goal(body: GoalIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_goals (
                tenant_id, client_id, title, goal_type, target_exercise_id,
                target_reps, target_duration_seconds, target_date, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                goal_type = EXCLUDED.goal_type,
                target_exercise_id = EXCLUDED.target_exercise_id,
                target_reps = EXCLUDED.target_reps,
                target_duration_seconds = EXCLUDED.target_duration_seconds,
                target_date = EXCLUDED.target_date,
                notes = EXCLUDED.notes
            RETURNING *
            """,
            (
                tid, body.client_id, body.title, body.goal_type, body.target_exercise_id,
                body.target_reps, body.target_duration_seconds, body.target_date, body.notes,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/fitness/goals/{record_id}")
def delete_goal(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_goals WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

@router.get("/fitness/milestones")
def list_milestones():
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_milestones WHERE tenant_id = %s ORDER BY date DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/fitness/milestones")
def upsert_milestone(body: MilestoneIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_milestones (tenant_id, client_id, title, date, exercise_id, notes)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                date = EXCLUDED.date,
                exercise_id = EXCLUDED.exercise_id,
                notes = EXCLUDED.notes
            RETURNING *
            """,
            (tid, body.client_id, body.title, body.date, body.exercise_id, body.notes),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/fitness/milestones/{record_id}")
def delete_milestone(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_milestones WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Bodyweight logs
# ---------------------------------------------------------------------------

@router.get("/fitness/bodyweight")
def list_bodyweight(limit: int = 200):
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        """
        SELECT * FROM fitness_bodyweight_logs
        WHERE tenant_id = %s
        ORDER BY date DESC
        LIMIT %s
        """,
        (tid, limit),
    )
    return [_serialize(r) for r in rows]


@router.post("/fitness/bodyweight")
def upsert_bodyweight(body: BodyweightIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_bodyweight_logs (tenant_id, client_id, date, weight_kg)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                date = EXCLUDED.date,
                weight_kg = EXCLUDED.weight_kg
            RETURNING *
            """,
            (tid, body.client_id, body.date, body.weight_kg),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/fitness/bodyweight/{record_id}")
def delete_bodyweight(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_bodyweight_logs WHERE id = %s AND tenant_id = %s",
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
        elif k in ("exercises",) and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        else:
            out[k] = v
    return out
