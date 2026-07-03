package com.quailcash.android.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.ChartMode
import com.quailcash.android.data.model.ChartPoint
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

data class DateRange(val start: LocalDate, val end: LocalDate)

sealed interface ChartUiState {
    data object Loading : ChartUiState
    data class Error(val message: String) : ChartUiState
    data class Success(val points: List<ChartPoint>) : ChartUiState
}

private val TODAY: LocalDate = LocalDate.now()

private fun clampToToday(date: LocalDate): LocalDate = if (date.isAfter(TODAY)) TODAY else date

private fun quarterRange(year: Int, quarter: Int): DateRange {
    val startMonth = (quarter - 1) * 3 + 1
    val start = LocalDate.of(year, startMonth, 1)
    return DateRange(start, clampToToday(start.plusMonths(3).minusDays(1)))
}

private fun annualRange(year: Int): DateRange =
    DateRange(LocalDate.of(year, 1, 1), clampToToday(LocalDate.of(year, 12, 31)))

private fun monthRange(year: Int, month: Int): DateRange {
    val start = LocalDate.of(year, month, 1)
    return DateRange(start, clampToToday(start.plusMonths(1).minusDays(1)))
}

/** Mirrors HomeView.swift's chart section: mode cycling (net worth / savings
 * / investments / spending), quarter/YTD/annual/month range presets, and a
 * client-side linear-projection toggle (server never returns future points). */
class NetWorthChartViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _mode = MutableStateFlow(ChartMode.NET_WORTH)
    val mode: StateFlow<ChartMode> = _mode.asStateFlow()

    private val _year = MutableStateFlow(TODAY.year)
    val year: StateFlow<Int> = _year.asStateFlow()

    private val _range = MutableStateFlow(annualRange(TODAY.year))
    val range: StateFlow<DateRange> = _range.asStateFlow()

    private val _projectGrowth = MutableStateFlow(false)
    val projectGrowth: StateFlow<Boolean> = _projectGrowth.asStateFlow()

    private val _uiState = MutableStateFlow<ChartUiState>(ChartUiState.Loading)
    val uiState: StateFlow<ChartUiState> = _uiState.asStateFlow()

    val canGoToNextYear: Boolean get() = _year.value < TODAY.year

    init {
        load()
    }

    fun cycleMode() {
        val modes = ChartMode.entries
        _mode.value = modes[(modes.indexOf(_mode.value) + 1) % modes.size]
        if (_mode.value != ChartMode.NET_WORTH) _projectGrowth.value = false
        load()
    }

    fun setProjectGrowth(enabled: Boolean) {
        _projectGrowth.value = enabled
    }

    fun selectQuarter(quarter: Int) = setRange(quarterRange(_year.value, quarter))
    fun selectAnnual() = setRange(annualRange(_year.value))
    fun selectMonth(month: Int) = setRange(monthRange(_year.value, month))

    fun setCustomRange(start: LocalDate, end: LocalDate) {
        val safeEnd = clampToToday(if (end.isBefore(start)) start else end)
        setRange(DateRange(start, safeEnd))
    }

    fun previousYear() {
        _year.value -= 1
        setRange(annualRange(_year.value))
    }

    fun nextYear() {
        if (!canGoToNextYear) return
        _year.value += 1
        setRange(annualRange(_year.value))
    }

    private fun setRange(newRange: DateRange) {
        _range.value = newRange
        load()
    }

    private fun load() {
        viewModelScope.launch {
            _uiState.value = ChartUiState.Loading
            try {
                val r = _range.value
                val points = repository.getChartSeries(_mode.value, r.start, r.end)
                _uiState.value = ChartUiState.Success(points)
            } catch (e: Exception) {
                _uiState.value = ChartUiState.Error(e.message ?: "Couldn't load chart")
            }
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return NetWorthChartViewModel(repository) as T
        }
    }
}

/** Last-8-point linear extrapolation, 7 days forward — matches HomeView.swift's
 * client-side "Project Growth" toggle; the server never returns future points. */
fun projectedPoints(points: List<ChartPoint>): List<ChartPoint> {
    val sample = points.takeLast(8)
    val first = sample.firstOrNull() ?: return emptyList()
    val last = sample.lastOrNull() ?: return emptyList()
    val firstDate = runCatching { LocalDate.parse(first.date) }.getOrNull() ?: return emptyList()
    val lastDate = runCatching { LocalDate.parse(last.date) }.getOrNull() ?: return emptyList()
    val intervalDays = java.time.temporal.ChronoUnit.DAYS.between(firstDate, lastDate).toInt().coerceAtLeast(1)
    val slope = (last.value - first.value) / intervalDays

    return (1..7).map { step ->
        val date = lastDate.plusDays(step.toLong())
        ChartPoint(date = date.toString(), value = last.value + slope * step)
    }
}
