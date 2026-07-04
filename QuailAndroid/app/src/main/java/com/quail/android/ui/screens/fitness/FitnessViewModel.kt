package com.quail.android.ui.screens.fitness

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.fitness.FitnessRepository
import com.quail.android.data.model.BodyweightRecord
import com.quail.android.data.model.Exercise
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.WorkoutExerciseEntry
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.WorkoutSet
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.util.UUID

data class FitnessData(
    val sessions: List<WorkoutSessionRecord>,
    val routines: List<RoutineRecord>,
    val goals: List<GoalRecord>,
    val bodyweightLogs: List<BodyweightRecord>,
) {
    val recentSessions: List<WorkoutSessionRecord> get() = sessions.sortedByDescending { it.date }.take(10)
    val workoutsThisWeek: Int get() {
        val cutoff = LocalDate.now().minusDays(7)
        return sessions.count { runCatching { LocalDate.parse(it.date) }.getOrNull()?.isAfter(cutoff) == true }
    }
    val latestBodyweightKg: Double? get() = bodyweightLogs.maxByOrNull { it.date }?.weightKg
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
        repository.sessions,
        repository.routines,
        repository.goals,
        repository.bodyweightLogs,
    ) { sessions, routines, goals, bodyweightLogs ->
        FitnessData(sessions, routines, goals, bodyweightLogs)
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

    fun logBodyweight(weightKg: Double) {
        viewModelScope.launch {
            repository.saveBodyweight(BodyweightRecord(clientId = FitnessRepository.newClientId(), date = LocalDate.now().toString(), weightKg = weightKg))
        }
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

    class Factory(private val repository: FitnessRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return FitnessViewModel(repository) as T
        }
    }
}
