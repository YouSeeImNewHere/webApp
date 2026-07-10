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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.quail.android.data.maps.MapsRepository
import com.quail.android.data.model.MapsPlaceResult
import com.quail.android.data.model.MapsRoutePoint
import com.quail.android.data.model.MapsRouteStep
import com.quail.android.ui.theme.QuailAccent
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailTextDim
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sqrt

private val CATEGORY_FILTERS = listOf(
    "gas" to "⛽", "food" to "🍔", "coffee" to "☕", "attraction" to "🎡",
    "museum" to "🏛️", "viewpoint" to "🌆", "park" to "🌳",
    "historic" to "🗿", "lodging" to "🏨",
)

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
    var discoverOpen by remember { mutableStateOf(false) }

    val placesState by viewModel.placesState.collectAsState()
    val selectedCategory by viewModel.selectedCategory.collectAsState()
    val destination by viewModel.destination.collectAsState()
    val routeState by viewModel.routeState.collectAsState()
    val navigating by viewModel.navigating.collectAsState()
    val liveLocation by viewModel.liveLocation.collectAsState()
    val locationError by viewModel.locationError.collectAsState()

    val destinationLatLon = destination?.let { it.lat to it.lon }
    val route = (routeState as? RouteUiState.Success)?.route
    val routePoints = route?.points?.map { it.lat to it.lon }

    val nearestPointIndex = remember(liveLocation, route) {
        val r = route ?: return@remember 0
        val loc = liveLocation ?: return@remember 0
        findNearestPointIndex(r.points, loc.latitude, loc.longitude)
    }
    val currentStepIndex = remember(nearestPointIndex, route) {
        route?.let { currentStepIndexFor(it.steps, nearestPointIndex) } ?: 0
    }
    val distanceToManeuverM = remember(liveLocation, route, currentStepIndex) {
        val r = route ?: return@remember 0.0
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
        floatingActionButton = {
            if (!discoverOpen && !navigating) {
                ExtendedFloatingActionButton(
                    onClick = {
                        discoverOpen = true
                        viewModel.searchPlaces(currentLat, currentLon)
                    },
                    icon = { Icon(Icons.Filled.Search, contentDescription = null) },
                    text = { Text("Discover") },
                )
            }
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
                    currentStep = route?.steps?.getOrNull(currentStepIndex),
                    nextStep = route?.steps?.getOrNull(currentStepIndex + 1),
                    distanceToManeuverM = distanceToManeuverM,
                    locationError = locationError,
                    onExit = { viewModel.clearDestination() },
                    modifier = Modifier.align(Alignment.TopCenter).padding(12.dp),
                )
            } else {
                RouteSummaryOverlay(
                    routeState = routeState,
                    destinationName = destination?.name,
                    onClear = { viewModel.clearDestination() },
                    onStart = { viewModel.startNavigation() },
                    modifier = Modifier.align(Alignment.TopCenter).padding(12.dp),
                )
            }

            if (discoverOpen) {
                DiscoverPanel(
                    placesState = placesState,
                    selectedCategory = selectedCategory,
                    onCategoryClick = { category ->
                        viewModel.setCategoryFilter(category)
                        viewModel.searchPlaces(currentLat, currentLon)
                    },
                    onSearch = { q -> viewModel.searchPlaces(currentLat, currentLon, q = q.ifBlank { null }) },
                    onClose = { discoverOpen = false },
                    onPlaceSelected = { place ->
                        viewModel.selectDestination(place, currentLat, currentLon)
                        discoverOpen = false
                    },
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            }
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
                    "${distanceToManeuverM.roundToInt()} m",
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
private fun RouteSummaryOverlay(
    routeState: RouteUiState,
    destinationName: String?,
    onClear: () -> Unit,
    onStart: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (routeState is RouteUiState.Idle) return
    Surface(color = Color(0xFF171C26), shape = RoundedCornerShape(14.dp), modifier = modifier.fillMaxWidth()) {
        Column {
            Row(
                Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                when (routeState) {
                    is RouteUiState.Loading -> {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CircularProgressIndicator(modifier = Modifier.size(18.dp))
                            Text("Finding a route...", color = Color.White)
                        }
                    }
                    is RouteUiState.Success -> {
                        val route = routeState.route
                        val km = route.distanceM / 1000.0
                        val minutes = (route.durationSec / 60.0).roundToInt()
                        Column {
                            Text(destinationName ?: "Route", color = Color.White, fontWeight = FontWeight.Bold)
                            Text(
                                "%.1f km · %d min".format(km, minutes),
                                color = QuailTextDim,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            Button(onClick = onStart) {
                                Icon(Icons.Filled.Navigation, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(4.dp))
                                Text("Start")
                            }
                        }
                    }
                    is RouteUiState.Error -> {
                        Text(routeState.message, color = QuailBadRed)
                    }
                    is RouteUiState.Idle -> {}
                }
                IconButton(onClick = onClear) {
                    Icon(Icons.Filled.Close, contentDescription = "Clear route", tint = Color.White)
                }
            }
            if (routeState is RouteUiState.Success) {
                TurnByTurnList(steps = routeState.route.steps)
            }
        }
    }
}

@Composable
private fun TurnByTurnList(steps: List<MapsRouteStep>) {
    if (steps.isEmpty()) return
    LazyColumn(modifier = Modifier.heightIn(max = 160.dp)) {
        items(steps) { step ->
            Column(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                Text(step.instruction, color = Color.White, style = MaterialTheme.typography.bodyMedium)
                if (step.distanceM > 0) {
                    Text(
                        "${step.distanceM.roundToInt()} m",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }
    }
}

@Composable
private fun DiscoverPanel(
    placesState: PlacesUiState,
    selectedCategory: String?,
    onCategoryClick: (String) -> Unit,
    onSearch: (String) -> Unit,
    onClose: () -> Unit,
    onPlaceSelected: (MapsPlaceResult) -> Unit,
    modifier: Modifier = Modifier,
) {
    var query by remember { mutableStateOf("") }

    Surface(
        color = Color(0xFF11151D),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        modifier = modifier.fillMaxWidth().heightIn(max = 420.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("Discover", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Color.White)
                IconButton(onClick = onClose) { Icon(Icons.Filled.Close, contentDescription = "Close", tint = Color.White) }
            }

            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search nearby places") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                trailingIcon = {
                    IconButton(onClick = { onSearch(query) }) { Icon(Icons.Filled.Search, contentDescription = "Search") }
                },
            )

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
                            items(placesState.places) { place -> PlaceRow(place, onClick = { onPlaceSelected(place) }) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PlaceRow(place: MapsPlaceResult, onClick: () -> Unit) {
    Surface(color = Color(0xFF171C26), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(place.name, color = Color.White, fontWeight = FontWeight.Bold)
                if (place.address.isNotBlank()) {
                    Text(place.address, color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("%.1f km".format(place.distanceKm), color = QuailGoodGreen, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.width(8.dp))
                Button(onClick = onClick) { Text("Go") }
            }
        }
    }
}
