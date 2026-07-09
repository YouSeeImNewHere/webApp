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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.MonitorWeight
import androidx.compose.material.icons.filled.Settings
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import com.quail.android.data.model.DEFAULT_PROGRESSION_PATHS
import com.quail.android.data.model.FitnessGoalTypeOption
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.MilestoneRecord
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.exerciseById
import com.quail.android.data.model.frequencyAdvice
import com.quail.android.data.model.repRange
import com.quail.android.data.model.restAdvice
import com.quail.android.data.model.setsAdvice
import com.quail.android.data.model.strategyNotes
import com.quail.android.bugreport.BugReportTopBarAction
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

sealed interface FitnessSheet {
    data object AddGoal : FitnessSheet
    data object LogBodyweight : FitnessSheet
    data object AddMilestone : FitnessSheet
    data object CreateRoutine : FitnessSheet
    data class ScheduledWorkoutDetail(val record: com.quail.android.data.model.ScheduledWorkoutRecord) : FitnessSheet
    data object EditAvailability : FitnessSheet
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessScreen(
    viewModel: FitnessViewModel,
    onStartWorkout: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenCalendar: () -> Unit,
    onOpenAnalytics: () -> Unit,
    onOpenPlan: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val data by viewModel.uiState.collectAsState()
    val garminHealth by viewModel.garminHealth.collectAsState()
    var activeSheet by remember { mutableStateOf<FitnessSheet?>(null) }

    Scaffold(
        topBar = { FitnessTopBar(onOpenSettings) },
        bottomBar = {
            FitnessBottomBar(
                selectedTab = FitnessTab.HOME,
                onSelectHome = {},
                onSelectCalendar = onOpenCalendar,
                onSelectAnalytics = onOpenAnalytics,
                onSelectPlan = onOpenPlan,
                onOpenDashboard = onOpenDashboard,
            )
        },
    ) { padding ->
        if (data == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        } else {
            var isRefreshing by remember { mutableStateOf(false) }
            androidx.compose.material3.pulltorefresh.PullToRefreshBox(
                isRefreshing = isRefreshing,
                onRefresh = { viewModel.refresh(); isRefreshing = false },
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                FitnessContent(
                    data = data!!,
                    latestHealth = garminHealth.firstOrNull(),
                    padding = PaddingValues(0.dp),
                    onStartWorkout = onStartWorkout,
                    onOpenSheet = { activeSheet = it },
                    onDeleteSession = viewModel::deleteSession,
                    onDeleteRoutine = viewModel::deleteRoutine,
                    onDeleteGoal = viewModel::deleteGoal,
                    onDeleteMilestone = viewModel::deleteMilestone,
                    onStartFromRoutine = { routine -> viewModel.startWorkout(fromRoutine = routine); onStartWorkout() },
                )
            }
        }
    }

    activeSheet?.let { sheet ->
        FitnessSheetHost(sheet = sheet, viewModel = viewModel, onDismiss = { activeSheet = null })
    }
}

@Composable
fun FitnessTopBar(onOpenSettings: () -> Unit) {
    Surface(color = QuailSurface) {
        Box(modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 12.dp, vertical = 8.dp).height(40.dp)) {
            IconButton(onClick = onOpenSettings, modifier = Modifier.align(Alignment.CenterStart)) {
                Icon(Icons.Filled.Settings, contentDescription = "Settings")
            }
            Text(
                "Quail Fitness",
                fontWeight = FontWeight.ExtraBold,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.align(Alignment.Center),
            )
            Box(modifier = Modifier.align(Alignment.CenterEnd)) {
                BugReportTopBarAction()
            }
        }
    }
}

enum class FitnessTab { HOME, CALENDAR, ANALYTICS, PLAN }

@Composable
fun FitnessBottomBar(
    selectedTab: FitnessTab?,
    onSelectHome: () -> Unit,
    onSelectCalendar: () -> Unit,
    onSelectAnalytics: () -> Unit,
    onSelectPlan: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    Surface(color = QuailSurface) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FitnessBottomBarTab("Home", Icons.Filled.FitnessCenter, selected = selectedTab == FitnessTab.HOME, onClick = onSelectHome, modifier = Modifier.weight(1f))
            FitnessBottomBarTab("Plan", Icons.Filled.EmojiEvents, selected = selectedTab == FitnessTab.PLAN, onClick = onSelectPlan, modifier = Modifier.weight(1f))
            FitnessBottomBarTab("Calendar", Icons.Filled.CalendarMonth, selected = selectedTab == FitnessTab.CALENDAR, onClick = onSelectCalendar, modifier = Modifier.weight(1f))
            FitnessBottomBarTab("Analytics", Icons.Filled.BarChart, selected = selectedTab == FitnessTab.ANALYTICS, onClick = onSelectAnalytics, modifier = Modifier.weight(1f))
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
private fun FitnessBottomBarTab(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Surface(
        onClick = onClick,
        color = if (selected) QuailSurfaceRaised else Color.Transparent,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, contentDescription = label, tint = if (selected) MaterialTheme.colorScheme.onSurface else QuailTextDim)
            Text(label, color = if (selected) MaterialTheme.colorScheme.onSurface else QuailTextDim, style = MaterialTheme.typography.labelSmall)
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
    latestHealth: com.quail.android.data.model.GarminDailyHealthRecord?,
    padding: PaddingValues,
    onStartWorkout: () -> Unit,
    onOpenSheet: (FitnessSheet) -> Unit,
    onDeleteSession: (String) -> Unit,
    onDeleteRoutine: (String) -> Unit,
    onDeleteGoal: (String) -> Unit,
    onDeleteMilestone: (String) -> Unit,
    onStartFromRoutine: (RoutineRecord) -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { StartWorkoutCard(data, onStartWorkout) }
        if (latestHealth != null) {
            item { HealthMetricsSection(latestHealth) }
        }
        item { BodyweightCard(data, onOpenSheet) }
        item { ProgressionsSection(data) }
        item { WeeklyVolumeSection(data) }
        item { RoutinesSection(data.routines, onOpenSheet, onStartFromRoutine, onDeleteRoutine) }
        if (data.recentSessions.isNotEmpty()) {
            item { RecentSessionsSection(data.recentSessions, onDeleteSession) }
        }
        item { GoalsSection(data.goals, data.sessions, onOpenSheet, onDeleteGoal) }
        item { MilestonesSection(data.milestones, onOpenSheet, onDeleteMilestone) }
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

private fun formatHoursMinutes(seconds: Int?): String? {
    if (seconds == null || seconds <= 0) return null
    val h = seconds / 3600
    val m = (seconds % 3600) / 60
    return if (h > 0) "${h}h ${m}m" else "${m}m"
}

@Composable
private fun HealthMetricsSection(health: com.quail.android.data.model.GarminDailyHealthRecord) {
    Column {
        SectionHeader("Health (Garmin — ${health.date})")
        Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    HealthStat("Resting HR", health.restingHeartRate?.let { "$it bpm" } ?: "—")
                    HealthStat("VO2 Max", health.vo2Max?.let { "%.1f".format(it) } ?: "—")
                    HealthStat("Calories", health.totalCalories?.let { "$it" } ?: "—")
                    HealthStat("Stress", health.averageStressLevel?.let { "$it" } ?: "—")
                }

                if (health.totalSteps != null) {
                    Column(Modifier.padding(top = 16.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Steps", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            Text(
                                health.dailyStepGoal?.let { goal -> "${health.totalSteps} / $goal" } ?: "${health.totalSteps}",
                                fontWeight = FontWeight.SemiBold,
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                        LinearProgressIndicator(
                            progress = { (health.totalSteps.toFloat() / (health.dailyStepGoal ?: health.totalSteps).toFloat().coerceAtLeast(1f)).coerceAtMost(1f) },
                            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                            color = MaterialTheme.colorScheme.primary,
                            trackColor = QuailSurfaceRaised,
                        )
                    }
                }

                if (health.totalSleepSeconds != null) {
                    Column(Modifier.padding(top = 16.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Sleep", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            Text(formatHoursMinutes(health.totalSleepSeconds) ?: "—", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelSmall)
                        }
                        Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            listOfNotNull(
                                formatHoursMinutes(health.sleepDeepSeconds)?.let { "Deep $it" },
                                formatHoursMinutes(health.sleepLightSeconds)?.let { "Light $it" },
                                formatHoursMinutes(health.sleepRemSeconds)?.let { "REM $it" },
                                formatHoursMinutes(health.sleepAwakeSeconds)?.let { "Awake $it" },
                            ).forEach { label ->
                                Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                                    Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
                                }
                            }
                        }
                    }
                }

                if (health.bodyBatteryHighest != null || health.bodyBatteryLowest != null) {
                    Row(modifier = Modifier.fillMaxWidth().padding(top = 16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Body Battery", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                        Text(
                            "${health.bodyBatteryLowest ?: "—"} – ${health.bodyBatteryHighest ?: "—"}",
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HealthStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
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
private fun RoutinesSection(routines: List<RoutineRecord>, onOpenSheet: (FitnessSheet) -> Unit, onStart: (RoutineRecord) -> Unit, onDelete: (String) -> Unit) {
    Column {
        SectionHeader("Routines", actionLabel = "+ New") { onOpenSheet(FitnessSheet.CreateRoutine) }
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
private fun ProgressionsSection(data: FitnessData) {
    Column {
        SectionHeader("Progressions")
        Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DEFAULT_PROGRESSION_PATHS.forEach { path ->
                val step = currentProgressionStep(path, data.sessions, data.allExercises)
                Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.width(180.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text(path.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
                        if (step != null) {
                            val (exercise, index) = step
                            val total = path.exerciseIds.size
                            Text(
                                "Step ${index + 1} of $total",
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(top = 2.dp, bottom = 8.dp),
                            )
                            LinearProgressIndicator(
                                progress = { (index + 1).toFloat() / total.toFloat() },
                                modifier = Modifier.fillMaxWidth(),
                                color = MaterialTheme.colorScheme.primary,
                                trackColor = QuailSurfaceRaised,
                            )
                            Text(
                                exercise.name,
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(top = 8.dp),
                            )
                        } else {
                            Text("No data yet", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun WeeklyVolumeSection(data: FitnessData) {
    val volume = weeklyVolume(data.sessions, data.allExercises)
    val sorted = volume.entries.sortedByDescending { it.value }.take(6)
    if (sorted.isEmpty()) return
    val max = sorted.first().value.coerceAtLeast(1)

    Column {
        SectionHeader("This Week's Volume")
        Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                sorted.forEach { (muscle, reps) ->
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(muscle.displayName, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(90.dp))
                        androidx.compose.material3.LinearProgressIndicator(
                            progress = { reps.toFloat() / max.toFloat() },
                            modifier = Modifier.weight(1f),
                            color = MaterialTheme.colorScheme.primary,
                            trackColor = QuailSurfaceRaised,
                        )
                        Text("$reps", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.width(36.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                    }
                }
            }
        }
    }
}

private fun formatPace(secPerKm: Int?): String? {
    if (secPerKm == null || secPerKm <= 0) return null
    val min = secPerKm / 60
    val sec = secPerKm % 60
    return "%d:%02d /km".format(min, sec)
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
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (session.isFromGarmin) {
                                    Icon(
                                        Icons.Filled.DirectionsRun,
                                        contentDescription = "Synced from Garmin",
                                        tint = MaterialTheme.colorScheme.primary,
                                        modifier = Modifier.padding(end = 6.dp),
                                    )
                                }
                                Text(
                                    if (session.isFromGarmin) session.notes.ifBlank { "Run" } else session.date,
                                    fontWeight = FontWeight.SemiBold,
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                            val subtitle = if (session.isFromGarmin) {
                                listOfNotNull(
                                    session.date,
                                    session.distanceKm?.let { "%.2f km".format(it) },
                                    formatPace(session.avgPaceSecPerKm),
                                    session.avgHeartRate?.let { "$it bpm avg" },
                                    session.calories?.let { "$it cal" },
                                ).joinToString(" · ")
                            } else {
                                "${session.exercises.size} exercises · ${session.totalSets} sets · ${session.durationMinutes} min"
                            }
                            Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
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
private fun GoalsSection(goals: List<GoalRecord>, sessions: List<WorkoutSessionRecord>, onOpenSheet: (FitnessSheet) -> Unit, onDelete: (String) -> Unit) {
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
                        GoalRow(goal, sessions, onDelete)
                        if (idx < goals.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }
    }
}

@Composable
private fun GoalRow(goal: GoalRecord, sessions: List<WorkoutSessionRecord>, onDelete: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val goalType = runCatching { FitnessGoalTypeOption.valueOf(goal.goalType) }.getOrNull()
    val progress = progressForGoal(goal, sessions)

    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded },
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
        if (goal.targetExerciseId != null) {
            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                color = MaterialTheme.colorScheme.primary,
                trackColor = QuailSurfaceRaised,
            )
        }
        if (expanded && goalType != null) {
            Column(modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                Text("HOW TO GET THERE", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 6.dp))
                Text("Rep range: ${goalType.repRange}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text("Sets: ${goalType.setsAdvice}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text("Rest: ${goalType.restAdvice}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text("Frequency: ${goalType.frequencyAdvice}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                goalType.strategyNotes.forEach { note ->
                    Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                        Text("•", color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(end = 8.dp))
                        Text(note, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

@Composable
private fun MilestonesSection(milestones: List<MilestoneRecord>, onOpenSheet: (FitnessSheet) -> Unit, onDelete: (String) -> Unit) {
    Column {
        SectionHeader("Milestones", actionLabel = "+ New") { onOpenSheet(FitnessSheet.AddMilestone) }
        if (milestones.isEmpty()) {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Filled.EmojiEvents, contentDescription = null, tint = QuailTextDim)
                    Text("No milestones yet", color = QuailTextDim, modifier = Modifier.padding(top = 6.dp))
                }
            }
        } else {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column {
                    milestones.sortedByDescending { it.date }.forEachIndexed { idx, milestone ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(milestone.title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                Text(
                                    listOfNotNull(
                                        milestone.date,
                                        milestone.exerciseId?.let { exerciseById(it)?.name },
                                        milestone.notes.takeIf { it.isNotBlank() },
                                    ).joinToString(" · "),
                                    color = QuailTextDim,
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            }
                            Surface(onClick = { onDelete(milestone.clientId) }, color = Color.Transparent) {
                                Text("Delete", color = QuailTextDim, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
                            }
                        }
                        if (idx < milestones.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }
    }
}
