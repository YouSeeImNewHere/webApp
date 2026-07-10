package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class MapsRegionState(
    val region: String,
    @SerialName("source_md5") val sourceMd5: String = "",
    @SerialName("node_count") val nodeCount: Long = 0,
    @SerialName("way_count") val wayCount: Long = 0,
    @SerialName("place_count") val placeCount: Long = 0,
    @SerialName("size_bytes") val sizeBytes: Long = 0,
    @SerialName("built_at") val builtAt: String? = null,
)

@Serializable
data class MapsCarDriveState(
    @SerialName("drive_label") val driveLabel: String = "",
    @SerialName("synced_at") val syncedAt: String? = null,
)

@Serializable
data class MapsCarDriveStaleness(
    val stale: Boolean = false,
    val reason: String = "",
    @SerialName("days_since_sync") val daysSinceSync: Int? = null,
    @SerialName("behind_regions") val behindRegions: List<String> = emptyList(),
)

@Serializable
data class MapsStatusResponse(
    val enabled: Boolean = false,
    val regions: List<MapsRegionState> = emptyList(),
    @SerialName("car_drive") val carDrive: MapsCarDriveState? = null,
    @SerialName("car_drive_staleness") val carDriveStaleness: MapsCarDriveStaleness? = null,
)

/** Result of downloading a city extract — a real local file the client can
 * point a future offline nav/search feature at (same schema
 * quail_maps_car/geo/{roadnet,search_db}.py already read). */
data class MapsExtractResult(
    val filePath: String,
    val sizeBytes: Long,
    val lat: Double,
    val lon: Double,
    val radiusKm: Double,
)

@Serializable
data class MapsPlaceResult(
    val id: String,
    val name: String,
    val address: String = "",
    val icon: String = "",
    val category: String = "",
    val lat: Double,
    val lon: Double,
    @SerialName("distance_km") val distanceKm: Double = 0.0,
)

@Serializable
data class MapsPlacesResponse(
    val places: List<MapsPlaceResult> = emptyList(),
)

@Serializable
data class MapsRouteStep(
    val instruction: String,
    @SerialName("street") val street: String = "",
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("point_index") val pointIndex: Int = 0,
)

@Serializable
data class MapsRoutePoint(val lat: Double, val lon: Double)

@Serializable
data class MapsRouteResponse(
    val points: List<MapsRoutePoint> = emptyList(),
    val steps: List<MapsRouteStep> = emptyList(),
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("duration_sec") val durationSec: Double = 0.0,
)
