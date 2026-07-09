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

from app.core import fitness_plan_engine as fpe
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
        # Training-plan goal types (RUN_DISTANCE/RUN_PACE/MAX_REPS/MAX_HOLD) reuse
        # target_reps/target_duration_seconds/target_date above and add the
        # fields those didn't cover: a distance target, a pace target, and the
        # baseline ability captured at the end of the testing week (see
        # fitness_plan_engine.py) that the progressive plan is generated from.
        cur.execute("ALTER TABLE fitness_goals ADD COLUMN IF NOT EXISTS target_distance_km DECIMAL(6,2)")
        cur.execute("ALTER TABLE fitness_goals ADD COLUMN IF NOT EXISTS target_pace_sec_per_mile INTEGER")
        cur.execute("ALTER TABLE fitness_goals ADD COLUMN IF NOT EXISTS baseline_value DECIMAL(8,2)")
        cur.execute("ALTER TABLE fitness_goals ADD COLUMN IF NOT EXISTS baseline_captured_at DATE")
        # Which Progression Paths variant (see FitnessCatalog.kt's
        # DEFAULT_PROGRESSION_PATHS / FitnessViewModel.kt's
        # currentProgressionStep()) the baseline test was actually performed
        # at — ties the plan's starting difficulty to the user's real
        # demonstrated progress instead of guessing from a raw rep count.
        cur.execute("ALTER TABLE fitness_goals ADD COLUMN IF NOT EXISTS baseline_exercise_id TEXT")
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

        # -------------------------------------------------------------------
        # Training plan: availability + generated schedule (see
        # app/core/fitness_plan_engine.py)
        # -------------------------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_availability_weekday (
                tenant_id INTEGER NOT NULL,
                weekday INTEGER NOT NULL,
                available BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (tenant_id, weekday)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_unavailable_dates (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                date DATE NOT NULL,
                reason TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, date)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_training_plan (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'TESTING',
                started_at TIMESTAMPTZ DEFAULT NOW(),
                last_regenerated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fitness_scheduled_workouts (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                scheduled_date DATE NOT NULL,
                goal_ids JSONB NOT NULL DEFAULT '[]',
                workout_type TEXT NOT NULL,
                prescription JSONB NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'PLANNED',
                linked_session_client_id TEXT,
                week_number INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fitness_scheduled_workouts_tenant_date
                ON fitness_scheduled_workouts(tenant_id, scheduled_date)
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
    target_distance_km: Optional[float] = None
    target_pace_sec_per_mile: Optional[int] = None


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
                target_reps, target_duration_seconds, target_date, notes,
                target_distance_km, target_pace_sec_per_mile
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                goal_type = EXCLUDED.goal_type,
                target_exercise_id = EXCLUDED.target_exercise_id,
                target_reps = EXCLUDED.target_reps,
                target_duration_seconds = EXCLUDED.target_duration_seconds,
                target_date = EXCLUDED.target_date,
                notes = EXCLUDED.notes,
                target_distance_km = EXCLUDED.target_distance_km,
                target_pace_sec_per_mile = EXCLUDED.target_pace_sec_per_mile
            RETURNING *
            """,
            (
                tid, body.client_id, body.title, body.goal_type, body.target_exercise_id,
                body.target_reps, body.target_duration_seconds, body.target_date, body.notes,
                body.target_distance_km, body.target_pace_sec_per_mile,
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
# Training plan (see app/core/fitness_plan_engine.py for the actual
# progression/reflow/adjustment algorithms — this section is just DB glue)
# ---------------------------------------------------------------------------

_PLAN_CLIENT_ID = "main"  # one active plan per tenant


class WeekdayAvailabilityIn(BaseModel):
    weekday: int
    available: bool


class UnavailableDateIn(BaseModel):
    date: date
    reason: Optional[str] = ""


class AvailabilityIn(BaseModel):
    weekdays: List[WeekdayAvailabilityIn] = []
    unavailable_dates: List[UnavailableDateIn] = []


class CompleteScheduledWorkoutIn(BaseModel):
    session_client_id: Optional[str] = None
    # Free-form logged performance, shape depends on prescription type — see
    # fitness_plan_engine.performance_delta(): best_set_reps, best_hold_seconds,
    # avg_pace_sec_per_mile.
    logged: dict = {}


def _load_availability(tid: int) -> fpe.Availability:
    weekday_rows = query_db(
        "SELECT weekday, available FROM fitness_availability_weekday WHERE tenant_id = %s", (tid,)
    )
    if weekday_rows:
        available_weekdays = {r["weekday"] for r in weekday_rows if r["available"]}
    else:
        available_weekdays = {0, 1, 2, 3, 4, 5, 6}  # no rows saved yet — default to every day open
    date_rows = query_db(
        "SELECT date FROM fitness_unavailable_dates WHERE tenant_id = %s", (tid,)
    )
    unavailable_dates = {r["date"] for r in date_rows}
    return fpe.Availability(available_weekdays=available_weekdays, unavailable_dates=unavailable_dates)


def _load_goals(tid: int, goal_types: tuple[str, ...]) -> list[fpe.Goal]:
    placeholders = ",".join(["%s"] * len(goal_types))
    rows = query_db(
        f"SELECT * FROM fitness_goals WHERE tenant_id = %s AND goal_type IN ({placeholders})",
        (tid, *goal_types),
    )
    return [
        fpe.Goal(
            id=r["id"],
            goal_type=r["goal_type"],
            target_exercise_id=r.get("target_exercise_id"),
            target_reps=r.get("target_reps"),
            target_duration_seconds=r.get("target_duration_seconds"),
            target_date=r.get("target_date"),
            target_distance_km=float(r["target_distance_km"]) if r.get("target_distance_km") is not None else None,
            target_pace_sec_per_mile=r.get("target_pace_sec_per_mile"),
            baseline_value=float(r["baseline_value"]) if r.get("baseline_value") is not None else None,
            baseline_exercise_id=r.get("baseline_exercise_id"),
        )
        for r in rows
    ]


_TRAINING_GOAL_TYPES = (fpe.GOAL_RUN_DISTANCE, fpe.GOAL_RUN_PACE, fpe.GOAL_MAX_REPS, fpe.GOAL_MAX_HOLD)


def _insert_scheduled_workouts(cur, tid: int, rows: list[dict]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO fitness_scheduled_workouts (
                tenant_id, client_id, scheduled_date, goal_ids, workout_type, prescription, status, week_number
            ) VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO NOTHING
            """,
            (
                tid, row["client_id"], row["scheduled_date"], json.dumps(row["goal_ids"]),
                row["workout_type"], json.dumps(row["prescription"]), row["status"], row["week_number"],
            ),
        )


@router.get("/fitness/availability")
def get_availability():
    ensure_fitness_tables()
    tid = current_tenant_id()
    avail = _load_availability(tid)
    date_rows = query_db(
        "SELECT date, reason FROM fitness_unavailable_dates WHERE tenant_id = %s ORDER BY date", (tid,)
    )
    return {
        "weekdays": [{"weekday": d, "available": d in avail.available_weekdays} for d in range(7)],
        "unavailable_dates": [_serialize(r) for r in date_rows],
    }


@router.post("/fitness/availability")
def set_availability(body: AvailabilityIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        for w in body.weekdays:
            cur.execute(
                """
                INSERT INTO fitness_availability_weekday (tenant_id, weekday, available)
                VALUES (%s,%s,%s)
                ON CONFLICT (tenant_id, weekday) DO UPDATE SET available = EXCLUDED.available
                """,
                (tid, w.weekday, w.available),
            )
        cur.execute("DELETE FROM fitness_unavailable_dates WHERE tenant_id = %s", (tid,))
        for d in body.unavailable_dates:
            cur.execute(
                "INSERT INTO fitness_unavailable_dates (tenant_id, date, reason) VALUES (%s,%s,%s)",
                (tid, d.date, d.reason),
            )
        conn.commit()

    # Reflow any already-scheduled future plan around the new availability.
    plan_rows = query_db(
        "SELECT * FROM fitness_training_plan WHERE tenant_id = %s AND client_id = %s", (tid, _PLAN_CLIENT_ID)
    )
    if plan_rows:
        avail = _load_availability(tid)
        scheduled = query_db(
            "SELECT * FROM fitness_scheduled_workouts WHERE tenant_id = %s", (tid,)
        )
        updates = fpe.reflow_plan(scheduled, avail, date.today())
        if updates:
            with with_db_cursor() as (conn, cur):
                for u in updates:
                    cur.execute(
                        "UPDATE fitness_scheduled_workouts SET scheduled_date = %s WHERE tenant_id = %s AND client_id = %s",
                        (u["scheduled_date"], tid, u["client_id"]),
                    )
                conn.commit()

    return get_availability()


@router.post("/fitness/plan/start-testing-week")
def start_testing_week():
    ensure_fitness_tables()
    tid = current_tenant_id()
    goals = _load_goals(tid, _TRAINING_GOAL_TYPES)
    if not goals:
        raise HTTPException(status_code=400, detail="No training goals set up yet")
    avail = _load_availability(tid)
    testing_rows = fpe.generate_testing_week(goals, avail, date.today())

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO fitness_training_plan (tenant_id, client_id, status)
            VALUES (%s,%s,'TESTING')
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET status = 'TESTING', last_regenerated_at = NOW()
            """,
            (tid, _PLAN_CLIENT_ID),
        )
        cur.execute("DELETE FROM fitness_scheduled_workouts WHERE tenant_id = %s", (tid,))
        _insert_scheduled_workouts(cur, tid, testing_rows)
        conn.commit()

    return {"status": "TESTING", "scheduled": len(testing_rows)}


def _extract_baseline(prescription_type: str, session_row: dict) -> tuple[Optional[float], Optional[str]]:
    """Pulls the relevant baseline number (and which exercise variant it was
    achieved on — see Goal.baseline_exercise_id) out of a logged test
    session, depending on which test it was. `exercises` is already the
    parsed list (see _serialize) by the time this runs."""
    field = "reps" if prescription_type == "pushup_test" else "durationSeconds" if prescription_type == "lsit_test" else None
    if field is None:
        return None, None
    best = 0
    best_exercise_id: Optional[str] = None
    for ex in session_row.get("exercises") or []:
        for s in ex.get("sets") or []:
            value = s.get(field) or 0
            if value > best:
                best = value
                best_exercise_id = ex.get("exerciseId")
    return (float(best) if best else None), best_exercise_id


@router.post("/fitness/plan/generate")
def generate_real_plan():
    ensure_fitness_tables()
    tid = current_tenant_id()
    goals = _load_goals(tid, _TRAINING_GOAL_TYPES)
    if not goals:
        raise HTTPException(status_code=400, detail="No training goals set up yet")

    test_rows = query_db(
        "SELECT * FROM fitness_scheduled_workouts WHERE tenant_id = %s AND workout_type = 'TEST' AND status = 'COMPLETED'",
        (tid,),
    )
    with with_db_cursor() as (conn, cur):
        for test_row in test_rows:
            test_row = _serialize(test_row)
            if not test_row.get("linked_session_client_id"):
                continue
            session_rows = query_db(
                "SELECT * FROM fitness_workout_sessions WHERE tenant_id = %s AND client_id = %s",
                (tid, test_row["linked_session_client_id"]),
            )
            if not session_rows:
                continue
            session_row = _serialize(session_rows[0])
            prescription_type = test_row["prescription"].get("type")
            goal_ids = test_row["goal_ids"] or []

            if prescription_type == "run_test":
                distance_km = session_row.get("distance_km")
                avg_pace_sec_per_km = session_row.get("avg_pace_sec_per_km")
                for gid in goal_ids:
                    goal = next((g for g in goals if g.id == gid), None)
                    if goal is None:
                        continue
                    if goal.goal_type == fpe.GOAL_RUN_DISTANCE and distance_km is not None:
                        cur.execute(
                            "UPDATE fitness_goals SET baseline_value = %s, baseline_captured_at = %s WHERE id = %s AND tenant_id = %s",
                            (float(distance_km), date.today(), gid, tid),
                        )
                        goal.baseline_value = float(distance_km)
                    if goal.goal_type == fpe.GOAL_RUN_PACE and avg_pace_sec_per_km is not None:
                        pace_per_mile = float(avg_pace_sec_per_km) * 1.60934
                        cur.execute(
                            "UPDATE fitness_goals SET baseline_value = %s, baseline_captured_at = %s WHERE id = %s AND tenant_id = %s",
                            (pace_per_mile, date.today(), gid, tid),
                        )
                        goal.baseline_value = pace_per_mile
            else:
                baseline, baseline_exercise_id = _extract_baseline(prescription_type, session_row)
                if baseline is not None:
                    for gid in goal_ids:
                        cur.execute(
                            """
                            UPDATE fitness_goals
                            SET baseline_value = %s, baseline_captured_at = %s, baseline_exercise_id = %s
                            WHERE id = %s AND tenant_id = %s
                            """,
                            (baseline, date.today(), baseline_exercise_id, gid, tid),
                        )
                        goal = next((g for g in goals if g.id == gid), None)
                        if goal is not None:
                            goal.baseline_value = baseline
                            goal.baseline_exercise_id = baseline_exercise_id
        conn.commit()

    plan_rows = _regenerate_future_plan(tid, goals)
    return {"status": "ACTIVE", "scheduled": len(plan_rows)}


def _regenerate_future_plan(tid: int, goals: list[fpe.Goal]) -> list[dict]:
    """Rebuilds all not-yet-completed (PLANNED) scheduled workouts from
    today's availability + each goal's current baseline_value. History
    (COMPLETED/SKIPPED rows) is untouched — this is what both the initial
    `generate` call and the adaptive nudge in complete_scheduled_workout()
    use to keep the forward plan current."""
    avail = _load_availability(tid)
    plan_rows = fpe.generate_plan(goals, avail, date.today())
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM fitness_scheduled_workouts WHERE tenant_id = %s AND status = 'PLANNED'", (tid,)
        )
        _insert_scheduled_workouts(cur, tid, plan_rows)
        cur.execute(
            """
            INSERT INTO fitness_training_plan (tenant_id, client_id, status)
            VALUES (%s,%s,'ACTIVE')
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET status = 'ACTIVE', last_regenerated_at = NOW()
            """,
            (tid, _PLAN_CLIENT_ID),
        )
        conn.commit()
    return plan_rows


@router.get("/fitness/plan/status")
def get_plan_status():
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_training_plan WHERE tenant_id = %s AND client_id = %s", (tid, _PLAN_CLIENT_ID)
    )
    if not rows:
        return {"status": "NONE"}
    return _serialize(rows[0])


@router.get("/fitness/plan/scheduled")
def list_scheduled_workouts(start: Optional[date] = None, end: Optional[date] = None):
    ensure_fitness_tables()
    tid = current_tenant_id()
    query = "SELECT * FROM fitness_scheduled_workouts WHERE tenant_id = %s"
    params: list[Any] = [tid]
    if start is not None:
        query += " AND scheduled_date >= %s"
        params.append(start)
    if end is not None:
        query += " AND scheduled_date <= %s"
        params.append(end)
    query += " ORDER BY scheduled_date"
    rows = query_db(query, tuple(params))
    return [_serialize(r) for r in rows]


@router.post("/fitness/plan/scheduled/{record_id}/complete")
def complete_scheduled_workout(record_id: int, body: CompleteScheduledWorkoutIn):
    ensure_fitness_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM fitness_scheduled_workouts WHERE id = %s AND tenant_id = %s", (record_id, tid)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Scheduled workout not found")
    row = _serialize(rows[0])

    with with_db_cursor() as (conn, cur):
        cur.execute(
            "UPDATE fitness_scheduled_workouts SET status = 'COMPLETED', linked_session_client_id = %s WHERE id = %s AND tenant_id = %s",
            (body.session_client_id, record_id, tid),
        )
        conn.commit()

    # Bounded adaptive nudge — only applies to real training sessions, not
    # baseline tests (those feed generate_plan() directly instead).
    baseline_changed = False
    if row["workout_type"] != "TEST" and body.logged:
        delta = fpe.performance_delta(row["prescription"], body.logged)
        if delta is not None:
            for gid in row["goal_ids"] or []:
                goal_rows = query_db("SELECT * FROM fitness_goals WHERE id = %s AND tenant_id = %s", (gid, tid))
                if not goal_rows:
                    continue
                goal_row = _serialize(goal_rows[0])
                if goal_row.get("baseline_value") is None:
                    continue
                goal = fpe.Goal(id=gid, goal_type=goal_row["goal_type"], baseline_value=float(goal_row["baseline_value"]))
                new_baseline = fpe.adjust_for_performance(goal, delta)
                if new_baseline is not None:
                    with with_db_cursor() as (conn, cur):
                        cur.execute(
                            "UPDATE fitness_goals SET baseline_value = %s WHERE id = %s AND tenant_id = %s",
                            (new_baseline, gid, tid),
                        )
                        conn.commit()
                    baseline_changed = True

    if baseline_changed:
        plan_status = query_db(
            "SELECT status FROM fitness_training_plan WHERE tenant_id = %s AND client_id = %s", (tid, _PLAN_CLIENT_ID)
        )
        if plan_status and plan_status[0]["status"] == "ACTIVE":
            goals = _load_goals(tid, _TRAINING_GOAL_TYPES)
            _regenerate_future_plan(tid, goals)

    return {"ok": True}


@router.post("/fitness/plan/scheduled/{record_id}/skip")
def skip_scheduled_workout(record_id: int):
    ensure_fitness_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "UPDATE fitness_scheduled_workouts SET status = 'SKIPPED' WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Scheduled workout not found")
        conn.commit()
    return {"ok": True}


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
        elif k in ("exercises", "muscle_groups", "instructions", "goal_ids", "prescription") and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = {} if k == "prescription" else []
        else:
            out[k] = v
    return out
