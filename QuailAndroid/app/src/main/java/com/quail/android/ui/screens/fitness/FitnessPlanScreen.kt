package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Autorenew
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.ScheduledWorkoutRecord
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessPlanScreen(
    viewModel: FitnessViewModel,
    onOpenHome: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenCalendar: () -> Unit,
    onOpenAnalytics: () -> Unit,
    onOpenGoalSetupWizard: () -> Unit,
    onOpenDashboard: () -> Unit,
    onStartWorkout: () -> Unit,
) {
    val planState by viewModel.planState.collectAsState()
    val actionInFlight by viewModel.planActionInFlight.collectAsState()
    var activeSheet by remember { mutableStateOf<FitnessSheet?>(null) }

    Scaffold(
        topBar = { FitnessTopBar(onOpenSettings) },
        bottomBar = {
            FitnessBottomBar(
                selectedTab = FitnessTab.PLAN,
                onSelectHome = onOpenHome,
                onSelectCalendar = onOpenCalendar,
                onSelectAnalytics = onOpenAnalytics,
                onSelectPlan = {},
                onOpenDashboard = onOpenDashboard,
            )
        },
    ) { padding ->
        when (val state = planState) {
            is TrainingPlanUiState.Loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            is TrainingPlanUiState.Error -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(state.message, color = QuailBadRed)
                    Button(onClick = { viewModel.loadPlan() }, modifier = Modifier.padding(top = 12.dp)) { Text("Retry") }
                }
            }
            is TrainingPlanUiState.None -> NoPlanContent(padding, state.hasGoals, onOpenGoalSetupWizard)
            is TrainingPlanUiState.Testing -> TestingWeekContent(
                padding, state.scheduled, actionInFlight,
                onOpenDetail = { activeSheet = FitnessSheet.ScheduledWorkoutDetail(it) },
                onGenerate = { viewModel.generateTrainingPlan() },
            )
            is TrainingPlanUiState.Active -> ActivePlanContent(
                padding, state.scheduled,
                onOpenDetail = { activeSheet = FitnessSheet.ScheduledWorkoutDetail(it) },
                onEditAvailability = { activeSheet = FitnessSheet.EditAvailability },
                onRegenerate = { viewModel.generateTrainingPlan() },
                onOpenExerciseInfo = { activeSheet = FitnessSheet.ExerciseInfo(it) },
            )
        }
    }

    activeSheet?.let { sheet ->
        FitnessSheetHost(
            sheet = sheet,
            viewModel = viewModel,
            onDismiss = { activeSheet = null; viewModel.loadPlan() },
            onStartWorkout = onStartWorkout,
        )
    }
}

@Composable
private fun NoPlanContent(padding: PaddingValues, hasGoals: Boolean, onOpenGoalSetupWizard: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.CalendarMonth, contentDescription = null, modifier = Modifier.padding(bottom = 12.dp))
        Text("No training plan yet", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
        Text(
            "Set your running, push-up, and L-sit goals and we'll build a concrete weekly schedule toward all of them.",
            color = QuailTextDim,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            modifier = Modifier.padding(top = 8.dp, bottom = 20.dp),
        )
        Button(onClick = onOpenGoalSetupWizard) { Text(if (hasGoals) "Restart Training Plan" else "Set Up Training Plan") }
    }
}

@Composable
private fun TestingWeekContent(
    padding: PaddingValues,
    scheduled: List<ScheduledWorkoutRecord>,
    actionInFlight: Boolean,
    onOpenDetail: (ScheduledWorkoutRecord) -> Unit,
    onGenerate: () -> Unit,
) {
    val allDone = scheduled.isNotEmpty() && scheduled.all { it.status == "COMPLETED" || it.status == "SKIPPED" }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text(
                "Testing week — a few quick baseline tests so your plan starts from where you really are.",
                color = QuailTextDim,
            )
        }
        items(scheduled.sortedBy { it.scheduledDate }, key = { it.id }) { record ->
            ScheduledWorkoutRow(record, onClick = { onOpenDetail(record) })
        }
        item {
            Button(
                onClick = onGenerate,
                enabled = allDone && !actionInFlight,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            ) {
                Text(if (actionInFlight) "Generating..." else "Generate My Plan")
            }
        }
    }
}

@Composable
private fun ScheduledWorkoutRow(record: ScheduledWorkoutRecord, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = QuailSurfaceRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(record.workoutType.replace('_', ' ').lowercase().replaceFirstChar { it.uppercase() }, fontWeight = FontWeight.SemiBold)
                Text(prescriptionSummary(record.workoutType, record.prescription), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            StatusBadge(record.status)
        }
    }
}

/** One flattened, individually-tappable exercise within a scheduled day -
 * either one block of a bundled "session" prescription, or the whole
 * prescription itself for legacy single-exercise / run / test rows. Tapping
 * opens the exercise's how-to instructions when we know its catalog id. */
private data class DayExerciseItem(
    val label: String,
    val detail: String,
    val estimatedSeconds: Int,
    val exerciseId: String?,
)

private fun exerciseItemsFor(record: ScheduledWorkoutRecord): List<DayExerciseItem> {
    val prescription = record.prescription
    return if (prescription.str("type") == "session") {
        prescription.blocks().map { block ->
            val setsList = block.setsList()
            val setsDesc = if (setsList.isNotEmpty()) {
                setsList.joinToString(", ") { s -> s.holdSeconds?.let { "${it}s" } ?: s.reps?.let { "$it reps" } ?: "?" }
            } else ""
            DayExerciseItem(
                label = blockLabel(block),
                detail = setsDesc,
                estimatedSeconds = estimatedSecondsForBlock(block),
                exerciseId = block.str("exercise_id"),
            )
        }
    } else {
        listOf(
            DayExerciseItem(
                label = record.workoutType.replace('_', ' ').lowercase().replaceFirstChar { it.uppercase() },
                detail = prescriptionSummary(record.workoutType, prescription),
                estimatedSeconds = estimatedSecondsForPrescription(prescription),
                exerciseId = prescription.str("exercise_id"),
            ),
        )
    }
}

@Composable
private fun ActivePlanContent(
    padding: PaddingValues,
    scheduled: List<ScheduledWorkoutRecord>,
    onOpenDetail: (ScheduledWorkoutRecord) -> Unit,
    onEditAvailability: () -> Unit,
    onRegenerate: () -> Unit,
    onOpenExerciseInfo: (String) -> Unit,
) {
    val today = LocalDate.now()
    val upcoming = scheduled
        .filter { runCatching { LocalDate.parse(it.scheduledDate) }.getOrNull()?.let { d -> !d.isBefore(today) } == true }
        .sortedBy { it.scheduledDate }
        .take(14)
    val days = upcoming.map { it.scheduledDate }.distinct()
    var selectedDate by remember(days) { mutableStateOf(days.firstOrNull()) }
    LaunchedEffect(days) { if (selectedDate !in days) selectedDate = days.firstOrNull() }

    Column(modifier = Modifier.fillMaxSize().padding(padding)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Your Plan", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Row {
                // Only future PLANNED workouts get rebuilt (see backend
                // _regenerate_future_plan) - COMPLETED/SKIPPED history is
                // untouched, so this is safe to offer any time, not just
                // right after the testing week.
                IconButton(onClick = onRegenerate) { Icon(Icons.Filled.Autorenew, contentDescription = "Regenerate plan") }
                IconButton(onClick = onEditAvailability) { Icon(Icons.Filled.CalendarMonth, contentDescription = "Edit availability") }
            }
        }

        if (upcoming.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Nothing scheduled — check your availability.", color = QuailTextDim)
            }
            return@Column
        }

        LazyRow(
            contentPadding = PaddingValues(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(days) { date ->
                val parsed = runCatching { LocalDate.parse(date) }.getOrNull()
                val label = when {
                    parsed == today -> "Today"
                    parsed == today.plusDays(1) -> "Tomorrow"
                    parsed != null -> parsed.dayOfWeek.name.lowercase().replaceFirstChar { it.uppercase() }.take(3)
                    else -> date
                }
                DayChip(label = label, selected = date == selectedDate, onClick = { selectedDate = date })
            }
        }

        val dayWorkouts = upcoming.filter { it.scheduledDate == selectedDate }
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            dayWorkouts.forEach { record ->
                val items = exerciseItemsFor(record)
                val totalSeconds = items.sumOf { it.estimatedSeconds }
                item {
                    Surface(
                        onClick = { onOpenDetail(record) },
                        color = QuailSurfaceRaised,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column {
                                Text(record.workoutType.replace('_', ' ').lowercase().replaceFirstChar { it.uppercase() }, fontWeight = FontWeight.SemiBold)
                                val timeLabel = formatEstimatedMinutes(totalSeconds)
                                Text(
                                    if (timeLabel.isNotEmpty()) "${items.size} exercises • $timeLabel" else "${items.size} exercises",
                                    color = QuailTextDim,
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            }
                            StatusBadge(record.status)
                        }
                    }
                }
                items(items) { exerciseItem ->
                    ExerciseItemRow(exerciseItem, onClick = { exerciseItem.exerciseId?.let(onOpenExerciseInfo) })
                }
            }
        }
    }
}

@Composable
private fun DayChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(20.dp),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
            color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
        )
    }
}

@Composable
private fun ExerciseItemRow(item: DayExerciseItem, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth().padding(start = 12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(item.label, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                if (item.detail.isNotEmpty()) {
                    Text(item.detail, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                val timeLabel = formatEstimatedMinutes(item.estimatedSeconds)
                if (timeLabel.isNotEmpty()) {
                    Text(timeLabel, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(end = 4.dp))
                }
                if (item.exerciseId != null) {
                    Icon(Icons.Filled.Info, contentDescription = "How to", tint = QuailTextDim, modifier = Modifier.padding(start = 2.dp))
                }
            }
        }
    }
}

@Composable
private fun StatusBadge(status: String) {
    val color = when (status) {
        "COMPLETED" -> QuailGoodGreen
        "SKIPPED", "MISSED" -> QuailBadRed
        else -> QuailTextDim
    }
    Text(status.lowercase().replaceFirstChar { it.uppercase() }, color = color, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
}
