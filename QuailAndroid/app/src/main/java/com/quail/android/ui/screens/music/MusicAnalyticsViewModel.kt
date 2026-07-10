package com.quail.android.ui.screens.music

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.MusicAnalyticsResponse
import com.quail.android.data.music.MusicRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface MusicAnalyticsUiState {
    data object Loading : MusicAnalyticsUiState
    data class Error(val message: String) : MusicAnalyticsUiState
    data class Success(val data: MusicAnalyticsResponse) : MusicAnalyticsUiState
}

class MusicAnalyticsViewModel(private val repository: MusicRepository) : ViewModel() {
    private val _state = MutableStateFlow<MusicAnalyticsUiState>(MusicAnalyticsUiState.Loading)
    val state: StateFlow<MusicAnalyticsUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.value = MusicAnalyticsUiState.Loading
            _state.value = try {
                MusicAnalyticsUiState.Success(repository.getAnalytics())
            } catch (e: Exception) {
                MusicAnalyticsUiState.Error(e.message ?: "Couldn't reach the music server")
            }
        }
    }

    class Factory(private val repository: MusicRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return MusicAnalyticsViewModel(repository) as T
        }
    }
}
