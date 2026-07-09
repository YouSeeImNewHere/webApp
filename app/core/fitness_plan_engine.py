from __future__ import annotations

"""Goal-driven training plan generator for Quail Fitness.

Pure, deterministic functions — no ML, no network calls, no DB access. Given
goals + baselines + availability, these compute a week-by-week schedule of
`fitness_scheduled_workouts` rows (as plain dicts, ready for the caller to
persist). Kept separate from app/routers/fitness.py so the progression rules
can be read and unit-tested on their own.

Exercise ids referenced here ("pushup", "wall_pushup", "tuck_lsit", "lsit",
"running", ...) must match QuailAndroid's FitnessCatalog.kt catalog — the
backend has no exercise catalog of its own, it just stores/returns whatever
id the client uses.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import zip_longest
from typing import Optional

# ---------------------------------------------------------------------------
# Goal types
# ---------------------------------------------------------------------------

GOAL_RUN_DISTANCE = "RUN_DISTANCE"
GOAL_RUN_PACE = "RUN_PACE"
GOAL_MAX_REPS = "MAX_REPS"
GOAL_MAX_HOLD = "MAX_HOLD"

WORKOUT_RUN_EASY = "RUN_EASY"
WORKOUT_RUN_TEMPO = "RUN_TEMPO"
WORKOUT_RUN_LONG = "RUN_LONG"
WORKOUT_RUN_INTERVAL = "RUN_INTERVAL"
WORKOUT_PUSHUP_SESSION = "PUSHUP_SESSION"
WORKOUT_LSIT_SESSION = "LSIT_SESSION"
WORKOUT_TEST = "TEST"
WORKOUT_REST = "REST"

PUSHUP_PROGRESSION = ["wall_pushup", "incline_pushup", "pushup", "archer_pushup", "one_arm_pushup"]
LSIT_PROGRESSION = ["tuck_lsit", "lsit"]

# Bounded adaptive-adjustment tuning — see adjust_for_performance().
_BEAT_MARGIN = 0.15  # >15% over prescription bumps next week up a tier
_MISS_MARGIN = 0.20  # >20% under prescription, twice in a row, holds/eases back


@dataclass
class Goal:
    id: int
    goal_type: str
    target_exercise_id: Optional[str] = None
    target_reps: Optional[int] = None
    target_duration_seconds: Optional[int] = None
    target_date: Optional[date] = None
    target_distance_km: Optional[float] = None
    target_pace_sec_per_mile: Optional[int] = None
    baseline_value: Optional[float] = None
    # Which PUSHUP_PROGRESSION/LSIT_PROGRESSION variant the baseline test was
    # actually performed at (e.g. "archer_pushup") — captured from the user's
    # real Progression Paths standing (see FitnessViewModel.kt's
    # currentProgressionStep()) rather than assumed from a raw rep count.
    # Without this, a strong user testing on a harder variant would produce a
    # low rep number that the old threshold-based guess misread as a
    # beginner, regressing them to an easier variant they'd already mastered.
    baseline_exercise_id: Optional[str] = None


@dataclass
class Availability:
    # weekday: 0=Monday .. 6=Sunday, mirrors Python's date.weekday()
    available_weekdays: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4, 5, 6})
    unavailable_dates: set[date] = field(default_factory=set)

    def is_available(self, d: date) -> bool:
        return d not in self.unavailable_dates and d.weekday() in self.available_weekdays


def _client_id() -> str:
    return f"plan:{uuid.uuid4().hex}"


def _available_days(availability: Availability, start: date, count_days: int) -> list[date]:
    days = []
    d = start
    while len(days) < count_days:
        if availability.is_available(d):
            days.append(d)
        d += timedelta(days=1)
        if (d - start).days > count_days * 4 + 14:
            break  # safety valve against pathological all-unavailable input
    return days


def _week_dates(availability: Availability, start: date) -> list[date]:
    """Every day (available or not) in the 7 days starting at `start`, used
    when we need to reason about a whole week's available slots at once."""
    return [start + timedelta(days=i) for i in range(7)]


# ---------------------------------------------------------------------------
# Testing week
# ---------------------------------------------------------------------------

def generate_testing_week(goals: list[Goal], availability: Availability, start_date: date) -> list[dict]:
    """One baseline test per relevant goal type, spread across the coming
    week's available days. Only tests for goal types the user actually has
    active goals for."""
    goal_types = {g.goal_type for g in goals}
    tests: list[tuple[str, dict, list[int]]] = []  # (workout_type, prescription, goal ids)

    def goal_ids_for(*types: str) -> list[int]:
        return [g.id for g in goals if g.goal_type in types]

    if GOAL_MAX_REPS in goal_types:
        tests.append((
            WORKOUT_TEST,
            {"type": "pushup_test", "instructions": "Max reps in one set (AMRAP), good form, to failure."},
            goal_ids_for(GOAL_MAX_REPS),
        ))
    if GOAL_MAX_HOLD in goal_types:
        tests.append((
            WORKOUT_TEST,
            {"type": "lsit_test", "instructions": "Hold the toughest L-sit variant you can for max time."},
            goal_ids_for(GOAL_MAX_HOLD),
        ))
    if GOAL_RUN_PACE in goal_types or GOAL_RUN_DISTANCE in goal_types:
        tests.append((
            WORKOUT_TEST,
            {
                "type": "run_test",
                "instructions": "Run 1 mile as fast as you can hold pace, then keep going easy as far as comfortable.",
            },
            goal_ids_for(GOAL_RUN_PACE, GOAL_RUN_DISTANCE),
        ))

    slots = _available_days(availability, start_date, len(tests)) if tests else []
    scheduled = []
    for i, (workout_type, prescription, goal_ids) in enumerate(tests):
        scheduled.append({
            "client_id": _client_id(),
            "scheduled_date": slots[i] if i < len(slots) else start_date + timedelta(days=i),
            "goal_ids": goal_ids,
            "workout_type": workout_type,
            "prescription": prescription,
            "status": "PLANNED",
            "week_number": 0,
        })
    return scheduled


# ---------------------------------------------------------------------------
# Progressive plan generation
# ---------------------------------------------------------------------------

def _horizon_weeks(goals: list[Goal], start_date: date) -> int:
    dated = [g.target_date for g in goals if g.target_date]
    if not dated:
        return 8  # no deadline given anywhere — default to a solid 8-week block
    weeks = max((max(dated) - start_date).days // 7, 1)
    return min(weeks, 52)  # cap at a year; re-generation keeps it fresh anyway


def _run_distance_week_plan(goal: Goal, week_index: int) -> Optional[dict]:
    baseline = goal.baseline_value or 1.0
    target = goal.target_distance_km or baseline
    # ~10%/week toward target, with a deload (~20% cut) every 4th week.
    grown = baseline * (1.10 ** week_index)
    distance = min(grown, target)
    if (week_index + 1) % 4 == 0:
        distance *= 0.8
    return {
        "workout_type": WORKOUT_RUN_LONG,
        "prescription": {"type": "run", "distance_km": round(distance, 1), "notes": "Long run, easy conversational pace"},
    }


def _run_pace_week_plans(goal: Goal, week_index: int, total_weeks: int) -> list[dict]:
    baseline_pace = goal.baseline_value or 600.0  # sec/mile
    target_pace = goal.target_pace_sec_per_mile or baseline_pace
    progress = min((week_index + 1) / max(total_weeks, 1), 1.0)
    tempo_pace = baseline_pace + (target_pace - baseline_pace) * progress
    interval_pace = target_pace * 0.95  # intervals run a bit faster than goal pace
    reps = min(4 + week_index // 2, 10)
    return [
        {
            "workout_type": WORKOUT_RUN_INTERVAL,
            "prescription": {
                "type": "intervals", "reps": reps, "distance_km": 0.4,
                "target_pace_sec_per_mile": round(interval_pace),
                "rest_seconds": 90, "notes": f"{reps}x400m at goal pace, jog recovery",
            },
        },
        {
            "workout_type": WORKOUT_RUN_TEMPO,
            "prescription": {
                "type": "run", "distance_km": 3.0,
                "target_pace_sec_per_mile": round(tempo_pace),
                "notes": "Comfortably-hard tempo pace",
            },
        },
        {
            "workout_type": WORKOUT_RUN_EASY,
            "prescription": {"type": "run", "distance_km": 3.0, "notes": "Easy aerobic recovery run"},
        },
    ]


# Estimated-max thresholds (in standard full push-up equivalents) for
# unlocking each step of PUSHUP_PROGRESSION. A beginner testing under 5 reps
# starts at the easiest variant; the hardest variant only unlocks once
# estimated_max is well past the 100-rep goal's own midpoint.
_PUSHUP_VARIANT_THRESHOLDS = [
    (0, "wall_pushup"),
    (5, "incline_pushup"),
    (10, "pushup"),
    (40, "archer_pushup"),
    (70, "one_arm_pushup"),
]


def _pushup_variant_for(estimated_max: float, baseline_exercise_id: Optional[str], week_index: int) -> str:
    """Starts from the user's real current Progression Paths standing
    (baseline_exercise_id, captured from their actual session history at
    testing-week time — see FitnessViewModel.kt's currentProgressionStep())
    when known, advancing one step every 4 weeks. Falls back to the
    threshold guess only when no such standing was captured (e.g. an older
    goal predating this). Re-deriving a variant from a raw rep count alone
    would misread a low rep count on a hard variant (e.g. 8 archer push-ups)
    as beginner-level and regress the user to an easier one they'd already
    mastered."""
    if baseline_exercise_id in PUSHUP_PROGRESSION:
        start_index = PUSHUP_PROGRESSION.index(baseline_exercise_id)
        steps_advanced = week_index // 4
        return PUSHUP_PROGRESSION[min(start_index + steps_advanced, len(PUSHUP_PROGRESSION) - 1)]
    variant = _PUSHUP_VARIANT_THRESHOLDS[0][1]
    for threshold, step in _PUSHUP_VARIANT_THRESHOLDS:
        if estimated_max >= threshold:
            variant = step
    return variant


def _pushup_week_plan(goal: Goal, week_index: int) -> list[dict]:
    baseline_max = goal.baseline_value or 10.0
    estimated_max = baseline_max * (1.12 ** week_index)
    is_retest_week = week_index > 0 and week_index % 2 == 0
    if is_retest_week:
        return [{
            "workout_type": WORKOUT_TEST,
            "prescription": {"type": "pushup_test", "instructions": "AMRAP retest to recalibrate your working max."},
        }]
    pct_tiers = [0.6, 0.5, 0.4, 0.4, 0.3]
    sets = [{"reps": max(1, round(estimated_max * pct))} for pct in pct_tiers]
    variant = _pushup_variant_for(estimated_max, goal.baseline_exercise_id, week_index)
    return [{
        "workout_type": WORKOUT_PUSHUP_SESSION,
        "prescription": {"type": "pushups", "exercise_id": variant, "sets": sets, "rest_seconds": 90},
    }] * 3


def _lsit_week_plan(goal: Goal, week_index: int) -> list[dict]:
    baseline_hold = goal.baseline_value or 5.0
    target_hold = goal.target_duration_seconds or 60
    hold = min(baseline_hold * (1.10 ** week_index), target_hold)
    # Never regress below the variant the user actually tested at (see
    # Goal.baseline_exercise_id) — only the hold-time threshold can advance
    # it from there.
    variant = "lsit" if (goal.baseline_exercise_id == "lsit" or hold >= 15) else "tuck_lsit"
    sets = [{"hold_seconds": round(hold * 0.75)} for _ in range(5)]
    return [{
        "workout_type": WORKOUT_LSIT_SESSION,
        "prescription": {"type": "lsit_hold", "exercise_id": variant, "sets": sets, "rest_seconds": 60},
    }] * 3


def generate_plan(goals: list[Goal], availability: Availability, start_date: date) -> list[dict]:
    """Merge all active goals onto one shared weekly calendar. Degrades
    gracefully (stacking accessory work on the same day) when there are
    fewer available days than the ideal split calls for."""
    total_weeks = _horizon_weeks(goals, start_date)
    scheduled: list[dict] = []

    run_distance_goal = next((g for g in goals if g.goal_type == GOAL_RUN_DISTANCE), None)
    run_pace_goal = next((g for g in goals if g.goal_type == GOAL_RUN_PACE), None)
    pushup_goal = next((g for g in goals if g.goal_type == GOAL_MAX_REPS), None)
    lsit_goal = next((g for g in goals if g.goal_type == GOAL_MAX_HOLD), None)

    for week_index in range(total_weeks):
        week_start = start_date + timedelta(weeks=week_index)

        # Kept as separate per-goal groups, then interleaved round-robin
        # below — merging them in one flat list (all running, then all
        # pushups, then all L-sit) would stack every accessory session onto
        # whatever day is left over once running claims the early slots.
        groups: list[list[dict]] = []
        if run_pace_goal is not None:
            groups.append(_run_pace_week_plans(run_pace_goal, week_index, total_weeks))
        if run_distance_goal is not None:
            long_run = _run_distance_week_plan(run_distance_goal, week_index)
            if long_run:
                groups.append([long_run])
        if pushup_goal is not None:
            groups.append(_pushup_week_plan(pushup_goal, week_index))
        if lsit_goal is not None:
            groups.append(_lsit_week_plan(lsit_goal, week_index))

        sessions: list[dict] = [s for row in zip_longest(*groups) for s in row if s is not None]
        if not sessions:
            continue

        # Confined to this week's own 7 calendar dates — _available_days()
        # would otherwise keep searching into next week whenever there are
        # more sessions than available days, silently pushing every
        # subsequent week's sessions later and desyncing week_number from
        # the actual calendar. Sessions are interleaved above and assigned
        # round-robin across the week's available days, so overflow spreads
        # evenly (e.g. 2/day) instead of stacking onto a single day.
        available_in_week = [d for d in _week_dates(availability, week_start) if availability.is_available(d)]
        if not available_in_week:
            continue
        slots = [available_in_week[i % len(available_in_week)] for i in range(len(sessions))]
        for i, session in enumerate(sessions):
            goal_ids = []
            if session["workout_type"] in (WORKOUT_RUN_INTERVAL, WORKOUT_RUN_TEMPO, WORKOUT_RUN_EASY):
                goal_ids = [run_pace_goal.id] if run_pace_goal else []
            elif session["workout_type"] == WORKOUT_RUN_LONG:
                goal_ids = [run_distance_goal.id] if run_distance_goal else []
            elif session["workout_type"] == WORKOUT_PUSHUP_SESSION:
                goal_ids = [pushup_goal.id] if pushup_goal else []
            elif session["workout_type"] == WORKOUT_LSIT_SESSION:
                goal_ids = [lsit_goal.id] if lsit_goal else []
            elif session["workout_type"] == WORKOUT_TEST:
                # A retest week's pushup test carries the pushup goal id.
                goal_ids = [pushup_goal.id] if pushup_goal else []

            scheduled.append({
                "client_id": _client_id(),
                "scheduled_date": slots[i],
                "goal_ids": goal_ids,
                "workout_type": session["workout_type"],
                "prescription": session["prescription"],
                "status": "PLANNED",
                "week_number": week_index + 1,
            })

    return scheduled


# ---------------------------------------------------------------------------
# Reflow: redistribute future workouts off newly-unavailable days
# ---------------------------------------------------------------------------

def reflow_plan(
    scheduled_workouts: list[dict],
    availability: Availability,
    from_date: date,
) -> list[dict]:
    """Returns the subset of `scheduled_workouts` that need their
    scheduled_date updated (dict with 'client_id' and new 'scheduled_date'),
    given the current availability. Only considers PLANNED rows on or after
    `from_date` — completed/skipped history and past dates are untouched."""
    future = [
        w for w in scheduled_workouts
        if w["status"] == "PLANNED" and w["scheduled_date"] >= from_date
    ]
    if not future:
        return []

    future.sort(key=lambda w: (w["week_number"], w["scheduled_date"]))
    updates: list[dict] = []

    # Reflow week by week so volume stays roughly grouped the way it was
    # generated, rather than a global reshuffle.
    by_week: dict[int, list[dict]] = {}
    for w in future:
        by_week.setdefault(w["week_number"], []).append(w)

    for week_number, week_workouts in sorted(by_week.items()):
        week_start = max(min(w["scheduled_date"] for w in week_workouts), from_date)
        blocked = [w for w in week_workouts if not availability.is_available(w["scheduled_date"])]
        if not blocked:
            continue
        slots = _available_days(availability, week_start, len(week_workouts))
        still_ok = [w for w in week_workouts if availability.is_available(w["scheduled_date"])]
        used_dates = {w["scheduled_date"] for w in still_ok}
        free_slots = [d for d in slots if d not in used_dates]
        for i, w in enumerate(blocked):
            new_date = free_slots[i] if i < len(free_slots) else (free_slots[-1] if free_slots else w["scheduled_date"])
            if new_date != w["scheduled_date"]:
                updates.append({"client_id": w["client_id"], "scheduled_date": new_date})

    return updates


# ---------------------------------------------------------------------------
# Adaptive adjustment
# ---------------------------------------------------------------------------

def performance_delta(prescription: dict, logged: dict) -> Optional[float]:
    """Fractional over/undershoot of a logged session vs. its prescription.
    Positive = beat it, negative = missed it. Returns None if the two aren't
    comparable (e.g. a rest day, or missing fields)."""
    ptype = prescription.get("type")
    if ptype == "pushups" and logged.get("best_set_reps") is not None:
        prescribed_best = max((s.get("reps", 0) for s in prescription.get("sets", [])), default=0)
        if prescribed_best <= 0:
            return None
        return (logged["best_set_reps"] - prescribed_best) / prescribed_best
    if ptype == "lsit_hold" and logged.get("best_hold_seconds") is not None:
        prescribed_best = max((s.get("hold_seconds", 0) for s in prescription.get("sets", [])), default=0)
        if prescribed_best <= 0:
            return None
        return (logged["best_hold_seconds"] - prescribed_best) / prescribed_best
    if ptype == "run" and logged.get("avg_pace_sec_per_mile") is not None and prescription.get("target_pace_sec_per_mile"):
        target = prescription["target_pace_sec_per_mile"]
        # Faster (lower seconds) than prescribed = beat it.
        return (target - logged["avg_pace_sec_per_mile"]) / target
    return None


def adjust_for_performance(goal: Goal, delta: float) -> Optional[float]:
    """Returns a new baseline_value for `goal` if this result should shift
    next week's targets, else None (no change). Bounded, single-step nudges —
    not a full re-generation; the caller re-runs generate_plan for future
    weeks with the updated baseline."""
    if goal.baseline_value is None:
        return None
    if delta >= _BEAT_MARGIN:
        return goal.baseline_value * 1.10
    if delta <= -_MISS_MARGIN:
        return goal.baseline_value * 0.95
    return None
