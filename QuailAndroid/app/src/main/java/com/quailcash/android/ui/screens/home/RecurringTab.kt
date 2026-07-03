package com.quailcash.android.ui.screens.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quailcash.android.data.model.RecurringCalendarEvent
import com.quailcash.android.data.model.RecurringGroup
import com.quailcash.android.data.model.RecurringPattern
import com.quailcash.android.ui.theme.QuailBadRed
import com.quailcash.android.ui.theme.QuailGoodGreen
import com.quailcash.android.ui.theme.QuailSurface
import com.quailcash.android.ui.theme.QuailSurfaceRaised
import com.quailcash.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.Month
import java.time.YearMonth
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.abs

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

/** Mirrors NativeRecurringPageView: one continuously scrolling page — the
 * calendarCard (projected occurrences for the visible month) above the
 * merchant/pattern list, not a toggle between the two. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecurringTab(padding: PaddingValues, viewModel: RecurringViewModel) {
    val state by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { viewModel.pullRefresh() },
        modifier = Modifier.fillMaxSize().padding(padding),
    ) {
        when (val s = state) {
            is RecurringUiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            is RecurringUiState.Error -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(s.message, color = QuailTextDim)
            }
            is RecurringUiState.Success -> {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(
                        top = 8.dp,
                        bottom = 16.dp,
                        start = 12.dp,
                        end = 12.dp,
                    ),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item { HeaderRow(s, viewModel) }
                    item { RecurringCalendarCard(s, viewModel) }
                    if (s.groups.isEmpty()) {
                        item {
                            Box(Modifier.fillMaxWidth().padding(vertical = 30.dp), contentAlignment = Alignment.Center) {
                                Text("No recurring transactions detected yet.", color = QuailTextDim)
                            }
                        }
                    } else {
                        items(s.groups, key = { it.merchant }) { group ->
                            RecurringGroupCard(
                                group = group,
                                onIgnoreMerchant = { viewModel.ignoreMerchant(group.merchant) },
                                onTapPattern = { viewModel.openPattern(it) },
                            )
                        }
                    }
                }

                s.selectedPattern?.let { pattern ->
                    ModalBottomSheet(onDismissRequest = { viewModel.closePattern() }, sheetState = rememberModalBottomSheetState()) {
                        PatternDetailContent(pattern, onIgnore = { viewModel.ignorePattern(pattern) })
                    }
                }
                s.selectedDay?.let { day ->
                    val eventsByDay = remember(s.calendarEvents) { (s.calendarEvents ?: emptyList()).groupBy { it.date } }
                    ModalBottomSheet(onDismissRequest = { viewModel.selectDay(null) }, sheetState = rememberModalBottomSheetState()) {
                        DayDetailContent(day, eventsByDay[day] ?: emptyList())
                    }
                }
            }
        }
    }
}

@Composable
private fun HeaderRow(s: RecurringUiState.Success, viewModel: RecurringViewModel) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text("Recurring & subscriptions", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Include stale", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Switch(checked = s.includeStale, onCheckedChange = { viewModel.toggleIncludeStale() })
        }
    }
}

@Composable
private fun RecurringCalendarCard(s: RecurringUiState.Success, viewModel: RecurringViewModel) {
    val events = s.calendarEvents ?: emptyList()
    val eventsByDay = remember(events) { events.groupBy { it.date } }

    // Matches HomeView.swift's calendarCard: Out = non-income events (max(0, amount)),
    // In = income events (paycheck/interest) by absolute value.
    val outTotal = remember(events) { events.filterNot { it.isIncome }.sumOf { maxOf(0.0, it.amount) } }
    val inTotal = remember(events) { events.filter { it.isIncome }.sumOf { abs(it.amount) } }

    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                SmallNavButton("‹") { viewModel.shiftCalendarMonth(-1) }
                Text(
                    "${Month.of(s.calendarMonth).getDisplayName(TextStyle.FULL, Locale.US)} ${s.calendarYear}",
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                SmallNavButton("›") { viewModel.shiftCalendarMonth(1) }
            }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("Out: ${currency.format(outTotal)}", color = QuailBadRed, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
                Text("In: ${currency.format(inTotal)}", color = QuailGoodGreen, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
            }

            if (s.calendarLoading) {
                Box(Modifier.fillMaxWidth().padding(vertical = 30.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            } else {
                WeekdayHeaderRow()
                MonthGrid(s.calendarYear, s.calendarMonth, eventsByDay, onDayClick = { viewModel.selectDay(it) })
            }
        }
    }
}

@Composable
private fun SmallNavButton(symbol: String, onClick: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = CircleShape, modifier = Modifier.size(32.dp)) {
        Box(contentAlignment = Alignment.Center) {
            Text(symbol, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun WeekdayHeaderRow() {
    Row(Modifier.fillMaxWidth()) {
        listOf(DayOfWeek.SUNDAY, DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY, DayOfWeek.SATURDAY).forEach { dow ->
            Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                Text(
                    dow.getDisplayName(TextStyle.NARROW, Locale.US),
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

/** Plain Column/Row grid (not LazyVerticalGrid) since this lives inside an
 * enclosing LazyColumn item — nesting one scrollable inside another is what
 * caused the broken layout previously; a fixed ≤6-week grid never needs its
 * own scroll behavior. */
@Composable
private fun MonthGrid(year: Int, month: Int, eventsByDay: Map<String, List<RecurringCalendarEvent>>, onDayClick: (String) -> Unit) {
    val yearMonth = YearMonth.of(year, month)
    val firstDay = yearMonth.atDay(1)
    // Sunday-first week: DayOfWeek.value is 1=Mon..7=Sun, so `% 7` maps Sun->0, Mon->1, ... Sat->6.
    val leadingBlanks = firstDay.dayOfWeek.value % 7
    val daysInMonth = yearMonth.lengthOfMonth()
    val cells: List<LocalDate?> = List(leadingBlanks) { null } + (1..daysInMonth).map { yearMonth.atDay(it) }
    val weeks = cells.chunked(7)

    Column(Modifier.fillMaxWidth()) {
        weeks.forEach { week ->
            Row(Modifier.fillMaxWidth()) {
                week.forEach { date ->
                    Box(Modifier.weight(1f)) {
                        DayCell(date, eventsByDay[date?.toString()] ?: emptyList(), onDayClick)
                    }
                }
                repeat(7 - week.size) { Box(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun DayCell(date: LocalDate?, events: List<RecurringCalendarEvent>, onDayClick: (String) -> Unit) {
    Box(
        modifier = Modifier
            .aspectRatio(1f)
            .padding(2.dp),
        contentAlignment = Alignment.Center,
    ) {
        if (date == null) return@Box
        val hasIncome = events.any { it.isIncome }
        val hasExpense = events.any { !it.isIncome }
        Surface(
            onClick = { if (events.isNotEmpty()) onDayClick(date.toString()) },
            color = if (events.isNotEmpty()) QuailSurfaceRaised else Color.Transparent,
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Text("${date.dayOfMonth}", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                if (events.isNotEmpty()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        if (hasExpense) Box(Modifier.size(4.dp).background(QuailBadRed, CircleShape))
                        if (hasIncome) Box(Modifier.size(4.dp).background(QuailGoodGreen, CircleShape))
                    }
                }
            }
        }
    }
}

@Composable
private fun DayDetailContent(day: String, events: List<RecurringCalendarEvent>) {
    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Text(day, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            events.forEach { event ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text(event.merchantDisplay ?: event.merchant, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            listOfNotNull(event.category, event.cadence).joinToString(" • "),
                            color = QuailTextDim,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                    Text(
                        currency.format(event.amount),
                        fontWeight = FontWeight.Bold,
                        color = if (event.isIncome) QuailGoodGreen else QuailBadRed,
                    )
                }
            }
        }
    }
}

@Composable
private fun RecurringGroupCard(group: RecurringGroup, onIgnoreMerchant: () -> Unit, onTapPattern: (RecurringPattern) -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .background(if (group.active) QuailGoodGreen else QuailTextDim, CircleShape),
                    )
                    Text(
                        group.merchantDisplay ?: group.merchant,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                Surface(onClick = onIgnoreMerchant, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                    Text(
                        "Ignore",
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
            Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                group.patterns.forEach { pattern -> RecurringPatternRow(pattern, onClick = { onTapPattern(pattern) }) }
            }
        }
    }
}

@Composable
private fun RecurringPatternRow(pattern: RecurringPattern, onClick: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text(
                    (pattern.cadence ?: "irregular").replaceFirstChar { it.uppercase() },
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    "${pattern.occurrences}x · last ${pattern.lastSeen ?: "—"}",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Text(
                currency.format(pattern.amount),
                fontWeight = FontWeight.Bold,
                color = if (pattern.amount >= 0) QuailBadRed else QuailGoodGreen,
            )
        }
    }
}

@Composable
private fun PatternDetailContent(pattern: RecurringPattern, onIgnore: () -> Unit) {
    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Text(pattern.merchant ?: "Pattern", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            DetailRow("Cadence", pattern.cadence ?: "irregular")
            DetailRow("Amount", currency.format(pattern.amount))
            DetailRow("Occurrences", pattern.occurrences.toString())
            DetailRow("Last seen", pattern.lastSeen ?: "—")
        }
        Surface(
            onClick = onIgnore,
            color = QuailBadRed.copy(alpha = 0.16f),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
        ) {
            Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                Text("Ignore this pattern", fontWeight = FontWeight.Bold, color = QuailBadRed)
            }
        }
        if (pattern.tx.isNotEmpty()) {
            HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))
            Text("Matching transactions", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                pattern.tx.forEach { tx ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text(tx.merchant ?: "Transaction", style = MaterialTheme.typography.bodyMedium)
                            tx.date?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall) }
                        }
                        Text(currency.format(tx.amount), fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = QuailTextDim)
        Text(value, fontWeight = FontWeight.SemiBold)
    }
}
