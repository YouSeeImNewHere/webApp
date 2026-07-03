package com.quailcash.android.ui.screens.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.MonthBudget
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface DashboardUiState {
    data object Loading : DashboardUiState
    data class Error(val message: String) : DashboardUiState
    data class Success(val cashSnapshot: MonthBudget?) : DashboardUiState
}

/** Mirrors the iOS DashboardPageView glance strip — currently only the Cash
 * card has real data behind it (from the same /page/home month_budget the
 * Home screen uses); Car/Fitness have no Android backend integration yet. */
class DashboardViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<DashboardUiState>(DashboardUiState.Loading)
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.value = DashboardUiState.Loading
            try {
                val payload = repository.getHome(txLimit = 1)
                _uiState.value = DashboardUiState.Success(payload.monthBudget)
            } catch (e: Exception) {
                _uiState.value = DashboardUiState.Error(e.message ?: "Something went wrong")
            }
        }
    }

    /** Pull-to-refresh: keeps whatever's already on screen visible instead of
     * flashing the full loading state, and fails silently (the user can
     * always pull again) rather than replacing good data with an error. */
    fun pullRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val payload = repository.getHome(txLimit = 1)
                _uiState.value = DashboardUiState.Success(payload.monthBudget)
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return DashboardViewModel(repository) as T
        }
    }
}
