package com.quail.android.ui.screens.maps

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsExtractResult
import com.quail.android.data.model.MapsStatusResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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

    private val _openMapEvent = MutableSharedFlow<Pair<Double, Double>>(extraBufferCapacity = 1)
    val openMapEvent: SharedFlow<Pair<Double, Double>> = _openMapEvent.asSharedFlow()

    private val _openMapLoading = MutableStateFlow(false)
    val openMapLoading: StateFlow<Boolean> = _openMapLoading.asStateFlow()

    private val _openMapError = MutableStateFlow<String?>(null)
    val openMapError: StateFlow<String?> = _openMapError.asStateFlow()

    init {
        refreshStatus()
        checkForExistingDownload()
    }

    private fun checkForExistingDownload() {
        viewModelScope.launch {
            val existing = withContext(Dispatchers.IO) { repository.mostRecentExtract() }
            if (existing != null) {
                _downloadState.value = DownloadUiState.Success(existing)
            }
        }
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

    /** Gets a fresh GPS fix and emits a one-shot event to open the live
     * tile map there — the tile view needs nothing else (no download, no
     * parsing) since it fetches only the small handful of tiles actually
     * on screen from the server as you pan/zoom. */
    fun openLiveMap() {
        viewModelScope.launch {
            _openMapLoading.value = true
            _openMapError.value = null
            try {
                val location = repository.getCurrentLocation()
                _openMapEvent.emit(location.latitude to location.longitude)
            } catch (e: Exception) {
                _openMapError.value = e.message ?: "Couldn't get your location"
            } finally {
                _openMapLoading.value = false
            }
        }
    }

    class Factory(private val repository: MapsRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return MapsViewModel(repository) as T
        }
    }
}
