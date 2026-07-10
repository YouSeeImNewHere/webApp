package com.quail.android.ui.screens.maps

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.maps.TilePackProgress
import com.quail.android.data.model.MapsStatusResponse
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface MapsStatusUiState {
    data object Loading : MapsStatusUiState
    data class Success(val status: MapsStatusResponse) : MapsStatusUiState
    data class Error(val message: String) : MapsStatusUiState
}

sealed interface TilePackUiState {
    data object Idle : TilePackUiState
    data object RequestingLocation : TilePackUiState
    data class Downloading(val progress: TilePackProgress) : TilePackUiState
    data class Success(val tileCount: Int) : TilePackUiState
    data class Error(val message: String) : TilePackUiState
}

class MapsViewModel(private val repository: MapsRepository) : ViewModel() {
    private val _status = MutableStateFlow<MapsStatusUiState>(MapsStatusUiState.Loading)
    val status: StateFlow<MapsStatusUiState> = _status.asStateFlow()

    private val _tilePackState = MutableStateFlow<TilePackUiState>(TilePackUiState.Idle)
    val tilePackState: StateFlow<TilePackUiState> = _tilePackState.asStateFlow()

    private val _openMapEvent = MutableSharedFlow<Pair<Double, Double>>(extraBufferCapacity = 1)
    val openMapEvent: SharedFlow<Pair<Double, Double>> = _openMapEvent.asSharedFlow()

    private val _openMapLoading = MutableStateFlow(false)
    val openMapLoading: StateFlow<Boolean> = _openMapLoading.asStateFlow()

    private val _openMapError = MutableStateFlow<String?>(null)
    val openMapError: StateFlow<String?> = _openMapError.asStateFlow()

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

    /** Downloads every tile within [radiusKm] of the current location across
     * a street-to-neighborhood zoom range — once this finishes, the live
     * map (TileMapView) works fully offline for that area, since it always
     * checks the on-disk tile store before the network. */
    fun downloadOfflinePack(radiusKm: Double = 5.0) {
        viewModelScope.launch {
            _tilePackState.value = TilePackUiState.RequestingLocation
            try {
                val location = repository.getCurrentLocation()
                repository.downloadTilePack(location.latitude, location.longitude, radiusKm) { progress ->
                    _tilePackState.value = TilePackUiState.Downloading(progress)
                }
                val finalCount = (_tilePackState.value as? TilePackUiState.Downloading)?.progress?.total ?: 0
                _tilePackState.value = TilePackUiState.Success(finalCount)
            } catch (e: Exception) {
                _tilePackState.value = TilePackUiState.Error(e.message ?: "Download failed")
            }
        }
    }

    fun resetTilePackState() {
        _tilePackState.value = TilePackUiState.Idle
    }

    /** Gets a fresh GPS fix and emits a one-shot event to open the live
     * tile map there — the tile view needs nothing else (no download, no
     * parsing) since it fetches only the small handful of tiles actually
     * on screen from the server as you pan/zoom (or from the on-disk pack
     * cache if you've downloaded one and have no network). */
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
