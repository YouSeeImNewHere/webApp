package com.quail.android.ui.screens.fitness

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.fitness.FitnessRepository
import com.quail.android.data.model.AvailabilityRecord
import com.quail.android.data.model.BodyweightRecord
import com.quail.android.data.model.CustomExerciseRecord
import com.quail.android.data.model.DEFAULT_EXERCISES
import com.quail.android.data.model.Exercise
import com.quail.android.data.model.GarminDailyHealthRecord
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.MilestoneRecord
import com.quail.android.data.model.MuscleGroup
import com.quail.android.data.model.DEFAULT_PROGRESSION_PATHS
import com.quail.android.data.model.ProgressionPath
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.ScheduledWorkoutRecord
import com.quail.android.data.model.UnavailableDate
import com.quail.android.data.model.WeekdayAvailability
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
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
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
 * to the backend once connected). `scheduledWorkoutId` is set when this
 * workout was started from the training plan's "Start" action, so Finish
 * can report the result back (see completeScheduledWorkout in
 * FitnessRepository / fitness_plan_engine.adjust_for_performance). */
data class ActiveWorkout(
    val clientId: String = UUID.randomUUID().toString(),
    val startedAtMillis: Long = System.currentTimeMillis(),
    val exercises: List<WorkoutExerciseEntry> = emptyList(),
    val bodyweightKg: Double? = null,
    val notes: String = "",
    val scheduledWorkoutId: Int? = null,
)

sealed interface TrainingPlanUiState {
    data object Loading : TrainingPlanUiState
    data class Error(val message: String) : TrainingPlanUiState
    data class None(val hasGoals: Boolean) : TrainingPlanUiState
    data class Testing(val scheduled: List<ScheduledWorkoutRecord>) : TrainingPlanUiState
    data class Active(val scheduled: List<ScheduledWorkoutRecord>) : TrainingPlanUiState
}

sealed interface GarminConnectState {
    data object Unknown : GarminConnectState
    data object Disconnected : GarminConnectState
    data object Connected : GarminConnectState
    data object Connecting : GarminConnectState
    data class NeedsMfa(val sessionId: String) : GarminConnectState
    data class Error(val message: String) : GarminConnectState
}

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

    private val _garminState = MutableStateFlow<GarminConnectState>(GarminConnectState.Unknown)
    val garminState: StateFlow<GarminConnectState> = _garminState

    private val _garminHealth = MutableStateFlow<List<GarminDailyHealthRecord>>(emptyList())
    val garminHealth: StateFlow<List<GarminDailyHealthRecord>> = _garminHealth

    private val _planState = MutableStateFlow<TrainingPlanUiState>(TrainingPlanUiState.Loading)
    val planState: StateFlow<TrainingPlanUiState> = _planState

    private val _availability = MutableStateFlow<AvailabilityRecord?>(null)
    val availability: StateFlow<AvailabilityRecord?> = _availability

    private val _planActionInFlight = MutableStateFlow(false)
    val planActionInFlight: StateFlow<Boolean> = _planActionInFlight

    init {
        refreshGarminHealth()
        loadPlan()
        loadAvailability()
    }

    // Rows scheduled before the session-bundling backend change still carry
    // the old single-exercise top-level prescription "type" ("pushups"/
    // "lsit_hold") instead of the new bundled "session" type - a real user
    // report showed these surviving indefinitely because nothing ever
    // prompted a regenerate. Detected here so loadPlan() can self-heal by
    // regenerating once, instead of requiring the user to notice and tap
    // the refresh icon themselves.
    private var autoRegeneratedStalePlan = false
    private fun hasStaleLegacyPrescription(scheduled: List<com.quail.android.data.model.ScheduledWorkoutRecord>): Boolean =
        scheduled.any { it.status == "PLANNED" && it.prescription.str("type") in setOf("pushups", "lsit_hold") }

    fun loadPlan() {
        viewModelScope.launch {
            _planState.value = TrainingPlanUiState.Loading
            try {
                val status = repository.getTrainingPlanStatus().status
                when (status) {
                    "TESTING" -> _planState.value = TrainingPlanUiState.Testing(repository.getScheduledWorkouts())
                    "ACTIVE" -> {
                        val scheduled = repository.getScheduledWorkouts()
                        if (!autoRegeneratedStalePlan && hasStaleLegacyPrescription(scheduled)) {
                            autoRegeneratedStalePlan = true
                            repository.generateTrainingPlan()
                            _planState.value = TrainingPlanUiState.Active(repository.getScheduledWorkouts())
                        } else {
                            _planState.value = TrainingPlanUiState.Active(scheduled)
                        }
                    }
                    else -> {
                        val hasGoals = uiState.value?.goals?.isNotEmpty() == true
                        _planState.value = TrainingPlanUiState.None(hasGoals)
                    }
                }
            } catch (e: Exception) {
                _planState.value = TrainingPlanUiState.Error(e.message ?: "Couldn't load your training plan")
            }
        }
    }

    fun loadAvailability() {
        viewModelScope.launch {
            runCatching { repository.getAvailability() }.onSuccess { _availability.value = it }
        }
    }

    fun saveAvailability(weekdays: List<WeekdayAvailability>, unavailableDates: List<UnavailableDate>) {
        viewModelScope.launch {
            _planActionInFlight.value = true
            try {
                _availability.value = repository.setAvailability(weekdays, unavailableDates)
                loadPlan() // availability changes can reflow the active plan
            } finally {
                _planActionInFlight.value = false
            }
        }
    }

    fun startTrainingPlanTestingWeek() {
        viewModelScope.launch {
            _planActionInFlight.value = true
            try {
                repository.startTrainingPlanTestingWeek()
                loadPlan()
            } catch (e: Exception) {
                _planState.value = TrainingPlanUiState.Error(e.message ?: "Couldn't start your testing week")
            } finally {
                _planActionInFlight.value = false
            }
        }
    }

    fun generateTrainingPlan() {
        viewModelScope.launch {
            _planActionInFlight.value = true
            try {
                repository.generateTrainingPlan()
                loadPlan()
            } catch (e: Exception) {
                _planState.value = TrainingPlanUiState.Error(e.message ?: "Couldn't generate your plan")
            } finally {
                _planActionInFlight.value = false
            }
        }
    }

    /** Used for scheduled workouts with no in-app logging path (runs — this
     * app has no manual cardio entry, only Garmin sync) and for skip. */
    fun markScheduledWorkoutDone(id: Int) {
        viewModelScope.launch {
            runCatching { repository.completeScheduledWorkout(id, sessionClientId = null) }
            loadPlan()
        }
    }

    fun skipScheduledWorkout(id: Int) {
        viewModelScope.launch {
            runCatching { repository.skipScheduledWorkout(id) }
            loadPlan()
        }
    }

    /** Seeds the active workout with the prescribed exercise + target
     * sets/reps (or a single freeform set for the testing-week AMRAP tests),
     * so the strength/hold-based portion of the plan flows straight into the
     * normal workout logger. Run prescriptions aren't started this way (see
     * markScheduledWorkoutDone). */
    /** Which variant to start a fresh AMRAP/hold test at — the user's real
     * current standing in the matching Progression Path (see
     * currentProgressionStep() below), not always the easiest step. Ties the
     * training plan to progress already made instead of re-testing from
     * scratch every time. */
    private fun currentPathExerciseId(pathId: String): String? {
        val data = uiState.value ?: return null
        val path = DEFAULT_PROGRESSION_PATHS.firstOrNull { it.id == pathId } ?: return null
        return currentProgressionStep(path, data.sessions, data.allExercises)?.first?.id
    }

    // Fallback exercise_id per block type, matched to whether that type is
    // actually timed (see isTimedExercise) - falling back to a non-timed
    // exercise (e.g. "pushup") for a missing exercise_id on a timed block
    // was a real bug: it made isTimedExercise resolve false for an L-sit or
    // core hold, so the logger showed a bare rep count with no seconds
    // unit instead of a timed hold.
    private fun fallbackExerciseId(blockType: String?): String = when (blockType) {
        "lsit_hold" -> "tuck_lsit"
        "accessory", "core_hold" -> "hollow_body_hold"
        else -> "pushup"
    }

    private fun exerciseEntryFromBlock(block: Map<String, JsonElement>): WorkoutExerciseEntry {
        val exerciseId = block.str("exercise_id") ?: fallbackExerciseId(block.str("type"))
        val sets = block.setsList().map {
            WorkoutSet(id = UUID.randomUUID().toString(), reps = it.reps, durationSeconds = it.holdSeconds)
        }
        return WorkoutExerciseEntry(UUID.randomUUID().toString(), exerciseId, sets)
    }

    fun startWorkoutFromScheduled(scheduled: ScheduledWorkoutRecord) {
        val type = scheduled.prescription.str("type")
        val exercises = when (type) {
            // A bundled multi-exercise day (see fitness_plan_engine.py's
            // _skills_week_plan) - one WorkoutExerciseEntry per block, so
            // the logger shows the whole day's routine, not just one move.
            "session" -> scheduled.prescription.blocks().map { exerciseEntryFromBlock(it) }
            // Old single-exercise prescriptions, from before session
            // bundling existed - kept for any already-scheduled rows.
            "pushups", "lsit_hold" -> listOf(exerciseEntryFromBlock(scheduled.prescription))
            "pushup_test" -> {
                val exerciseId = currentPathExerciseId("path_pushup") ?: "pushup"
                listOf(WorkoutExerciseEntry(UUID.randomUUID().toString(), exerciseId, listOf(WorkoutSet(id = UUID.randomUUID().toString()))))
            }
            "lsit_test" -> {
                val exerciseId = currentPathExerciseId("path_lsit") ?: "tuck_lsit"
                listOf(WorkoutExerciseEntry(UUID.randomUUID().toString(), exerciseId, listOf(WorkoutSet(id = UUID.randomUUID().toString()))))
            }
            else -> emptyList()
        }
        _activeWorkout.value = ActiveWorkout(exercises = exercises, scheduledWorkoutId = scheduled.id)
    }

    fun refreshGarminHealth() {
        viewModelScope.launch {
            runCatching { repository.getGarminDailyHealth() }.onSuccess { _garminHealth.value = it }
        }
    }

    fun refreshGarminStatus() {
        viewModelScope.launch {
            _garminState.value = runCatching { repository.getGarminStatus() }
                .fold(
                    onSuccess = { connected -> if (connected) GarminConnectState.Connected else GarminConnectState.Disconnected },
                    onFailure = { GarminConnectState.Unknown },
                )
        }
    }

    fun connectGarmin(email: String, password: String) {
        viewModelScope.launch {
            _garminState.value = GarminConnectState.Connecting
            runCatching { repository.connectGarmin(email, password) }
                .onSuccess { result ->
                    _garminState.value = when {
                        result.needsMfa && result.sessionId != null -> GarminConnectState.NeedsMfa(result.sessionId)
                        result.connected -> GarminConnectState.Connected
                        else -> GarminConnectState.Error("Login did not complete")
                    }
                }
                .onFailure { e -> _garminState.value = GarminConnectState.Error(e.message ?: "Connection failed") }
        }
    }

    fun submitGarminMfa(sessionId: String, code: String) {
        viewModelScope.launch {
            _garminState.value = GarminConnectState.Connecting
            runCatching { repository.submitGarminMfa(sessionId, code) }
                .onSuccess { connected -> _garminState.value = if (connected) GarminConnectState.Connected else GarminConnectState.Error("Incorrect code") }
                .onFailure { e -> _garminState.value = GarminConnectState.Error(e.message ?: "Incorrect code") }
        }
    }

    fun disconnectGarmin() {
        viewModelScope.launch {
            runCatching { repository.disconnectGarmin() }
            _garminState.value = GarminConnectState.Disconnected
        }
    }

    /** Pull-to-refresh entry point — uiState is already a live Room flow, so
     * this just eagerly pushes any pending local edits and pulls the latest
     * from the server (Garmin runs, other devices' edits) instead of waiting
     * for the periodic background sync. */
    fun refresh() {
        viewModelScope.launch {
            runCatching { repository.pushPending() }
            runCatching { repository.pullFromServer() }
        }
        refreshGarminHealth()
    }

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
            workout.scheduledWorkoutId?.let { scheduledId ->
                val bestReps = workout.exercises.flatMap { it.sets }.mapNotNull { it.reps }.maxOrNull()
                val bestHold = workout.exercises.flatMap { it.sets }.mapNotNull { it.durationSeconds }.maxOrNull()
                val logged = buildMap {
                    bestReps?.let { put("best_set_reps", JsonPrimitive(it)) }
                    bestHold?.let { put("best_hold_seconds", JsonPrimitive(it)) }
                }
                // Push now (rather than waiting for the background sync worker)
                // so the session this scheduled workout links to already exists
                // server-side — /fitness/plan/generate reads baselines straight
                // from fitness_workout_sessions right after a testing-week test.
                runCatching { repository.pushPending() }
                runCatching { repository.completeScheduledWorkout(scheduledId, workout.clientId, logged) }
                loadPlan()
            }
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

/** Total completed reps (all muscle groups combined) per week, for the last
 * [weeks] calendar weeks (Mon-Sun), oldest first — used for the Analytics
 * page's volume-over-time trend. */
fun weeklyVolumeHistory(sessions: List<WorkoutSessionRecord>, weeks: Int = 8): List<Pair<LocalDate, Int>> {
    val today = LocalDate.now()
    return (0 until weeks).map { weekIndex ->
        val weekStart = today.minusWeeks(weekIndex.toLong()).with(java.time.DayOfWeek.MONDAY)
        val weekEnd = weekStart.plusDays(6)
        val total = sessions.filter { session ->
            val d = runCatching { LocalDate.parse(session.date) }.getOrNull() ?: return@filter false
            !d.isBefore(weekStart) && !d.isAfter(weekEnd)
        }.sumOf { session -> session.exercises.sumOf { entry -> entry.sets.filter { it.isCompleted }.sumOf { it.reps ?: 0 } } }
        weekStart to total
    }.reversed()
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
