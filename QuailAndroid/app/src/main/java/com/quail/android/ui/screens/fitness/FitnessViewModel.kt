package com.quail.android.ui.screens.fitness

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.fitness.FitnessRepository
import com.quail.android.data.model.BodyweightRecord
import com.quail.android.data.model.CustomExerciseRecord
import com.quail.android.data.model.DEFAULT_EXERCISES
import com.quail.android.data.model.Exercise
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.MilestoneRecord
import com.quail.android.data.model.MuscleGroup
import com.quail.android.data.model.ProgressionPath
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.WorkoutExerciseEntry
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.WorkoutSet
import com.quail.android.data.model.toExercise
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.util.UUID

private data class SessionsBundle(
    val sessions: List<WorkoutSessionRecord>,
    val routines: List<RoutineRecord>,
    val goals: List<GoalRecord>,
    val bodyweightLogs: List<BodyweightRecord>,
)

data class FitnessData(
    val sessions: List<WorkoutSessionRecord>,
    val routines: List<RoutineRecord>,
    val goals: List<GoalRecord>,
    val bodyweightLogs: List<BodyweightRecord>,
    val milestones: List<MilestoneRecord>,
    val customExerciseRecords: List<CustomExerciseRecord>,
) {
    val recentSessions: List<WorkoutSessionRecord> get() = sessions.sortedByDescending { it.date }.take(10)
    val workoutsThisWeek: Int get() {
        val cutoff = LocalDate.now().minusDays(7)
        return sessions.count { runCatching { LocalDate.parse(it.date) }.getOrNull()?.isAfter(cutoff) == true }
    }
    val latestBodyweightKg: Double? get() = bodyweightLogs.maxByOrNull { it.date }?.weightKg
    val customExercises: List<Exercise> get() = customExerciseRecords.map { it.toExercise() }
    val allExercises: List<Exercise> get() = DEFAULT_EXERCISES + customExercises
}

/** The workout currently being logged — held in memory only until Finish,
 * at which point it's written through FitnessRepository (Room first, synced
 * to the backend once connected). */
data class ActiveWorkout(
    val clientId: String = UUID.randomUUID().toString(),
    val startedAtMillis: Long = System.currentTimeMillis(),
    val exercises: List<WorkoutExerciseEntry> = emptyList(),
    val bodyweightKg: Double? = null,
    val notes: String = "",
)

class FitnessViewModel(private val repository: FitnessRepository) : ViewModel() {
    val uiState: StateFlow<FitnessData?> = combine(
        combine(repository.sessions, repository.routines, repository.goals, repository.bodyweightLogs, ::SessionsBundle),
        repository.milestones,
        repository.customExercises,
    ) { bundle, milestones, customExercises ->
        FitnessData(bundle.sessions, bundle.routines, bundle.goals, bundle.bodyweightLogs, milestones, customExercises)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    private val _activeWorkout = MutableStateFlow<ActiveWorkout?>(null)
    val activeWorkout: StateFlow<ActiveWorkout?> = _activeWorkout

    fun startWorkout(fromRoutine: RoutineRecord? = null, bodyweightKg: Double? = null) {
        _activeWorkout.value = ActiveWorkout(
            exercises = fromRoutine?.exercises?.map { it.copy(id = UUID.randomUUID().toString()) } ?: emptyList(),
            bodyweightKg = bodyweightKg,
        )
    }

    fun cancelWorkout() {
        _activeWorkout.value = null
    }

    fun addExerciseToActiveWorkout(exercise: Exercise) {
        val current = _activeWorkout.value ?: return
        val sets = (0 until exercise.defaultSets).map {
            WorkoutSet(
                id = UUID.randomUUID().toString(),
                reps = if (!exercise.isTimedExercise) exercise.defaultReps else null,
                durationSeconds = if (exercise.isTimedExercise) exercise.defaultDurationSeconds else null,
            )
        }
        _activeWorkout.value = current.copy(
            exercises = current.exercises + WorkoutExerciseEntry(UUID.randomUUID().toString(), exercise.id, sets),
        )
    }

    fun updateActiveWorkoutExercise(entryId: String, update: (WorkoutExerciseEntry) -> WorkoutExerciseEntry) {
        val current = _activeWorkout.value ?: return
        _activeWorkout.value = current.copy(
            exercises = current.exercises.map { if (it.id == entryId) update(it) else it },
        )
    }

    fun removeActiveWorkoutExercise(entryId: String) {
        val current = _activeWorkout.value ?: return
        _activeWorkout.value = current.copy(exercises = current.exercises.filter { it.id != entryId })
    }

    fun finishWorkout(durationMinutes: Int, notes: String) {
        val workout = _activeWorkout.value ?: return
        viewModelScope.launch {
            repository.saveSession(
                WorkoutSessionRecord(
                    clientId = workout.clientId,
                    date = LocalDate.now().toString(),
                    durationMinutes = durationMinutes,
                    bodyweightKg = workout.bodyweightKg,
                    notes = notes,
                    exercises = workout.exercises,
                ),
            )
            _activeWorkout.value = null
        }
    }

    fun deleteSession(clientId: String) {
        viewModelScope.launch { repository.deleteSession(clientId) }
    }

    fun saveRoutineFromWorkout(name: String, exercises: List<WorkoutExerciseEntry>) {
        if (name.isBlank()) return
        viewModelScope.launch {
            repository.saveRoutine(RoutineRecord(clientId = FitnessRepository.newClientId(), name = name.trim(), exercises = exercises))
        }
    }

    fun deleteRoutine(clientId: String) {
        viewModelScope.launch { repository.deleteRoutine(clientId) }
    }

    fun addGoal(title: String, goalType: String, targetExerciseId: String?, targetReps: Int?, targetDurationSeconds: Int?, targetDate: String?) {
        if (title.isBlank()) return
        viewModelScope.launch {
            repository.saveGoal(
                GoalRecord(
                    clientId = FitnessRepository.newClientId(),
                    title = title.trim(),
                    goalType = goalType,
                    targetExerciseId = targetExerciseId,
                    targetReps = targetReps,
                    targetDurationSeconds = targetDurationSeconds,
                    targetDate = targetDate,
                ),
            )
        }
    }

    fun deleteGoal(clientId: String) {
        viewModelScope.launch { repository.deleteGoal(clientId) }
    }

    fun addMilestone(title: String, date: String, exerciseId: String?, notes: String) {
        if (title.isBlank()) return
        viewModelScope.launch {
            repository.saveMilestone(
                MilestoneRecord(
                    clientId = FitnessRepository.newClientId(),
                    title = title.trim(),
                    date = date,
                    exerciseId = exerciseId,
                    notes = notes,
                ),
            )
        }
    }

    fun deleteMilestone(clientId: String) {
        viewModelScope.launch { repository.deleteMilestone(clientId) }
    }

    fun logBodyweight(weightKg: Double) {
        viewModelScope.launch {
            repository.saveBodyweight(BodyweightRecord(clientId = FitnessRepository.newClientId(), date = LocalDate.now().toString(), weightKg = weightKg))
        }
    }

    fun saveCustomExercise(
        name: String,
        category: String,
        muscleGroups: List<String>,
        difficulty: String,
        instructions: List<String>,
        videoUrl: String?,
        isTimedExercise: Boolean,
        defaultSets: Int,
        defaultReps: Int,
        defaultDurationSeconds: Int,
    ) {
        if (name.isBlank()) return
        viewModelScope.launch {
            repository.saveCustomExercise(
                CustomExerciseRecord(
                    clientId = FitnessRepository.newClientId(), name = name.trim(), category = category,
                    muscleGroups = muscleGroups, difficulty = difficulty,
                    instructions = instructions.map { it.trim() }.filter { it.isNotBlank() },
                    videoUrl = videoUrl?.trim().takeUnless { it.isNullOrBlank() },
                    isTimedExercise = isTimedExercise, defaultSets = defaultSets,
                    defaultReps = defaultReps, defaultDurationSeconds = defaultDurationSeconds,
                ),
            )
        }
    }

    fun deleteCustomExercise(clientId: String) {
        viewModelScope.launch { repository.deleteCustomExercise(clientId) }
    }

    class Factory(private val repository: FitnessRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return FitnessViewModel(repository) as T
        }
    }
}

/** Mirrors FitnessStore.swift's progressForGoal(_:) — 0..1 based on personal
 * best vs. the goal's target reps/duration for its target exercise. */
fun progressForGoal(goal: GoalRecord, sessions: List<WorkoutSessionRecord>): Float {
    val exerciseId = goal.targetExerciseId ?: return 0f
    val pb = personalBest(exerciseId, sessions) ?: return 0f
    goal.targetReps?.let { target -> pb.reps?.let { current -> return (current.toFloat() / target.toFloat()).coerceAtMost(1f) } }
    goal.targetDurationSeconds?.let { target -> pb.durationSeconds?.let { current -> return (current.toFloat() / target.toFloat()).coerceAtMost(1f) } }
    return 0f
}

fun personalBest(exerciseId: String, sessions: List<WorkoutSessionRecord>): WorkoutSet? {
    val allSets = sessions.flatMap { it.exercises }
        .filter { it.exerciseId == exerciseId }
        .flatMap { it.sets }
        .filter { it.isCompleted }
    val bestReps = allSets.mapNotNull { it.reps }.maxOrNull()
    val bestDuration = allSets.mapNotNull { it.durationSeconds }.maxOrNull()
    return when {
        bestReps != null -> WorkoutSet(id = "", reps = bestReps, isCompleted = true)
        bestDuration != null -> WorkoutSet(id = "", durationSeconds = bestDuration, isCompleted = true)
        else -> null
    }
}

/** Mirrors FitnessStore.swift's currentProgressionStep(in:) — walks the path in
 * order and returns the first not-yet-mastered exercise (PB below the "achieved"
 * threshold: defaultReps for rep-based exercises, 20s for timed ones). If every
 * exercise in the path is mastered, returns the last one (fully progressed). */
fun currentProgressionStep(path: ProgressionPath, sessions: List<WorkoutSessionRecord>, allExercises: List<Exercise>): Pair<Exercise, Int>? {
    path.exerciseIds.forEachIndexed { index, exerciseId ->
        val exercise = allExercises.firstOrNull { it.id == exerciseId } ?: return@forEachIndexed
        val pb = personalBest(exerciseId, sessions)
        val threshold = if (exercise.isTimedExercise) 20 else exercise.defaultReps
        val achieved = if (exercise.isTimedExercise) (pb?.durationSeconds ?: 0) >= threshold else (pb?.reps ?: 0) >= threshold
        if (!achieved) return exercise to index
    }
    val lastId = path.exerciseIds.lastOrNull() ?: return null
    val lastExercise = allExercises.firstOrNull { it.id == lastId } ?: return null
    return lastExercise to (path.exerciseIds.size - 1)
}

/** Mirrors FitnessStore.swift's weeklyVolume() — total completed reps per
 * muscle group across sessions from the last 7 days. */
fun weeklyVolume(sessions: List<WorkoutSessionRecord>, allExercises: List<Exercise>): Map<MuscleGroup, Int> {
    val cutoff = LocalDate.now().minusDays(7)
    val totals = mutableMapOf<MuscleGroup, Int>()
    sessions.forEach { session ->
        val sessionDate = runCatching { LocalDate.parse(session.date) }.getOrNull() ?: return@forEach
        if (sessionDate.isBefore(cutoff)) return@forEach
        session.exercises.forEach { entry ->
            val exercise = allExercises.firstOrNull { it.id == entry.exerciseId } ?: return@forEach
            val reps = entry.sets.filter { it.isCompleted }.sumOf { it.reps ?: 0 }
            exercise.muscleGroups.forEach { muscle -> totals[muscle] = (totals[muscle] ?: 0) + reps }
        }
    }
    return totals
}
