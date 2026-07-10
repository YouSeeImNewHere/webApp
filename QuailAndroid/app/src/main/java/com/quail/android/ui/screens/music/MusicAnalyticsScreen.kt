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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.MusicAnalyticsResponse
import com.quail.android.data.model.MusicLbArtist
import com.quail.android.data.model.MusicLbRecording
import com.quail.android.data.model.MusicLbRelease
import com.quail.android.data.model.MusicLibraryArtist
import com.quail.android.data.model.MusicListeningActivityPoint
import com.quail.android.data.model.MusicSkippedArtist
import com.quail.android.data.model.MusicSkippedTrack
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
fun MusicAnalyticsScreen(viewModel: MusicAnalyticsViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Listening Analytics", fontWeight = FontWeight.ExtraBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        when (val s = state) {
            is MusicAnalyticsUiState.Loading -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }

            is MusicAnalyticsUiState.Error -> Box(Modifier.fillMaxSize().padding(padding)) {
                InfoCard("Couldn't reach the music server: ${s.message}", Modifier.padding(16.dp))
            }

            is MusicAnalyticsUiState.Success -> AnalyticsContent(s.data, Modifier.fillMaxSize().padding(padding))
        }
    }
}

@Composable
private fun AnalyticsContent(data: MusicAnalyticsResponse, modifier: Modifier = Modifier) {
    LazyColumn(
        modifier = modifier,
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { SectionTitle("ListenBrainz") }
        item {
            StatRow(
                "Total listens",
                data.listenbrainz.listenCount?.toString() ?: "Not available yet",
            )
        }

        val lb = data.listenbrainz
        if (lb.topArtists.isEmpty() && lb.topRecordings.isEmpty() && lb.topReleases.isEmpty() && lb.listeningActivity.isEmpty()) {
            item {
                InfoCard("ListenBrainz hasn't computed top artists/tracks/releases or listening activity for this account yet.")
            }
        } else {
            if (lb.topArtists.isNotEmpty()) {
                item { SubsectionTitle("Top artists (all time)") }
                items(lb.topArtists) { LbArtistRow(it) }
            }
            if (lb.topRecordings.isNotEmpty()) {
                item { SubsectionTitle("Top tracks (all time)") }
                items(lb.topRecordings) { LbRecordingRow(it) }
            }
            if (lb.topReleases.isNotEmpty()) {
                item { SubsectionTitle("Top albums (all time)") }
                items(lb.topReleases) { LbReleaseRow(it) }
            }
            if (lb.listeningActivity.isNotEmpty()) {
                item { SubsectionTitle("Listening activity (past year)") }
                items(lb.listeningActivity) { ListeningActivityRow(it) }
            }
        }

        item { SectionTitle("Skips") }
        item { StatRow("Total skips logged", data.skips.total.toString()) }
        if (data.skips.total == 0) {
            item { InfoCard("No skips logged yet.") }
        } else {
            if (data.skips.topSkippedArtists.isNotEmpty()) {
                item { SubsectionTitle("Most-skipped artists") }
                items(data.skips.topSkippedArtists) { SkippedArtistRow(it) }
            }
            if (data.skips.topSkippedTracks.isNotEmpty()) {
                item { SubsectionTitle("Most-skipped tracks") }
                items(data.skips.topSkippedTracks) { SkippedTrackRow(it) }
            }
        }

        item { SectionTitle("Library") }
        item { StatRow("Total tracks", data.library.totalTracks.toString()) }
        item { StatRow("Total artists", data.library.totalArtists.toString()) }
        item { StatRow("Total size", formatBytes(data.library.totalSizeBytes)) }
        if (data.library.topArtists.isNotEmpty()) {
            item { SubsectionTitle("Most-downloaded artists") }
            items(data.library.topArtists) { LibraryArtistRow(it) }
        }
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.ExtraBold)
}

@Composable
private fun SubsectionTitle(title: String) {
    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
}

@Composable
private fun InfoCard(message: String, modifier: Modifier = Modifier) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = modifier.fillMaxWidth()) {
        Text(message, color = QuailTextDim, modifier = Modifier.padding(16.dp))
    }
}

@Composable
private fun StatRow(label: String, value: String) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, color = QuailTextDim)
            Text(value, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun RankedRow(title: String, subtitle: String?, count: Int) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(title, fontWeight = FontWeight.Bold)
                if (subtitle != null) {
                    Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                }
            }
            Text(count.toString(), color = QuailTextDim)
        }
    }
}

@Composable
private fun LbArtistRow(artist: MusicLbArtist) = RankedRow(artist.name, null, artist.listenCount)

@Composable
private fun LbRecordingRow(recording: MusicLbRecording) =
    RankedRow(recording.name, recording.artist, recording.listenCount)

@Composable
private fun LbReleaseRow(release: MusicLbRelease) = RankedRow(release.name, release.artist, release.listenCount)

@Composable
private fun ListeningActivityRow(point: MusicListeningActivityPoint) = RankedRow(point.timeRange, null, point.listenCount)

@Composable
private fun SkippedArtistRow(artist: MusicSkippedArtist) = RankedRow(artist.artist, null, artist.count)

@Composable
private fun SkippedTrackRow(track: MusicSkippedTrack) = RankedRow(track.track, track.artist, track.count)

@Composable
private fun LibraryArtistRow(artist: MusicLibraryArtist) = RankedRow(artist.name, null, artist.count)
