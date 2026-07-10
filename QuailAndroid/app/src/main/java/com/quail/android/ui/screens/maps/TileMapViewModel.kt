package com.quail.android.ui.screens.maps

import android.location.Location
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsCitiesResponse
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

sealed interface CitiesUiState {
    data object Idle : CitiesUiState
    data object Loading : CitiesUiState
    data class Success(val cities: MapsCitiesResponse) : CitiesUiState
    data class Error(val message: String) : CitiesUiState
}

private const val MAX_RECENTS = 8

// Multi-category filter passed to /api/maps/places for the "Things to do
// near me" discovery row — every non-errand category maps_pipeline/tags.py
// classifies. Deliberately excludes gas/food/coffee/parking/grocery/etc.,
// those are errands, not "things to do".
private const val THINGS_TO_DO_CATEGORIES =
    "attraction,museum,viewpoint,park,historic,entertainment,recreation,beach"

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

    // "drive" or "walk" — no "transit" option, this routing engine has no
    // real transit schedule data (GTFS) to route over.
    private val _mode = MutableStateFlow("drive")
    val mode: StateFlow<String> = _mode.asStateFlow()

    // Expanded-landing-sheet discovery content: nearby unranked restaurants
    // (no OSM rating data exists, so this is "near you", not "top"),
    // unranked things-to-do, and nearby cities/towns. Loaded once per
    // screen open, not tied to the search flow.
    private val _nearbyFood = MutableStateFlow<List<MapsPlaceResult>>(emptyList())
    val nearbyFood: StateFlow<List<MapsPlaceResult>> = _nearbyFood.asStateFlow()

    private val _nearbyThingsToDo = MutableStateFlow<List<MapsPlaceResult>>(emptyList())
    val nearbyThingsToDo: StateFlow<List<MapsPlaceResult>> = _nearbyThingsToDo.asStateFlow()

    private val _citiesState = MutableStateFlow<CitiesUiState>(CitiesUiState.Idle)
    val citiesState: StateFlow<CitiesUiState> = _citiesState.asStateFlow()

    // "route" or "explore" — the docked panel's two tabs, matching the real
    // iOS Quail Maps flow (NativeMapPage.swift).
    private val _activeTab = MutableStateFlow("route")
    val activeTab: StateFlow<String> = _activeTab.asStateFlow()

    // null = "My Location" (route starts from wherever the phone actually
    // is); set when the user explicitly picks a different starting point
    // via the Route tab's "Starting location" field.
    private val _routeOrigin = MutableStateFlow<MapsPlaceResult?>(null)
    val routeOrigin: StateFlow<MapsPlaceResult?> = _routeOrigin.asStateFlow()

    private var searchJob: Job? = null
    private var locationJob: Job? = null
    private var routeJob: Job? = null
    private var discoveryJob: Job? = null

    fun setMode(newMode: String) {
        if (_mode.value == newMode) return
        _mode.value = newMode
    }

    fun setActiveTab(tab: String) {
        _activeTab.value = tab
    }

    fun setRouteOrigin(place: MapsPlaceResult?) {
        _routeOrigin.value = place
    }

    /** Reverses the whole trip: old destination becomes the new starting
     * point, old origin becomes the new destination, stop order flips too.
     * If origin was "My Location" (null), the destination becomes null —
     * i.e. "route back to where I am now", the only sensible meaning of
     * swapping when one side wasn't a real place to begin with. */
    fun swapRouteEndpoints() {
        val oldOrigin = _routeOrigin.value
        val oldDestination = _destination.value
        _routeOrigin.value = oldDestination
        _destination.value = oldOrigin
        _stops.value = _stops.value.reversed()
    }

    /** Loads the expanded landing sheet's discovery content — call once
     * when a real location becomes available (not on every recomposition;
     * the caller is responsible for not spamming this on every pan). */
    fun loadDiscovery(lat: Double, lon: Double) {
        discoveryJob?.cancel()
        discoveryJob = viewModelScope.launch {
            launch {
                runCatching { repository.searchPlaces(lat, lon, 8.0, "food", null) }
                    .onSuccess { _nearbyFood.value = it.take(10) }
            }
            launch {
                runCatching { repository.searchPlaces(lat, lon, 15.0, THINGS_TO_DO_CATEGORIES, null) }
                    .onSuccess { _nearbyThingsToDo.value = it.take(10) }
            }
            launch {
                _citiesState.value = CitiesUiState.Loading
                _citiesState.value = try {
                    CitiesUiState.Success(repository.getNearbyCities(lat, lon))
                } catch (e: Exception) {
                    CitiesUiState.Error(e.message ?: "Couldn't load nearby cities")
                }
            }
        }
    }

    /** [radiusKm] defaults to a wide search when there's a real text query
     * (someone searching "Walmart" expects it found regardless of whether
     * it's 3 miles or 20 miles away, same as any real map app) and a tight
     * "near me" radius for pure category browsing (tapping the "Food" chip
     * with no query should mean nearby, not every restaurant in the
     * county). Real bug this fixes: every call site in TileMapScreen.kt
     * left radiusKm at this function's old flat 5.0 default regardless of
     * whether a query was typed, so a named-store search silently searched
     * only ~3 miles — indistinguishable from "there's only one" unless you
     * already know there should be more. Caller-supplied [radiusKm]
     * (stops-along-the-way's deliberately tight 3km along-route search)
     * still overrides this. */
    fun searchPlaces(lat: Double, lon: Double, radiusKm: Double? = null, q: String? = null) {
        val effectiveRadiusKm = radiusKm ?: if (!q.isNullOrBlank()) 48.0 else 5.0
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            _placesState.value = PlacesUiState.Loading
            _placesState.value = try {
                PlacesUiState.Success(repository.searchPlaces(lat, lon, effectiveRadiusKm, _selectedCategory.value, q))
            } catch (e: Exception) {
                PlacesUiState.Error(e.message ?: "Couldn't load nearby places")
            }
        }
    }

    fun setCategoryFilter(category: String?) {
        _selectedCategory.value = if (_selectedCategory.value == category) null else category
    }

    fun clearCategoryFilter() {
        _selectedCategory.value = null
        _placesState.value = PlacesUiState.Idle
    }

    /** Replaces the destination outright — distinct from [addStop], which
     * inserts before whatever destination already exists. Used when the
     * user explicitly taps the Route tab's "Destination" field or an
     * Explore-tab result's quick-route shortcut, both of which mean
     * "route to this place instead", not "route to this place as well". */
    fun setDestination(place: MapsPlaceResult) {
        _destination.value = place
        _selectedPlace.value = null
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
     * a second place gets added.
     *
     * Real bug fixed here: this used to push the CURRENT destination into
     * [stops] and make the newly-picked place the new destination — so
     * adding any stop silently changed where the trip ended, which only
     * went unnoticed while nothing surfaced multi-stop adds directly (the
     * old "+Add Stop" button always immediately re-requested routes, and
     * with a 2-point trip the wrong-looking result was indistinguishable
     * from a correct one). The "stops along the way" flow made the bug
     * obvious: picking a coffee shop "along the way" to Costco was ending
     * the trip AT the coffee shop instead of treating it as a waypoint
     * before Costco. Now the new place is simply inserted before whatever
     * destination already exists, which is what "add a stop" should mean. */
    fun addStop(place: MapsPlaceResult) {
        if (_destination.value == null) {
            _destination.value = place
        } else {
            _stops.value = _stops.value + place
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
        _routeOrigin.value = null
        _routeState.value = RouteUiState.Idle
    }

    /** [fallbackLat]/[fallbackLon] are used as the starting point only when
     * no explicit [routeOrigin] has been picked (i.e. still "My Location"). */
    fun requestRoutes(fallbackLat: Double, fallbackLon: Double) {
        val destination = _destination.value ?: return
        val origin = _routeOrigin.value
        val fromLat = origin?.lat ?: fallbackLat
        val fromLon = origin?.lon ?: fallbackLon
        routeJob?.cancel()
        routeJob = viewModelScope.launch {
            _routeState.value = RouteUiState.Loading
            val points = buildList {
                add(fromLat to fromLon)
                addAll(_stops.value.map { it.lat to it.lon })
                add(destination.lat to destination.lon)
            }
            _routeState.value = try {
                val options = repository.getRoutes(points, _mode.value)
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
