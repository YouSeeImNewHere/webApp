package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
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
import com.quail.android.data.model.Exercise
import com.quail.android.data.model.ExerciseCategory
import com.quail.android.data.model.WorkoutExerciseEntry
import com.quail.android.data.model.WorkoutSet
import com.quail.android.data.model.exerciseById
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.util.UUID

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessActiveWorkoutScreen(viewModel: FitnessViewModel, onFinished: () -> Unit, onCancelled: () -> Unit) {
    val workout by viewModel.activeWorkout.collectAsState()
    var showExercisePicker by remember { mutableStateOf(false) }
    var showFinishDialog by remember { mutableStateOf(false) }

    val current = workout ?: run { onCancelled(); return }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Active Workout", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = { viewModel.cancelWorkout(); onCancelled() }) { Icon(Icons.Filled.Close, contentDescription = "Cancel") } },
                actions = {
                    Surface(onClick = { showFinishDialog = true }, color = MaterialTheme.colorScheme.primary, shape = RoundedCornerShape(999.dp)) {
                        Text("Finish", color = Color.Black, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(current.exercises, key = { it.id }) { entry ->
                ActiveExerciseCard(
                    entry = entry,
                    onUpdate = { update -> viewModel.updateActiveWorkoutExercise(entry.id, update) },
                    onRemove = { viewModel.removeActiveWorkoutExercise(entry.id) },
                )
            }
            item {
                Surface(
                    onClick = { showExercisePicker = true },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Box(Modifier.fillMaxWidth().padding(vertical = 14.dp), contentAlignment = Alignment.Center) {
                        Text("+ Add Exercise", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }

    if (showExercisePicker) {
        ExercisePickerSheet(
            onDismiss = { showExercisePicker = false },
            onSelect = { exercise -> viewModel.addExerciseToActiveWorkout(exercise); showExercisePicker = false },
        )
    }

    if (showFinishDialog) {
        FinishWorkoutSheet(
            onDismiss = { showFinishDialog = false },
            onConfirm = { durationMinutes, notes, saveAsRoutineName ->
                if (!saveAsRoutineName.isNullOrBlank()) {
                    viewModel.saveRoutineFromWorkout(saveAsRoutineName, current.exercises)
                }
                viewModel.finishWorkout(durationMinutes, notes)
                showFinishDialog = false
                onFinished()
            },
        )
    }
}

@Composable
private fun ActiveExerciseCard(entry: WorkoutExerciseEntry, onUpdate: ((WorkoutExerciseEntry) -> WorkoutExerciseEntry) -> Unit, onRemove: () -> Unit) {
    val exercise = exerciseById(entry.exerciseId)
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(exercise?.name ?: "Exercise", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
                Surface(onClick = onRemove, color = Color.Transparent) {
                    Text("Remove", color = QuailBadRed, style = MaterialTheme.typography.labelSmall)
                }
            }
            HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(vertical = 8.dp))
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                entry.sets.forEachIndexed { idx, set ->
                    SetRow(
                        index = idx + 1,
                        set = set,
                        isTimed = exercise?.isTimedExercise == true,
                        onChange = { newSet ->
                            onUpdate { e -> e.copy(sets = e.sets.toMutableList().also { it[idx] = newSet }) }
                        },
                        onRemove = {
                            onUpdate { e -> e.copy(sets = e.sets.filterIndexed { i, _ -> i != idx }) }
                        },
                    )
                }
            }
            Surface(
                onClick = {
                    val templateSet = entry.sets.lastOrNull()
                    val newSet = WorkoutSet(
                        id = UUID.randomUUID().toString(),
                        reps = if (exercise?.isTimedExercise != true) (templateSet?.reps ?: exercise?.defaultReps ?: 10) else null,
                        durationSeconds = if (exercise?.isTimedExercise == true) (templateSet?.durationSeconds ?: exercise.defaultDurationSeconds) else null,
                    )
                    onUpdate { e -> e.copy(sets = e.sets + newSet) }
                },
                color = Color.Transparent,
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
            ) {
                Text("+ Add Set", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}

@Composable
private fun SetRow(index: Int, set: WorkoutSet, isTimed: Boolean, onChange: (WorkoutSet) -> Unit, onRemove: () -> Unit) {
    var valueText by remember(set.id) { mutableStateOf((if (isTimed) set.durationSeconds else set.reps)?.toString() ?: "") }
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("$index", color = QuailTextDim, modifier = Modifier.padding(end = 2.dp))
        OutlinedTextField(
            value = valueText,
            onValueChange = { new ->
                valueText = new.filter(Char::isDigit)
                val intVal = valueText.toIntOrNull()
                onChange(if (isTimed) set.copy(durationSeconds = intVal) else set.copy(reps = intVal))
            },
            label = { Text(if (isTimed) "sec" else "reps") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = { onChange(set.copy(isCompleted = !set.isCompleted)) }) {
            Icon(
                if (set.isCompleted) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
                contentDescription = "Completed",
                tint = if (set.isCompleted) QuailGoodGreen else QuailTextDim,
            )
        }
        Surface(onClick = onRemove, color = Color.Transparent) {
            Text("✕", color = QuailTextDim, modifier = Modifier.padding(8.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ExercisePickerSheet(onDismiss: () -> Unit, onSelect: (Exercise) -> Unit) {
    var category by remember { mutableStateOf<ExerciseCategory?>(null) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp).padding(bottom = 24.dp)) {
            Text("Add Exercise", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))
            Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CategoryChip("All", category == null) { category = null }
                ExerciseCategory.entries.forEach { cat ->
                    CategoryChip(cat.displayName, category == cat) { category = cat }
                }
            }
            Column(
                modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(top = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                DEFAULT_EXERCISES.filter { category == null || it.category == category }.forEach { exercise ->
                    Surface(onClick = { onSelect(exercise) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column {
                                Text(exercise.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                Text("${exercise.category.displayName} · ${exercise.difficulty.displayName}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CategoryChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(999.dp),
    ) {
        Text(
            label,
            color = if (selected) Color.Black else QuailTextDim,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FinishWorkoutSheet(onDismiss: () -> Unit, onConfirm: (durationMinutes: Int, notes: String, routineName: String?) -> Unit) {
    var duration by remember { mutableStateOf("30") }
    var notes by remember { mutableStateOf("") }
    var saveAsRoutine by remember { mutableStateOf(false) }
    var routineName by remember { mutableStateOf("") }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text("Finish Workout", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))
            OutlinedTextField(
                value = duration,
                onValueChange = { duration = it.filter(Char::isDigit) },
                label = { Text("Duration (minutes)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it },
                label = { Text("Notes (optional)") },
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )
            Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = saveAsRoutine, onCheckedChange = { saveAsRoutine = it })
                Text("Save as routine")
            }
            if (saveAsRoutine) {
                OutlinedTextField(
                    value = routineName,
                    onValueChange = { routineName = it },
                    label = { Text("Routine name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                )
            }
            Surface(
                onClick = { onConfirm(duration.toIntOrNull() ?: 0, notes, if (saveAsRoutine) routineName else null) },
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            ) {
                Text(
                    "Finish",
                    fontWeight = FontWeight.Bold,
                    color = Color.Black,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
                )
            }
        }
    }
}
