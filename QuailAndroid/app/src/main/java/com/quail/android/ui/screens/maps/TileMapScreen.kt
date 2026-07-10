package com.quail.android.ui.screens.maps

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.LocationCity
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Straight
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
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
import kotlinx.coroutines.launch
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TileMapScreen(repository: MapsRepository, lat: Double, lon: Double, onBack: () -> Unit) {
    val viewModel: TileMapViewModel = viewModel(factory = TileMapViewModel.Factory(repository))

    var currentLat by remember { mutableStateOf(lat) }
    var currentLon by remember { mutableStateOf(lon) }
    var searchQuery by remember { mutableStateOf("") }
    var searchFocused by remember { mutableStateOf(false) }
    // True while the user tapped "+ Add Stop" from an already-started trip —
    // reopens the search sheet without losing the trip already in progress.
    var addingStop by remember { mutableStateOf(false) }
    // Two-state bottom sheet (collapsed/expanded), pulled up via the handle
    // — see BottomSheetChrome.
    var sheetExpanded by remember { mutableStateOf(false) }

    val placesState by viewModel.placesState.collectAsState()
    val selectedCategory by viewModel.selectedCategory.collectAsState()
    val selectedPlace by viewModel.selectedPlace.collectAsState()
    val previewRoute by viewModel.previewRoute.collectAsState()
    val recents by viewModel.recents.collectAsState()
    val nearbyFood by viewModel.nearbyFood.collectAsState()
    val nearbyThingsToDo by viewModel.nearbyThingsToDo.collectAsState()
    val citiesState by viewModel.citiesState.collectAsState()
    val mode by viewModel.mode.collectAsState()
    val stops by viewModel.stops.collectAsState()
    val destination by viewModel.destination.collectAsState()
    val routeState by viewModel.routeState.collectAsState()
    val navigating by viewModel.navigating.collectAsState()
    val liveLocation by viewModel.liveLocation.collectAsState()
    val locationError by viewModel.locationError.collectAsState()

    val selectedRoute = (routeState as? RouteUiState.Success)?.let { it.options.getOrNull(it.selectedIndex) }
    val destinationLatLon = destination?.let { it.lat to it.lon }
    val routePoints = selectedRoute?.points?.map { it.lat to it.lon }
    val showResults = searchFocused || searchQuery.isNotBlank() || selectedCategory != null

    LaunchedEffect(Unit) { viewModel.loadDiscovery(lat, lon) }

    LaunchedEffect(searchQuery) {
        if (searchQuery.isBlank()) return@LaunchedEffect
        delay(SEARCH_DEBOUNCE_MS)
        viewModel.searchPlaces(currentLat, currentLon, q = searchQuery)
    }

    // Pulling up the sheet, or focusing/typing in search, both mean "show
    // me more" — expand so results aren't squeezed into the collapsed peek
    // height (which is also what keeps them from being covered by the
    // keyboard once combined with imePadding() in BottomSheetChrome).
    LaunchedEffect(showResults) {
        if (showResults) sheetExpanded = true
    }
    // Detail/directions content is compact — default back to peek height
    // when either opens, without preventing the user from dragging it back
    // up if they want more room.
    LaunchedEffect(selectedPlace) {
        if (selectedPlace != null) sheetExpanded = false
    }
    LaunchedEffect(destination) {
        if (destination != null && selectedPlace == null) sheetExpanded = false
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
            RoundIconButton(
                icon = Icons.Filled.ArrowBack,
                contentDescription = "Back",
                onClick = onBack,
                modifier = Modifier.align(Alignment.TopStart).statusBarsPadding().padding(12.dp),
            )

            val place = selectedPlace
            val dest = destination
            val sheetHeightMode = if (place != null || (dest != null && !addingStop)) {
                SheetHeightMode.WrapContent
            } else {
                SheetHeightMode.Resizable(sheetExpanded, onExpandedChange = { sheetExpanded = it })
            }
            BottomSheetChrome(
                heightMode = sheetHeightMode,
                modifier = Modifier.align(Alignment.BottomCenter),
            ) {
                when {
                    place != null -> PlaceDetailContent(
                        place = place,
                        hasExistingTrip = dest != null,
                        previewRoute = previewRoute,
                        onDismiss = { viewModel.dismissPlaceDetail() },
                        onAddStop = {
                            viewModel.addStop(place)
                            viewModel.requestRoutes(currentLat, currentLon)
                            addingStop = false
                        },
                    )
                    dest != null && !addingStop -> DirectionsContent(
                        stops = stops,
                        destination = dest,
                        routeState = routeState,
                        mode = mode,
                        onModeChange = { m ->
                            viewModel.setMode(m)
                            viewModel.requestRoutes(currentLat, currentLon)
                        },
                        onAddStop = { addingStop = true },
                        onRemoveStop = { stop ->
                            viewModel.removeStop(stop)
                            viewModel.requestRoutes(currentLat, currentLon)
                        },
                        onSelectRoute = { i -> viewModel.selectRoute(i) },
                        onStart = { viewModel.startNavigation() },
                        onClose = { viewModel.clearTrip(); addingStop = false },
                    )
                    else -> SearchSheetContent(
                        query = searchQuery,
                        onQueryChange = { searchQuery = it },
                        onFocusChanged = { searchFocused = it },
                        onSubmit = { viewModel.searchPlaces(currentLat, currentLon, q = searchQuery.ifBlank { null }) },
                        showResults = showResults,
                        expanded = sheetExpanded,
                        placesState = placesState,
                        selectedCategory = selectedCategory,
                        onCategoryClick = { category ->
                            viewModel.setCategoryFilter(category)
                            viewModel.searchPlaces(currentLat, currentLon, q = searchQuery.ifBlank { null })
                        },
                        onPlaceClick = { p ->
                            viewModel.showPlaceDetail(p, currentLat, currentLon)
                            searchFocused = false
                        },
                        recents = recents,
                        nearbyFood = nearbyFood,
                        nearbyThingsToDo = nearbyThingsToDo,
                        citiesState = citiesState,
                        showCancel = addingStop,
                        onCancel = { addingStop = false; searchQuery = ""; searchFocused = false },
                    )
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

private val SHEET_SPRING = spring<Float>(dampingRatio = Spring.DampingRatioLowBouncy, stiffness = Spring.StiffnessMediumLow)
private val SHEET_COLLAPSED_HEIGHT = 230.dp
private val SHEET_WRAP_MAX_HEIGHT = 460.dp

/** Which of the two ways a sheet can size itself:
 * - [Resizable]: the search/discovery content, which genuinely has more to
 *   reveal — drag the handle between a small peek and ~82% of the screen.
 * - [WrapContent]: place-detail / directions content, which has a fixed
 *   amount to show and nothing more behind a drag. Forcing this into the
 *   same two states as Resizable was the actual bug a real screenshot
 *   caught: the 230dp peek clipped the bottom of a place card (hours/
 *   distance/address cut off below the visible edge), while dragging it to
 *   the 82%-screen expanded height left most of that space empty since
 *   there was never more content to fill it with — "cut short" and "wasted
 *   space" are two symptoms of the same root cause. */
private sealed interface SheetHeightMode {
    data class Resizable(val expanded: Boolean, val onExpandedChange: (Boolean) -> Unit) : SheetHeightMode
    data object WrapContent : SheetHeightMode
}

/** A real drag-to-expand bottom sheet, not a fixed-height card — pulling
 * the handle up reveals the full discovery/search content, matching the
 * iOS Quail Maps reference (NativeMapPage.swift's RoutePanel: a custom
 * capsule-handle drag, not SwiftUI .presentationDetents, two states rather
 * than a free-form continuum, with height computed per-content-type there
 * too). The drag gesture is bound ONLY to the handle's own hit box, same
 * reasoning as the iOS version — binding it to the whole sheet would fight
 * the results list's own scroll gestures. */
@Composable
private fun BottomSheetChrome(
    heightMode: SheetHeightMode,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val density = LocalDensity.current
    val configuration = LocalConfiguration.current
    val scope = rememberCoroutineScope()

    val collapsedPx = with(density) { SHEET_COLLAPSED_HEIGHT.toPx() }
    val expandedPx = with(density) { (configuration.screenHeightDp * 0.82f).dp.toPx() }
    // Declared unconditionally (Compose disallows a remember call that's
    // sometimes skipped at the same call site) — only actually driven when
    // heightMode is Resizable; WrapContent ignores it entirely in favor of
    // heightIn(max=...) below.
    val heightPx = remember { Animatable(collapsedPx) }

    if (heightMode is SheetHeightMode.Resizable) {
        LaunchedEffect(heightMode.expanded, collapsedPx, expandedPx) {
            heightPx.animateTo(if (heightMode.expanded) expandedPx else collapsedPx, animationSpec = SHEET_SPRING)
        }
    }

    val sheetModifier = when (heightMode) {
        is SheetHeightMode.WrapContent -> modifier.fillMaxWidth().heightIn(max = SHEET_WRAP_MAX_HEIGHT)
        is SheetHeightMode.Resizable -> modifier.fillMaxWidth().height(with(density) { heightPx.value.toDp() })
    }

    Surface(color = SheetBg, shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp), modifier = sheetModifier) {
        Column(Modifier.navigationBarsPadding().imePadding()) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 10.dp)
                    .then(
                        if (heightMode is SheetHeightMode.Resizable) {
                            Modifier.pointerInput(Unit) {
                                detectVerticalDragGestures(
                                    onDragEnd = {
                                        val goExpanded = heightPx.value > (collapsedPx + expandedPx) / 2
                                        heightMode.onExpandedChange(goExpanded)
                                        scope.launch {
                                            heightPx.animateTo(if (goExpanded) expandedPx else collapsedPx, animationSpec = SHEET_SPRING)
                                        }
                                    },
                                ) { change, dragAmount ->
                                    change.consume()
                                    scope.launch {
                                        heightPx.snapTo((heightPx.value - dragAmount).coerceIn(collapsedPx, expandedPx))
                                    }
                                }
                            }
                        } else {
                            Modifier
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Box(Modifier.size(width = 36.dp, height = 4.dp).background(Color(0xFF3A4150), RoundedCornerShape(2.dp)))
            }
            content()
        }
    }
}

@Composable
private fun SearchField(
    query: String,
    onQueryChange: (String) -> Unit,
    onFocusChanged: (Boolean) -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        placeholder = { Text("Search Maps", color = QuailTextDim) },
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
        modifier = modifier.onFocusChanged { onFocusChanged(it.isFocused) },
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
private fun SearchSheetContent(
    query: String,
    onQueryChange: (String) -> Unit,
    onFocusChanged: (Boolean) -> Unit,
    onSubmit: () -> Unit,
    showResults: Boolean,
    expanded: Boolean,
    placesState: PlacesUiState,
    selectedCategory: String?,
    onCategoryClick: (String) -> Unit,
    onPlaceClick: (MapsPlaceResult) -> Unit,
    recents: List<MapsPlaceResult>,
    nearbyFood: List<MapsPlaceResult>,
    nearbyThingsToDo: List<MapsPlaceResult>,
    citiesState: CitiesUiState,
    showCancel: Boolean,
    onCancel: () -> Unit,
) {
    val scrollState = rememberScrollState()
    Column(
        Modifier
            .padding(16.dp)
            .let { if (showResults) it else it.verticalScroll(scrollState) },
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SearchField(query, onQueryChange, onFocusChanged, onSubmit, modifier = Modifier.weight(1f))
            if (showCancel) {
                TextButton(onClick = onCancel) { Text("Cancel", color = QuailAccent) }
            }
        }

        if (showResults) {
            Spacer(Modifier.height(12.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(CATEGORY_FILTERS) { (category, icon) ->
                    FilterChip(
                        selected = selectedCategory == category,
                        onClick = { onCategoryClick(category) },
                        label = { Text("$icon ${category.replaceFirstChar { it.uppercase() }}") },
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            when (placesState) {
                is PlacesUiState.Idle -> {}
                is PlacesUiState.Loading -> {
                    Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                is PlacesUiState.Error -> {
                    Text(placesState.message, color = QuailBadRed, modifier = Modifier.padding(16.dp))
                }
                is PlacesUiState.Success -> {
                    if (placesState.places.isEmpty()) {
                        Text("Nothing found nearby.", color = QuailTextDim, modifier = Modifier.padding(16.dp))
                    } else {
                        LazyColumn(
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                            modifier = Modifier.heightIn(max = 440.dp),
                        ) {
                            items(placesState.places) { place -> PlaceRow(place, onClick = { onPlaceClick(place) }) }
                        }
                    }
                }
            }
        } else {
            if (recents.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                DiscoveryRow("Recent Places", recents, onPlaceClick)
            }
            if (expanded) {
                CitiesSection(citiesState)
                if (nearbyThingsToDo.isNotEmpty()) {
                    Spacer(Modifier.height(16.dp))
                    DiscoveryRow("Things to Do Near You", nearbyThingsToDo, onPlaceClick)
                }
                if (nearbyFood.isNotEmpty()) {
                    Spacer(Modifier.height(16.dp))
                    // Deliberately "near you", not "top" — OpenStreetMap has
                    // no rating/review data source to rank these by.
                    DiscoveryRow("Restaurants Near You", nearbyFood, onPlaceClick)
                }
                Spacer(Modifier.height(16.dp))
            }
        }
    }
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
    Spacer(Modifier.height(16.dp))
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

@Composable
private fun PlaceDetailContent(
    place: MapsPlaceResult,
    hasExistingTrip: Boolean,
    previewRoute: MapsRouteOption?,
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
            PillButton(
                icon = Icons.Filled.DirectionsCar,
                label = previewRoute?.let { "${(it.durationSec / 60.0).roundToInt()} min" } ?: (if (hasExistingTrip) "Add Stop" else "Drive"),
                containerColor = QuailAccent,
                contentColor = Color.Black,
                onClick = onAddStop,
            )
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
private fun StopRow(icon: ImageVector, iconTint: Color, label: String, onRemove: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(28.dp).background(iconTint.copy(alpha = 0.18f), CircleShape), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(16.dp))
        }
        Spacer(Modifier.width(10.dp))
        Text(label, color = Color.White, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (onRemove != null) {
            IconButton(onClick = onRemove, modifier = Modifier.size(28.dp)) {
                Icon(Icons.Filled.Close, contentDescription = "Remove stop", tint = QuailTextDim, modifier = Modifier.size(16.dp))
            }
        }
    }
}

@Composable
private fun DirectionsContent(
    stops: List<MapsPlaceResult>,
    destination: MapsPlaceResult,
    routeState: RouteUiState,
    mode: String,
    onModeChange: (String) -> Unit,
    onAddStop: () -> Unit,
    onRemoveStop: (MapsPlaceResult) -> Unit,
    onSelectRoute: (Int) -> Unit,
    onStart: () -> Unit,
    onClose: () -> Unit,
) {
    Column(Modifier.padding(20.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Directions", color = Color.White, fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.titleLarge)
            IconButton(onClick = onClose) { Icon(Icons.Filled.Close, contentDescription = "Close", tint = Color.White) }
        }
        Spacer(Modifier.height(10.dp))

        ModeToggle(mode = mode, onModeChange = onModeChange)
        Spacer(Modifier.height(10.dp))

        StopRow(Icons.Filled.MyLocation, QuailAccent, "My Location")
        stops.forEach { stop -> StopRow(Icons.Filled.Place, QuailAccent, stop.name, onRemove = { onRemoveStop(stop) }) }
        StopRow(Icons.Filled.Place, QuailBadRed, destination.name)

        Row(
            Modifier.fillMaxWidth().clickable(onClick = onAddStop).padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Filled.Add, contentDescription = null, tint = QuailAccent, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Text("Add Stop", color = QuailAccent, fontWeight = FontWeight.Bold)
        }

        Spacer(Modifier.height(10.dp))
        RouteSummarySection(routeState = routeState, onSelectRoute = onSelectRoute, onStart = onStart)
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
    Surface(
        onClick = onClick,
        color = if (selected) QuailAccent else ChipBg,
        shape = RoundedCornerShape(12.dp),
    ) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, contentDescription = null, tint = if (selected) Color.Black else Color.White, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(label, color = if (selected) Color.Black else Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun RouteSummarySection(
    routeState: RouteUiState,
    onSelectRoute: (Int) -> Unit,
    onStart: () -> Unit,
) {
    when (routeState) {
        is RouteUiState.Loading -> {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp))
                Text("Finding routes...", color = Color.White)
            }
        }
        is RouteUiState.Error -> {
            Text(routeState.message, color = QuailBadRed)
        }
        is RouteUiState.Success -> {
            val selected = routeState.options.getOrNull(routeState.selectedIndex)
            if (selected != null) {
                val etaMillis = System.currentTimeMillis() + (selected.durationSec * 1000).toLong()
                Surface(color = CardBg, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.padding(16.dp).fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column {
                            Text(
                                "${(selected.durationSec / 60.0).roundToInt()} min",
                                color = Color.White,
                                fontWeight = FontWeight.ExtraBold,
                                style = MaterialTheme.typography.headlineSmall,
                            )
                            Text(
                                "${formatClockTime(etaMillis)} ETA · ${formatDistanceImperial(selected.distanceM)}",
                                color = QuailTextDim,
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Text(selected.label, color = QuailAccent, style = MaterialTheme.typography.labelSmall)
                        }
                        Button(
                            onClick = onStart,
                            colors = ButtonDefaults.buttonColors(containerColor = QuailGoodGreen),
                        ) {
                            Text("GO", color = Color.Black, fontWeight = FontWeight.ExtraBold)
                        }
                    }
                }
                if (routeState.options.size > 1) {
                    Spacer(Modifier.height(8.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        routeState.options.forEachIndexed { i, option ->
                            if (i != routeState.selectedIndex) {
                                AltRouteRow(option, onClick = { onSelectRoute(i) })
                            }
                        }
                    }
                }
            }
        }
        is RouteUiState.Idle -> {}
    }
}

@Composable
private fun AltRouteRow(option: MapsRouteOption, onClick: () -> Unit) {
    Surface(onClick = onClick, color = Color(0xFF0F131B), shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 10.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(option.label, color = Color.White, style = MaterialTheme.typography.bodyMedium)
            Text(
                "${(option.durationSec / 60.0).roundToInt()} min · ${formatDistanceImperial(option.distanceM)}",
                color = QuailTextDim,
                style = MaterialTheme.typography.bodySmall,
            )
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
