package com.quail.android.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.RecurringCalendarEvent
import com.quail.android.data.model.RecurringGroup
import com.quail.android.data.model.RecurringPattern
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

sealed interface RecurringUiState {
    data object Loading : RecurringUiState
    data class Error(val message: String) : RecurringUiState
    data class Success(
        val groups: List<RecurringGroup>,
        val includeStale: Boolean,
        val selectedPattern: RecurringPattern? = null,
        val calendarYear: Int = LocalDate.now().year,
        val calendarMonth: Int = LocalDate.now().monthValue,
        val calendarEvents: List<RecurringCalendarEvent>? = null,
        val calendarLoading: Boolean = false,
        val selectedDay: String? = null,
    ) : RecurringUiState
}

/** Port of NativeRecurringPageView: a calendar card (projected occurrences
 * for the visible month) followed by the merchant/pattern list, on one
 * continuously scrolling page — matching iOS, not a tab/toggle between the
 * two. Include-stale toggle, ignore actions, and pattern detail (with its
 * embedded matching transactions) round it out; pattern-merge UI is still
 * out of scope for this pass. */
class RecurringViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<RecurringUiState>(RecurringUiState.Loading)
    val uiState: StateFlow<RecurringUiState> = _uiState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        load(includeStale = false)
    }

    /** Pull-to-refresh: reloads the merchant list and the visible calendar
     * month, keeping current content on screen instead of flashing Loading. */
    fun pullRefresh() {
        val current = _uiState.value as? RecurringUiState.Success
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val includeStale = current?.includeStale ?: false
                val groups = repository.getRecurring(minOcc = 3, includeStale = includeStale)
                val events = runCatching {
                    repository.getRecurringCalendar(
                        year = current?.calendarYear ?: LocalDate.now().year,
                        month = current?.calendarMonth ?: LocalDate.now().monthValue,
                        minOcc = 3,
                        includeStale = includeStale,
                    )
                }.getOrNull()
                _uiState.value = RecurringUiState.Success(
                    groups = groups,
                    includeStale = includeStale,
                    calendarYear = current?.calendarYear ?: LocalDate.now().year,
                    calendarMonth = current?.calendarMonth ?: LocalDate.now().monthValue,
                    calendarEvents = events ?: current?.calendarEvents,
                )
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    fun load(includeStale: Boolean) {
        viewModelScope.launch {
            val prev = _uiState.value as? RecurringUiState.Success
            _uiState.value = RecurringUiState.Loading
            try {
                val groups = repository.getRecurring(minOcc = 3, includeStale = includeStale)
                _uiState.value = RecurringUiState.Success(
                    groups = groups,
                    includeStale = includeStale,
                    calendarYear = prev?.calendarYear ?: LocalDate.now().year,
                    calendarMonth = prev?.calendarMonth ?: LocalDate.now().monthValue,
                )
                loadCalendar()
            } catch (e: Exception) {
                _uiState.value = RecurringUiState.Error(e.message ?: "Couldn't load recurring transactions")
            }
        }
    }

    fun toggleIncludeStale() {
        val current = _uiState.value as? RecurringUiState.Success ?: return
        load(includeStale = !current.includeStale)
    }

    fun openPattern(pattern: RecurringPattern) {
        val current = _uiState.value as? RecurringUiState.Success ?: return
        _uiState.value = current.copy(selectedPattern = pattern)
    }

    fun closePattern() {
        val current = _uiState.value as? RecurringUiState.Success ?: return
        _uiState.value = current.copy(selectedPattern = null)
    }

    fun ignoreMerchant(merchant: String) {
        viewModelScope.launch {
            try {
                repository.ignoreRecurringMerchant(merchant)
                load((_uiState.value as? RecurringUiState.Success)?.includeStale ?: false)
            } catch (e: Exception) {
                // Ignore — list stays as-is, user can retry.
            }
        }
    }

    fun ignorePattern(pattern: RecurringPattern) {
        viewModelScope.launch {
            try {
                repository.ignoreRecurringPattern(pattern.merchant ?: "", pattern.amount, pattern.accountId ?: -1)
                closePattern()
                load((_uiState.value as? RecurringUiState.Success)?.includeStale ?: false)
            } catch (e: Exception) {
                // Ignore — list stays as-is, user can retry.
            }
        }
    }

    fun shiftCalendarMonth(delta: Int) {
        val current = _uiState.value as? RecurringUiState.Success ?: return
        val total = current.calendarYear * 12 + (current.calendarMonth - 1) + delta
        val year = total / 12
        val month = total % 12 + 1
        _uiState.value = current.copy(calendarYear = year, calendarMonth = month, calendarEvents = null, selectedDay = null)
        loadCalendar()
    }

    fun selectDay(day: String?) {
        val current = _uiState.value as? RecurringUiState.Success ?: return
        _uiState.value = current.copy(selectedDay = day)
    }

    private fun loadCalendar() {
        val current = _uiState.value as? RecurringUiState.Success ?: return
        _uiState.value = current.copy(calendarLoading = true)
        viewModelScope.launch {
            try {
                val events = repository.getRecurringCalendar(
                    year = current.calendarYear,
                    month = current.calendarMonth,
                    minOcc = 3,
                    includeStale = current.includeStale,
                )
                val latest = _uiState.value as? RecurringUiState.Success ?: return@launch
                _uiState.value = latest.copy(calendarEvents = events, calendarLoading = false)
            } catch (e: Exception) {
                val latest = _uiState.value as? RecurringUiState.Success ?: return@launch
                _uiState.value = latest.copy(calendarEvents = emptyList(), calendarLoading = false)
            }
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return RecurringViewModel(repository) as T
        }
    }
}
