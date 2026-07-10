package com.quail.android.ui.screens.maps

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.LocationCity
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Straight
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material.icons.filled.TurnLeft
import androidx.compose.material.icons.filled.TurnRight
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsCityResult
import com.quail.android.data.model.MapsPlaceResult
import com.quail.android.data.model.MapsRouteOption
import com.quail.android.data.model.MapsRoutePoint
import com.quail.android.data.model.MapsRouteStep
import com.quail.android.ui.theme.QuailAccent
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sqrt

private val CATEGORY_FILTERS = listOf(
    "gas" to "⛽", "food" to "🍔", "coffee" to "☕", "attraction" to "🎡",
    "museum" to "🏛️", "viewpoint" to "🌆", "park" to "🌳",
    "historic" to "🗿", "lodging" to "🏨",
)

private const val SEARCH_DEBOUNCE_MS = 300L
private val SheetBg = Color(0xFF11151D)
private val CardBg = Color(0xFF171C26)
private val ChipBg = Color(0xFF232A38)
private val PANEL_MAX_HEIGHT = 560.dp

/** Feet under ~0.1mi (Apple/Google Maps' rough switchover point), miles
 * with one decimal above that — feet rounded to the nearest 25ft to avoid
 * implying precision the underlying GPS/routing doesn't have. */
private fun formatDistanceImperial(meters: Double): String {
    val feet = meters * 3.28084
    if (feet < 528.0) {
        val roundedFeet = (Math.round(feet / 25.0) * 25).coerceAtLeast(25)
        return "$roundedFeet ft"
    }
    val miles = meters / 1609.344
    return "%.1f mi".format(miles)
}

private fun formatClockTime(epochMillis: Long): String =
    SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(epochMillis))

/** Rough icon per turn instruction, matched against the vocabulary
 * maps_pipeline/routing.py's _turn_word() actually generates ("Turn left
 * onto", "Turn right onto", "Continue onto", "Head <compass> on", "Arrive
 * at ..."). Anything else (continue/head) reads fine as a straight arrow. */
private fun turnIconFor(instruction: String): ImageVector {
    val lower = instruction.lowercase()
    return when {
        lower.contains("arrive") -> Icons.Filled.Flag
        lower.contains("turn right") -> Icons.Filled.TurnRight
        lower.contains("turn left") -> Icons.Filled.TurnLeft
        else -> Icons.Filled.Straight
    }
}

private fun approxDistanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
    val dLat = (lat2 - lat1) * 110_540.0
    val dLon = (lon2 - lon1) * 111_320.0 * cos(Math.toRadians(lat1))
    return sqrt(dLat * dLat + dLon * dLon)
}

private fun findNearestPointIndex(points: List<MapsRoutePoint>, lat: Double, lon: Double): Int {
    var bestIdx = 0
    var bestDist = Double.MAX_VALUE
    points.forEachIndexed { i, p ->
        val d = approxDistanceMeters(lat, lon, p.lat, p.lon)
        if (d < bestDist) {
            bestDist = d
            bestIdx = i
        }
    }
    return bestIdx
}

private fun currentStepIndexFor(steps: List<MapsRouteStep>, nearestPointIndex: Int): Int {
    var idx = 0
    for (i in steps.indices) {
        if (steps[i].pointIndex <= nearestPointIndex) idx = i else break
    }
    return idx
}

/** Persistent docked Route/Explore panel, matching the real iOS Quail Maps
 * screen (QuailCash/Quail/NativeMapPage.swift) rather than the earlier
 * search-first floating-sheet design: a Route tab (Starting location / swap
 * / Destination fields, mode toggle, ranked route cards, stops-along-the-
 * way suggestions) and an Explore tab (search, category chips, results with
 * a quick-route shortcut). The colorful terrain/land-use basemap in the iOS
 * screenshots is NOT replicated here — this server's tile renderer
 * (maps_pipeline/tile_render.py) only draws roads on a plain dark
 * background; matching that look would mean ingesting OSM landuse/water/
 * building polygons and rewriting the renderer, a separate backend project. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TileMapScreen(repository: MapsRepository, lat: Double, lon: Double, onBack: () -> Unit) {
    val viewModel: TileMapViewModel = viewModel(factory = TileMapViewModel.Factory(repository))

    var currentLat by remember { mutableStateOf(lat) }
    var currentLon by remember { mutableStateOf(lon) }
    var searchQuery by remember { mutableStateOf("") }
    // "origin" | "destination" | null — which Route-tab field a tap opened
    // the shared search UI for.
    var pickingField by remember { mutableStateOf<String?>(null) }
    // "map" (search centered on wherever the map is panned to) or
    // "location" (search centered on the real GPS fix from opening this
    // screen — not re-fetched live, same fix used for the "you are here"
    // marker).
    var exploreCenterMode by remember { mutableStateOf("map") }

    val placesState by viewModel.placesState.collectAsState()
    val selectedCategory by viewModel.selectedCategory.collectAsState()
    val selectedPlace by viewModel.selectedPlace.collectAsState()
    val previewRoute by viewModel.previewRoute.collectAsState()
    val recents by viewModel.recents.collectAsState()
    val nearbyFood by viewModel.nearbyFood.collectAsState()
    val nearbyThingsToDo by viewModel.nearbyThingsToDo.collectAsState()
    val citiesState by viewModel.citiesState.collectAsState()
    val mode by viewModel.mode.collectAsState()
    val activeTab by viewModel.activeTab.collectAsState()
    val routeOrigin by viewModel.routeOrigin.collectAsState()
    val stops by viewModel.stops.collectAsState()
    val destination by viewModel.destination.collectAsState()
    val routeState by viewModel.routeState.collectAsState()
    val navigating by viewModel.navigating.collectAsState()
    val liveLocation by viewModel.liveLocation.collectAsState()
    val locationError by viewModel.locationError.collectAsState()

    val selectedRoute = (routeState as? RouteUiState.Success)?.let { it.options.getOrNull(it.selectedIndex) }
    val destinationLatLon = destination?.let { it.lat to it.lon }
    val routePoints = selectedRoute?.points?.map { it.lat to it.lon }
    val showExploreResults = pickingField == null && activeTab == "explore" &&
        (searchQuery.isNotBlank() || selectedCategory != null)
    // Where the "STOPS ALONG THE WAY" suggestions search — the actual
    // middle of the current route if one exists, otherwise wherever the map
    // is centered. Not a true polyline-buffer search along the whole route,
    // just a reasonable single-point approximation.
    val routeMidpoint = remember(selectedRoute) {
        val pts = selectedRoute?.points
        if (pts.isNullOrEmpty()) null else pts[pts.size / 2].let { it.lat to it.lon }
    }

    fun exitPicker() {
        pickingField = null
        searchQuery = ""
        viewModel.clearCategoryFilter()
    }

    LaunchedEffect(Unit) { viewModel.loadDiscovery(lat, lon) }

    LaunchedEffect(searchQuery, pickingField, activeTab, exploreCenterMode) {
        if (searchQuery.isBlank()) return@LaunchedEffect
        delay(SEARCH_DEBOUNCE_MS)
        val (slat, slon) = if (pickingField == null && activeTab == "explore" && exploreCenterMode == "location") {
            lat to lon
        } else {
            currentLat to currentLon
        }
        viewModel.searchPlaces(slat, slon, q = searchQuery)
    }

    val nearestPointIndex = remember(liveLocation, selectedRoute) {
        val r = selectedRoute ?: return@remember 0
        val loc = liveLocation ?: return@remember 0
        findNearestPointIndex(r.points, loc.latitude, loc.longitude)
    }
    val currentStepIndex = remember(nearestPointIndex, selectedRoute) {
        selectedRoute?.let { currentStepIndexFor(it.steps, nearestPointIndex) } ?: 0
    }
    val distanceToManeuverM = remember(liveLocation, selectedRoute, currentStepIndex) {
        val r = selectedRoute ?: return@remember 0.0
        val loc = liveLocation ?: return@remember 0.0
        val nextPointIndex = r.steps.getOrNull(currentStepIndex + 1)?.pointIndex ?: (r.points.size - 1)
        val target = r.points.getOrNull(nextPointIndex) ?: return@remember 0.0
        approxDistanceMeters(loc.latitude, loc.longitude, target.lat, target.lon)
    }
    // Whole-trip remaining distance/duration for the bottom stat bar —
    // walks the rest of the route's points from the nearest one, then
    // scales the total route duration by what fraction of distance is left
    // (we don't have per-edge live ETA, so this proportional estimate is
    // the best available without re-querying the routing engine every fix).
    val remaining = remember(liveLocation, selectedRoute, nearestPointIndex) {
        val r = selectedRoute
        val loc = liveLocation
        if (r == null || loc == null || r.points.isEmpty()) return@remember null
        var distRemaining = approxDistanceMeters(
            loc.latitude, loc.longitude,
            r.points[nearestPointIndex].lat, r.points[nearestPointIndex].lon,
        )
        for (i in nearestPointIndex until r.points.size - 1) {
            distRemaining += approxDistanceMeters(
                r.points[i].lat, r.points[i].lon, r.points[i + 1].lat, r.points[i + 1].lon,
            )
        }
        val fraction = (distRemaining / r.distanceM.coerceAtLeast(1.0)).coerceIn(0.0, 1.0)
        distRemaining to (r.durationSec * fraction)
    }

    Box(Modifier.fillMaxSize()) {
        TileMapView(
            repository = repository,
            initialLat = lat,
            initialLon = lon,
            destination = destinationLatLon,
            routePoints = routePoints,
            navigating = navigating,
            liveLocation = liveLocation,
            onCenterChanged = { newLat, newLon -> currentLat = newLat; currentLon = newLon },
            modifier = Modifier.fillMaxSize(),
        )

        if (navigating) {
            NavigationTopBanner(
                currentStep = selectedRoute?.steps?.getOrNull(currentStepIndex),
                nextStep = selectedRoute?.steps?.getOrNull(currentStepIndex + 1),
                distanceToManeuverM = distanceToManeuverM,
                locationError = locationError,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .statusBarsPadding()
                    .fillMaxWidth()
                    .padding(start = 12.dp, end = 68.dp, top = 12.dp),
            )
            RoundIconButton(
                icon = Icons.Filled.Close,
                contentDescription = "Exit navigation",
                onClick = { viewModel.clearTrip() },
                modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(top = 12.dp, end = 12.dp),
            )
            remaining?.let { (distRemaining, durRemainingSec) ->
                NavigationBottomBar(
                    arrivalClock = formatClockTime((System.currentTimeMillis() + durRemainingSec * 1000).toLong()),
                    minutesRemaining = (durRemainingSec / 60.0).roundToInt(),
                    distanceRemaining = formatDistanceImperial(distRemaining),
                    modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(16.dp),
                )
            }
        } else {
            MapsTopBar(onBack = onBack, modifier = Modifier.align(Alignment.TopCenter))

            val place = selectedPlace
            DockedPanel(modifier = Modifier.align(Alignment.BottomCenter)) {
                when {
                    place != null -> PlaceDetailContent(
                        place = place,
                        hasExistingTrip = destination != null,
                        previewRoute = previewRoute,
                        selectAction = when (pickingField) {
                            "origin" -> "Set as Starting Point" to {
                                viewModel.setRouteOrigin(place)
                                if (destination != null) viewModel.requestRoutes(currentLat, currentLon)
                                viewModel.dismissPlaceDetail()
                                exitPicker()
                            }
                            "destination" -> "Set as Destination" to {
                                viewModel.setDestination(place)
                                viewModel.requestRoutes(currentLat, currentLon)
                                viewModel.dismissPlaceDetail()
                                exitPicker()
                            }
                            else -> null
                        },
                        onDismiss = { viewModel.dismissPlaceDetail() },
                        onAddStop = {
                            viewModel.addStop(place)
                            viewModel.requestRoutes(currentLat, currentLon)
                        },
                    )
                    else -> {
                        Box(Modifier.padding(horizontal = 16.dp)) {
                            RouteExploreToggle(
                                activeTab = activeTab,
                                onTabChange = { tab ->
                                    viewModel.setActiveTab(tab)
                                    pickingField = null
                                    searchQuery = ""
                                    viewModel.clearCategoryFilter()
                                },
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        if (activeTab == "route") {
                            RouteTabContent(
                                routeOrigin = routeOrigin,
                                destination = destination,
                                stops = stops,
                                routeState = routeState,
                                mode = mode,
                                onModeChange = { m ->
                                    viewModel.setMode(m)
                                    viewModel.requestRoutes(currentLat, currentLon)
                                },
                                pickingField = pickingField,
                                fieldQuery = searchQuery,
                                onFieldQueryChange = { searchQuery = it },
                                onFieldSubmit = { viewModel.searchPlaces(currentLat, currentLon, q = searchQuery.ifBlank { null }) },
                                fieldPlacesState = placesState,
                                fieldSelectedCategory = selectedCategory,
                                onFieldCategoryClick = { category ->
                                    viewModel.setCategoryFilter(category)
                                    viewModel.searchPlaces(currentLat, currentLon, q = searchQuery.ifBlank { null })
                                },
                                onFieldPlaceClick = { p ->
                                    when (pickingField) {
                                        "origin" -> {
                                            viewModel.setRouteOrigin(p)
                                            if (destination != null) viewModel.requestRoutes(currentLat, currentLon)
                                        }
                                        "destination" -> {
                                            viewModel.setDestination(p)
                                            viewModel.requestRoutes(currentLat, currentLon)
                                        }
                                    }
                                    exitPicker()
                                },
                                onFieldPlaceInfo = { p -> viewModel.showPlaceDetail(p, currentLat, currentLon) },
                                onPickCurrentLocation = {
                                    when (pickingField) {
                                        // Origin's "current location" IS the null/default state — a
                                        // live GPS fallback resolved at request time, not a frozen
                                        // coordinate — so this just clears any custom origin back to it.
                                        "origin" -> {
                                            viewModel.setRouteOrigin(null)
                                            if (destination != null) viewModel.requestRoutes(currentLat, currentLon)
                                        }
                                        // Destination has no such "null means here" concept — it must
                                        // be a concrete point to route to, so build one from the real
                                        // GPS fix this screen opened with.
                                        "destination" -> {
                                            viewModel.setDestination(
                                                MapsPlaceResult(id = "current_location", name = "Current Location", lat = lat, lon = lon),
                                            )
                                            viewModel.requestRoutes(currentLat, currentLon)
                                        }
                                    }
                                    exitPicker()
                                },
                                onCancelPicking = { exitPicker() },
                                onPickOrigin = { pickingField = "origin"; searchQuery = ""; viewModel.clearCategoryFilter() },
                                onPickDestination = { pickingField = "destination"; searchQuery = ""; viewModel.clearCategoryFilter() },
                                onSwap = {
                                    viewModel.swapRouteEndpoints()
                                    viewModel.requestRoutes(currentLat, currentLon)
                                },
                                onRemoveStop = { stop ->
                                    viewModel.removeStop(stop)
                                    viewModel.requestRoutes(currentLat, currentLon)
                                },
                                onSelectRoute = { i -> viewModel.selectRoute(i) },
                                onStart = { viewModel.startNavigation() },
                                onClearTrip = { viewModel.clearTrip() },
                                stopsCategory = selectedCategory,
                                onStopsCategoryClick = { category ->
                                    viewModel.setCategoryFilter(category)
                                    val (mlat, mlon) = routeMidpoint ?: (currentLat to currentLon)
                                    viewModel.searchPlaces(mlat, mlon, radiusKm = 3.0, q = null)
                                },
                                stopsPlacesState = placesState,
                                onStopsPlaceClick = { p ->
                                    viewModel.addStop(p)
                                    viewModel.requestRoutes(currentLat, currentLon)
                                    viewModel.clearCategoryFilter()
                                },
                            )
                        } else {
                            ExploreTabContent(
                                query = searchQuery,
                                onQueryChange = { searchQuery = it },
                                onSubmit = {
                                    val (slat, slon) = if (exploreCenterMode == "location") lat to lon else currentLat to currentLon
                                    viewModel.searchPlaces(slat, slon, q = searchQuery.ifBlank { null })
                                },
                                centerMode = exploreCenterMode,
                                onCenterModeChange = { m ->
                                    exploreCenterMode = m
                                    if (showExploreResults) {
                                        val (slat, slon) = if (m == "location") lat to lon else currentLat to currentLon
                                        viewModel.searchPlaces(slat, slon, q = searchQuery.ifBlank { null })
                                    }
                                },
                                showResults = showExploreResults,
                                placesState = placesState,
                                selectedCategory = selectedCategory,
                                onCategoryClick = { category ->
                                    viewModel.setCategoryFilter(category)
                                    val (slat, slon) = if (exploreCenterMode == "location") lat to lon else currentLat to currentLon
                                    viewModel.searchPlaces(slat, slon, q = searchQuery.ifBlank { null })
                                },
                                onPlaceClick = { p -> viewModel.showPlaceDetail(p, currentLat, currentLon) },
                                onQuickRoute = { p ->
                                    viewModel.setDestination(p)
                                    viewModel.requestRoutes(currentLat, currentLon)
                                    viewModel.setActiveTab("route")
                                },
                                recents = recents,
                                nearbyFood = nearbyFood,
                                nearbyThingsToDo = nearbyThingsToDo,
                                citiesState = citiesState,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RoundIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    IconButton(
        onClick = onClick,
        modifier = modifier.size(44.dp).background(CardBg, CircleShape),
    ) {
        Icon(icon, contentDescription = contentDescription, tint = Color.White)
    }
}

@Composable
private fun MapsTopBar(onBack: () -> Unit, modifier: Modifier = Modifier) {
    Surface(color = SheetBg.copy(alpha = 0.94f), modifier = modifier.fillMaxWidth()) {
        Box(Modifier.statusBarsPadding().fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp)) {
            IconButton(onClick = onBack, modifier = Modifier.align(Alignment.CenterStart)) {
                Icon(Icons.Filled.ArrowBack, contentDescription = "Back", tint = Color.White)
            }
            Text(
                "Quail Maps",
                color = Color.White,
                fontWeight = FontWeight.ExtraBold,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.align(Alignment.Center),
            )
        }
    }
}

/** Content sizes itself (wraps up to [PANEL_MAX_HEIGHT], scrolls internally
 * beyond that) instead of being forced into fixed states — a real bug two
 * rounds ago (a place-detail card clipped in a too-short fixed "peek"
 * height, then wasted empty space in a too-tall fixed "expanded" height)
 * came directly from forcing every content type into the same two sizes. */
@Composable
private fun DockedPanel(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(
        color = SheetBg,
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        modifier = modifier.fillMaxWidth().heightIn(max = PANEL_MAX_HEIGHT),
    ) {
        Column(
            Modifier
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState()),
        ) {
            Box(Modifier.fillMaxWidth().padding(vertical = 10.dp), contentAlignment = Alignment.Center) {
                Box(Modifier.size(width = 36.dp, height = 4.dp).background(Color(0xFF3A4150), RoundedCornerShape(2.dp)))
            }
            content()
        }
    }
}

@Composable
private fun RouteExploreToggle(activeTab: String, onTabChange: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().background(ChipBg, RoundedCornerShape(12.dp)).padding(4.dp)) {
        TabPill("Route", selected = activeTab == "route", onClick = { onTabChange("route") }, modifier = Modifier.weight(1f))
        TabPill("Explore", selected = activeTab == "explore", onClick = { onTabChange("explore") }, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun TabPill(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Surface(
        onClick = onClick,
        color = if (selected) QuailAccent else Color.Transparent,
        shape = RoundedCornerShape(10.dp),
        modifier = modifier,
    ) {
        Box(Modifier.padding(vertical = 10.dp), contentAlignment = Alignment.Center) {
            Text(label, color = if (selected) Color.Black else Color.White, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun SearchField(
    query: String,
    onQueryChange: (String) -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        placeholder = { Text("Search restaurants, stores...", color = QuailTextDim) },
        singleLine = true,
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = ChipBg,
            unfocusedContainerColor = ChipBg,
            focusedBorderColor = Color.Transparent,
            unfocusedBorderColor = Color.Transparent,
            focusedTextColor = Color.White,
            unfocusedTextColor = Color.White,
        ),
        modifier = modifier,
        leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null, tint = QuailTextDim) },
        trailingIcon = {
            if (query.isNotBlank()) {
                IconButton(onClick = { onQueryChange("") }) {
                    Icon(Icons.Filled.Close, contentDescription = "Clear search", tint = QuailTextDim)
                }
            }
        },
        keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSearch = { onSubmit() }),
        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
            imeAction = androidx.compose.ui.text.input.ImeAction.Search,
        ),
    )
}

@Composable
private fun DiscoveryRow(title: String, places: List<MapsPlaceResult>, onPlaceClick: (MapsPlaceResult) -> Unit) {
    Text(title, color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelLarge)
    Spacer(Modifier.height(8.dp))
    LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        items(places) { place -> RecentPlaceChip(place, onClick = { onPlaceClick(place) }) }
    }
}

@Composable
private fun CitiesSection(citiesState: CitiesUiState) {
    val cities = (citiesState as? CitiesUiState.Success)?.cities ?: return
    if (cities.current == null && cities.nearby.isEmpty()) return
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Filled.LocationCity, contentDescription = null, tint = QuailTextDim, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        Text("Nearby Cities", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelLarge)
    }
    Spacer(Modifier.height(8.dp))
    cities.current?.let { current ->
        Text("You're near ${current.name}", color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(8.dp))
    }
    if (cities.nearby.isNotEmpty()) {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(cities.nearby) { city -> CityChip(city) }
        }
    }
}

@Composable
private fun CityChip(city: MapsCityResult) {
    Surface(color = ChipBg, shape = RoundedCornerShape(12.dp)) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            Text(city.name, color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
            Text(formatDistanceImperial(city.distanceKm * 1000.0), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun RecentPlaceChip(place: MapsPlaceResult, onClick: () -> Unit) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(72.dp).clickable(onClick = onClick),
    ) {
        Box(Modifier.size(48.dp).background(ChipBg, CircleShape), contentAlignment = Alignment.Center) {
            Text(place.icon.ifBlank { "📍" }, style = MaterialTheme.typography.titleLarge)
        }
        Spacer(Modifier.height(6.dp))
        Text(
            place.name,
            color = Color.White,
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        Text(
            formatDistanceImperial(place.distanceKm * 1000.0),
            color = QuailTextDim,
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

@Composable
private fun PlaceRow(place: MapsPlaceResult, onClick: () -> Unit) {
    Surface(color = CardBg, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth(), onClick = onClick) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).background(ChipBg, CircleShape), contentAlignment = Alignment.Center) {
                    Text(place.icon.ifBlank { "📍" }, style = MaterialTheme.typography.titleMedium)
                }
                Spacer(Modifier.width(10.dp))
                Column {
                    Text(place.name, color = Color.White, fontWeight = FontWeight.Bold)
                    val subtitle = listOfNotNull(
                        place.category.takeIf { it.isNotBlank() }?.replaceFirstChar { it.uppercase() },
                        place.openingHours.takeIf { it.isNotBlank() },
                    ).joinToString(" · ")
                    if (subtitle.isNotBlank()) {
                        Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            Text(formatDistanceImperial(place.distanceKm * 1000.0), color = QuailGoodGreen, style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** A result row with two distinct taps — the row body opens the place's
 * detail card (view info, hours, phone, website — without committing to
 * anything), the trailing circular button performs a quick action
 * immediately (route there, or select this field). Used by both the
 * Explore tab (quick-route arrow) and the Route tab's field picker (quick-
 * select checkmark) — previously the field picker only had the instant-
 * select tap, so there was no way to see a place's info without it
 * immediately becoming your destination. */
@Composable
private fun QuickActionPlaceRow(
    place: MapsPlaceResult,
    onClick: () -> Unit,
    actionIcon: ImageVector,
    actionColor: Color,
    actionContentDescription: String,
    onAction: () -> Unit,
) {
    Surface(color = CardBg, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth(), onClick = onClick) {
        Row(Modifier.padding(12.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(40.dp).background(ChipBg, CircleShape), contentAlignment = Alignment.Center) {
                Text(place.icon.ifBlank { "📍" }, style = MaterialTheme.typography.titleMedium)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(place.name, color = Color.White, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val subtitle = listOfNotNull(
                    place.category.takeIf { it.isNotBlank() }?.replaceFirstChar { it.uppercase() },
                    place.address.takeIf { it.isNotBlank() },
                ).joinToString(" · ")
                if (subtitle.isNotBlank()) {
                    Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.width(8.dp))
            Text(formatDistanceImperial(place.distanceKm * 1000.0), color = QuailGoodGreen, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.width(8.dp))
            IconButton(onClick = onAction, modifier = Modifier.size(32.dp).background(actionColor, CircleShape)) {
                Icon(actionIcon, contentDescription = actionContentDescription, tint = Color.Black, modifier = Modifier.size(16.dp))
            }
        }
    }
}

@Composable
private fun PlaceDetailContent(
    place: MapsPlaceResult,
    hasExistingTrip: Boolean,
    previewRoute: MapsRouteOption?,
    // Non-null when this detail card was opened from the Route tab's field
    // picker (label, onClick) — replaces the normal Drive/Add-Stop pill
    // with an explicit "Set as Starting Point"/"Set as Destination" pill,
    // so viewing a place's info from that flow doesn't itself commit it to
    // anything; picking it is now a separate, deliberate action.
    selectAction: Pair<String, () -> Unit>?,
    onDismiss: () -> Unit,
    onAddStop: () -> Unit,
) {
    val context = LocalContext.current
    Column(Modifier.padding(20.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(44.dp).background(ChipBg, CircleShape), contentAlignment = Alignment.Center) {
                    Text(place.icon.ifBlank { "📍" }, style = MaterialTheme.typography.titleLarge)
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(place.name, color = Color.White, fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.titleLarge)
                    if (place.category.isNotBlank()) {
                        Text(place.category.replaceFirstChar { it.uppercase() }, color = QuailTextDim, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close", tint = Color.White) }
        }

        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (selectAction != null) {
                val (label, onClick) = selectAction
                PillButton(icon = Icons.Filled.Check, label = label, containerColor = QuailGoodGreen, contentColor = Color.Black, onClick = onClick)
            } else {
                PillButton(
                    icon = Icons.Filled.DirectionsCar,
                    label = previewRoute?.let { "${(it.durationSec / 60.0).roundToInt()} min" } ?: (if (hasExistingTrip) "Add Stop" else "Drive"),
                    containerColor = QuailAccent,
                    contentColor = Color.Black,
                    onClick = onAddStop,
                )
            }
            if (place.phone.isNotBlank()) {
                PillButton(Icons.Filled.Call, "Call", ChipBg, Color.White) {
                    runCatching { context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${place.phone}"))) }
                }
            }
            if (place.website.isNotBlank()) {
                PillButton(Icons.Filled.Language, "Website", ChipBg, Color.White) {
                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(place.website))) }
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
            StatBlock("Hours", place.openingHours.ifBlank { "Not listed" })
            StatBlock("Distance", formatDistanceImperial(place.distanceKm * 1000.0))
        }
        if (place.address.isNotBlank()) {
            Spacer(Modifier.height(12.dp))
            Text(place.address, color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
        }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun PillButton(icon: ImageVector, label: String, containerColor: Color, contentColor: Color, onClick: () -> Unit) {
    Surface(onClick = onClick, color = containerColor, shape = RoundedCornerShape(14.dp)) {
        Column(
            Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, contentDescription = label, tint = contentColor, modifier = Modifier.size(20.dp))
            Spacer(Modifier.height(2.dp))
            Text(label, color = contentColor, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun StatBlock(label: String, value: String) {
    Column {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Text(value, color = Color.White, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun RouteFieldRow(icon: ImageVector, tint: Color, label: String, isPlaceholder: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, color = ChipBg, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 13.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(10.dp))
            Text(label, color = if (isPlaceholder) QuailTextDim else Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** Pinned above the field picker's search results, regardless of query —
 * lets a field be set to (or reset to) wherever the phone actually is,
 * same as every real map app's "Current Location" search entry. */
@Composable
private fun CurrentLocationRow(onClick: () -> Unit) {
    Surface(color = CardBg, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth(), onClick = onClick) {
        Row(Modifier.padding(12.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(40.dp).background(QuailAccent.copy(alpha = 0.18f), CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.MyLocation, contentDescription = null, tint = QuailAccent, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(10.dp))
            Text("Current Location", color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun SwapButton(onClick: () -> Unit) {
    Box(Modifier.fillMaxWidth().padding(vertical = 2.dp), contentAlignment = Alignment.Center) {
        IconButton(onClick = onClick, modifier = Modifier.size(32.dp).background(ChipBg, CircleShape)) {
            Icon(Icons.Filled.SwapVert, contentDescription = "Swap start and destination", tint = QuailAccent, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun RemovableChip(label: String, onRemove: () -> Unit) {
    Surface(color = ChipBg, shape = RoundedCornerShape(10.dp)) {
        Row(Modifier.padding(start = 10.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                label, color = Color.White, style = MaterialTheme.typography.labelSmall,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 100.dp),
            )
            IconButton(onClick = onRemove, modifier = Modifier.size(20.dp)) {
                Icon(Icons.Filled.Close, contentDescription = "Remove stop", tint = QuailTextDim, modifier = Modifier.size(14.dp))
            }
        }
    }
}

@Composable
private fun RouteTabContent(
    routeOrigin: MapsPlaceResult?,
    destination: MapsPlaceResult?,
    stops: List<MapsPlaceResult>,
    routeState: RouteUiState,
    mode: String,
    onModeChange: (String) -> Unit,
    // Which field (if any) is being actively edited in place — "origin",
    // "destination", or null. Editing a field replaces JUST that field's
    // row with a search box + inline results; the tab toggle, the other
    // field, and the swap button all stay visible around it. Earlier this
    // opened a completely separate full-panel search screen (hiding the
    // Route/Explore toggle entirely), which — since it reused the same
    // search field + category chip styling as the old search-first
    // design — looked and felt like "the old search bar" reappearing
    // rather than an in-place edit of one field.
    pickingField: String?,
    fieldQuery: String,
    onFieldQueryChange: (String) -> Unit,
    onFieldSubmit: () -> Unit,
    fieldPlacesState: PlacesUiState,
    fieldSelectedCategory: String?,
    onFieldCategoryClick: (String) -> Unit,
    onFieldPlaceClick: (MapsPlaceResult) -> Unit,
    onFieldPlaceInfo: (MapsPlaceResult) -> Unit,
    onPickCurrentLocation: () -> Unit,
    onCancelPicking: () -> Unit,
    onPickOrigin: () -> Unit,
    onPickDestination: () -> Unit,
    onSwap: () -> Unit,
    onRemoveStop: (MapsPlaceResult) -> Unit,
    onSelectRoute: (Int) -> Unit,
    onStart: () -> Unit,
    onClearTrip: () -> Unit,
    stopsCategory: String?,
    onStopsCategoryClick: (String) -> Unit,
    stopsPlacesState: PlacesUiState,
    onStopsPlaceClick: (MapsPlaceResult) -> Unit,
) {
    Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
        if (pickingField == "origin") {
            EditableFieldSearch(fieldQuery, onFieldQueryChange, onFieldSubmit, onCancelPicking)
        } else {
            RouteFieldRow(Icons.Filled.MyLocation, QuailAccent, routeOrigin?.name ?: "My Location", isPlaceholder = routeOrigin == null, onClick = onPickOrigin)
        }

        if (pickingField == null) SwapButton(onSwap)

        if (pickingField == "destination") {
            EditableFieldSearch(fieldQuery, onFieldQueryChange, onFieldSubmit, onCancelPicking)
        } else {
            RouteFieldRow(Icons.Filled.Place, QuailBadRed, destination?.name ?: "Destination", isPlaceholder = destination == null, onClick = onPickDestination)
        }

        if (pickingField != null) {
            Spacer(Modifier.height(10.dp))
            CurrentLocationRow(onClick = onPickCurrentLocation)
            Spacer(Modifier.height(8.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(CATEGORY_FILTERS) { (category, icon) ->
                    FilterChip(
                        selected = fieldSelectedCategory == category,
                        onClick = { onFieldCategoryClick(category) },
                        label = { Text("$icon ${category.replaceFirstChar { it.uppercase() }}") },
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            when (fieldPlacesState) {
                is PlacesUiState.Idle -> Text("Search for a place", color = QuailTextDim, modifier = Modifier.padding(vertical = 12.dp))
                is PlacesUiState.Loading -> Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                is PlacesUiState.Error -> Text(fieldPlacesState.message, color = QuailBadRed)
                is PlacesUiState.Success -> {
                    if (fieldPlacesState.places.isEmpty()) {
                        Text("Nothing found.", color = QuailTextDim, modifier = Modifier.padding(vertical = 12.dp))
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            val fieldColor = if (pickingField == "origin") QuailAccent else QuailBadRed
                            fieldPlacesState.places.forEach { p ->
                                QuickActionPlaceRow(
                                    place = p, onClick = { onFieldPlaceInfo(p) },
                                    actionIcon = Icons.Filled.Check, actionColor = fieldColor,
                                    actionContentDescription = "Select", onAction = { onFieldPlaceClick(p) },
                                )
                            }
                        }
                    }
                }
            }
        } else {
            if (stops.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(stops) { stop -> RemovableChip(stop.name, onRemove = { onRemoveStop(stop) }) }
                }
            }

            if (destination != null) {
                Spacer(Modifier.height(12.dp))
                ModeToggle(mode = mode, onModeChange = onModeChange)
                Spacer(Modifier.height(10.dp))
                RouteResultsSection(routeState = routeState, onSelectRoute = onSelectRoute, onStart = onStart)
                Spacer(Modifier.height(14.dp))
                StopsAlongSection(
                    selectedCategory = stopsCategory,
                    onCategoryClick = onStopsCategoryClick,
                    placesState = stopsPlacesState,
                    onPlaceClick = onStopsPlaceClick,
                )
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = onClearTrip) { Text("Clear Route", color = QuailTextDim) }
            }
        }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun EditableFieldSearch(query: String, onQueryChange: (String) -> Unit, onSubmit: () -> Unit, onCancel: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 3.dp)) {
        SearchField(query, onQueryChange, onSubmit, modifier = Modifier.weight(1f))
        TextButton(onClick = onCancel) { Text("Cancel", color = QuailAccent) }
    }
}

/** Drive/Walk only — no Transit pill. This routing engine is Dijkstra over
 * the OSM road/path graph, not backed by any real transit schedule feed
 * (GTFS); a "Transit" option here would have nothing to route with. */
@Composable
private fun ModeToggle(mode: String, onModeChange: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        ModePill("Drive", Icons.Filled.DirectionsCar, selected = mode == "drive", onClick = { onModeChange("drive") })
        ModePill("Walk", Icons.Filled.DirectionsWalk, selected = mode == "walk", onClick = { onModeChange("walk") })
    }
}

@Composable
private fun ModePill(label: String, icon: ImageVector, selected: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, color = if (selected) QuailAccent else ChipBg, shape = RoundedCornerShape(12.dp)) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = if (selected) Color.Black else Color.White, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(label, color = if (selected) Color.Black else Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun RouteResultsSection(routeState: RouteUiState, onSelectRoute: (Int) -> Unit, onStart: () -> Unit) {
    when (routeState) {
        is RouteUiState.Loading -> {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp))
                Text("Finding routes...", color = Color.White)
            }
        }
        is RouteUiState.Error -> Text(routeState.message, color = QuailBadRed)
        is RouteUiState.Success -> {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                routeState.options.forEachIndexed { i, option ->
                    RankedRouteCard(rank = i + 1, option = option, selected = i == routeState.selectedIndex, onClick = { onSelectRoute(i) })
                }
            }
            Spacer(Modifier.height(8.dp))
            Button(onClick = onStart, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = QuailGoodGreen)) {
                Text("GO", color = Color.Black, fontWeight = FontWeight.ExtraBold)
            }
        }
        is RouteUiState.Idle -> {}
    }
}

@Composable
private fun RankedRouteCard(rank: Int, option: MapsRouteOption, selected: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, color = if (selected) CardBg else Color(0xFF0F131B), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(24.dp).background(if (selected) QuailAccent else ChipBg, CircleShape), contentAlignment = Alignment.Center) {
                    Text("$rank", color = if (selected) Color.Black else Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                }
                Spacer(Modifier.width(10.dp))
                Column {
                    Text(
                        "${(option.durationSec / 60.0).roundToInt()} min · ${formatDistanceImperial(option.distanceM)}",
                        color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(option.label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            if (selected) Icon(Icons.Filled.Check, contentDescription = "Selected", tint = QuailAccent)
        }
    }
}

@Composable
private fun StopsAlongSection(
    selectedCategory: String?,
    onCategoryClick: (String) -> Unit,
    placesState: PlacesUiState,
    onPlaceClick: (MapsPlaceResult) -> Unit,
) {
    Text("STOPS ALONG THE WAY", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
    Spacer(Modifier.height(8.dp))
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(CATEGORY_FILTERS) { (category, icon) ->
            FilterChip(
                selected = selectedCategory == category,
                onClick = { onCategoryClick(category) },
                label = { Text("$icon ${category.replaceFirstChar { it.uppercase() }}") },
            )
        }
    }
    if (selectedCategory != null) {
        Spacer(Modifier.height(8.dp))
        when (placesState) {
            is PlacesUiState.Loading -> {
                Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp))
                }
            }
            is PlacesUiState.Error -> Text(placesState.message, color = QuailBadRed)
            is PlacesUiState.Success -> {
                if (placesState.places.isEmpty()) {
                    Text("Nothing found along the way.", color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        placesState.places.take(5).forEach { p -> PlaceRow(p, onClick = { onPlaceClick(p) }) }
                    }
                }
            }
            is PlacesUiState.Idle -> {}
        }
    }
}

@Composable
private fun ExploreTabContent(
    query: String,
    onQueryChange: (String) -> Unit,
    onSubmit: () -> Unit,
    centerMode: String,
    onCenterModeChange: (String) -> Unit,
    showResults: Boolean,
    placesState: PlacesUiState,
    selectedCategory: String?,
    onCategoryClick: (String) -> Unit,
    onPlaceClick: (MapsPlaceResult) -> Unit,
    onQuickRoute: (MapsPlaceResult) -> Unit,
    recents: List<MapsPlaceResult>,
    nearbyFood: List<MapsPlaceResult>,
    nearbyThingsToDo: List<MapsPlaceResult>,
    citiesState: CitiesUiState,
) {
    Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
        SearchField(query, onQueryChange, onSubmit, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ModePill("Map view", Icons.Filled.Map, selected = centerMode == "map", onClick = { onCenterModeChange("map") })
            ModePill("My Location", Icons.Filled.MyLocation, selected = centerMode == "location", onClick = { onCenterModeChange("location") })
        }
        Spacer(Modifier.height(10.dp))
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(CATEGORY_FILTERS) { (category, icon) ->
                FilterChip(
                    selected = selectedCategory == category,
                    onClick = { onCategoryClick(category) },
                    label = { Text("$icon ${category.replaceFirstChar { it.uppercase() }}") },
                )
            }
        }
        Spacer(Modifier.height(10.dp))

        if (showResults) {
            when (placesState) {
                is PlacesUiState.Idle -> {}
                is PlacesUiState.Loading -> Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                is PlacesUiState.Error -> Text(placesState.message, color = QuailBadRed)
                is PlacesUiState.Success -> {
                    if (placesState.places.isEmpty()) {
                        Text("Nothing found nearby.", color = QuailTextDim)
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            placesState.places.forEach { p ->
                                QuickActionPlaceRow(
                                    place = p, onClick = { onPlaceClick(p) },
                                    actionIcon = Icons.Filled.ArrowForward, actionColor = QuailAccent,
                                    actionContentDescription = "Route here", onAction = { onQuickRoute(p) },
                                )
                            }
                        }
                    }
                }
            }
        } else {
            if (recents.isNotEmpty()) {
                DiscoveryRow("Recent Places", recents, onPlaceClick)
                Spacer(Modifier.height(16.dp))
            }
            CitiesSection(citiesState)
            if (nearbyThingsToDo.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                DiscoveryRow("Things to Do Near You", nearbyThingsToDo, onPlaceClick)
            }
            if (nearbyFood.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                // Deliberately "near you", not "top" — OpenStreetMap has no
                // rating/review data source to rank these by.
                DiscoveryRow("Restaurants Near You", nearbyFood, onPlaceClick)
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
private fun NavigationTopBanner(
    currentStep: MapsRouteStep?,
    nextStep: MapsRouteStep?,
    distanceToManeuverM: Double,
    locationError: String?,
    modifier: Modifier = Modifier,
) {
    Column(modifier) {
        if (locationError != null) {
            Surface(color = QuailBadRed, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp)) {
                Text(locationError, color = Color.White, modifier = Modifier.padding(8.dp), style = MaterialTheme.typography.bodySmall)
            }
        }
        Surface(color = CardBg, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(44.dp).background(QuailAccent.copy(alpha = 0.22f), CircleShape), contentAlignment = Alignment.Center) {
                    Icon(turnIconFor(currentStep?.instruction ?: ""), contentDescription = null, tint = QuailAccent, modifier = Modifier.size(26.dp))
                }
                Spacer(Modifier.width(14.dp))
                Column {
                    if (distanceToManeuverM > 0) {
                        Text(formatDistanceImperial(distanceToManeuverM), color = QuailAccent, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                    }
                    Text(
                        currentStep?.instruction ?: "Finding your route...",
                        color = Color.White,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.ExtraBold,
                    )
                }
            }
        }
        if (nextStep != null) {
            Surface(color = SheetBg, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(turnIconFor(nextStep.instruction), contentDescription = null, tint = QuailTextDim, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(10.dp))
                    Text("Then ${nextStep.street.ifBlank { nextStep.instruction }}", color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun NavigationBottomBar(arrivalClock: String, minutesRemaining: Int, distanceRemaining: String, modifier: Modifier = Modifier) {
    Surface(color = SheetBg, shape = RoundedCornerShape(18.dp), modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(vertical = 14.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            NavStat(arrivalClock, "arrival")
            NavStat("$minutesRemaining", "min")
            NavStat(distanceRemaining, "")
        }
    }
}

@Composable
private fun NavStat(value: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, color = Color.White, fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.titleLarge)
        if (label.isNotBlank()) Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
    }
}
