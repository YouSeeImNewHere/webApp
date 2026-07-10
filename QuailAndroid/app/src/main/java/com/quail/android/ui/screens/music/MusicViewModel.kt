package com.quail.android.ui.screens.music

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.MusicRecommendedPlaylist
import com.quail.android.data.model.MusicSearchResult
import com.quail.android.data.music.MusicRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.launch

sealed interface MusicRecommendedUiState {
    data object Loading : MusicRecommendedUiState
    data class Error(val message: String) : MusicRecommendedUiState
    data class Success(val playlists: List<MusicRecommendedPlaylist>) : MusicRecommendedUiState
}

sealed interface MusicSearchUiState {
    data object Idle : MusicSearchUiState
    data object Loading : MusicSearchUiState
    data class Error(val message: String) : MusicSearchUiState
    data class Success(val results: List<MusicSearchResult>) : MusicSearchUiState
}

class MusicViewModel(private val repository: MusicRepository) : ViewModel() {
    private val _recommendedState = MutableStateFlow<MusicRecommendedUiState>(MusicRecommendedUiState.Loading)
    val recommendedState: StateFlow<MusicRecommendedUiState> = _recommendedState.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    private val _searchState = MutableStateFlow<MusicSearchUiState>(MusicSearchUiState.Idle)
    val searchState: StateFlow<MusicSearchUiState> = _searchState.asStateFlow()

    private val _deleteError = MutableStateFlow<String?>(null)
    val deleteError: StateFlow<String?> = _deleteError.asStateFlow()

    init {
        refreshRecommended()
        observeSearchQuery()
    }

    fun refreshRecommended() {
        viewModelScope.launch {
            _recommendedState.value = MusicRecommendedUiState.Loading
            _recommendedState.value = try {
                MusicRecommendedUiState.Success(repository.getRecommended().playlists)
            } catch (e: Exception) {
                MusicRecommendedUiState.Error(e.message ?: "Couldn't reach the music server")
            }
        }
    }

    fun onSearchQueryChange(query: String) {
        _searchQuery.value = query
    }

    // Debounced so search doesn't fire a request on every keystroke — same
    // pattern as the email parser rule form's live preview.
    private fun observeSearchQuery() {
        viewModelScope.launch {
            _searchQuery.debounce(300).collectLatest { query ->
                if (query.isBlank()) {
                    _searchState.value = MusicSearchUiState.Idle
                    return@collectLatest
                }
                _searchState.value = MusicSearchUiState.Loading
                _searchState.value = try {
                    MusicSearchUiState.Success(repository.search(query))
                } catch (e: Exception) {
                    MusicSearchUiState.Error(e.message ?: "Search failed")
                }
            }
        }
    }

    fun deleteTrack(id: String) {
        viewModelScope.launch {
            try {
                repository.deleteTrack(id)
                val current = _searchState.value
                if (current is MusicSearchUiState.Success) {
                    _searchState.value = MusicSearchUiState.Success(current.results.filter { it.id != id })
                }
            } catch (e: Exception) {
                _deleteError.value = e.message ?: "Delete failed"
            }
        }
    }

    fun clearDeleteError() {
        _deleteError.value = null
    }

    class Factory(private val repository: MusicRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return MusicViewModel(repository) as T
        }
    }
}
