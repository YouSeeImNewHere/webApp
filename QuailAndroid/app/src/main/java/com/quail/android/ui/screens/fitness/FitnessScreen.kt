package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.MonitorWeight
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.exerciseById
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

sealed interface FitnessSheet {
    data object AddGoal : FitnessSheet
    data object LogBodyweight : FitnessSheet
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessScreen(
    viewModel: FitnessViewModel,
    onStartWorkout: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val data by viewModel.uiState.collectAsState()
    var activeSheet by remember { mutableStateOf<FitnessSheet?>(null) }

    Scaffold(
        topBar = { FitnessTopBar() },
        bottomBar = { FitnessBottomBar(onOpenDashboard) },
    ) { padding ->
        if (data == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        } else {
            FitnessContent(
                data = data!!,
                padding = padding,
                onStartWorkout = onStartWorkout,
                onOpenSheet = { activeSheet = it },
                onDeleteSession = viewModel::deleteSession,
                onDeleteRoutine = viewModel::deleteRoutine,
                onDeleteGoal = viewModel::deleteGoal,
                onStartFromRoutine = { routine -> viewModel.startWorkout(fromRoutine = routine); onStartWorkout() },
            )
        }
    }

    activeSheet?.let { sheet ->
        FitnessSheetHost(sheet = sheet, viewModel = viewModel, onDismiss = { activeSheet = null })
    }
}

@Composable
private fun FitnessTopBar() {
    Surface(color = QuailSurface) {
        Box(modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(vertical = 8.dp).height(40.dp), contentAlignment = Alignment.Center) {
            Text("Quail Fitness", fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.titleLarge)
        }
    }
}

@Composable
private fun FitnessBottomBar(onOpenDashboard: () -> Unit) {
    Surface(color = QuailSurface) {
        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp), horizontalArrangement = Arrangement.End) {
            Surface(onClick = onOpenDashboard, color = MaterialTheme.colorScheme.primary, shape = RoundedCornerShape(12.dp)) {
                Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Dashboard, contentDescription = null, tint = Color.Black)
                    Text("Dashboard", color = Color.Black, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 6.dp))
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(title: String, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(title, color = QuailTextDim, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
        if (actionLabel != null && onAction != null) {
            Surface(onClick = onAction, color = Color.Transparent) {
                Text(actionLabel, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

@Composable
private fun FitnessContent(
    data: FitnessData,
    padding: PaddingValues,
    onStartWorkout: () -> Unit,
    onOpenSheet: (FitnessSheet) -> Unit,
    onDeleteSession: (String) -> Unit,
    onDeleteRoutine: (String) -> Unit,
    onDeleteGoal: (String) -> Unit,
    onStartFromRoutine: (RoutineRecord) -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { StartWorkoutCard(data, onStartWorkout) }
        item { BodyweightCard(data, onOpenSheet) }
        item { RoutinesSection(data.routines, onStartFromRoutine, onDeleteRoutine) }
        if (data.recentSessions.isNotEmpty()) {
            item { RecentSessionsSection(data.recentSessions, onDeleteSession) }
        }
        item { GoalsSection(data.goals, onOpenSheet, onDeleteGoal) }
    }
}

@Composable
private fun StartWorkoutCard(data: FitnessData, onStartWorkout: () -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column {
                    Text("${data.workoutsThisWeek} workouts this week", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("${data.sessions.size} total logged", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
                Icon(Icons.Filled.FitnessCenter, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            }
            Surface(
                onClick = onStartWorkout,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    Text("Start Workout", color = Color.Black, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun BodyweightCard(data: FitnessData, onOpenSheet: (FitnessSheet) -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Filled.MonitorWeight, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Column {
                    Text(
                        data.latestBodyweightKg?.let { "%.1f kg".format(it) } ?: "No weight logged",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text("Body weight", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            Surface(onClick = { onOpenSheet(FitnessSheet.LogBodyweight) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                Text("Log Weight", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
            }
        }
    }
}

@Composable
private fun RoutinesSection(routines: List<RoutineRecord>, onStart: (RoutineRecord) -> Unit, onDelete: (String) -> Unit) {
    Column {
        SectionHeader("Routines")
        if (routines.isEmpty()) {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Text(
                    "Finish a workout and save it as a routine to see it here.",
                    color = QuailTextDim,
                    modifier = Modifier.fillMaxWidth().padding(20.dp),
                )
            }
        } else {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column {
                    routines.forEachIndexed { idx, routine ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(routine.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                Text("${routine.exercises.size} exercises", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Surface(onClick = { onStart(routine) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                                    Text("Start", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
                                }
                                Surface(onClick = { onDelete(routine.clientId) }, color = Color.Transparent) {
                                    Text("Delete", color = QuailTextDim, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
                                }
                            }
                        }
                        if (idx < routines.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }
    }
}

@Composable
private fun RecentSessionsSection(sessions: List<WorkoutSessionRecord>, onDelete: (String) -> Unit) {
    Column {
        SectionHeader("Recent Sessions")
        Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
            Column {
                sessions.forEachIndexed { idx, session ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(session.date, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                            Text(
                                "${session.exercises.size} exercises · ${session.totalSets} sets · ${session.durationMinutes} min",
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                        Surface(onClick = { onDelete(session.clientId) }, color = Color.Transparent) {
                            Text("Delete", color = QuailTextDim, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
                        }
                    }
                    if (idx < sessions.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                }
            }
        }
    }
}

@Composable
private fun GoalsSection(goals: List<GoalRecord>, onOpenSheet: (FitnessSheet) -> Unit, onDelete: (String) -> Unit) {
    Column {
        SectionHeader("Goals", actionLabel = "+ New") { onOpenSheet(FitnessSheet.AddGoal) }
        if (goals.isEmpty()) {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Filled.EmojiEvents, contentDescription = null, tint = QuailTextDim)
                    Text("No goals yet", color = QuailTextDim, modifier = Modifier.padding(top = 6.dp))
                }
            }
        } else {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column {
                    goals.forEachIndexed { idx, goal ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(goal.title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                Text(
                                    listOfNotNull(
                                        goal.targetExerciseId?.let { exerciseById(it)?.name },
                                        goal.targetReps?.let { "$it reps" },
                                        goal.targetDurationSeconds?.let { "${it}s" },
                                        goal.targetDate,
                                    ).joinToString(" · "),
                                    color = QuailTextDim,
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            }
                            Surface(onClick = { onDelete(goal.clientId) }, color = Color.Transparent) {
                                Text("Delete", color = QuailTextDim, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
                            }
                        }
                        if (idx < goals.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }
    }
}
