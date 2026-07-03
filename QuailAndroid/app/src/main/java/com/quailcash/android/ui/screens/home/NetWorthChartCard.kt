package com.quailcash.android.ui.screens.home

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.KeyboardArrowLeft
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quailcash.android.data.model.ChartMode
import com.quailcash.android.data.model.ChartPoint
import com.quailcash.android.ui.theme.QuailBadRed
import com.quailcash.android.ui.theme.QuailGoodGreen
import com.quailcash.android.ui.theme.QuailSurface
import com.quailcash.android.ui.theme.QuailSurfaceRaised
import com.quailcash.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.Month
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.roundToInt

private val currencyFormat: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)
private val axisFormat: NumberFormat = NumberFormat.getIntegerInstance(Locale.US)
private val chipDateFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)

private fun LocalDate.toUtcMillis(): Long = atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
private fun Long.toLocalDateUtc(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate()

@Composable
fun NetWorthChartCard(viewModel: NetWorthChartViewModel) {
    val mode by viewModel.mode.collectAsState()
    val year by viewModel.year.collectAsState()
    val range by viewModel.range.collectAsState()
    val projectGrowth by viewModel.projectGrowth.collectAsState()
    val uiState by viewModel.uiState.collectAsState()

    Surface(
        color = QuailSurface,
        shape = RoundedCornerShape(18.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(mode.label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Surface(
                    onClick = { viewModel.cycleMode() },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(999.dp),
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Next", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                        Icon(Icons.Filled.ChevronRight, contentDescription = null, modifier = Modifier.padding(start = 2.dp))
                    }
                }
            }

            DateRangeControls(range = range, onApply = { start, end -> viewModel.setCustomRange(start, end) })

            if (uiState is ChartUiState.Success) {
                val points = (uiState as ChartUiState.Success).points
                MetricPills(mode, points)
            }

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    modifier = Modifier
                        .weight(1f, fill = false)
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    (1..4).forEach { q ->
                        ChipButton("Q$q") { viewModel.selectQuarter(q) }
                    }
                    ChipButton("YTD") { viewModel.selectAnnual() }
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { viewModel.previousYear() }, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Filled.KeyboardArrowLeft, contentDescription = "Previous year")
                    }
                    Text("$year", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    IconButton(onClick = { viewModel.nextYear() }, enabled = viewModel.canGoToNextYear, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Filled.KeyboardArrowRight, contentDescription = "Next year")
                    }
                }
            }

            LazyRow(
                modifier = Modifier.padding(top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(12) { i ->
                    val month = i + 1
                    ChipButton(Month.of(month).getDisplayName(TextStyle.SHORT, Locale.US)) {
                        viewModel.selectMonth(month)
                    }
                }
            }

            Box(modifier = Modifier.padding(top = 12.dp)) {
                when (val state = uiState) {
                    is ChartUiState.Loading -> Box(
                        Modifier.fillMaxWidth().height(220.dp),
                        contentAlignment = Alignment.Center,
                    ) { Text("Loading…", color = QuailTextDim) }

                    is ChartUiState.Error -> Box(
                        Modifier.fillMaxWidth().height(220.dp),
                        contentAlignment = Alignment.Center,
                    ) { Text(state.message, color = QuailTextDim) }

                    is ChartUiState.Success -> Column {
                        if (mode == ChartMode.NET_WORTH) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.padding(bottom = 8.dp),
                            ) {
                                Text("Project Growth", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                                Switch(checked = projectGrowth, onCheckedChange = { viewModel.setProjectGrowth(it) })
                            }
                        }
                        ChartCanvas(
                            points = state.points,
                            projected = if (projectGrowth && mode == ChartMode.NET_WORTH) projectedPoints(state.points) else emptyList(),
                            mode = mode,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MetricPills(mode: ChartMode, points: List<ChartPoint>) {
    val first = points.firstOrNull()
    val last = points.lastOrNull()
    val growthPct = if (first != null && last != null && first.value != 0.0) {
        (last.value - first.value) / kotlin.math.abs(first.value) * 100.0
    } else null

    Row(
        modifier = Modifier.padding(top = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp)) {
            Row(modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(mode.label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(currencyFormat.format(last?.value ?: 0.0), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
            }
        }
        if (growthPct != null) {
            Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp)) {
                Row(modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("% Growth", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                    Text(
                        "${if (growthPct >= 0) "+" else ""}${"%.1f".format(growthPct)}%",
                        color = if (growthPct >= 0) QuailGoodGreen else QuailBadRed,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
    }
}

@Composable
private fun ChipButton(label: String, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = QuailSurfaceRaised,
        shape = RoundedCornerShape(999.dp),
    ) {
        Text(
            label,
            modifier = Modifier.widthIn(min = 30.dp).padding(horizontal = 9.dp, vertical = 6.dp),
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

private fun nearestIndex(x: Float, widthPx: Float, count: Int): Int {
    if (count <= 1) return 0
    return (x / widthPx * (count - 1)).roundToInt().coerceIn(0, count - 1)
}

@Composable
private fun DateRangeControls(range: DateRange, onApply: (LocalDate, LocalDate) -> Unit) {
    var pendingStart by remember(range) { mutableStateOf(range.start) }
    var pendingEnd by remember(range) { mutableStateOf(range.end) }
    var showStartPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }

    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Start", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            ChipButton(pendingStart.format(chipDateFormat)) { showStartPicker = true }
        }
        Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("End", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            ChipButton(pendingEnd.format(chipDateFormat)) { showEndPicker = true }
        }
        Column(modifier = Modifier.padding(top = 18.dp)) {
            Surface(
                onClick = { onApply(pendingStart, pendingEnd) },
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(12.dp),
            ) {
                Text(
                    "Update",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                    color = Color.Black,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }

    if (showStartPicker) {
        DatePickerModal(
            initial = pendingStart,
            onDismiss = { showStartPicker = false },
            onConfirm = { pendingStart = it; showStartPicker = false },
        )
    }
    if (showEndPicker) {
        DatePickerModal(
            initial = pendingEnd,
            onDismiss = { showEndPicker = false },
            onConfirm = { pendingEnd = it; showEndPicker = false },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DatePickerModal(initial: LocalDate, onDismiss: () -> Unit, onConfirm: (LocalDate) -> Unit) {
    val state = rememberDatePickerState(initialSelectedDateMillis = initial.toUtcMillis())
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                val millis = state.selectedDateMillis
                if (millis != null) onConfirm(millis.toLocalDateUtc()) else onDismiss()
            }) { Text("OK") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    ) {
        DatePicker(state = state)
    }
}

@Composable
private fun ChartCanvas(points: List<ChartPoint>, projected: List<ChartPoint>, mode: ChartMode) {
    var selectedIndex by remember(points) { mutableStateOf<Int?>(null) }

    if (points.size < 2) {
        Box(Modifier.fillMaxWidth().height(220.dp), contentAlignment = Alignment.Center) {
            Text("Not enough data yet", color = QuailTextDim)
        }
        return
    }

    val allValues = points.map { it.value } + projected.map { it.value }
    val minValue = allValues.min()
    val maxValue = allValues.max()
    val rawSpan = (maxValue - minValue).let { if (it == 0.0) kotlin.math.abs(maxValue).coerceAtLeast(1.0) else it }
    val paddedSpan = rawSpan * 1.12
    val paddedMin = minValue - (paddedSpan - rawSpan) / 2.0

    val accentColor = MaterialTheme.colorScheme.primary

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(220.dp)
            .pointerInput(points) {
                detectTapGestures(onTap = { offset -> selectedIndex = nearestIndex(offset.x, size.width.toFloat(), points.size) })
            }
            .pointerInput(points) {
                detectDragGestures(
                    onDrag = { change, _ ->
                        change.consume()
                        selectedIndex = nearestIndex(change.position.x, size.width.toFloat(), points.size)
                    },
                )
            },
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            val totalCount = points.size + projected.size

            fun xFor(i: Int) = if (totalCount <= 1) 0f else w * i / (totalCount - 1)
            fun yFor(v: Double) = h - ((v - paddedMin) / paddedSpan * h).toFloat()

            val gridColor = Color.White.copy(alpha = 0.08f)
            for (i in 0..3) {
                val y = h * i / 3f
                drawLine(gridColor, Offset(0f, y), Offset(w, y), strokeWidth = 1f)
            }

            val linePath = Path()
            points.forEachIndexed { i, p ->
                val x = xFor(i)
                val y = yFor(p.value)
                if (i == 0) linePath.moveTo(x, y) else linePath.lineTo(x, y)
            }
            val areaPath = Path().apply {
                addPath(linePath)
                lineTo(xFor(points.size - 1), h)
                lineTo(xFor(0), h)
                close()
            }
            drawPath(
                areaPath,
                brush = Brush.verticalGradient(listOf(accentColor.copy(alpha = 0.18f), accentColor.copy(alpha = 0.02f))),
            )
            drawPath(
                linePath,
                color = accentColor,
                style = Stroke(width = 2.8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round),
            )

            if (projected.isNotEmpty()) {
                val projPath = Path()
                projPath.moveTo(xFor(points.size - 1), yFor(points.last().value))
                projected.forEachIndexed { j, p ->
                    projPath.lineTo(xFor(points.size + j), yFor(p.value))
                }
                drawPath(
                    projPath,
                    color = accentColor.copy(alpha = 0.55f),
                    style = Stroke(
                        width = 2.1.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 8f)),
                    ),
                )
            }

            selectedIndex?.let { idx ->
                if (idx in points.indices) {
                    val x = xFor(idx)
                    val y = yFor(points[idx].value)
                    drawLine(Color.White.copy(alpha = 0.25f), Offset(x, 0f), Offset(x, h), strokeWidth = 1f)
                    drawCircle(accentColor, radius = 5.dp.toPx(), center = Offset(x, y))
                    drawCircle(Color.White, radius = 5.dp.toPx(), center = Offset(x, y), style = Stroke(width = 2.dp.toPx()))
                }
            }
        }

        Column(
            modifier = Modifier.fillMaxSize().padding(vertical = 2.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(axisFormat.format(maxValue), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Text(axisFormat.format(minValue), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }

        selectedIndex?.let { idx ->
            if (idx in points.indices) {
                ChartTooltip(points[idx], mode, modifier = Modifier.align(Alignment.BottomEnd).padding(8.dp))
            }
        }
    }
}

@Composable
private fun ChartTooltip(point: ChartPoint, mode: ChartMode, modifier: Modifier = Modifier) {
    Surface(
        color = Color.Black.copy(alpha = 0.82f),
        shape = RoundedCornerShape(10.dp),
        modifier = modifier.widthIn(max = 180.dp),
    ) {
        Column(Modifier.padding(10.dp)) {
            Text(point.date, color = Color.White, style = MaterialTheme.typography.labelSmall)
            Text(
                "${mode.label}: ${currencyFormat.format(point.value)}",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.labelSmall,
            )
            if (mode == ChartMode.NET_WORTH) {
                point.banks?.let { Text("Banks: ${currencyFormat.format(it)}", color = Color.White, style = MaterialTheme.typography.labelSmall) }
                point.savings?.let { Text("Savings: ${currencyFormat.format(it)}", color = Color.White, style = MaterialTheme.typography.labelSmall) }
                point.cards?.let { Text("Cards: ${currencyFormat.format(it)}", color = Color.White, style = MaterialTheme.typography.labelSmall) }
            }
        }
    }
}
