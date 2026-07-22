package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.DEFAULT_EXERCISES
import com.quail.android.data.model.FitnessGoalTypeOption
import com.quail.android.data.model.WorkoutExerciseEntry
import com.quail.android.data.model.WorkoutSet
import com.quail.android.data.model.exerciseById
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.UUID

private fun LocalDate.toUtcMillis(): Long = atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
private fun Long.toLocalDateUtc(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate()

@Composable
fun FitnessSheetHost(sheet: FitnessSheet, viewModel: FitnessViewModel, onDismiss: () -> Unit, onStartWorkout: () -> Unit = {}) {
    val content: @Composable () -> Unit = {
        when (sheet) {
            is FitnessSheet.AddGoal -> AddGoalSheet(viewModel, onDismiss)
            is FitnessSheet.LogBodyweight -> LogBodyweightSheet(viewModel, onDismiss)
            is FitnessSheet.AddMilestone -> AddMilestoneSheet(viewModel, onDismiss)
            is FitnessSheet.CreateRoutine -> CreateRoutineContent(viewModel, onDismiss)
            is FitnessSheet.ScheduledWorkoutDetail -> ScheduledWorkoutDetailSheet(sheet.record, viewModel, onDismiss, onStartWorkout)
            is FitnessSheet.EditAvailability -> EditAvailabilitySheet(viewModel, onDismiss)
            is FitnessSheet.ExerciseInfo -> ExerciseInfoSheet(sheet.exerciseId, onDismiss)
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@Composable
private fun SheetScaffold(title: String, onDismiss: () -> Unit, content: @Composable () -> Unit) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
        }
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { content() }
    }
}

@Composable
private fun SaveButton(label: String, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (enabled) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            label,
            fontWeight = FontWeight.Bold,
            color = if (enabled) Color.Black else QuailTextDim,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
        )
    }
}

// ---- Log bodyweight ----

@Composable
private fun LogBodyweightSheet(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    var weight by remember { mutableStateOf("") }

    SheetScaffold("Log Weight", onDismiss) {
        OutlinedTextField(
            value = weight,
            onValueChange = { weight = it.filter { c -> c.isDigit() || c == '.' } },
            label = { Text("Weight (kg)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        val kg = weight.toDoubleOrNull()
        SaveButton("Save", enabled = kg != null && kg > 0) {
            if (kg != null && kg > 0) {
                viewModel.logBodyweight(kg)
                onDismiss()
            }
        }
    }
}

// ---- Add goal ----

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddGoalSheet(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    var title by remember { mutableStateOf("") }
    var goalType by remember { mutableStateOf(FitnessGoalTypeOption.entries.first()) }
    var showTypePicker by remember { mutableStateOf(false) }
    var targetExerciseId by remember { mutableStateOf<String?>(null) }
    var showExercisePicker by remember { mutableStateOf(false) }
    var targetReps by remember { mutableStateOf("") }
    var targetDate by remember { mutableStateOf(LocalDate.now().plusMonths(1)) }
    var showDatePicker by remember { mutableStateOf(false) }

    SheetScaffold("New Goal", onDismiss) {
        OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true, modifier = Modifier.fillMaxWidth())

        Column {
            Text("Goal Type", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            Surface(onClick = { showTypePicker = !showTypePicker }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(goalType.displayName, modifier = Modifier.padding(12.dp))
            }
            if (showTypePicker) {
                Column {
                    FitnessGoalTypeOption.entries.forEach { option ->
                        Surface(onClick = { goalType = option; showTypePicker = false }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                            Text(option.displayName, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                }
            }
        }

        Column {
            Text("Target Exercise (optional)", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            Surface(onClick = { showExercisePicker = !showExercisePicker }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(targetExerciseId?.let { id -> DEFAULT_EXERCISES.firstOrNull { it.id == id }?.name } ?: "None", modifier = Modifier.padding(12.dp))
            }
            if (showExercisePicker) {
                Column {
                    DEFAULT_EXERCISES.forEach { exercise ->
                        Surface(onClick = { targetExerciseId = exercise.id; showExercisePicker = false }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                            Text(exercise.name, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                }
            }
        }

        OutlinedTextField(
            value = targetReps,
            onValueChange = { targetReps = it.filter(Char::isDigit) },
            label = { Text("Target reps (optional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Surface(onClick = { showDatePicker = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Target date", color = QuailTextDim)
                Text(targetDate.toString(), fontWeight = FontWeight.SemiBold)
            }
        }

        SaveButton("Save Goal", enabled = title.isNotBlank()) {
            if (title.isNotBlank()) {
                viewModel.addGoal(title, goalType.name, targetExerciseId, targetReps.toIntOrNull(), null, targetDate.toString())
                onDismiss()
            }
        }
    }

    if (showDatePicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = targetDate.toUtcMillis())
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { targetDate = it.toLocalDateUtc() }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } },
        ) { DatePicker(state = pickerState) }
    }
}

// ---- Add milestone ----

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddMilestoneSheet(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    var title by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var showDatePicker by remember { mutableStateOf(false) }
    var exerciseId by remember { mutableStateOf<String?>(null) }
    var showExercisePicker by remember { mutableStateOf(false) }

    SheetScaffold("New Milestone", onDismiss) {
        OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true, modifier = Modifier.fillMaxWidth())

        Surface(onClick = { showDatePicker = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Date", color = QuailTextDim)
                Text(date.toString(), fontWeight = FontWeight.SemiBold)
            }
        }

        Column {
            Text("Related Exercise (optional)", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            Surface(onClick = { showExercisePicker = !showExercisePicker }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(exerciseId?.let { id -> DEFAULT_EXERCISES.firstOrNull { it.id == id }?.name } ?: "None", modifier = Modifier.padding(12.dp))
            }
            if (showExercisePicker) {
                Column {
                    DEFAULT_EXERCISES.forEach { exercise ->
                        Surface(onClick = { exerciseId = exercise.id; showExercisePicker = false }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                            Text(exercise.name, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                }
            }
        }

        OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes (optional)") }, modifier = Modifier.fillMaxWidth())

        SaveButton("Save Milestone", enabled = title.isNotBlank()) {
            if (title.isNotBlank()) {
                viewModel.addMilestone(title, date.toString(), exerciseId, notes)
                onDismiss()
            }
        }
    }

    if (showDatePicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = date.toUtcMillis())
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { date = it.toLocalDateUtc() }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } },
        ) { DatePicker(state = pickerState) }
    }
}

// ---- Create routine from scratch (no live workout needed) ----

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateRoutineContent(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    val data by viewModel.uiState.collectAsState()
    val customExercises = data?.customExercises ?: emptyList()
    val sessions = data?.sessions ?: emptyList()

    var name by remember { mutableStateOf("") }
    var draftExercises by remember { mutableStateOf(listOf<WorkoutExerciseEntry>()) }
    var showExercisePicker by remember { mutableStateOf(false) }

    SheetScaffold("New Routine", onDismiss) {
        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text("e.g. Push Day A, Full Body") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (draftExercises.isEmpty()) {
            Text("No exercises yet", color = QuailTextDim, modifier = Modifier.padding(vertical = 8.dp))
        } else {
            Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                Column {
                    draftExercises.forEachIndexed { idx, entry ->
                        val exercise = exerciseById(entry.exerciseId, customExercises)
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(exercise?.name ?: "Exercise", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                Text("${entry.sets.size} sets", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                IconButton(onClick = {
                                    if (entry.sets.size > 1) {
                                        draftExercises = draftExercises.toMutableList().also {
                                            it[idx] = entry.copy(sets = entry.sets.dropLast(1))
                                        }
                                    }
                                }) { Text("–", color = QuailTextDim) }
                                Text("${entry.sets.size}", fontWeight = FontWeight.SemiBold)
                                IconButton(onClick = {
                                    val template = entry.sets.lastOrNull()
                                    val newSet = WorkoutSet(
                                        id = UUID.randomUUID().toString(),
                                        reps = if (exercise?.isTimedExercise != true) (template?.reps ?: exercise?.defaultReps ?: 10) else null,
                                        durationSeconds = if (exercise?.isTimedExercise == true) (template?.durationSeconds ?: exercise.defaultDurationSeconds) else null,
                                    )
                                    draftExercises = draftExercises.toMutableList().also { it[idx] = entry.copy(sets = entry.sets + newSet) }
                                }) { Text("+", color = QuailTextDim) }
                                Surface(onClick = { draftExercises = draftExercises.filterIndexed { i, _ -> i != idx } }, color = Color.Transparent) {
                                    Text("✕", color = QuailTextDim, modifier = Modifier.padding(start = 4.dp))
                                }
                            }
                        }
                        if (idx < draftExercises.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }

        Surface(
            onClick = { showExercisePicker = true },
            color = Color.Transparent,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                "+ Add Exercise",
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.SemiBold,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
            )
        }

        SaveButton("Save Routine", enabled = name.isNotBlank() && draftExercises.isNotEmpty()) {
            if (name.isNotBlank() && draftExercises.isNotEmpty()) {
                viewModel.saveRoutineFromWorkout(name, draftExercises)
                onDismiss()
            }
        }
    }

    if (showExercisePicker) {
        ExercisePickerSheet(
            customExercises = customExercises,
            sessions = sessions,
            onDismiss = { showExercisePicker = false },
            onSelect = { exercise ->
                val newSet = WorkoutSet(
                    id = UUID.randomUUID().toString(),
                    reps = if (!exercise.isTimedExercise) exercise.defaultReps else null,
                    durationSeconds = if (exercise.isTimedExercise) exercise.defaultDurationSeconds else null,
                )
                draftExercises = draftExercises + WorkoutExerciseEntry(UUID.randomUUID().toString(), exercise.id, listOf(newSet))
                showExercisePicker = false
            },
            onShowInfo = {},
            onCreateCustomExercise = {},
        )
    }
}

// ---- Training plan: scheduled workout detail ----

@Composable
private fun ScheduledWorkoutDetailSheet(
    record: com.quail.android.data.model.ScheduledWorkoutRecord,
    viewModel: FitnessViewModel,
    onDismiss: () -> Unit,
    onStartWorkout: () -> Unit,
) {
    val prescriptionType = record.prescription.str("type")
    // "session" (a bundled multi-exercise day - see fitness_plan_engine.py's
    // _skills_week_plan) was missing here entirely, which meant the "Start"
    // button never showed for the new bundled workouts at all - a real bug
    // that made the whole feature untappable in the UI despite the
    // ViewModel/backend side being correct.
    val canLogInApp = prescriptionType in setOf("session", "pushups", "lsit_hold", "pushup_test", "lsit_test")

    SheetScaffold(record.workoutType.replace('_', ' ').lowercase().replaceFirstChar { it.uppercase() }, onDismiss) {
        Text(prescriptionSummary(record.workoutType, record.prescription), fontWeight = FontWeight.SemiBold)
        if (prescriptionType == "session") {
            // Per-block breakdown so the preview actually shows what the
            // full routine involves, not just the one-line "Pushups + L-sit
            // + Core" summary.
            record.prescription.blocks().forEach { block ->
                val setsList = block.setsList()
                val setsDesc = if (setsList.isNotEmpty()) {
                    setsList.joinToString(", ") { s -> s.holdSeconds?.let { "${it}s" } ?: s.reps?.let { "${it} reps" } ?: "?" }
                } else null
                Column(modifier = Modifier.padding(top = 4.dp)) {
                    Text("• ${blockLabel(block)}" + (setsDesc?.let { " — $it" } ?: ""), fontWeight = FontWeight.SemiBold)
                    block.str("notes")?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        record.prescription.str("notes")?.let { Text(it, color = QuailTextDim) }
        record.prescription.str("instructions")?.let { Text(it, color = QuailTextDim) }

        if (record.status == "PLANNED") {
            if (canLogInApp) {
                SaveButton("Start", enabled = true) {
                    viewModel.startWorkoutFromScheduled(record)
                    onDismiss()
                    onStartWorkout()
                }
            } else {
                SaveButton("Mark as Done", enabled = true) {
                    viewModel.markScheduledWorkoutDone(record.id)
                    onDismiss()
                }
            }
            TextButton(onClick = { viewModel.skipScheduledWorkout(record.id); onDismiss() }, modifier = Modifier.fillMaxWidth()) {
                Text("Skip this session")
            }
        } else {
            Text("Status: ${record.status.lowercase().replaceFirstChar { it.uppercase() }}", color = QuailTextDim)
        }
    }
}

@Composable
private fun ExerciseInfoSheet(exerciseId: String, onDismiss: () -> Unit) {
    val exercise = exerciseById(exerciseId, DEFAULT_EXERCISES)
    SheetScaffold(exercise?.name ?: exerciseId.replace('_', ' ').replaceFirstChar { it.uppercase() }, onDismiss) {
        if (exercise == null) {
            Text("No instructions available for this exercise.", color = QuailTextDim)
            return@SheetScaffold
        }
        Text(
            exercise.difficulty.name.lowercase().replaceFirstChar { it.uppercase() } + " • " +
                exercise.category.name.lowercase().replaceFirstChar { it.uppercase() },
            color = QuailTextDim,
            style = MaterialTheme.typography.labelSmall,
        )
        exercise.instructions.forEachIndexed { i, step ->
            Row(modifier = Modifier.padding(top = 8.dp)) {
                Text("${i + 1}.", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(end = 6.dp))
                Text(step)
            }
        }
    }
}

// ---- Training plan: availability editor ----

private val PLAN_WEEKDAY_LABELS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

@Composable
private fun EditAvailabilitySheet(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    val availability by viewModel.availability.collectAsState()
    var selectedWeekdays by remember(availability) {
        mutableStateOf(
            availability?.weekdays?.filter { it.available }?.map { it.weekday }?.toSet()
                ?: setOf(0, 1, 2, 3, 4, 5, 6),
        )
    }

    SheetScaffold("Availability", onDismiss) {
        Text("Which days can you usually train?", color = QuailTextDim)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
            PLAN_WEEKDAY_LABELS.forEachIndexed { index, label ->
                val selected = index in selectedWeekdays
                Surface(
                    onClick = { selectedWeekdays = if (selected) selectedWeekdays - index else selectedWeekdays + index },
                    color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                    shape = RoundedCornerShape(999.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text(
                        label,
                        color = if (selected) Color.Black else Color.Unspecified,
                        fontWeight = FontWeight.SemiBold,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(vertical = 10.dp),
                    )
                }
            }
        }
        SaveButton("Save", enabled = selectedWeekdays.isNotEmpty()) {
            viewModel.saveAvailability(
                weekdays = (0..6).map { com.quail.android.data.model.WeekdayAvailability(it, it in selectedWeekdays) },
                unavailableDates = availability?.unavailableDates ?: emptyList(),
            )
            onDismiss()
        }
    }
}
