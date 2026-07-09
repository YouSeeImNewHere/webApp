package com.quail.android.ui.screens.wizards

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.fitness.FitnessRepository
import com.quail.android.data.model.FitnessGoalType
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.WeekdayAvailability
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

/** One weekly-plan setup covering all four trackable goal types at once —
 * per the user's request, these are trained toward simultaneously in a
 * single integrated schedule (see app/core/fitness_plan_engine.py), not
 * one at a time. Target values are text-backed (same pattern as Income
 * Wizard's LesFormState) so the form can hold in-progress/invalid input
 * without crashing on parse. */
data class GoalSetupFormState(
    val includeRunDistance: Boolean = true,
    val targetDistanceKm: String = "10",
    val includeRunPace: Boolean = true,
    val targetMilePaceText: String = "9:00",
    val includeMaxReps: Boolean = true,
    val targetReps: String = "100",
    val includeMaxHold: Boolean = true,
    val targetHoldSeconds: String = "30",
    val targetDateText: String = LocalDate.now().plusMonths(3).toString(),
    val weekdaysAvailable: Set<Int> = setOf(0, 1, 2, 3, 4, 5, 6),
)

sealed interface GoalSetupSubmitState {
    data object Idle : GoalSetupSubmitState
    data object Saving : GoalSetupSubmitState
    data object Done : GoalSetupSubmitState
    data class Error(val message: String) : GoalSetupSubmitState
}

private fun parseMilePaceSeconds(text: String): Int? {
    val parts = text.trim().split(":")
    if (parts.size != 2) return null
    val minutes = parts[0].toIntOrNull() ?: return null
    val seconds = parts[1].toIntOrNull() ?: return null
    return minutes * 60 + seconds
}

class GoalSetupWizardViewModel(private val repository: FitnessRepository) : ViewModel() {
    private val _form = MutableStateFlow(GoalSetupFormState())
    val form: StateFlow<GoalSetupFormState> = _form.asStateFlow()

    private val _submitState = MutableStateFlow<GoalSetupSubmitState>(GoalSetupSubmitState.Idle)
    val submitState: StateFlow<GoalSetupSubmitState> = _submitState.asStateFlow()

    fun updateForm(transform: (GoalSetupFormState) -> GoalSetupFormState) {
        _form.value = transform(_form.value)
    }

    fun toggleWeekday(weekday: Int) {
        val current = _form.value.weekdaysAvailable
        _form.value = _form.value.copy(
            weekdaysAvailable = if (weekday in current) current - weekday else current + weekday,
        )
    }

    /** Saves the selected goals, pushes them to the server (start-testing-week
     * reads goals server-side, so they must exist there first), saves
     * availability, then kicks off the testing week. */
    fun submit() {
        val f = _form.value
        if (!f.includeRunDistance && !f.includeRunPace && !f.includeMaxReps && !f.includeMaxHold) {
            _submitState.value = GoalSetupSubmitState.Error("Pick at least one goal")
            return
        }
        if (f.weekdaysAvailable.isEmpty()) {
            _submitState.value = GoalSetupSubmitState.Error("You need at least one available day per week")
            return
        }

        viewModelScope.launch {
            _submitState.value = GoalSetupSubmitState.Saving
            try {
                if (f.includeRunDistance) {
                    val distance = f.targetDistanceKm.toDoubleOrNull()
                        ?: throw IllegalArgumentException("Enter a valid target distance")
                    repository.saveGoal(
                        GoalRecord(
                            clientId = FitnessRepository.newClientId(),
                            title = "Run ${f.targetDistanceKm} km",
                            goalType = FitnessGoalType.RUN_DISTANCE,
                            targetDistanceKm = distance,
                            targetDate = f.targetDateText,
                        ),
                    )
                }
                if (f.includeRunPace) {
                    val paceSeconds = parseMilePaceSeconds(f.targetMilePaceText)
                        ?: throw IllegalArgumentException("Enter mile pace as mm:ss")
                    repository.saveGoal(
                        GoalRecord(
                            clientId = FitnessRepository.newClientId(),
                            title = "${f.targetMilePaceText} mile",
                            goalType = FitnessGoalType.RUN_PACE,
                            targetPaceSecPerMile = paceSeconds,
                            targetDate = f.targetDateText,
                        ),
                    )
                }
                if (f.includeMaxReps) {
                    val reps = f.targetReps.toIntOrNull() ?: throw IllegalArgumentException("Enter a valid rep target")
                    repository.saveGoal(
                        GoalRecord(
                            clientId = FitnessRepository.newClientId(),
                            title = "$reps push-ups",
                            goalType = FitnessGoalType.MAX_REPS,
                            targetExerciseId = "pushup",
                            targetReps = reps,
                            targetDate = f.targetDateText,
                        ),
                    )
                }
                if (f.includeMaxHold) {
                    val holdSeconds = f.targetHoldSeconds.toIntOrNull()
                        ?: throw IllegalArgumentException("Enter a valid hold time")
                    repository.saveGoal(
                        GoalRecord(
                            clientId = FitnessRepository.newClientId(),
                            title = "${holdSeconds}s L-sit",
                            goalType = FitnessGoalType.MAX_HOLD,
                            targetExerciseId = "lsit",
                            targetDurationSeconds = holdSeconds,
                            targetDate = f.targetDateText,
                        ),
                    )
                }

                repository.pushPending()
                repository.setAvailability(
                    weekdays = (0..6).map { WeekdayAvailability(it, it in f.weekdaysAvailable) },
                    unavailableDates = emptyList(),
                )
                repository.startTrainingPlanTestingWeek()
                _submitState.value = GoalSetupSubmitState.Done
            } catch (e: Exception) {
                _submitState.value = GoalSetupSubmitState.Error(e.message ?: "Couldn't set up your plan")
            }
        }
    }

    class Factory(private val repository: FitnessRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = GoalSetupWizardViewModel(repository) as T
    }
}
