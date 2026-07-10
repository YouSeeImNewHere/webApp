package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class MusicSearchResult(
    val id: String,
    val name: String = "",
    val artist: String = "",
    val album: String = "",
    @SerialName("size_bytes") val sizeBytes: Long = 0,
)

@Serializable
data class MusicRecommendedTrack(
    val title: String = "",
    val artist: String = "",
    val album: String? = null,
    @SerialName("in_library") val inLibrary: Boolean = false,
)

@Serializable
data class MusicRecommendedPlaylist(
    val name: String = "",
    val tracks: List<MusicRecommendedTrack> = emptyList(),
)

@Serializable
data class MusicRecommendedResponse(
    val playlists: List<MusicRecommendedPlaylist> = emptyList(),
)

@Serializable
data class MusicDeleteResponse(
    val status: String = "",
    val path: String? = null,
)

@Serializable
data class MusicLbArtist(
    val name: String = "",
    @SerialName("listen_count") val listenCount: Int = 0,
)

@Serializable
data class MusicLbRecording(
    val name: String = "",
    val artist: String = "",
    @SerialName("listen_count") val listenCount: Int = 0,
)

@Serializable
data class MusicLbRelease(
    val name: String = "",
    val artist: String = "",
    @SerialName("listen_count") val listenCount: Int = 0,
)

@Serializable
data class MusicListeningActivityPoint(
    @SerialName("time_range") val timeRange: String = "",
    @SerialName("listen_count") val listenCount: Int = 0,
)

@Serializable
data class MusicListenBrainzStats(
    @SerialName("listen_count") val listenCount: Int? = null,
    @SerialName("top_artists") val topArtists: List<MusicLbArtist> = emptyList(),
    @SerialName("top_recordings") val topRecordings: List<MusicLbRecording> = emptyList(),
    @SerialName("top_releases") val topReleases: List<MusicLbRelease> = emptyList(),
    @SerialName("listening_activity") val listeningActivity: List<MusicListeningActivityPoint> = emptyList(),
)

@Serializable
data class MusicSkippedTrack(
    val artist: String = "",
    val track: String = "",
    val count: Int = 0,
)

@Serializable
data class MusicSkippedArtist(
    val artist: String = "",
    val count: Int = 0,
)

@Serializable
data class MusicSkipStats(
    val total: Int = 0,
    @SerialName("top_skipped_tracks") val topSkippedTracks: List<MusicSkippedTrack> = emptyList(),
    @SerialName("top_skipped_artists") val topSkippedArtists: List<MusicSkippedArtist> = emptyList(),
)

@Serializable
data class MusicLibraryArtist(
    val name: String = "",
    val count: Int = 0,
)

@Serializable
data class MusicLibraryStats(
    @SerialName("total_tracks") val totalTracks: Int = 0,
    @SerialName("total_artists") val totalArtists: Int = 0,
    @SerialName("total_size_bytes") val totalSizeBytes: Long = 0,
    @SerialName("top_artists") val topArtists: List<MusicLibraryArtist> = emptyList(),
)

@Serializable
data class MusicAnalyticsResponse(
    val listenbrainz: MusicListenBrainzStats = MusicListenBrainzStats(),
    val skips: MusicSkipStats = MusicSkipStats(),
    val library: MusicLibraryStats = MusicLibraryStats(),
)
