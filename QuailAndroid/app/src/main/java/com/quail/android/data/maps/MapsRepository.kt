package com.quail.android.data.maps

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.location.Location
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.quail.android.data.model.MapsExtractResult
import com.quail.android.data.model.MapsStatusResponse
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.FileOutputStream
import kotlin.coroutines.resume

class LocationUnavailableException(message: String) : Exception(message)

class MapsRepository(private val api: QuailApi, private val context: Context) {

    private val tileCache = TileCache()

    suspend fun getStatus(): MapsStatusResponse = api.getMapsStatus()

    /** Fetches one slippy-map tile (or returns it from the in-memory
     * cache). Deliberately small and self-contained: unlike the old
     * whole-extract approach, a single tile miss is cheap to retry and
     * never risks blocking the UI for more than one small image fetch. */
    suspend fun fetchTile(z: Int, x: Int, y: Int): Bitmap? {
        tileCache[z, x, y]?.let { return it }
        return withContext(Dispatchers.IO) {
            try {
                val bytes = api.getMapTile(z, x, y).bytes()
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@withContext null
                tileCache.put(z, x, y, bitmap)
                bitmap
            } catch (e: Exception) {
                null
            }
        }
    }

    /** Uses Google's Fused Location Provider (fuses GPS + wifi + cell —
     * already available since Play Services is a dependency via Firebase)
     * rather than a single raw LocationManager provider, which struggled to
     * produce a fix at all when tested indoors. Falls back to the provider's
     * cached last-known fix if a live one doesn't land within [timeoutMs]. */
    suspend fun getCurrentLocation(timeoutMs: Long = 20_000): Location {
        if (!hasLocationPermission()) {
            throw LocationUnavailableException("Location permission not granted")
        }
        val client = LocationServices.getFusedLocationProviderClient(context)

        val fresh = withTimeoutOrNull(timeoutMs) { requestFreshLocation(client) }
        if (fresh != null) return fresh

        return lastKnownLocation(client)
            ?: throw LocationUnavailableException(
                "No location fix available — check Location is on (High accuracy mode) and try again",
            )
    }

    private fun hasLocationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
    }

    private suspend fun requestFreshLocation(client: FusedLocationProviderClient): Location? =
        suspendCancellableCoroutine { cont ->
            val cancellationSource = CancellationTokenSource()
            try {
                client.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, cancellationSource.token)
                    .addOnSuccessListener { location -> if (cont.isActive) cont.resume(location) }
                    .addOnFailureListener { if (cont.isActive) cont.resume(null) }
            } catch (e: SecurityException) {
                cont.resume(null)
                return@suspendCancellableCoroutine
            }
            cont.invokeOnCancellation { cancellationSource.cancel() }
        }

    private suspend fun lastKnownLocation(client: FusedLocationProviderClient): Location? =
        suspendCancellableCoroutine { cont ->
        try {
            client.lastLocation
                .addOnSuccessListener { location -> if (cont.isActive) cont.resume(location) }
                .addOnFailureListener { if (cont.isActive) cont.resume(null) }
        } catch (e: SecurityException) {
            cont.resume(null)
        }
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

    /** Parses a downloaded extract's nodes/edges/places off the main thread
     * — a 40km-radius extract can be tens of thousands of rows. */
    suspend fun readExtract(filePath: String, onProgress: ((Float) -> Unit)? = null): MapExtractData =
        withContext(Dispatchers.IO) {
            MapsExtractReader.read(filePath, onProgress)
        }

    private val filenamePattern = Regex("""extract_(-?[\d.]+)_(-?[\d.]+)_(\d+)km\.sqlite3""")

    /** Whatever's already on disk from a previous session — the ViewModel
     * was otherwise always starting from "nothing downloaded" on every
     * fresh process (app relaunch, not just a real reinstall), even though
     * the file was still sitting in storage the whole time. */
    fun mostRecentExtract(): MapsExtractResult? {
        val dir = File(context.filesDir, "maps")
        val file = dir.listFiles { f -> f.name.endsWith(".sqlite3") }
            ?.maxByOrNull { it.lastModified() }
            ?: return null

        val match = filenamePattern.matchEntire(file.name)
        val lat = match?.groupValues?.get(1)?.toDoubleOrNull() ?: 0.0
        val lon = match?.groupValues?.get(2)?.toDoubleOrNull() ?: 0.0
        val radiusKm = match?.groupValues?.get(3)?.toDoubleOrNull() ?: 0.0

        return MapsExtractResult(
            filePath = file.absolutePath,
            sizeBytes = file.length(),
            lat = lat,
            lon = lon,
            radiusKm = radiusKm,
        )
    }
}
