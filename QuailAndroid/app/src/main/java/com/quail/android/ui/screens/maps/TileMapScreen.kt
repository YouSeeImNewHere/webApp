package com.quail.android.ui.screens.maps

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsPlaceResult
import com.quail.android.data.model.MapsRouteOption
import com.quail.android.data.model.MapsRoutePoint
import com.quail.android.data.model.MapsRouteStep
import com.quail.android.ui.theme.QuailAccent
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.delay
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sqrt

private val CATEGORY_FILTERS = listOf(
    "gas" to "⛽", "food" to "🍔", "coffee" to "☕", "attraction" to "🎡",
    "museum" to "🏛️", "viewpoint" to "🌆", "park" to "🌳",
    "historic" to "🗿", "lodging" to "🏨",
)

private const val SEARCH_DEBOUNCE_MS = 300L

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

    val placesState by viewModel.placesState.collectAsState()
    val selectedCategory by viewModel.selectedCategory.collectAsState()
    val selectedPlace by viewModel.selectedPlace.collectAsState()
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

    LaunchedEffect(searchQuery) {
        if (searchQuery.isBlank()) return@LaunchedEffect
        delay(SEARCH_DEBOUNCE_MS)
        viewModel.searchPlaces(currentLat, currentLon, q = searchQuery)
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

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Map", fontWeight = FontWeight.ExtraBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF0A0D13)),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
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
                NavigationBanner(
                    currentStep = selectedRoute?.steps?.getOrNull(currentStepIndex),
                    nextStep = selectedRoute?.steps?.getOrNull(currentStepIndex + 1),
                    distanceToManeuverM = distanceToManeuverM,
                    locationError = locationError,
                    onExit = { viewModel.clearTrip() },
                    modifier = Modifier.align(Alignment.TopCenter).padding(12.dp),
                )
            } else {
                Column(Modifier.align(Alignment.TopCenter).fillMaxWidth().padding(12.dp)) {
                    SearchBar(
                        query = searchQuery,
                        onQueryChange = { searchQuery = it },
                        onFocusChanged = { searchFocused = it },
                        onSubmit = { viewModel.searchPlaces(currentLat, currentLon, q = searchQuery.ifBlank { null }) },
                    )

                    if (showResults) {
                        Spacer(Modifier.padding(top = 8.dp))
                        SearchResultsPanel(
                            placesState = placesState,
                            selectedCategory = selectedCategory,
                            onCategoryClick = { category ->
                                viewModel.setCategoryFilter(category)
                                viewModel.searchPlaces(currentLat, currentLon, q = searchQuery.ifBlank { null })
                            },
                            onPlaceClick = { place ->
                                viewModel.showPlaceDetail(place)
                                searchFocused = false
                            },
                        )
                    } else if (routeState !is RouteUiState.Idle) {
                        Spacer(Modifier.padding(top = 8.dp))
                        RoutePickerCard(
                            routeState = routeState,
                            onSelectRoute = { i -> viewModel.selectRoute(i) },
                            onStart = { viewModel.startNavigation() },
                            onClear = { viewModel.clearTrip() },
                        )
                    } else if (destination != null) {
                        Spacer(Modifier.padding(top = 8.dp))
                        TripBar(
                            stops = stops,
                            destination = destination,
                            onGetRoutes = { viewModel.requestRoutes(currentLat, currentLon) },
                            onClear = { viewModel.clearTrip() },
                        )
                    }
                }
            }

            selectedPlace?.let { place ->
                PlaceDetailSheet(
                    place = place,
                    hasExistingTrip = destination != null,
                    onDismiss = { viewModel.dismissPlaceDetail() },
                    onAddStop = {
                        val hadDestination = destination != null
                        viewModel.addStop(place)
                        if (!hadDestination) {
                            viewModel.requestRoutes(currentLat, currentLon)
                        }
                    },
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            }
        }
    }
}

@Composable
private fun SearchBar(
    query: String,
    onQueryChange: (String) -> Unit,
    onFocusChanged: (Boolean) -> Unit,
    onSubmit: () -> Unit,
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        placeholder = { Text("Search Maps") },
        singleLine = true,
        modifier = Modifier
            .fillMaxWidth()
            .onFocusChanged { onFocusChanged(it.isFocused) },
        leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
        trailingIcon = {
            if (query.isNotBlank()) {
                IconButton(onClick = { onQueryChange("") }) {
                    Icon(Icons.Filled.Close, contentDescription = "Clear search")
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
private fun SearchResultsPanel(
    placesState: PlacesUiState,
    selectedCategory: String?,
    onCategoryClick: (String) -> Unit,
    onPlaceClick: (MapsPlaceResult) -> Unit,
) {
    Surface(
        color = Color(0xFF11151D),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth().heightIn(max = 420.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                items(CATEGORY_FILTERS) { (category, icon) ->
                    FilterChip(
                        selected = selectedCategory == category,
                        onClick = { onCategoryClick(category) },
                        label = { Text("$icon ${category.replaceFirstChar { it.uppercase() }}") },
                    )
                }
            }

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
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            items(placesState.places) { place -> PlaceRow(place, onClick = { onPlaceClick(place) }) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PlaceRow(place: MapsPlaceResult, onClick: () -> Unit) {
    Surface(color = Color(0xFF171C26), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth(), onClick = onClick) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(place.icon.ifBlank { "📍" }, style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.width(10.dp))
                Column {
                    Text(place.name, color = Color.White, fontWeight = FontWeight.Bold)
                    if (place.address.isNotBlank()) {
                        Text(place.address, color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Text(formatDistanceImperial(place.distanceKm * 1000.0), color = QuailGoodGreen, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun PlaceDetailSheet(
    place: MapsPlaceResult,
    hasExistingTrip: Boolean,
    onDismiss: () -> Unit,
    onAddStop: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        color = Color(0xFF11151D),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(place.icon.ifBlank { "📍" }, style = MaterialTheme.typography.headlineMedium)
                    Spacer(Modifier.width(10.dp))
                    Text(place.name, color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                }
                IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close", tint = Color.White) }
            }
            Spacer(Modifier.padding(top = 12.dp))
            if (place.address.isNotBlank()) {
                DetailRow(icon = "📍", text = place.address)
            }
            DetailRow(
                icon = "🕒",
                text = place.openingHours.ifBlank { "Hours not listed" },
                dim = place.openingHours.isBlank(),
            )
            DetailRow(icon = "📏", text = "${formatDistanceImperial(place.distanceKm * 1000.0)} away")
            Spacer(Modifier.padding(top = 12.dp))
            Button(onClick = onAddStop, modifier = Modifier.fillMaxWidth()) {
                Text(if (hasExistingTrip) "Add Stop" else "Route Here")
            }
        }
    }
}

@Composable
private fun DetailRow(icon: String, text: String, dim: Boolean = false) {
    Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(icon, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.width(10.dp))
        Text(text, color = if (dim) QuailTextDim else Color.White, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun TripBar(
    stops: List<MapsPlaceResult>,
    destination: MapsPlaceResult?,
    onGetRoutes: () -> Unit,
    onClear: () -> Unit,
) {
    if (destination == null) return
    Surface(color = Color(0xFF171C26), shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            stops.forEach { stop ->
                Text("● ${stop.name}", color = QuailTextDim, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 2.dp))
            }
            Text("📍 ${destination.name}", color = Color.White, fontWeight = FontWeight.Bold)
            Spacer(Modifier.padding(top = 8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onGetRoutes) { Text(if (stops.isEmpty()) "Get Routes" else "Get Routes (${stops.size + 1} stops)") }
                IconButton(onClick = onClear) { Icon(Icons.Filled.Close, contentDescription = "Clear trip", tint = Color.White) }
            }
        }
    }
}

@Composable
private fun RoutePickerCard(
    routeState: RouteUiState,
    onSelectRoute: (Int) -> Unit,
    onStart: () -> Unit,
    onClear: () -> Unit,
) {
    Surface(color = Color(0xFF171C26), shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Choose a route", color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                IconButton(onClick = onClear) { Icon(Icons.Filled.Close, contentDescription = "Clear route", tint = Color.White) }
            }
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
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 8.dp)) {
                        routeState.options.forEachIndexed { i, option ->
                            RouteOptionRow(option, selected = i == routeState.selectedIndex, onClick = { onSelectRoute(i) })
                        }
                    }
                    val selected = routeState.options.getOrNull(routeState.selectedIndex)
                    if (selected != null) {
                        TurnByTurnList(steps = selected.steps)
                    }
                    Button(onClick = onStart, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                        Icon(Icons.Filled.Navigation, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Start")
                    }
                }
                is RouteUiState.Idle -> {}
            }
        }
    }
}

@Composable
private fun RouteOptionRow(option: MapsRouteOption, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (selected) QuailSurfaceRaised else Color(0xFF0F131B),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(option.label, color = Color.White, fontWeight = FontWeight.Bold)
                Text(
                    "${formatDistanceImperial(option.distanceM)} · ${(option.durationSec / 60.0).roundToInt()} min",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (selected) Icon(Icons.Filled.Check, contentDescription = "Selected", tint = QuailAccent)
        }
    }
}

@Composable
private fun NavigationBanner(
    currentStep: MapsRouteStep?,
    nextStep: MapsRouteStep?,
    distanceToManeuverM: Double,
    locationError: String?,
    onExit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(color = Color(0xFF171C26), shape = RoundedCornerShape(16.dp), modifier = modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(Modifier.weight(1f)) {
                if (locationError != null) {
                    Text(locationError, color = QuailBadRed, style = MaterialTheme.typography.bodySmall)
                }
                Text(
                    formatDistanceImperial(distanceToManeuverM),
                    color = QuailAccent,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.ExtraBold,
                )
                Text(
                    currentStep?.instruction ?: "Finding your route...",
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                if (nextStep != null) {
                    Text(
                        "Then ${nextStep.instruction}",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            IconButton(onClick = onExit) {
                Icon(Icons.Filled.Close, contentDescription = "Exit navigation", tint = Color.White)
            }
        }
    }
}

@Composable
private fun TurnByTurnList(steps: List<MapsRouteStep>) {
    if (steps.isEmpty()) return
    LazyColumn(modifier = Modifier.heightIn(max = 140.dp)) {
        items(steps) { step ->
            Column(Modifier.padding(horizontal = 4.dp, vertical = 4.dp)) {
                Text(step.instruction, color = Color.White, style = MaterialTheme.typography.bodySmall)
                if (step.distanceM > 0) {
                    Text(
                        formatDistanceImperial(step.distanceM),
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }
    }
}
