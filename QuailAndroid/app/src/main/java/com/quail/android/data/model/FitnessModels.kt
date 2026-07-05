package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---- Nested workout shapes (stored as JSONB server-side, JSON text in Room) ----

@Serializable
data class WorkoutSet(
    val id: String,
    val reps: Int? = null,
    val durationSeconds: Int? = null,
    val addedWeightKg: Double? = null,
    val isCompleted: Boolean = false,
    val rpe: Int? = null,
    val restSeconds: Int? = null,
)

@Serializable
data class WorkoutExerciseEntry(
    val id: String,
    val exerciseId: String,
    val sets: List<WorkoutSet> = emptyList(),
    val notes: String = "",
)

// ---- Backend-synced records ----

@Serializable
data class WorkoutSessionRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val date: String = "",
    @SerialName("duration_minutes") val durationMinutes: Int = 0,
    @SerialName("bodyweight_kg") val bodyweightKg: Double? = null,
    val notes: String = "",
    val exercises: List<WorkoutExerciseEntry> = emptyList(),
    @SerialName("distance_km") val distanceKm: Double? = null,
    @SerialName("avg_pace_sec_per_km") val avgPaceSecPerKm: Int? = null,
    @SerialName("avg_heart_rate") val avgHeartRate: Int? = null,
    val calories: Int? = null,
    val source: String = "manual",
) {
    val totalSets: Int get() = exercises.sumOf { it.sets.count(WorkoutSet::isCompleted) }
    val isFromGarmin: Boolean get() = source == "garmin"
}

@Serializable
data class WorkoutSessionListResponse(val records: List<WorkoutSessionRecord> = emptyList(), val total: Int = 0)

@Serializable
data class WorkoutSessionUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val date: String,
    @SerialName("duration_minutes") val durationMinutes: Int = 0,
    @SerialName("bodyweight_kg") val bodyweightKg: Double? = null,
    val notes: String = "",
    val exercises: List<WorkoutExerciseEntry> = emptyList(),
)

@Serializable
data class RoutineRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val name: String = "",
    val exercises: List<WorkoutExerciseEntry> = emptyList(),
)

@Serializable
data class RoutineUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val name: String,
    val exercises: List<WorkoutExerciseEntry> = emptyList(),
)

@Serializable
data class GoalRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val title: String = "",
    @SerialName("goal_type") val goalType: String = "",
    @SerialName("target_exercise_id") val targetExerciseId: String? = null,
    @SerialName("target_reps") val targetReps: Int? = null,
    @SerialName("target_duration_seconds") val targetDurationSeconds: Int? = null,
    @SerialName("target_date") val targetDate: String? = null,
    val notes: String = "",
)

@Serializable
data class GoalUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val title: String,
    @SerialName("goal_type") val goalType: String,
    @SerialName("target_exercise_id") val targetExerciseId: String? = null,
    @SerialName("target_reps") val targetReps: Int? = null,
    @SerialName("target_duration_seconds") val targetDurationSeconds: Int? = null,
    @SerialName("target_date") val targetDate: String? = null,
    val notes: String = "",
)

@Serializable
data class MilestoneRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val title: String = "",
    val date: String = "",
    @SerialName("exercise_id") val exerciseId: String? = null,
    val notes: String = "",
)

@Serializable
data class MilestoneUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val title: String,
    val date: String,
    @SerialName("exercise_id") val exerciseId: String? = null,
    val notes: String = "",
)

@Serializable
data class BodyweightRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val date: String = "",
    @SerialName("weight_kg") val weightKg: Double = 0.0,
)

@Serializable
data class BodyweightUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val date: String,
    @SerialName("weight_kg") val weightKg: Double,
)

@Serializable
data class CustomExerciseRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val name: String = "",
    val category: String = "PUSH",
    @SerialName("muscle_groups") val muscleGroups: List<String> = emptyList(),
    val difficulty: String = "BEGINNER",
    val instructions: List<String> = emptyList(),
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("is_timed_exercise") val isTimedExercise: Boolean = false,
    @SerialName("default_sets") val defaultSets: Int = 3,
    @SerialName("default_reps") val defaultReps: Int = 10,
    @SerialName("default_duration_seconds") val defaultDurationSeconds: Int = 30,
)

@Serializable
data class CustomExerciseUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val name: String,
    val category: String,
    @SerialName("muscle_groups") val muscleGroups: List<String> = emptyList(),
    val difficulty: String = "BEGINNER",
    val instructions: List<String> = emptyList(),
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("is_timed_exercise") val isTimedExercise: Boolean = false,
    @SerialName("default_sets") val defaultSets: Int = 3,
    @SerialName("default_reps") val defaultReps: Int = 10,
    @SerialName("default_duration_seconds") val defaultDurationSeconds: Int = 30,
)

// ---- Exercise catalog (hardcoded client-side, same as iOS's built-in seed data —
// no backend table since it's identical static reference content on every install) ----

enum class ExerciseCategory(val displayName: String) {
    PUSH("Push"), PULL("Pull"), LEGS("Legs"), CORE("Core"), SKILL("Skill"), CARDIO("Cardio"),
}

enum class MuscleGroup(val displayName: String) {
    CHEST("Chest"), BACK("Back"), SHOULDERS("Shoulders"), TRICEPS("Triceps"), BICEPS("Biceps"),
    FOREARMS("Forearms"), QUADS("Quads"), HAMSTRINGS("Hamstrings"), GLUTES("Glutes"),
    CALVES("Calves"), ABS("Abs"), OBLIQUES("Obliques"),
}

enum class ExerciseDifficulty(val displayName: String, val sortKey: Int) {
    BEGINNER("Beginner", 0), INTERMEDIATE("Intermediate", 1), ADVANCED("Advanced", 2), ELITE("Elite", 3),
}

/** Mirrors FitnessStore.swift's FitnessGoalType — `goal_type` on GoalRecord is
 * stored as this enum's name (e.g. "MUSCLE_MASS") in the backend/local DB. */
enum class FitnessGoalTypeOption(val displayName: String) {
    MUSCLE_MASS("Muscle Mass"), STRENGTH("Strength"), ENDURANCE("Endurance"), FAT_LOSS("Fat Loss"),
}

/** Mirrors FitnessStore.swift's FitnessGoalType computed properties (repRange,
 * setsAdvice, restAdvice, frequencyAdvice, strategyNotes) — static "how to get
 * there" coaching content per goal type, shown on each goal's detail. */
val FitnessGoalTypeOption.repRange: String get() = when (this) {
    FitnessGoalTypeOption.MUSCLE_MASS -> "8–15 reps"
    FitnessGoalTypeOption.STRENGTH -> "3–6 reps"
    FitnessGoalTypeOption.ENDURANCE -> "15–25 reps"
    FitnessGoalTypeOption.FAT_LOSS -> "12–20 reps"
}

val FitnessGoalTypeOption.setsAdvice: String get() = when (this) {
    FitnessGoalTypeOption.MUSCLE_MASS -> "3–5 sets per exercise"
    FitnessGoalTypeOption.STRENGTH -> "4–6 sets per exercise"
    FitnessGoalTypeOption.ENDURANCE -> "2–4 sets, higher volume"
    FitnessGoalTypeOption.FAT_LOSS -> "3–4 sets, shorter rest"
}

val FitnessGoalTypeOption.restAdvice: String get() = when (this) {
    FitnessGoalTypeOption.MUSCLE_MASS -> "60–90 seconds"
    FitnessGoalTypeOption.STRENGTH -> "2–5 minutes"
    FitnessGoalTypeOption.ENDURANCE -> "30–60 seconds"
    FitnessGoalTypeOption.FAT_LOSS -> "30–45 seconds"
}

val FitnessGoalTypeOption.frequencyAdvice: String get() = when (this) {
    FitnessGoalTypeOption.MUSCLE_MASS -> "Each muscle 2–3× per week"
    FitnessGoalTypeOption.STRENGTH -> "3–4 sessions per week, full rest days"
    FitnessGoalTypeOption.ENDURANCE -> "4–5 sessions per week"
    FitnessGoalTypeOption.FAT_LOSS -> "4–5 sessions, mix strength & cardio"
}

val FitnessGoalTypeOption.strategyNotes: List<String> get() = when (this) {
    FitnessGoalTypeOption.MUSCLE_MASS -> listOf(
        "Add reps before moving to a harder variation — this is calisthenics progressive overload.",
        "Track your weekly sets per muscle group. 12–20 sets/week is the hypertrophy sweet spot.",
        "Eat at a modest calorie surplus (~250–500 kcal/day) with 0.7–1g of protein per lb bodyweight.",
        "Prioritise compound movements: push-ups, pull-ups, dips, rows, squats.",
        "Sleep 7–9 hours — muscle is built during recovery, not during the workout.",
    )
    FitnessGoalTypeOption.STRENGTH -> listOf(
        "Skill progressions (L-sit, front lever, handstand) build relative strength fast because bodyweight never increases the way a barbell does.",
        "Practise the hardest variation you can do for 2–4 clean reps, rest fully, repeat.",
        "Frequency beats volume at high intensities — 3–4 sets of hard work beats 10 sets of sloppy reps.",
        "Greasing the groove: practice at 50–60% of max effort multiple times a day to build neural efficiency.",
        "Adequate protein and sleep are non-negotiable — central nervous system recovery takes 48–72h after maximal efforts.",
    )
    FitnessGoalTypeOption.ENDURANCE -> listOf(
        "Build aerobic base first: 20–40 min of easy cardio (Zone 2) 3–4× per week before adding HIIT.",
        "Increase total volume by no more than 10% per week to avoid overuse injury.",
        "Add sprint or HIIT sessions once your aerobic base is solid — 1–2 per week maximum.",
        "Run/cycle easy enough that you can hold a full conversation. Zone 2 is your fat-burning engine.",
        "Combine calisthenics circuits with cardio for full-body conditioning without equipment.",
    )
    FitnessGoalTypeOption.FAT_LOSS -> listOf(
        "Fat loss is driven by a calorie deficit — exercise helps, but diet is the main lever.",
        "Preserve muscle by keeping protein high (0.7–1g/lb) and resistance training 3× per week.",
        "Minimise rest between sets (30–45s) to elevate heart rate and burn more calories.",
        "Circuit training (full body, no rest between exercises) maximises calorie burn per session.",
        "Cardio after weights burns more fat — glycogen is depleted so you go straight to fat as fuel.",
    )
}

/** id is a stable slug (e.g. "push_up"), not a random UUID — sessions/routines/goals
 * reference exercises by this id, and it must stay stable across app versions since
 * it's persisted in synced workout history. */
data class Exercise(
    val id: String,
    val name: String,
    val category: ExerciseCategory,
    val muscleGroups: List<MuscleGroup>,
    val difficulty: ExerciseDifficulty,
    val instructions: List<String>,
    val isTimedExercise: Boolean = false,
    val defaultSets: Int = 3,
    val defaultReps: Int = 10,
    val defaultDurationSeconds: Int = 30,
    val videoUrl: String? = null,
    val isCustom: Boolean = false,
    val customClientId: String? = null,
)

/** Maps a user-created CustomExerciseRecord onto the same Exercise shape the
 * built-in catalog uses, so the picker/active workout/detail screen can treat
 * both uniformly. customClientId carries the backend client_id for deletion —
 * `id` itself stays a "custom_<clientId>" slug so it never collides with a
 * built-in DEFAULT_EXERCISES id. */
fun CustomExerciseRecord.toExercise(): Exercise = Exercise(
    id = "custom_$clientId",
    name = name,
    category = runCatching { ExerciseCategory.valueOf(category) }.getOrDefault(ExerciseCategory.PUSH),
    muscleGroups = muscleGroups.mapNotNull { runCatching { MuscleGroup.valueOf(it) }.getOrNull() },
    difficulty = runCatching { ExerciseDifficulty.valueOf(difficulty) }.getOrDefault(ExerciseDifficulty.BEGINNER),
    instructions = instructions,
    isTimedExercise = isTimedExercise,
    defaultSets = defaultSets,
    defaultReps = defaultReps,
    defaultDurationSeconds = defaultDurationSeconds,
    videoUrl = videoUrl,
    isCustom = true,
    customClientId = clientId,
)

// ---- Garmin connect ----

@Serializable
data class GarminConnectRequest(val email: String, val password: String)

@Serializable
data class GarminConnectResponse(
    @SerialName("needs_mfa") val needsMfa: Boolean = false,
    @SerialName("session_id") val sessionId: String? = null,
    val connected: Boolean = false,
)

@Serializable
data class GarminMfaRequest(@SerialName("session_id") val sessionId: String, @SerialName("mfa_code") val mfaCode: String)

@Serializable
data class GarminMfaResponse(val connected: Boolean = false)

@Serializable
data class GarminStatusResponse(val connected: Boolean = false)

@Serializable
data class GarminDailyHealthRecord(
    val id: Int = 0,
    val date: String = "",
    @SerialName("resting_heart_rate") val restingHeartRate: Int? = null,
    @SerialName("min_heart_rate") val minHeartRate: Int? = null,
    @SerialName("max_heart_rate") val maxHeartRate: Int? = null,
    @SerialName("total_steps") val totalSteps: Int? = null,
    @SerialName("daily_step_goal") val dailyStepGoal: Int? = null,
    @SerialName("total_calories") val totalCalories: Int? = null,
    @SerialName("active_calories") val activeCalories: Int? = null,
    @SerialName("vo2_max") val vo2Max: Double? = null,
    @SerialName("sleep_deep_seconds") val sleepDeepSeconds: Int? = null,
    @SerialName("sleep_light_seconds") val sleepLightSeconds: Int? = null,
    @SerialName("sleep_rem_seconds") val sleepRemSeconds: Int? = null,
    @SerialName("sleep_awake_seconds") val sleepAwakeSeconds: Int? = null,
    @SerialName("body_battery_highest") val bodyBatteryHighest: Int? = null,
    @SerialName("body_battery_lowest") val bodyBatteryLowest: Int? = null,
    @SerialName("average_stress_level") val averageStressLevel: Int? = null,
    @SerialName("floors_ascended") val floorsAscended: Double? = null,
) {
    val totalSleepSeconds: Int? get() {
        val parts = listOfNotNull(sleepDeepSeconds, sleepLightSeconds, sleepRemSeconds, sleepAwakeSeconds)
        return if (parts.isEmpty()) null else parts.sum()
    }
}

data class ProgressionPath(
    val id: String,
    val name: String,
    val description: String,
    val category: ExerciseCategory,
    val exerciseIds: List<String>,
)
