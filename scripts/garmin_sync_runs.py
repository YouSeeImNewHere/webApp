"""Pull recent running activities from Garmin Connect and merge them into
Quail Fitness's workout history.

Requires scripts/garmin_login_setup.py to have been run once already (this
script only loads the saved session tokens — it never prompts for a password
and never touches Garmin credentials directly).

Meant to run on a schedule (see deploy/systemd/quail-garmin-sync.timer).
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db

TOKENSTORE_PATH = os.getenv("GARMIN_TOKENSTORE_PATH") or str(Path.home() / ".garminconnect_tokens")
LOOKBACK_DAYS = 7  # re-pulls a rolling window; upsert is idempotent by client_id


def log(msg: str) -> None:
    print(f"[garmin_sync_runs] {msg}")


def upsert_run(cur, tenant_id: int, activity: dict) -> None:
    activity_id = activity.get("activityId")
    if not activity_id:
        return
    client_id = f"garmin:{activity_id}"

    start_local = str(activity.get("startTimeLocal") or "")
    run_date = start_local.split(" ")[0] if start_local else datetime.now().date().isoformat()

    duration_sec = float(activity.get("duration") or 0)
    distance_m = float(activity.get("distance") or 0)
    distance_km = round(distance_m / 1000.0, 2) if distance_m > 0 else None
    avg_pace_sec_per_km = int(duration_sec / (distance_m / 1000.0)) if distance_m > 0 and duration_sec > 0 else None
    avg_hr = activity.get("averageHR")
    calories = activity.get("calories")
    name = str(activity.get("activityName") or "Run").strip()

    cur.execute(
        """
        INSERT INTO fitness_workout_sessions (
            tenant_id, client_id, date, duration_minutes, notes, exercises,
            distance_km, avg_pace_sec_per_km, avg_heart_rate, calories, source
        ) VALUES (%s,%s,%s,%s,%s,'[]'::jsonb,%s,%s,%s,%s,'garmin')
        ON CONFLICT (tenant_id, client_id) DO UPDATE SET
            date = EXCLUDED.date,
            duration_minutes = EXCLUDED.duration_minutes,
            notes = EXCLUDED.notes,
            distance_km = EXCLUDED.distance_km,
            avg_pace_sec_per_km = EXCLUDED.avg_pace_sec_per_km,
            avg_heart_rate = EXCLUDED.avg_heart_rate,
            calories = EXCLUDED.calories
        """,
        (
            tenant_id, client_id, run_date, round(duration_sec / 60), name,
            distance_km, avg_pace_sec_per_km,
            round(avg_hr) if avg_hr else None,
            round(calories) if calories else None,
        ),
    )


def main() -> None:
    if not os.path.exists(TOKENSTORE_PATH):
        log(f"No Garmin session found at {TOKENSTORE_PATH} — run scripts/garmin_login_setup.py once first.")
        sys.exit(1)

    from garminconnect import Garmin
    from app.core.tenancy import get_owner_tenant_id
    from app.routers.fitness import ensure_fitness_tables

    garmin = Garmin()
    try:
        garmin.login(tokenstore=TOKENSTORE_PATH)
    except Exception as e:
        log(f"Garmin login failed: {e}")
        sys.exit(1)

    tenant_id = get_owner_tenant_id()
    if not tenant_id:
        log("No owner tenant configured; nothing to sync into.")
        return

    end = datetime.now().date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    activities = garmin.get_activities_by_date(start.isoformat(), end.isoformat(), "running")
    log(f"Found {len(activities)} running activities between {start} and {end}.")

    db.open_pool()
    try:
        ensure_fitness_tables()
        with db.with_db_cursor() as (conn, cur):
            for activity in activities:
                upsert_run(cur, int(tenant_id), activity)
            conn.commit()
    finally:
        db.close_pool()

    log(f"Synced {len(activities)} run(s).")


if __name__ == "__main__":
    main()
