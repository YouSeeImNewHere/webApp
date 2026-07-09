package com.quail.android.ui.screens.maps

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsExtractResult
import com.quail.android.data.model.MapsStatusResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface MapsStatusUiState {
    data object Loading : MapsStatusUiState
    data class Success(val status: MapsStatusResponse) : MapsStatusUiState
    data class Error(val message: String) : MapsStatusUiState
}

sealed interface DownloadUiState {
    data object Idle : DownloadUiState
    data object RequestingLocation : DownloadUiState
    data object Downloading : DownloadUiState
    data class Success(val result: MapsExtractResult) : DownloadUiState
    data class Error(val message: String) : DownloadUiState
}

class MapsViewModel(private val repository: MapsRepository) : ViewModel() {
    private val _status = MutableStateFlow<MapsStatusUiState>(MapsStatusUiState.Loading)
    val status: StateFlow<MapsStatusUiState> = _status.asStateFlow()

    private val _downloadState = MutableStateFlow<DownloadUiState>(DownloadUiState.Idle)
    val downloadState: StateFlow<DownloadUiState> = _downloadState.asStateFlow()

    init {
        refreshStatus()
    }

    fun refreshStatus() {
        viewModelScope.launch {
            _status.value = MapsStatusUiState.Loading
            _status.value = try {
                MapsStatusUiState.Success(repository.getStatus())
            } catch (e: Exception) {
                MapsStatusUiState.Error(e.message ?: "Couldn't reach the maps server")
            }
        }
    }

    fun downloadCurrentCity(radiusKm: Double = 15.0) {
        viewModelScope.launch {
            _downloadState.value = DownloadUiState.RequestingLocation
            try {
                val location = repository.getCurrentLocation()
                _downloadState.value = DownloadUiState.Downloading
                val result = repository.downloadExtract(location.latitude, location.longitude, radiusKm)
                _downloadState.value = DownloadUiState.Success(result)
            } catch (e: Exception) {
                _downloadState.value = DownloadUiState.Error(e.message ?: "Download failed")
            }
        }
    }

    fun resetDownloadState() {
        _downloadState.value = DownloadUiState.Idle
    }

    class Factory(private val repository: MapsRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return MapsViewModel(repository) as T
        }
    }
}
