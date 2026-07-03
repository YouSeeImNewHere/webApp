package com.quailcash.android.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.MonthlyReport
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

sealed interface AnalyticsUiState {
    data object Loading : AnalyticsUiState
    data class Error(val message: String) : AnalyticsUiState
    data class Success(val report: MonthlyReport, val year: Int, val month: Int) : AnalyticsUiState
}

class AnalyticsViewModel(private val repository: HomeRepository) : ViewModel() {
    private val today = LocalDate.now()
    private var year = today.year
    private var month = today.monthValue

    private val _uiState = MutableStateFlow<AnalyticsUiState>(AnalyticsUiState.Loading)
    val uiState: StateFlow<AnalyticsUiState> = _uiState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        load()
    }

    fun selectMonth(year: Int, month: Int) {
        this.year = year
        this.month = month
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = AnalyticsUiState.Loading
            try {
                val monthKey = "%04d-%02d".format(year, month)
                _uiState.value = AnalyticsUiState.Success(repository.getMonthlyReport(monthKey), year, month)
            } catch (e: Exception) {
                _uiState.value = AnalyticsUiState.Error(e.message ?: "Couldn't load report")
            }
        }
    }

    /** Pull-to-refresh: re-fetches the currently selected month, keeping the
     * current report visible instead of flashing Loading. */
    fun pullRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val monthKey = "%04d-%02d".format(year, month)
                _uiState.value = AnalyticsUiState.Success(repository.getMonthlyReport(monthKey), year, month)
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return AnalyticsViewModel(repository) as T
        }
    }
}
