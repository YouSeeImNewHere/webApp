package com.quail.android.ui.screens.notifications

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.NotificationDetail
import com.quail.android.data.model.NotificationItem
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface NotificationsUiState {
    data object Loading : NotificationsUiState
    data class Error(val message: String) : NotificationsUiState
    data class Success(val items: List<NotificationItem>) : NotificationsUiState
}

class NotificationsViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<NotificationsUiState>(NotificationsUiState.Loading)
    val uiState: StateFlow<NotificationsUiState> = _uiState.asStateFlow()

    private val _selected = MutableStateFlow<NotificationDetail?>(null)
    val selected: StateFlow<NotificationDetail?> = _selected.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = NotificationsUiState.Loading
            try {
                _uiState.value = NotificationsUiState.Success(repository.getNotifications())
            } catch (e: Exception) {
                _uiState.value = NotificationsUiState.Error(e.message ?: "Couldn't load notifications")
            }
        }
    }

    /** Pull-to-refresh: reloads the list, keeping current content on screen
     * instead of flashing Loading. */
    fun pullRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                _uiState.value = NotificationsUiState.Success(repository.getNotifications())
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    fun openNotification(id: Int) {
        viewModelScope.launch {
            try {
                val detail = repository.getNotificationDetail(id)
                _selected.value = detail
                repository.markNotificationRead(id)
                val current = _uiState.value as? NotificationsUiState.Success ?: return@launch
                _uiState.value = current.copy(
                    items = current.items.map { if (it.id == id) it.copy(isRead = true) else it },
                )
            } catch (e: Exception) {
                // Leave list state as-is; detail sheet simply won't open.
            }
        }
    }

    fun closeDetail() { _selected.value = null }

    fun dismiss(id: Int) {
        viewModelScope.launch {
            try {
                repository.dismissNotification(id)
                _selected.value = null
                val current = _uiState.value as? NotificationsUiState.Success ?: return@launch
                _uiState.value = current.copy(items = current.items.filterNot { it.id == id })
            } catch (e: Exception) {
                // Ignore — user can retry from the list.
            }
        }
    }

    fun markAllRead() {
        viewModelScope.launch {
            try {
                repository.markAllNotificationsRead()
                load()
            } catch (e: Exception) {
                // Ignore — Refresh will re-sync.
            }
        }
    }

    fun clearRead() {
        viewModelScope.launch {
            try {
                repository.clearReadNotifications()
                load()
            } catch (e: Exception) {
                // Ignore — Refresh will re-sync.
            }
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return NotificationsViewModel(repository) as T
        }
    }
}
