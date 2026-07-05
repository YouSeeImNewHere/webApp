package com.quail.android.ui.screens.fitness

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.core.net.toUri
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.Exercise
import com.quail.android.data.model.ExerciseCategory
import com.quail.android.data.model.ExerciseDifficulty
import com.quail.android.data.model.MuscleGroup
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.WorkoutSet
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

@Composable
fun ExerciseDetailSheet(
    exercise: Exercise,
    sessions: List<WorkoutSessionRecord>,
    personalBest: WorkoutSet?,
    onDelete: (() -> Unit)?,
    onDismiss: () -> Unit,
) {
    var showAllInstructions by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val recentSessions = sessions
        .filter { session -> session.exercises.any { it.exerciseId == exercise.id } }
        .sortedByDescending { it.date }
        .take(5)

    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text(exercise.name, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(
                "${exercise.category.displayName} · ${exercise.difficulty.displayName}",
                color = QuailTextDim,
                modifier = Modifier.padding(top = 4.dp, bottom = 12.dp),
            )

            if (exercise.muscleGroups.isNotEmpty()) {
                Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    exercise.muscleGroups.forEach { mg ->
                        Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                            Text(mg.displayName, color = QuailTextDim, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
                        }
                    }
                }
            }

            personalBest?.let { pb ->
                Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().padding(top = 16.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text("PERSONAL BEST", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                        Text(
                            pb.reps?.let { "$it reps" } ?: pb.durationSeconds?.let { "$it sec" } ?: "—",
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                }
            }

            exercise.videoUrl?.let { url ->
                Surface(
                    onClick = { runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri())) } },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                ) {
                    Row(Modifier.padding(vertical = 12.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.PlayCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        Text("Watch Tutorial", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
                    }
                }
            }

            if (exercise.instructions.isNotEmpty()) {
                Text("HOW TO PERFORM", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 20.dp, bottom = 8.dp))
                val steps = if (showAllInstructions) exercise.instructions else exercise.instructions.take(3)
                steps.forEachIndexed { idx, step ->
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                        Text("${idx + 1}.", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 8.dp))
                        Text(step, modifier = Modifier.weight(1f))
                    }
                }
                if (exercise.instructions.size > 3) {
                    Surface(onClick = { showAllInstructions = !showAllInstructions }, color = Color.Transparent, modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
                        Text(
                            if (showAllInstructions) "Show Less" else "Show All ${exercise.instructions.size} Steps",
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
            }

            if (recentSessions.isNotEmpty()) {
                Text("RECENT PERFORMANCE", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 20.dp, bottom = 8.dp))
                Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(vertical = 6.dp)) {
                        recentSessions.forEachIndexed { idx, session ->
                            val entry = session.exercises.first { it.exerciseId == exercise.id }
                            val bestSet = entry.sets.filter { it.isCompleted }.maxByOrNull { (it.reps ?: 0) + (it.durationSeconds ?: 0) }
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text(session.date, color = QuailTextDim)
                                Text(
                                    bestSet?.reps?.let { "$it reps" } ?: bestSet?.durationSeconds?.let { "$it sec" } ?: "${entry.sets.size} sets",
                                    fontWeight = FontWeight.SemiBold,
                                )
                            }
                            if (idx < recentSessions.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                        }
                    }
                }
            }

            if (onDelete != null) {
                Surface(
                    onClick = onDelete,
                    color = Color.Transparent,
                    modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
                ) {
                    Text(
                        "Delete Custom Exercise",
                        color = QuailBadRed,
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
fun CreateCustomExerciseSheet(
    onDismiss: () -> Unit,
    onSave: (
        name: String, category: String, muscleGroups: List<String>, difficulty: String,
        instructions: List<String>, videoUrl: String?, isTimed: Boolean,
        defaultSets: Int, defaultReps: Int, defaultDurationSeconds: Int,
    ) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var category by remember { mutableStateOf(ExerciseCategory.PUSH) }
    var difficulty by remember { mutableStateOf(ExerciseDifficulty.BEGINNER) }
    val selectedMuscles = remember { mutableStateOf(setOf<MuscleGroup>()) }
    var instructions by remember { mutableStateOf(listOf("")) }
    var videoUrl by remember { mutableStateOf("") }
    var isTimed by remember { mutableStateOf(false) }
    var defaultSets by remember { mutableStateOf("3") }
    var defaultReps by remember { mutableStateOf("10") }
    var defaultDuration by remember { mutableStateOf("30") }

    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text("Create Exercise", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))

            OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())

            Text("Category", color = QuailTextDim, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ExerciseCategory.entries.forEach { cat ->
                    Surface(
                        onClick = { category = cat },
                        color = if (category == cat) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                        shape = RoundedCornerShape(999.dp),
                    ) {
                        Text(
                            cat.displayName,
                            color = if (category == cat) Color.Black else QuailTextDim,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        )
                    }
                }
            }

            Text("Difficulty", color = QuailTextDim, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ExerciseDifficulty.entries.forEach { diff ->
                    Surface(
                        onClick = { difficulty = diff },
                        color = if (difficulty == diff) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                        shape = RoundedCornerShape(999.dp),
                    ) {
                        Text(
                            diff.displayName,
                            color = if (difficulty == diff) Color.Black else QuailTextDim,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        )
                    }
                }
            }

            Text("Muscle Groups", color = QuailTextDim, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                MuscleGroup.entries.forEach { mg ->
                    val selected = mg in selectedMuscles.value
                    Surface(
                        onClick = { selectedMuscles.value = if (selected) selectedMuscles.value - mg else selectedMuscles.value + mg },
                        color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                        shape = RoundedCornerShape(999.dp),
                    ) {
                        Text(
                            mg.displayName,
                            color = if (selected) Color.Black else QuailTextDim,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        )
                    }
                }
            }

            Row(modifier = Modifier.fillMaxWidth().padding(top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = isTimed, onCheckedChange = { isTimed = it })
                Text("Timed exercise (seconds, not reps)")
            }

            Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = defaultSets, onValueChange = { defaultSets = it.filter(Char::isDigit) },
                    label = { Text("Sets") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.weight(1f),
                )
                if (isTimed) {
                    OutlinedTextField(
                        value = defaultDuration, onValueChange = { defaultDuration = it.filter(Char::isDigit) },
                        label = { Text("Seconds") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                } else {
                    OutlinedTextField(
                        value = defaultReps, onValueChange = { defaultReps = it.filter(Char::isDigit) },
                        label = { Text("Reps") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            OutlinedTextField(
                value = videoUrl, onValueChange = { videoUrl = it },
                label = { Text("Video URL (optional)") }, singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )

            Text("Instructions", color = QuailTextDim, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            instructions.forEachIndexed { idx, step ->
                Row(modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = step,
                        onValueChange = { new -> instructions = instructions.toMutableList().also { it[idx] = new } },
                        label = { Text("Step ${idx + 1}") },
                        modifier = Modifier.weight(1f),
                    )
                    if (instructions.size > 1) {
                        Surface(onClick = { instructions = instructions.filterIndexed { i, _ -> i != idx } }, color = Color.Transparent) {
                            Text("✕", color = QuailTextDim, modifier = Modifier.padding(8.dp))
                        }
                    }
                }
            }
            Surface(onClick = { instructions = instructions + "" }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                Text("+ Add Step", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
            }

            Surface(
                onClick = {
                    onSave(
                        name, category.name, selectedMuscles.value.map { it.name }, difficulty.name,
                        instructions, videoUrl.takeUnless { it.isBlank() }, isTimed,
                        defaultSets.toIntOrNull() ?: 3, defaultReps.toIntOrNull() ?: 10, defaultDuration.toIntOrNull() ?: 30,
                    )
                },
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
            ) {
                Text(
                    "Save Exercise",
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
