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
