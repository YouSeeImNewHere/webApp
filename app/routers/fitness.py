from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.tenancy import current_tenant_id
from db import query_db, with_db_cursor

router = APIRouter()

_tables_ready = False

# ---------------------------------------------------------------------------
# Garmin connect (in-app login — replaces the SSH-only setup script)
# ---------------------------------------------------------------------------

GARMIN_TOKENSTORE_PATH = os.getenv("GARMIN_TOKENSTORE_PATH") or str(Path.home() / ".garminconnect_tokens")
_GARMIN_MFA_TTL_SECONDS = 600
# Garmin's MFA resume needs the *same* in-memory client object that started the
# login (its session/cookies aren't serializable), so we hold it here between
# the "connect" and "submit MFA code" requests rather than returning it to the
# client. Fine for a single-user personal deployment; not something to scale
# to concurrent multi-tenant logins without a real per-session store.
_pending_garmin_logins: dict[str, tuple[Any, Any, float]] = {}


def _prune_expired_garmin_logins() -> None:
    now = time.time()
    expired = [k for k, (_, _, ts) in _pending_garmin_logins.items() if now - ts > _GARMIN_MFA_TTL_SECONDS]
    for k in expired:
        _pending_garmin_logins.pop(k, None)


class GarminConnectIn(BaseModel):
    email: str
    password: str


class GarminMfaIn(BaseModel):
    session_id: str
    mfa_code: str


@router.get("/fitness/garmin/status")
def garmin_status():
    return {"connected": os.path.exists(GARMIN_TOKENSTORE_PATH)}


@router.post("/fitness/garmin/connect")
def garmin_connect(body: GarminConnectIn):
    _prune_expired_garmin_logins()
    try:
        from garminconnect import Garmin
    except ImportError:
        raise HTTPException(status_code=500, detail="garminconnect_not_installed")

    garmin = Garmin(email=body.email, password=body.password, return_on_mfa=True)
    try:
        result1, result2 = garmin.login(tokenstore=GARMIN_TOKENSTORE_PATH)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"garmin_login_failed: {e}")

    if result1 == "needs_mfa":
        session_id = str(uuid.uuid4())
        _pending_garmin_logins[session_id] = (garmin, result2, time.time())
        return {"needs_mfa": True, "session_id": session_id}

    # login(return_on_mfa=True) never dumps tokens itself on a clean, no-MFA
    # success — that auto-save only happens in the non-return_on_mfa branch —
    # so we have to persist them ourselves here.
    garmin.client.dump(GARMIN_TOKENSTORE_PATH)
    return {"needs_mfa": False, "connected": True}


@router.post("/fitness/garmin/mfa")
def garmin_mfa(body: GarminMfaIn):
    _prune_expired_garmin_logins()
    pending = _pending_garmin_logins.pop(body.session_id, None)
    if not pending:
        raise HTTPException(status_code=400, detail="session_expired_or_unknown")
    garmin, client_state, _ = pending
    try:
        garmin.resume_login(client_state, body.mfa_code)
        garmin.client.dump(GARMIN_TOKENSTORE_PATH)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"garmin_mfa_failed: {e}")
    return {"connected": True}


@router.delete("/fitness/garmin/connect")
def garmin_disconnect():
    if os.path.exists(GARMIN_TOKENSTORE_PATH):
        os.remove(GARMIN_TOKENSTORE_PATH)
    return {"connected": False}


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
        # Cardio fields for Garmin-synced runs — a run has no sets/reps, so it's
        # kept in the same table as top-level session fields rather than in the
        # `exercises` JSONB list. `source` distinguishes manual entries from
        # Garmin imports; Garmin rows reuse the existing client_id unique
        # constraint (client_id = "garmin:<activity_id>") for idempotent upsert.
        cur.execute("ALTER TABLE fitness_workout_sessions ADD COLUMN IF NOT EXISTS distance_km DECIMAL(6,2)")
        cur.execute("ALTER TABLE fitness_workout_sessions ADD COLUMN IF NOT EXISTS avg_pace_sec_per_km INTEGER")
        cur.execute("ALTER TABLE fitness_workout_sessions ADD COLUMN IF NOT EXISTS avg_heart_rate INTEGER")
        cur.execute("ALTER TABLE fitness_workout_sessions ADD COLUMN IF NOT EXISTS calories INTEGER")
        cur.execute("ALTER TABLE fitness_workout_sessions ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'")
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_custom_exercises (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                muscle_groups JSONB NOT NULL DEFAULT '[]',
                difficulty TEXT NOT NULL DEFAULT 'BEGINNER',
                instructions JSONB NOT NULL DEFAULT '[]',
                video_url TEXT,
                is_timed_exercise BOOLEAN DEFAULT FALSE,
                default_sets INTEGER DEFAULT 3,
                default_reps INTEGER DEFAULT 10,
                default_duration_seconds INTEGER DEFAULT 30,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_garmin_daily_health (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                date DATE NOT NULL,
                resting_heart_rate INTEGER,
                min_heart_rate INTEGER,
                max_heart_rate INTEGER,
                total_steps INTEGER,
                daily_step_goal INTEGER,
                total_calories INTEGER,
                active_calories INTEGER,
                vo2_max DECIMAL(5,2),
                sleep_deep_seconds INTEGER,
                sleep_light_seconds INTEGER,
                sleep_rem_seconds INTEGER,
                sleep_awake_seconds INTEGER,
                body_battery_highest INTEGER,
                body_battery_lowest INTEGER,
                average_stress_level INTEGER,
                floors_ascended DECIMAL(6,2),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, date)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fitness_garmin_daily_health_tenant_date
                ON fitness_garmin_daily_health(tenant_id, date DESC)
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
    distance_km: Optional[float] = None
    avg_pace_sec_per_km: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    calories: Optional[int] = None
    source: str = "manual"


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


class CustomExerciseIn(BaseModel):
    client_id: str
    name: str
    category: str
    muscle_groups: List[str] = []
    difficulty: str = "BEGINNER"
    instructions: List[str] = []
    video_url: Optional[str] = None
    is_timed_exercise: bool = False
    default_sets: int = 3
    default_reps: int = 10
    default_duration_seconds: int = 30


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
                tenant_id, client_id, date, duration_minutes, bodyweight_kg, notes, exercises,
                distance_km, avg_pace_sec_per_km, avg_heart_rate, calories, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                date = EXCLUDED.date,
                duration_minutes = EXCLUDED.duration_minutes,
                bodyweight_kg = EXCLUDED.bodyweight_kg,
                notes = EXCLUDED.notes,
                exercises = EXCLUDED.exercises,
                distance_km = EXCLUDED.distance_km,
                avg_pace_sec_per_km = EXCLUDED.avg_pace_sec_per_km,
                avg_heart_rate = EXCLUDED.avg_heart_rate,
                calories = EXCLUDED.calories,
                source = EXCLUDED.source
            RETURNING *
            """,
            (
                tid, body.client_id, body.date, body.duration_minutes, body.bodyweight_kg,
                body.notes, json.dumps(body.exercises),
                body.distance_km, body.avg_pace_sec_per_km, body.avg_heart_rate, body.calories, body.source,
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
# Custom exercises (user-created, on top of the built-in static catalog)
# ---------------------------------------------------------------------------

@router.get("/fitness/custom-exercises")
def list_custom_exercises():
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_custom_exercises WHERE tenant_id = %s ORDER BY name",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/fitness/custom-exercises")
def upsert_custom_exercise(body: CustomExerciseIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_custom_exercises (
                tenant_id, client_id, name, category, muscle_groups, difficulty, instructions,
                video_url, is_timed_exercise, default_sets, default_reps, default_duration_seconds
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                muscle_groups = EXCLUDED.muscle_groups,
                difficulty = EXCLUDED.difficulty,
                instructions = EXCLUDED.instructions,
                video_url = EXCLUDED.video_url,
                is_timed_exercise = EXCLUDED.is_timed_exercise,
                default_sets = EXCLUDED.default_sets,
                default_reps = EXCLUDED.default_reps,
                default_duration_seconds = EXCLUDED.default_duration_seconds
            RETURNING *
            """,
            (
                tid, body.client_id, body.name, body.category, json.dumps(body.muscle_groups),
                body.difficulty, json.dumps(body.instructions), body.video_url,
                body.is_timed_exercise, body.default_sets, body.default_reps, body.default_duration_seconds,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/fitness/custom-exercises/{record_id}")
def delete_custom_exercise(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_custom_exercises WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Garmin daily health (steps, resting HR, sleep, calories, VO2 max, ...)
# ---------------------------------------------------------------------------

@router.get("/fitness/garmin/daily-health")
def list_garmin_daily_health(days: int = 14):
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_garmin_daily_health WHERE tenant_id = %s ORDER BY date DESC LIMIT %s",
        (tid, days),
    )
    return [_serialize(r) for r in rows]


def upsert_garmin_daily_health(cur, tenant_id: int, day: str, fields: dict) -> None:
    """Called from scripts/garmin_sync_runs.py — tables must already exist
    (ensure_fitness_tables() is called once at the top of that script)."""
    cur.execute(
        """
        INSERT INTO fitness_garmin_daily_health (
            tenant_id, date, resting_heart_rate, min_heart_rate, max_heart_rate,
            total_steps, daily_step_goal, total_calories, active_calories, vo2_max,
            sleep_deep_seconds, sleep_light_seconds, sleep_rem_seconds, sleep_awake_seconds,
            body_battery_highest, body_battery_lowest, average_stress_level, floors_ascended
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id, date) DO UPDATE SET
            resting_heart_rate = COALESCE(EXCLUDED.resting_heart_rate, fitness_garmin_daily_health.resting_heart_rate),
            min_heart_rate = COALESCE(EXCLUDED.min_heart_rate, fitness_garmin_daily_health.min_heart_rate),
            max_heart_rate = COALESCE(EXCLUDED.max_heart_rate, fitness_garmin_daily_health.max_heart_rate),
            total_steps = COALESCE(EXCLUDED.total_steps, fitness_garmin_daily_health.total_steps),
            daily_step_goal = COALESCE(EXCLUDED.daily_step_goal, fitness_garmin_daily_health.daily_step_goal),
            total_calories = COALESCE(EXCLUDED.total_calories, fitness_garmin_daily_health.total_calories),
            active_calories = COALESCE(EXCLUDED.active_calories, fitness_garmin_daily_health.active_calories),
            vo2_max = COALESCE(EXCLUDED.vo2_max, fitness_garmin_daily_health.vo2_max),
            sleep_deep_seconds = COALESCE(EXCLUDED.sleep_deep_seconds, fitness_garmin_daily_health.sleep_deep_seconds),
            sleep_light_seconds = COALESCE(EXCLUDED.sleep_light_seconds, fitness_garmin_daily_health.sleep_light_seconds),
            sleep_rem_seconds = COALESCE(EXCLUDED.sleep_rem_seconds, fitness_garmin_daily_health.sleep_rem_seconds),
            sleep_awake_seconds = COALESCE(EXCLUDED.sleep_awake_seconds, fitness_garmin_daily_health.sleep_awake_seconds),
            body_battery_highest = COALESCE(EXCLUDED.body_battery_highest, fitness_garmin_daily_health.body_battery_highest),
            body_battery_lowest = COALESCE(EXCLUDED.body_battery_lowest, fitness_garmin_daily_health.body_battery_lowest),
            average_stress_level = COALESCE(EXCLUDED.average_stress_level, fitness_garmin_daily_health.average_stress_level),
            floors_ascended = COALESCE(EXCLUDED.floors_ascended, fitness_garmin_daily_health.floors_ascended)
        """,
        (
            tenant_id, day,
            fields.get("resting_heart_rate"), fields.get("min_heart_rate"), fields.get("max_heart_rate"),
            fields.get("total_steps"), fields.get("daily_step_goal"),
            fields.get("total_calories"), fields.get("active_calories"), fields.get("vo2_max"),
            fields.get("sleep_deep_seconds"), fields.get("sleep_light_seconds"),
            fields.get("sleep_rem_seconds"), fields.get("sleep_awake_seconds"),
            fields.get("body_battery_highest"), fields.get("body_battery_lowest"),
            fields.get("average_stress_level"), fields.get("floors_ascended"),
        ),
    )


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
        elif k in ("exercises", "muscle_groups", "instructions") and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        else:
            out[k] = v
    return out
