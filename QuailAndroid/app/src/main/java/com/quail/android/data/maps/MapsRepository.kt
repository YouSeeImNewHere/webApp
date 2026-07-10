package com.quail.android.data.maps

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.location.Location
import android.os.Looper
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.quail.android.data.model.MapsExtractResult
import com.quail.android.data.model.MapsPlaceResult
import com.quail.android.data.model.MapsRouteOption
import com.quail.android.data.model.MapsRoutePointRequest
import com.quail.android.data.model.MapsRouteRequest
import com.quail.android.data.model.MapsStatusResponse
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.FileOutputStream
import kotlin.coroutines.resume
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.tan

class LocationUnavailableException(message: String) : Exception(message)

data class TilePackProgress(val done: Int, val total: Int)

class MapsRepository(private val api: QuailApi, private val context: Context) {

    private val tileCache = TileCache()
    private val tileDiskStore = TileDiskStore(context)

    suspend fun getStatus(): MapsStatusResponse = api.getMapsStatus()

    suspend fun searchPlaces(
        lat: Double,
        lon: Double,
        radiusKm: Double = 5.0,
        category: String? = null,
        q: String? = null,
    ): List<MapsPlaceResult> =
        api.getMapsPlaces(lat, lon, radiusKm, category, q).places

    /** [points] is the ordered trip: current location, then any stops, then
     * the final destination (2+ entries) — returns up to 3 labeled route
     * alternatives (fastest/shortest/avoid-highways). */
    suspend fun getRoutes(points: List<Pair<Double, Double>>): List<MapsRouteOption> =
        api.getMapsRoute(MapsRouteRequest(points.map { (lat, lon) -> MapsRoutePointRequest(lat, lon) })).routes

    /** Fetches one slippy-map tile: memory cache, then disk cache (works
     * fully offline once a tile has been seen once — either from ordinary
     * browsing or a bulk downloadTilePack() call), then the network. */
    suspend fun fetchTile(z: Int, x: Int, y: Int): Bitmap? {
        tileCache[z, x, y]?.let { return it }
        return withContext(Dispatchers.IO) {
            tileDiskStore.readBitmap(z, x, y)?.let { bitmap ->
                tileCache.put(z, x, y, bitmap)
                return@withContext bitmap
            }
            try {
                val bytes = api.getMapTile(z, x, y).bytes()
                tileDiskStore.write(z, x, y, bytes)
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@withContext null
                tileCache.put(z, x, y, bitmap)
                bitmap
            } catch (e: Exception) {
                null
            }
        }
    }

    private fun lonLatToTile(lon: Double, lat: Double, zoom: Int): Pair<Double, Double> {
        val latRad = Math.toRadians(lat)
        val n = 2.0.pow(zoom)
        val x = (lon + 180.0) / 360.0 * n
        val y = (1.0 - ln(tan(latRad) + 1.0 / cos(latRad)) / PI) / 2.0 * n
        return x to y
    }

    /** Downloads every tile covering a radius around (lat, lon) across
     * [minZoom]..[maxZoom], writing straight to TileDiskStore — after this
     * completes, that area works with the network off. Runs with bounded
     * concurrency (8 in flight) since a several-km-radius pack at street
     * zoom can be thousands of individual tile requests; even on a fast
     * local network, doing them one at a time would be painfully slow. */
    suspend fun downloadTilePack(
        centerLat: Double,
        centerLon: Double,
        radiusKm: Double,
        minZoom: Int = 13,
        maxZoom: Int = 16,
        onProgress: (TilePackProgress) -> Unit,
    ) = withContext(Dispatchers.IO) {
        val metersPerDegLat = 110_540.0
        val metersPerDegLon = 111_320.0 * cos(Math.toRadians(centerLat))
        val dLat = (radiusKm * 1000.0) / metersPerDegLat
        val dLon = (radiusKm * 1000.0) / metersPerDegLon

        val needed = mutableListOf<Triple<Int, Int, Int>>()
        for (z in minZoom..maxZoom) {
            val (txWest, tyNorth) = lonLatToTile(centerLon - dLon, centerLat + dLat, z)
            val (txEast, tySouth) = lonLatToTile(centerLon + dLon, centerLat - dLat, z)
            val tileCount = 1 shl z
            val minTx = floor(txWest).toInt().coerceIn(0, tileCount - 1)
            val maxTx = floor(txEast).toInt().coerceIn(0, tileCount - 1)
            val minTy = floor(tyNorth).toInt().coerceIn(0, tileCount - 1)
            val maxTy = floor(tySouth).toInt().coerceIn(0, tileCount - 1)
            for (tx in minTx..maxTx) {
                for (ty in minTy..maxTy) {
                    if (!tileDiskStore.has(z, tx, ty)) needed.add(Triple(z, tx, ty))
                }
            }
        }

        val total = needed.size
        var done = 0
        val progressMutex = Mutex()
        val semaphore = Semaphore(8)
        coroutineScope {
            needed.map { (z, x, y) ->
                async {
                    semaphore.withPermit {
                        try {
                            val bytes = api.getMapTile(z, x, y).bytes()
                            tileDiskStore.write(z, x, y, bytes)
                        } catch (e: Exception) {
                            // Best-effort: one missing tile shouldn't abort
                            // the whole pack, it'll just fall back to a live
                            // fetch (or stay blank offline) for that tile.
                        }
                    }
                    progressMutex.withLock {
                        done++
                        onProgress(TilePackProgress(done, total))
                    }
                }
            }.forEach { it.await() }
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

    /** Live position stream for driving mode — one fix every [intervalMs],
     * used to follow the user and derive heading (Location.bearing, which
     * Fused Location populates from movement) so the map can rotate to keep
     * direction-of-travel "up" the way Apple/Google Maps do while
     * navigating. Distinct from getCurrentLocation()'s one-shot fix. */
    fun observeLocation(intervalMs: Long = 2000L): Flow<Location> = callbackFlow {
        if (!hasLocationPermission()) {
            close(LocationUnavailableException("Location permission not granted"))
            return@callbackFlow
        }
        val client = LocationServices.getFusedLocationProviderClient(context)
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, intervalMs).build()
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.lastLocation?.let { trySend(it) }
            }
        }
        try {
            client.requestLocationUpdates(request, callback, Looper.getMainLooper())
        } catch (e: SecurityException) {
            close(e)
        }
        awaitClose { client.removeLocationUpdates(callback) }
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
