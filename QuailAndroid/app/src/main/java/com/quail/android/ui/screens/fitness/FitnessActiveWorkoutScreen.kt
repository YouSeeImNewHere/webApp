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
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.DEFAULT_EXERCISES
import com.quail.android.data.model.Exercise
import com.quail.android.data.model.ExerciseCategory
import com.quail.android.data.model.WorkoutExerciseEntry
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.WorkoutSet
import com.quail.android.data.model.exerciseById
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.delay
import java.util.UUID
import com.quail.android.bugreport.BugReportTopBarAction

private const val FITNESS_PREFS_NAME = "quail_fitness_prefs"
private const val KEY_LAST_REST_SECONDS = "last_rest_seconds"

private fun getLastRestSeconds(context: android.content.Context): Int =
    context.getSharedPreferences(FITNESS_PREFS_NAME, android.content.Context.MODE_PRIVATE).getInt(KEY_LAST_REST_SECONDS, 60)

private fun setLastRestSeconds(context: android.content.Context, seconds: Int) {
    context.getSharedPreferences(FITNESS_PREFS_NAME, android.content.Context.MODE_PRIVATE).edit().putInt(KEY_LAST_REST_SECONDS, seconds).apply()
}

private fun formatElapsed(seconds: Int): String {
    val m = seconds / 60
    val s = seconds % 60
    return "%d:%02d".format(m, s)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessActiveWorkoutScreen(viewModel: FitnessViewModel, onFinished: () -> Unit, onCancelled: () -> Unit) {
    val workout by viewModel.activeWorkout.collectAsState()
    val data by viewModel.uiState.collectAsState()
    var showExercisePicker by remember { mutableStateOf(false) }
    var showFinishDialog by remember { mutableStateOf(false) }
    var showCreateCustomExercise by remember { mutableStateOf(false) }
    var viewingExercise by remember { mutableStateOf<Exercise?>(null) }

    val current = workout ?: run { onCancelled(); return }
    val customExercises = data?.customExercises ?: emptyList()
    val sessions = data?.sessions ?: emptyList()

    var elapsedSeconds by remember { mutableIntStateOf(((System.currentTimeMillis() - current.startedAtMillis) / 1000).toInt()) }
    LaunchedEffect(current.startedAtMillis) {
        while (true) {
            elapsedSeconds = ((System.currentTimeMillis() - current.startedAtMillis) / 1000).toInt()
            delay(1000)
        }
    }
    val totalSetsDone = current.exercises.sumOf { it.sets.count(WorkoutSet::isCompleted) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Active Workout", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = { viewModel.cancelWorkout(); onCancelled() }) { Icon(Icons.Filled.Close, contentDescription = "Cancel") } },
                actions = {
                    BugReportTopBarAction()
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
            item { ElapsedTimerHeader(elapsedSeconds = elapsedSeconds, setsDone = totalSetsDone) }
            items(current.exercises, key = { it.id }) { entry ->
                ActiveExerciseCard(
                    entry = entry,
                    customExercises = customExercises,
                    onUpdate = { update -> viewModel.updateActiveWorkoutExercise(entry.id, update) },
                    onRemove = { viewModel.removeActiveWorkoutExercise(entry.id) },
                    onShowInfo = { viewingExercise = exerciseById(entry.exerciseId, customExercises) },
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
            customExercises = customExercises,
            sessions = sessions,
            onDismiss = { showExercisePicker = false },
            onSelect = { exercise -> viewModel.addExerciseToActiveWorkout(exercise); showExercisePicker = false },
            onShowInfo = { exercise -> viewingExercise = exercise },
            onCreateCustomExercise = {
                showExercisePicker = false
                showCreateCustomExercise = true
            },
        )
    }

    if (showCreateCustomExercise) {
        CreateCustomExerciseSheet(
            onDismiss = { showCreateCustomExercise = false },
            onSave = { name, category, muscleGroups, difficulty, instructions, videoUrl, isTimed, sets, reps, duration ->
                viewModel.saveCustomExercise(name, category, muscleGroups, difficulty, instructions, videoUrl, isTimed, sets, reps, duration)
                showCreateCustomExercise = false
            },
        )
    }

    viewingExercise?.let { exercise ->
        ExerciseDetailSheet(
            exercise = exercise,
            sessions = sessions,
            personalBest = personalBest(exercise.id, sessions),
            onDelete = if (exercise.isCustom) {
                { exercise.customClientId?.let { viewModel.deleteCustomExercise(it) }; viewingExercise = null }
            } else null,
            onDismiss = { viewingExercise = null },
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
private fun ElapsedTimerHeader(elapsedSeconds: Int, setsDone: Int) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(formatElapsed(elapsedSeconds), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                Text("Elapsed", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("$setsDone", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                Text("Sets Done", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun ActiveExerciseCard(
    entry: WorkoutExerciseEntry,
    customExercises: List<Exercise>,
    onUpdate: ((WorkoutExerciseEntry) -> WorkoutExerciseEntry) -> Unit,
    onRemove: () -> Unit,
    onShowInfo: () -> Unit,
) {
    val exercise = exerciseById(entry.exerciseId, customExercises)
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(exercise?.name ?: "Exercise", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
                    IconButton(onClick = onShowInfo, modifier = Modifier.padding(start = 2.dp)) {
                        Icon(Icons.Filled.Info, contentDescription = "How to perform", tint = QuailTextDim)
                    }
                }
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
    val context = LocalContext.current
    var lastRestSeconds by remember { mutableIntStateOf(getLastRestSeconds(context)) }

    Column(modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            // Was a bare "$index" with no label - a real user mistook the
            // set-row number itself for a prescribed value ("it says 4").
            Text("Set $index", color = QuailTextDim, modifier = Modifier.padding(end = 2.dp))
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
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 32.dp, top = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Icon(Icons.Filled.Timer, contentDescription = null, tint = QuailTextDim, modifier = Modifier.padding(end = 0.dp))
            Text("Rest:", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            IconButton(onClick = {
                val newVal = ((set.restSeconds ?: lastRestSeconds) - 15).coerceAtLeast(0)
                onChange(set.copy(restSeconds = newVal))
                lastRestSeconds = newVal
                setLastRestSeconds(context, newVal)
            }) {
                Text("–", color = QuailTextDim)
            }
            Text(
                set.restSeconds?.let { "${it}s" } ?: "–",
                color = QuailTextDim,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.labelSmall,
            )
            IconButton(onClick = {
                val newVal = ((set.restSeconds ?: lastRestSeconds) + 15).coerceAtMost(600)
                onChange(set.copy(restSeconds = newVal))
                lastRestSeconds = newVal
                setLastRestSeconds(context, newVal)
            }) {
                Text("+", color = QuailTextDim)
            }
            if (set.restSeconds == null) {
                Surface(
                    onClick = {
                        onChange(set.copy(restSeconds = lastRestSeconds))
                    },
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.10f),
                    shape = RoundedCornerShape(999.dp),
                ) {
                    Text(
                        "Use ${lastRestSeconds}s",
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                    )
                }
            }
        }
    }
}

@Composable
fun ExercisePickerSheet(
    customExercises: List<Exercise>,
    sessions: List<WorkoutSessionRecord>,
    onDismiss: () -> Unit,
    onSelect: (Exercise) -> Unit,
    onShowInfo: (Exercise) -> Unit,
    onCreateCustomExercise: () -> Unit,
) {
    var category by remember { mutableStateOf<ExerciseCategory?>(null) }
    val allExercises = DEFAULT_EXERCISES + customExercises
    val content: @Composable () -> Unit = {
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
                allExercises.filter { category == null || it.category == category }.forEach { exercise ->
                    Surface(onClick = { onSelect(exercise) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column {
                                Text(exercise.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                val pb = personalBest(exercise.id, sessions)
                                val pbText = pb?.reps?.let { "PB: $it reps" } ?: pb?.durationSeconds?.let { "PB: $it sec" }
                                Text(
                                    listOfNotNull("${exercise.category.displayName} · ${exercise.difficulty.displayName}", pbText).joinToString(" · "),
                                    color = QuailTextDim,
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            }
                            IconButton(onClick = { onShowInfo(exercise) }) {
                                Icon(Icons.Filled.Info, contentDescription = "How to perform", tint = QuailTextDim)
                            }
                        }
                    }
                }
                Surface(
                    onClick = onCreateCustomExercise,
                    color = Color.Transparent,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                ) {
                    Text(
                        "+ Create Custom Exercise",
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
                    )
                }
            }
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
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

@Composable
private fun FinishWorkoutSheet(onDismiss: () -> Unit, onConfirm: (durationMinutes: Int, notes: String, routineName: String?) -> Unit) {
    var duration by remember { mutableStateOf("30") }
    var notes by remember { mutableStateOf("") }
    var saveAsRoutine by remember { mutableStateOf(false) }
    var routineName by remember { mutableStateOf("") }

    val content: @Composable () -> Unit = {
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
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}
