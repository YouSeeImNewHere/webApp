package com.quail.android.ui.screens.music

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
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.MusicRecommendedPlaylist
import com.quail.android.data.model.MusicRecommendedTrack
import com.quail.android.data.model.MusicSearchResult
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

private fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "-"
    val mb = bytes / 1_048_576.0
    return if (mb >= 1024) "%.1f GB".format(mb / 1024.0) else "%.1f MB".format(mb)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MusicScreen(viewModel: MusicViewModel, onBack: () -> Unit) {
    val recommendedState by viewModel.recommendedState.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()
    val searchState by viewModel.searchState.collectAsState()
    val deleteError by viewModel.deleteError.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Music", fontWeight = FontWeight.ExtraBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = viewModel::onSearchQueryChange,
                label = { Text("Search by title, artist, or album") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            )

            if (deleteError != null) {
                Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                    Text(deleteError ?: "", color = QuailBadRed, modifier = Modifier.padding(12.dp))
                }
            }

            when (val s = searchState) {
                is MusicSearchUiState.Idle -> RecommendedList(recommendedState)
                is MusicSearchUiState.Loading -> LoadingBox()
                is MusicSearchUiState.Error -> ErrorCard(s.message)
                is MusicSearchUiState.Success -> SearchResultsList(s.results, onDelete = viewModel::deleteTrack)
            }
        }
    }
}

@Composable
private fun LoadingBox() {
    Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun ErrorCard(message: String) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().padding(16.dp)) {
        Text(message, color = QuailTextDim, modifier = Modifier.padding(16.dp))
    }
}

@Composable
private fun RecommendedList(state: MusicRecommendedUiState) {
    when (state) {
        is MusicRecommendedUiState.Loading -> LoadingBox()
        is MusicRecommendedUiState.Error -> ErrorCard("Couldn't reach the music server: ${state.message}")
        is MusicRecommendedUiState.Success -> {
            if (state.playlists.all { it.tracks.isEmpty() }) {
                ErrorCard("No recommendations yet — ListenBrainz hasn't generated any for your account.")
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    state.playlists.forEach { playlist ->
                        if (playlist.tracks.isNotEmpty()) {
                            item { PlaylistHeader(playlist) }
                            items(playlist.tracks) { track -> RecommendedTrackRow(track) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PlaylistHeader(playlist: MusicRecommendedPlaylist) {
    Text(playlist.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
}

@Composable
private fun RecommendedTrackRow(track: MusicRecommendedTrack) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(track.title, fontWeight = FontWeight.Bold)
                Text(
                    if (track.album != null) "${track.artist} · ${track.album}" else track.artist,
                    color = QuailTextDim,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (track.inLibrary) {
                Icon(Icons.Filled.CheckCircle, contentDescription = "Already in library", tint = QuailGoodGreen)
            }
        }
    }
}

@Composable
private fun SearchResultsList(results: List<MusicSearchResult>, onDelete: (String) -> Unit) {
    if (results.isEmpty()) {
        ErrorCard("No matches.")
        return
    }
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(results, key = { it.id }) { track -> SearchResultRow(track, onDelete) }
    }
}

@Composable
private fun SearchResultRow(track: MusicSearchResult, onDelete: (String) -> Unit) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(track.name, fontWeight = FontWeight.Bold)
                Text(
                    "${track.artist} · ${track.album} · ${formatBytes(track.sizeBytes)}",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            IconButton(onClick = { onDelete(track.id) }) {
                Icon(Icons.Filled.Delete, contentDescription = "Delete", tint = QuailBadRed)
            }
        }
    }
}
