package com.quail.android.ui.screens.maps

import android.location.Location
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsPlaceResult
import com.quail.android.data.model.MapsRouteResponse
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.launch

sealed interface PlacesUiState {
    data object Idle : PlacesUiState
    data object Loading : PlacesUiState
    data class Success(val places: List<MapsPlaceResult>) : PlacesUiState
    data class Error(val message: String) : PlacesUiState
}

sealed interface RouteUiState {
    data object Idle : RouteUiState
    data object Loading : RouteUiState
    data class Success(val route: MapsRouteResponse) : RouteUiState
    data class Error(val message: String) : RouteUiState
}

/** Backs TileMapScreen: place discovery near the current map view, routing
 * to a selected destination, and turn-by-turn driving mode (live location +
 * progressive step tracking). Separate from MapsViewModel, which backs the
 * earlier "Maps" landing screen (status/offline-pack). */
class TileMapViewModel(private val repository: MapsRepository) : ViewModel() {
    private val _placesState = MutableStateFlow<PlacesUiState>(PlacesUiState.Idle)
    val placesState: StateFlow<PlacesUiState> = _placesState.asStateFlow()

    private val _selectedCategory = MutableStateFlow<String?>(null)
    val selectedCategory: StateFlow<String?> = _selectedCategory.asStateFlow()

    private val _destination = MutableStateFlow<MapsPlaceResult?>(null)
    val destination: StateFlow<MapsPlaceResult?> = _destination.asStateFlow()

    private val _routeState = MutableStateFlow<RouteUiState>(RouteUiState.Idle)
    val routeState: StateFlow<RouteUiState> = _routeState.asStateFlow()

    private val _navigating = MutableStateFlow(false)
    val navigating: StateFlow<Boolean> = _navigating.asStateFlow()

    private val _liveLocation = MutableStateFlow<Location?>(null)
    val liveLocation: StateFlow<Location?> = _liveLocation.asStateFlow()

    private val _locationError = MutableStateFlow<String?>(null)
    val locationError: StateFlow<String?> = _locationError.asStateFlow()

    private var searchJob: Job? = null
    private var locationJob: Job? = null

    fun searchPlaces(lat: Double, lon: Double, radiusKm: Double = 5.0, q: String? = null) {
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            _placesState.value = PlacesUiState.Loading
            _placesState.value = try {
                PlacesUiState.Success(repository.searchPlaces(lat, lon, radiusKm, _selectedCategory.value, q))
            } catch (e: Exception) {
                PlacesUiState.Error(e.message ?: "Couldn't load nearby places")
            }
        }
    }

    fun setCategoryFilter(category: String?) {
        _selectedCategory.value = if (_selectedCategory.value == category) null else category
    }

    fun selectDestination(place: MapsPlaceResult, fromLat: Double, fromLon: Double) {
        _destination.value = place
        requestRoute(fromLat, fromLon, place.lat, place.lon)
    }

    fun clearDestination() {
        stopNavigation()
        _destination.value = null
        _routeState.value = RouteUiState.Idle
    }

    fun requestRoute(fromLat: Double, fromLon: Double, toLat: Double, toLon: Double) {
        viewModelScope.launch {
            _routeState.value = RouteUiState.Loading
            _routeState.value = try {
                RouteUiState.Success(repository.getRoute(fromLat, fromLon, toLat, toLon))
            } catch (e: Exception) {
                RouteUiState.Error(e.message ?: "Couldn't find a route there")
            }
        }
    }

    /** Starts turn-by-turn driving mode: live location updates flow into
     * [liveLocation], which TileMapView uses to follow the user and rotate
     * the map to keep heading up, and TileMapScreen uses to figure out
     * which turn step is "next". */
    fun startNavigation() {
        if (_navigating.value) return
        _navigating.value = true
        _locationError.value = null
        locationJob = viewModelScope.launch {
            repository.observeLocation()
                .catch { e -> _locationError.value = e.message ?: "Lost location updates" }
                .collect { location -> _liveLocation.value = location }
        }
    }

    fun stopNavigation() {
        _navigating.value = false
        locationJob?.cancel()
        locationJob = null
        _liveLocation.value = null
    }

    class Factory(private val repository: MapsRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return TileMapViewModel(repository) as T
        }
    }
}
