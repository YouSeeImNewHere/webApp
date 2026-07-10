package com.quail.android.ui.screens.maps

import android.location.Location
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsPlaceResult
import com.quail.android.data.model.MapsRouteOption
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
    data class Success(val options: List<MapsRouteOption>, val selectedIndex: Int) : RouteUiState
    data class Error(val message: String) : RouteUiState
}

private const val MAX_RECENTS = 8

/** Backs TileMapScreen: place discovery/search, a trip made of an ordered
 * list of stops + a final destination, routing with alternatives, and
 * turn-by-turn driving mode (live location + progressive step tracking).
 * Separate from MapsViewModel, which backs the earlier "Maps" landing
 * screen (status/offline-pack). */
class TileMapViewModel(private val repository: MapsRepository) : ViewModel() {
    private val _placesState = MutableStateFlow<PlacesUiState>(PlacesUiState.Idle)
    val placesState: StateFlow<PlacesUiState> = _placesState.asStateFlow()

    private val _selectedCategory = MutableStateFlow<String?>(null)
    val selectedCategory: StateFlow<String?> = _selectedCategory.asStateFlow()

    private val _selectedPlace = MutableStateFlow<MapsPlaceResult?>(null)
    val selectedPlace: StateFlow<MapsPlaceResult?> = _selectedPlace.asStateFlow()

    // Places whose detail sheet was actually opened this session — backs the
    // "Recent Places" row on the landing sheet. Session-only (no saved-places
    // backend exists yet), most-recent-first, deduped by id.
    private val _recents = MutableStateFlow<List<MapsPlaceResult>>(emptyList())
    val recents: StateFlow<List<MapsPlaceResult>> = _recents.asStateFlow()

    // Quick "how long to drive there" estimate shown on the detail sheet's
    // Drive pill, fetched the moment a place is opened — same routing call
    // requestRoutes() makes, just for a single leg and not tied to the trip.
    private val _previewRoute = MutableStateFlow<MapsRouteOption?>(null)
    val previewRoute: StateFlow<MapsRouteOption?> = _previewRoute.asStateFlow()
    private var previewJob: Job? = null

    // Ordered intermediate waypoints — the trip is fromLat/fromLon -> stops -> destination.
    private val _stops = MutableStateFlow<List<MapsPlaceResult>>(emptyList())
    val stops: StateFlow<List<MapsPlaceResult>> = _stops.asStateFlow()

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
    private var routeJob: Job? = null

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

    fun showPlaceDetail(place: MapsPlaceResult, fromLat: Double, fromLon: Double) {
        _selectedPlace.value = place
        _recents.value = (listOf(place) + _recents.value.filterNot { it.id == place.id }).take(MAX_RECENTS)

        _previewRoute.value = null
        previewJob?.cancel()
        previewJob = viewModelScope.launch {
            _previewRoute.value = try {
                repository.getRoutes(listOf(fromLat to fromLon, place.lat to place.lon))
                    .minByOrNull { it.durationSec }
            } catch (e: Exception) {
                null
            }
        }
    }

    fun dismissPlaceDetail() {
        _selectedPlace.value = null
        previewJob?.cancel()
        _previewRoute.value = null
    }

    /** Adds a stop, or if there's no destination yet, sets it as the
     * destination directly — "Add Stop" on the very first place picked has
     * nothing to be a waypoint *before*, so it's just the destination until
     * a second place gets added. */
    fun addStop(place: MapsPlaceResult) {
        if (_destination.value == null) {
            _destination.value = place
        } else {
            _stops.value = _stops.value + _destination.value!!
            _destination.value = place
        }
        _selectedPlace.value = null
        previewJob?.cancel()
        _previewRoute.value = null
    }

    fun removeStop(place: MapsPlaceResult) {
        _stops.value = _stops.value.filterNot { it.id == place.id }
    }

    fun clearTrip() {
        stopNavigation()
        _stops.value = emptyList()
        _destination.value = null
        _routeState.value = RouteUiState.Idle
    }

    /** points: fromLat/fromLon, every stop in order, then the destination. */
    fun requestRoutes(fromLat: Double, fromLon: Double) {
        val destination = _destination.value ?: return
        routeJob?.cancel()
        routeJob = viewModelScope.launch {
            _routeState.value = RouteUiState.Loading
            val points = buildList {
                add(fromLat to fromLon)
                addAll(_stops.value.map { it.lat to it.lon })
                add(destination.lat to destination.lon)
            }
            _routeState.value = try {
                val options = repository.getRoutes(points)
                if (options.isEmpty()) {
                    RouteUiState.Error("Couldn't find a route there")
                } else {
                    RouteUiState.Success(options, selectedIndex = 0)
                }
            } catch (e: Exception) {
                RouteUiState.Error(e.message ?: "Couldn't find a route there")
            }
        }
    }

    fun selectRoute(index: Int) {
        val state = _routeState.value
        if (state is RouteUiState.Success && index in state.options.indices) {
            _routeState.value = state.copy(selectedIndex = index)
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
