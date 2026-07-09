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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
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
            )
        }
    }

    activeSheet?.let { sheet ->
        FitnessSheetHost(sheet = sheet, viewModel = viewModel, onDismiss = { activeSheet = null; viewModel.loadPlan() })
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
private fun ActivePlanContent(
    padding: PaddingValues,
    scheduled: List<ScheduledWorkoutRecord>,
    onOpenDetail: (ScheduledWorkoutRecord) -> Unit,
    onEditAvailability: () -> Unit,
) {
    val today = LocalDate.now()
    val upcoming = scheduled
        .filter { runCatching { LocalDate.parse(it.scheduledDate) }.getOrNull()?.let { d -> !d.isBefore(today) } == true }
        .sortedBy { it.scheduledDate }
        .take(14)
    val grouped = upcoming.groupBy { it.scheduledDate }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("This Week's Plan", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                IconButton(onClick = onEditAvailability) { Icon(Icons.Filled.CalendarMonth, contentDescription = "Edit availability") }
            }
        }
        if (upcoming.isEmpty()) {
            item { Text("Nothing scheduled — check your availability.", color = QuailTextDim) }
        }
        grouped.forEach { (date, workouts) ->
            item {
                val parsed = runCatching { LocalDate.parse(date) }.getOrNull()
                val label = if (parsed == today) "Today" else parsed?.dayOfWeek?.name?.lowercase()?.replaceFirstChar { it.uppercase() } ?: date
                Text(label, fontWeight = FontWeight.SemiBold, color = QuailTextDim, modifier = Modifier.padding(top = 4.dp))
            }
            items(workouts, key = { it.id }) { record ->
                ScheduledWorkoutRow(record, onClick = { onOpenDetail(record) })
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

@Composable
private fun StatusBadge(status: String) {
    val color = when (status) {
        "COMPLETED" -> QuailGoodGreen
        "SKIPPED", "MISSED" -> QuailBadRed
        else -> QuailTextDim
    }
    Text(status.lowercase().replaceFirstChar { it.uppercase() }, color = color, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
}
