package com.quail.android.ui.screens.maps

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.MapsRegionState
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.ui.theme.QuailWarnYellow
import java.util.Locale

private fun formatBytes(bytes: Long): String {
    val mb = bytes / 1_048_576.0
    return if (mb >= 1024) "%.1f GB".format(mb / 1024.0) else "%.0f MB".format(mb)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapsScreen(viewModel: MapsViewModel, onBack: () -> Unit, onOpenMap: (Double, Double) -> Unit) {
    val statusState by viewModel.status.collectAsState()
    val downloadState by viewModel.downloadState.collectAsState()
    val openMapLoading by viewModel.openMapLoading.collectAsState()
    val openMapError by viewModel.openMapError.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.openMapEvent.collect { (lat, lon) -> onOpenMap(lat, lon) }
    }

    val locationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) viewModel.downloadCurrentCity()
    }
    val openMapPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) viewModel.openLiveMap()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Maps", fontWeight = FontWeight.ExtraBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                OpenMapCard(
                    loading = openMapLoading,
                    error = openMapError,
                    onOpen = { openMapPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) },
                )
            }

            item {
                DownloadCard(
                    downloadState = downloadState,
                    onDownload = { locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) },
                    onViewMap = { lat, lon -> onOpenMap(lat, lon) },
                )
            }

            when (val s = statusState) {
                is MapsStatusUiState.Loading -> item {
                    Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                is MapsStatusUiState.Error -> item {
                    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                        Text(
                            "Couldn't reach the maps server: ${s.message}",
                            color = QuailTextDim,
                            modifier = Modifier.padding(16.dp),
                        )
                    }
                }
                is MapsStatusUiState.Success -> {
                    val staleness = s.status.carDriveStaleness
                    if (staleness != null && staleness.stale) {
                        item { StalenessCard(staleness.reason, staleness.daysSinceSync) }
                    }
                    if (s.status.regions.isEmpty()) {
                        item {
                            Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                                Text(
                                    "No regions built yet on the server.",
                                    color = QuailTextDim,
                                    modifier = Modifier.padding(16.dp),
                                )
                            }
                        }
                    } else {
                        item {
                            Text("Server coverage", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        }
                        items(s.status.regions) { region -> RegionCard(region) }
                    }
                }
            }
        }
    }
}

@Composable
private fun OpenMapCard(loading: Boolean, error: String?, onOpen: () -> Unit) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Live map", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text(
                "Pan and zoom the road network near you, streamed from the server.",
                color = QuailTextDim,
                style = MaterialTheme.typography.bodySmall,
            )
            if (error != null) {
                Text(error, color = QuailBadRed, style = MaterialTheme.typography.bodySmall)
            }
            if (loading) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(modifier = Modifier.padding(2.dp))
                    Text("Finding your location...", color = QuailTextDim)
                }
            } else {
                Button(onClick = onOpen) { Text("Open map") }
            }
        }
    }
}

@Composable
private fun DownloadCard(
    downloadState: DownloadUiState,
    onDownload: () -> Unit,
    onViewMap: (Double, Double) -> Unit,
) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Offline city map", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text(
                "Downloads roads and places around your current location for a future fully-offline mode.",
                color = QuailTextDim,
                style = MaterialTheme.typography.bodySmall,
            )
            when (downloadState) {
                is DownloadUiState.Idle -> {
                    Button(onClick = onDownload) { Text("Download current city") }
                }
                is DownloadUiState.RequestingLocation -> {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CircularProgressIndicator(modifier = Modifier.padding(2.dp))
                        Text("Finding your location...", color = QuailTextDim)
                    }
                }
                is DownloadUiState.Downloading -> {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CircularProgressIndicator(modifier = Modifier.padding(2.dp))
                        Text("Downloading map data...", color = QuailTextDim)
                    }
                }
                is DownloadUiState.Success -> {
                    Text(
                        "Saved ${formatBytes(downloadState.result.sizeBytes)} for this area.",
                        color = QuailGoodGreen,
                        fontWeight = FontWeight.Bold,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { onViewMap(downloadState.result.lat, downloadState.result.lon) }) {
                            Text("View on map")
                        }
                        Button(onClick = onDownload) { Text("Re-download") }
                    }
                }
                is DownloadUiState.Error -> {
                    Text(downloadState.message, color = QuailBadRed)
                    Button(onClick = onDownload) { Text("Try again") }
                }
            }
        }
    }
}

@Composable
private fun StalenessCard(reason: String, daysSinceSync: Int?) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(Icons.Filled.Warning, contentDescription = null, tint = QuailWarnYellow)
            Column {
                Text("Car drive needs an update", fontWeight = FontWeight.Bold, color = QuailWarnYellow)
                val detail = when (reason) {
                    "never_synced" -> "It's never been synced."
                    "behind_regions" -> "It's missing data the server has already rebuilt."
                    else -> if (daysSinceSync != null) "It's been $daysSinceSync days since the last sync." else "It's out of date."
                }
                Text(detail, color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun RegionCard(region: MapsRegionState) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                region.region.substringAfterLast("/").replaceFirstChar { it.titlecase(Locale.US) },
                fontWeight = FontWeight.Bold,
            )
            Text(
                "${region.wayCount} roads · ${region.placeCount} places · ${formatBytes(region.sizeBytes)}",
                color = QuailTextDim,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
