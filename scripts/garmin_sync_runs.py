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


def sync_daily_health(garmin, cur, tenant_id: int, day) -> bool:
    """Pulls one day's stats/sleep/max-metrics and upserts whatever fields
    Garmin actually returns for that day. Individual calls are wrapped so one
    missing metric (e.g. no VO2 max reading that day) doesn't block the rest."""
    from app.routers.fitness import upsert_garmin_daily_health

    day_str = day.isoformat()
    fields: dict = {}

    try:
        stats = garmin.get_stats(day_str) or {}
        fields["resting_heart_rate"] = stats.get("restingHeartRate")
        fields["min_heart_rate"] = stats.get("minHeartRate")
        fields["max_heart_rate"] = stats.get("maxHeartRate")
        fields["total_steps"] = stats.get("totalSteps")
        fields["daily_step_goal"] = stats.get("dailyStepGoal")
        total_kcal = stats.get("totalKilocalories")
        active_kcal = stats.get("activeKilocalories")
        fields["total_calories"] = round(total_kcal) if total_kcal else None
        fields["active_calories"] = round(active_kcal) if active_kcal else None
        fields["average_stress_level"] = stats.get("averageStressLevel")
        fields["floors_ascended"] = stats.get("floorsAscended")
        fields["body_battery_highest"] = stats.get("bodyBatteryHighestValue")
        fields["body_battery_lowest"] = stats.get("bodyBatteryLowestValue")
    except Exception as e:
        log(f"get_stats failed for {day_str}: {e}")

    try:
        sleep = garmin.get_sleep_data(day_str) or {}
        dto = sleep.get("dailySleepDTO") or {}
        fields["sleep_deep_seconds"] = dto.get("deepSleepSeconds")
        fields["sleep_light_seconds"] = dto.get("lightSleepSeconds")
        fields["sleep_rem_seconds"] = dto.get("remSleepSeconds")
        fields["sleep_awake_seconds"] = dto.get("awakeSleepSeconds")
    except Exception as e:
        log(f"get_sleep_data failed for {day_str}: {e}")

    try:
        max_metrics = garmin.get_max_metrics(day_str)
        vo2 = None
        if isinstance(max_metrics, list) and max_metrics:
            generic = (max_metrics[0] or {}).get("generic") or {}
            vo2 = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
        elif isinstance(max_metrics, dict):
            generic = max_metrics.get("generic") or {}
            vo2 = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
        fields["vo2_max"] = vo2
    except Exception as e:
        log(f"get_max_metrics failed for {day_str}: {e}")

    if not any(v is not None for v in fields.values()):
        return False

    upsert_garmin_daily_health(cur, tenant_id, day_str, fields)
    return True


def main() -> None:
    if not os.path.exists(TOKENSTORE_PATH):
        log(f"No Garmin session found at {TOKENSTORE_PATH} — connect via Fitness Settings in the app first.")
        sys.exit(1)

    from garminconnect import Garmin

    garmin = Garmin()
    try:
        garmin.login(tokenstore=TOKENSTORE_PATH)
    except Exception as e:
        log(f"Garmin login failed: {e}")
        sys.exit(1)

    # The DB pool must be open before any code path touches the database —
    # get_owner_tenant_id() included. It used to run before open_pool(), which
    # crashed every time this ran outside app_postgres's own startup.
    db.open_pool()
    try:
        from app.core.tenancy import get_owner_tenant_id
        from app.routers.fitness import ensure_fitness_tables

        tenant_id = get_owner_tenant_id()
        if not tenant_id:
            log("No owner tenant configured; nothing to sync into.")
            return

        end = datetime.now().date()
        start = end - timedelta(days=LOOKBACK_DAYS)
        activities = garmin.get_activities_by_date(start.isoformat(), end.isoformat(), "running")
        log(f"Found {len(activities)} running activities between {start} and {end}.")

        ensure_fitness_tables()
        health_days_synced = 0
        with db.with_db_cursor() as (conn, cur):
            for activity in activities:
                upsert_run(cur, int(tenant_id), activity)
            conn.commit()

            for i in range(LOOKBACK_DAYS):
                day = end - timedelta(days=i)
                if sync_daily_health(garmin, cur, int(tenant_id), day):
                    health_days_synced += 1
            conn.commit()

        log(f"Synced {len(activities)} run(s), {health_days_synced} day(s) of health stats.")
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
