package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.exerciseById
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.time.format.DateTimeFormatter
import java.util.Locale

private val weekLabelFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d", Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessAnalyticsScreen(
    viewModel: FitnessViewModel,
    onOpenHome: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenCalendar: () -> Unit,
    onOpenPlan: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val data by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = { FitnessTopBar(onOpenSettings) },
        bottomBar = {
            FitnessBottomBar(
                selectedTab = FitnessTab.ANALYTICS,
                onSelectHome = onOpenHome,
                onSelectCalendar = onOpenCalendar,
                onSelectAnalytics = {},
                onSelectPlan = onOpenPlan,
                onOpenDashboard = onOpenDashboard,
            )
        },
    ) { padding ->
        val fitnessData = data
        if (fitnessData == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Scaffold
        }

        val sessions = fitnessData.sessions
        val volumeHistory = weeklyVolumeHistory(sessions, weeks = 8)
        val maxVolume = volumeHistory.maxOfOrNull { it.second }?.coerceAtLeast(1) ?: 1
        val topExercises = sessions.flatMap { it.exercises }
            .groupBy { it.exerciseId }
            .mapValues { (_, entries) -> entries.sumOf { it.sets.size } }
            .entries.sortedByDescending { it.value }
            .take(5)
            .mapNotNull { (id, _) -> exerciseById(id, fitnessData.customExercises)?.let { it to personalBest(id, sessions) } }
        val runs = sessions.filter { it.isFromGarmin }.sortedByDescending { it.date }.take(10)
        val maxDistance = runs.mapNotNull { it.distanceKm }.maxOrNull()?.coerceAtLeast(0.1) ?: 1.0

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item {
                AnalyticsSection("Volume Trend (8 weeks)") {
                    if (volumeHistory.all { it.second == 0 }) {
                        Text("No workouts logged yet", color = QuailTextDim, modifier = Modifier.padding(vertical = 8.dp))
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            volumeHistory.forEach { (weekStart, reps) ->
                                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Text(weekStart.format(weekLabelFormat), color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.width(60.dp))
                                    LinearProgressIndicator(
                                        progress = { reps.toFloat() / maxVolume.toFloat() },
                                        modifier = Modifier.weight(1f),
                                        color = MaterialTheme.colorScheme.primary,
                                        trackColor = QuailSurfaceRaised,
                                    )
                                    Text("$reps", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.width(36.dp))
                                }
                            }
                        }
                    }
                }
            }

            item {
                AnalyticsSection("Personal Records") {
                    if (topExercises.isEmpty()) {
                        Text("Log a few workouts to see your top exercises here", color = QuailTextDim, modifier = Modifier.padding(vertical = 8.dp))
                    } else {
                        Column {
                            topExercises.forEachIndexed { idx, (exercise, pb) ->
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(exercise.name, fontWeight = FontWeight.SemiBold)
                                    Text(
                                        pb?.reps?.let { "$it reps" } ?: pb?.durationSeconds?.let { "$it sec" } ?: "—",
                                        color = QuailTextDim,
                                        fontWeight = FontWeight.Bold,
                                    )
                                }
                                if (idx < topExercises.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                            }
                        }
                    }
                }
            }

            item {
                AnalyticsSection("Garmin Runs") {
                    if (runs.isEmpty()) {
                        Text("No Garmin runs synced yet", color = QuailTextDim, modifier = Modifier.padding(vertical = 8.dp))
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            runs.forEach { run ->
                                Column {
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(run.date, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                                        Text(
                                            listOfNotNull(
                                                run.distanceKm?.let { "%.2f km".format(it) },
                                                formatRunPace(run.avgPaceSecPerKm),
                                                run.avgHeartRate?.let { "$it bpm" },
                                            ).joinToString(" · "),
                                            color = QuailTextDim,
                                            style = MaterialTheme.typography.labelSmall,
                                        )
                                    }
                                    LinearProgressIndicator(
                                        progress = { (run.distanceKm ?: 0.0).toFloat() / maxDistance.toFloat() },
                                        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                                        color = MaterialTheme.colorScheme.primary,
                                        trackColor = QuailSurfaceRaised,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun formatRunPace(secPerKm: Int?): String? {
    if (secPerKm == null || secPerKm <= 0) return null
    return "%d:%02d /km".format(secPerKm / 60, secPerKm % 60)
}

@Composable
private fun AnalyticsSection(title: String, content: @Composable () -> Unit) {
    Column {
        Text(title.uppercase(), color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
        Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) { content() }
        }
    }
}
