package com.quail.android.data.maps

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import androidx.core.content.ContextCompat
import com.quail.android.data.model.MapsExtractResult
import com.quail.android.data.model.MapsStatusResponse
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.FileOutputStream
import kotlin.coroutines.resume

class LocationUnavailableException(message: String) : Exception(message)

class MapsRepository(private val api: QuailApi, private val context: Context) {

    suspend fun getStatus(): MapsStatusResponse = api.getMapsStatus()

    /** Prefers a fresh GPS fix; falls back to the last known fix (from GPS
     * or network) if a live fix doesn't land within [timeoutMs] — good
     * enough for "roughly what city am I in" without stalling the download
     * button indefinitely on a weak signal indoors. */
    suspend fun getCurrentLocation(timeoutMs: Long = 15_000): Location {
        if (!hasLocationPermission()) {
            throw LocationUnavailableException("Location permission not granted")
        }
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

        val fresh = withTimeoutOrNull(timeoutMs) { requestSingleLocationUpdate(manager) }
        if (fresh != null) return fresh

        return lastKnownLocation(manager)
            ?: throw LocationUnavailableException("No location fix available — try again outdoors or with wifi/GPS on")
    }

    private fun hasLocationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
    }

    private fun lastKnownLocation(manager: LocationManager): Location? {
        val providers = manager.getProviders(true)
        return providers.mapNotNull { runCatching { manager.getLastKnownLocation(it) }.getOrNull() }
            .maxByOrNull { it.time }
    }

    private suspend fun requestSingleLocationUpdate(manager: LocationManager): Location? =
        suspendCancellableCoroutine { cont ->
            val provider = when {
                manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
                manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
                else -> null
            }
            if (provider == null) {
                cont.resume(null)
                return@suspendCancellableCoroutine
            }
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    manager.removeUpdates(this)
                    if (cont.isActive) cont.resume(location)
                }
                @Deprecated("Deprecated in Java")
                override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
                override fun onProviderEnabled(provider: String) {}
                override fun onProviderDisabled(provider: String) {}
            }
            try {
                manager.requestLocationUpdates(provider, 0L, 0f, listener, context.mainLooper)
            } catch (e: SecurityException) {
                cont.resume(null)
                return@suspendCancellableCoroutine
            }
            cont.invokeOnCancellation { manager.removeUpdates(listener) }
        }

    /** Streams the extract straight to disk rather than buffering it in
     * memory — a 40km-radius extract can run into the tens of MB. */
    suspend fun downloadExtract(lat: Double, lon: Double, radiusKm: Double): MapsExtractResult {
        val body = api.getMapsExtract(lat, lon, radiusKm)
        val dir = File(context.filesDir, "maps").apply { mkdirs() }
        val file = File(dir, "extract_${"%.3f".format(lat)}_${"%.3f".format(lon)}_${"%.0f".format(radiusKm)}km.sqlite3")

        body.byteStream().use { input ->
            FileOutputStream(file).use { output ->
                input.copyTo(output)
            }
        }

        return MapsExtractResult(
            filePath = file.absolutePath,
            sizeBytes = file.length(),
            lat = lat,
            lon = lon,
            radiusKm = radiusKm,
        )
    }
}
