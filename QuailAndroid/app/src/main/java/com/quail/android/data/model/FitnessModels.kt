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
) {
    val totalSets: Int get() = exercises.sumOf { it.sets.count(WorkoutSet::isCompleted) }
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
)

data class ProgressionPath(
    val id: String,
    val name: String,
    val description: String,
    val category: ExerciseCategory,
    val exerciseIds: List<String>,
)
