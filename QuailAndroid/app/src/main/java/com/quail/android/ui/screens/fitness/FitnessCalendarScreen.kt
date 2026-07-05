package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailTextDim
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.TextStyle
import java.util.Locale

private fun sessionDates(sessions: List<WorkoutSessionRecord>): Set<LocalDate> =
    sessions.mapNotNull { runCatching { LocalDate.parse(it.date) }.getOrNull() }.toSet()

private fun currentStreak(dates: Set<LocalDate>): Int {
    if (dates.isEmpty()) return 0
    var day = LocalDate.now()
    if (day !in dates) day = day.minusDays(1)
    var streak = 0
    while (day in dates) {
        streak++
        day = day.minusDays(1)
    }
    return streak
}

private fun longestStreak(dates: Set<LocalDate>): Int {
    if (dates.isEmpty()) return 0
    val sorted = dates.sorted()
    var longest = 1
    var current = 1
    for (i in 1 until sorted.size) {
        current = if (sorted[i] == sorted[i - 1].plusDays(1)) current + 1 else 1
        if (current > longest) longest = current
    }
    return longest
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessCalendarScreen(
    viewModel: FitnessViewModel,
    onOpenHome: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenAnalytics: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val data by viewModel.uiState.collectAsState()
    var month by remember { mutableStateOf(YearMonth.now()) }

    Scaffold(
        topBar = { FitnessTopBar(onOpenSettings) },
        bottomBar = {
            FitnessBottomBar(
                selectedTab = FitnessTab.CALENDAR,
                onSelectHome = onOpenHome,
                onSelectCalendar = {},
                onSelectAnalytics = onOpenAnalytics,
                onOpenDashboard = onOpenDashboard,
            )
        },
    ) { padding ->
        if (data == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Scaffold
        }
        val dates = sessionDates(data!!.sessions)

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StreakCard("Current Streak", currentStreak(dates), Modifier.weight(1f))
                    StreakCard("Longest Streak", longestStreak(dates), Modifier.weight(1f))
                }
            }
            item {
                Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            IconButton(onClick = { month = month.minusMonths(1) }) { Icon(Icons.Filled.ChevronLeft, contentDescription = "Previous month") }
                            Text(
                                "${month.month.getDisplayName(TextStyle.FULL, Locale.getDefault())} ${month.year}",
                                fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleMedium,
                            )
                            IconButton(onClick = { month = month.plusMonths(1) }) { Icon(Icons.Filled.ChevronRight, contentDescription = "Next month") }
                        }

                        Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                            listOf("S", "M", "T", "W", "T", "F", "S").forEach { d ->
                                Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.Center) {
                                    Text(d, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }

                        val firstOfMonth = month.atDay(1)
                        val leadingBlanks = firstOfMonth.dayOfWeek.value % 7 // Sunday=0
                        val daysInMonth = month.lengthOfMonth()
                        val cells = (0 until leadingBlanks).map { null } + (1..daysInMonth).map { month.atDay(it) }

                        LazyVerticalGrid(
                            columns = GridCells.Fixed(7),
                            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                        ) {
                            items(cells) { day ->
                                Box(modifier = Modifier.aspectRatio(1f).padding(3.dp), contentAlignment = Alignment.Center) {
                                    if (day != null) {
                                        val hasWorkout = day in dates
                                        val isToday = day == LocalDate.now()
                                        Surface(
                                            color = if (hasWorkout) MaterialTheme.colorScheme.primary else Color.Transparent,
                                            shape = CircleShape,
                                            modifier = Modifier.fillMaxSize(),
                                        ) {
                                            Box(contentAlignment = Alignment.Center) {
                                                Text(
                                                    "${day.dayOfMonth}",
                                                    color = if (hasWorkout) Color.Black else if (isToday) MaterialTheme.colorScheme.primary else QuailTextDim,
                                                    fontWeight = if (hasWorkout || isToday) FontWeight.Bold else FontWeight.Normal,
                                                    style = MaterialTheme.typography.labelMedium,
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
        }
    }
}

@Composable
private fun StreakCard(label: String, days: Int, modifier: Modifier = Modifier) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = modifier) {
        Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("$days", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
            Text(if (days == 1) "day" else "days", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
        }
    }
}
