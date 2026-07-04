package com.quail.android.ui.screens.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.NOTIFICATION_PREF_LABELS
import com.quail.android.data.model.NotificationSettingsResponse
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface SettingsUiState {
    data object Loading : SettingsUiState
    data class Error(val message: String) : SettingsUiState
    data class Success(val settings: NotificationSettingsResponse, val savingKey: String? = null) : SettingsUiState
}

class SettingsViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<SettingsUiState>(SettingsUiState.Loading)
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    private val _cacheStatus = MutableStateFlow<String?>(null)
    val cacheStatus: StateFlow<String?> = _cacheStatus.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = SettingsUiState.Loading
            try {
                _uiState.value = SettingsUiState.Success(repository.getNotificationSettings())
            } catch (e: Exception) {
                _uiState.value = SettingsUiState.Error(e.message ?: "Couldn't load settings")
            }
        }
    }

    /** Pull-to-refresh: reloads notification prefs, keeping current content
     * on screen instead of flashing Loading. */
    fun pullRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                _uiState.value = SettingsUiState.Success(repository.getNotificationSettings())
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    fun togglePref(key: String, enabled: Boolean) {
        val current = _uiState.value as? SettingsUiState.Success ?: return
        _uiState.value = current.copy(savingKey = key)
        viewModelScope.launch {
            try {
                val updated = repository.setNotificationSettings(mapOf(key to enabled))
                _uiState.value = SettingsUiState.Success(updated)
            } catch (e: Exception) {
                _uiState.value = current.copy(savingKey = null)
            }
        }
    }

    fun refreshCache() {
        viewModelScope.launch {
            _cacheStatus.value = "Refreshing..."
            try {
                val result = repository.refreshHomeWidgetCache()
                _cacheStatus.value = "Home v${result.homeSnapshotVersion}, Widget v${result.widgetVersion}"
            } catch (e: Exception) {
                _cacheStatus.value = e.message ?: "Refresh failed"
            }
        }
    }

    companion object {
        val PREF_LABELS = NOTIFICATION_PREF_LABELS
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return SettingsViewModel(repository) as T
        }
    }
}
