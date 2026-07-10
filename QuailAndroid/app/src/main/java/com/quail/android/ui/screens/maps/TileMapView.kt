package com.quail.android.ui.screens.maps

import android.graphics.Bitmap
import android.location.Location
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.quail.android.data.maps.MapsRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.log2
import kotlin.math.pow

private const val TILE_SIZE_PX = 256f
private const val MIN_ZOOM = 11
private const val MAX_ZOOM = 18
private const val DEFAULT_ZOOM = 15
private const val DRIVING_ZOOM = 17

// Waits for pan/zoom gestures to settle before firing a batch of tile
// fetches — without this, every intermediate frame of a drag cancelled the
// previous batch and started a new one, so nothing ever finished loading
// during continuous motion (visible in logcat as a wall of "HTTP FAILED:
// Canceled" and the screen going blank mid-pan).
private const val FETCH_DEBOUNCE_MS = 150L

// A manual pan of at least this many screen px while navigating counts as
// "the user wants to look somewhere else" and drops camera-follow, same as
// Apple/Google Maps — small jitter from a shaky hand shouldn't disengage it.
private const val MANUAL_PAN_BREAK_FOLLOW_PX = 8f

private val BgColor = Color(0xFF0A0D13)
private val AccentColor = Color(0xFF2B6CFF)
private val DestinationColor = Color(0xFFFF7A6E)
private val RouteColor = Color(0xFF2B6CFF)

private fun lonLatToTileF(lon: Double, lat: Double, zoom: Int): Pair<Float, Float> {
    val latRad = Math.toRadians(lat)
    val n = 2.0.pow(zoom)
    val x = (lon + 180.0) / 360.0 * n
    val y = (1.0 - Math.log(Math.tan(latRad) + 1.0 / Math.cos(latRad)) / Math.PI) / 2.0 * n
    return x.toFloat() to y.toFloat()
}

private fun tileToLonLat(x: Float, y: Float, zoom: Int): Pair<Double, Double> {
    val n = 2.0.pow(zoom)
    val lon = x / n * 360.0 - 180.0
    val latRad = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n)))
    return lon to Math.toDegrees(latRad)
}

/** A standard slippy map: the client only ever fetches/draws the handful of
 * 256x256 tiles actually visible, at the current integer zoom level.
 *
 * [navigating] + [liveLocation] together drive Apple/Google-Maps-style
 * turn-by-turn mode: the camera follows the live fix, zooms in to a driving
 * level, and the whole map rotates so direction-of-travel stays "up"
 * (derived from Location.bearing, which Fused Location populates from
 * movement). Manually panning away drops follow mode (shown via the
 * recenter button) without stopping navigation — matching how real nav
 * apps let you glance elsewhere on the map and snap back. */
@Composable
fun TileMapView(
    repository: MapsRepository,
    initialLat: Double,
    initialLon: Double,
    modifier: Modifier = Modifier,
    destination: Pair<Double, Double>? = null,
    routePoints: List<Pair<Double, Double>>? = null,
    navigating: Boolean = false,
    liveLocation: Location? = null,
    onCenterChanged: (Double, Double) -> Unit = { _, _ -> },
) {
    var canvasSize by remember { mutableStateOf(IntSize.Zero) }
    var zoom by remember { mutableIntStateOf(DEFAULT_ZOOM) }
    var centerTileX by remember { mutableFloatStateOf(0f) }
    var centerTileY by remember { mutableFloatStateOf(0f) }
    var zoomAccumulator by remember { mutableFloatStateOf(0f) }
    var initialized by remember { mutableStateOf(false) }
    var following by remember { mutableStateOf(true) }
    var heading by remember { mutableFloatStateOf(0f) }

    val markerTileX = remember { mutableFloatStateOf(0f) }
    val markerTileY = remember { mutableFloatStateOf(0f) }

    fun recenter() {
        following = true
        val target = if (navigating && liveLocation != null) {
            lonLatToTileF(liveLocation.longitude, liveLocation.latitude, zoom)
        } else {
            lonLatToTileF(initialLon, initialLat, zoom)
        }
        centerTileX = target.first
        centerTileY = target.second
    }

    fun stepZoom(delta: Int) {
        val newZoom = (zoom + delta).coerceIn(MIN_ZOOM, MAX_ZOOM)
        if (newZoom == zoom) return
        val factor = 2.0.pow(newZoom - zoom).toFloat()
        centerTileX *= factor
        centerTileY *= factor
        zoom = newZoom
        zoomAccumulator = 0f
    }

    LaunchedEffect(initialLat, initialLon) {
        val (tx, ty) = lonLatToTileF(initialLon, initialLat, DEFAULT_ZOOM)
        centerTileX = tx
        centerTileY = ty
        markerTileX.floatValue = tx
        markerTileY.floatValue = ty
        initialized = true
    }

    // Entering navigation: re-engage follow and jump to driving zoom.
    LaunchedEffect(navigating) {
        if (navigating) {
            following = true
            if (zoom < DRIVING_ZOOM) {
                val factor = 2.0.pow(DRIVING_ZOOM - zoom).toFloat()
                centerTileX *= factor
                centerTileY *= factor
                zoom = DRIVING_ZOOM
            }
        } else {
            heading = 0f
        }
    }

    // Camera-follow + heading: only while navigating and not manually panned away.
    LaunchedEffect(liveLocation, following, navigating) {
        if (!navigating || !following || liveLocation == null) return@LaunchedEffect
        val (tx, ty) = lonLatToTileF(liveLocation.longitude, liveLocation.latitude, zoom)
        centerTileX = tx
        centerTileY = ty
        markerTileX.floatValue = tx
        markerTileY.floatValue = ty
        if (liveLocation.hasBearing()) heading = liveLocation.bearing
    }

    val tileBitmaps = remember { mutableStateMapOf<String, Bitmap>() }
    val loadingTiles = remember { mutableSetOf<String>() }

    val centerTileXFloor = floor(centerTileX).toInt()
    val centerTileYFloor = floor(centerTileY).toInt()

    LaunchedEffect(zoom, centerTileXFloor, centerTileYFloor, canvasSize) {
        if (!initialized || canvasSize.width == 0 || canvasSize.height == 0) return@LaunchedEffect

        if (!navigating) {
            // Fixed "you were here when you opened the map" marker — while
            // navigating, the marker instead tracks liveLocation (above).
            val (mx, my) = lonLatToTileF(initialLon, initialLat, zoom)
            markerTileX.floatValue = mx
            markerTileY.floatValue = my
        }

        // Debounce: if the view moves again before this fires, this whole
        // effect (and the delay below) gets cancelled and restarted — only
        // the position where the gesture actually settled ever issues fetches.
        delay(FETCH_DEBOUNCE_MS)

        val (centerLon, centerLat) = tileToLonLat(centerTileX, centerTileY, zoom)
        onCenterChanged(centerLat, centerLon)

        val tilesAcrossX = (canvasSize.width / TILE_SIZE_PX).toInt() + 3
        val tilesAcrossY = (canvasSize.height / TILE_SIZE_PX).toInt() + 3
        val startTx = centerTileXFloor - tilesAcrossX / 2
        val startTy = centerTileYFloor - tilesAcrossY / 2
        val tileCountAtZoom = 1 shl zoom

        for (dx in 0..tilesAcrossX) {
            for (dy in 0..tilesAcrossY) {
                val tx = startTx + dx
                val ty = startTy + dy
                if (tx < 0 || ty < 0 || tx >= tileCountAtZoom || ty >= tileCountAtZoom) continue
                val key = "$zoom/$tx/$ty"
                if (tileBitmaps.containsKey(key) || key in loadingTiles) continue
                loadingTiles.add(key)
                launch {
                    val bmp = repository.fetchTile(zoom, tx, ty)
                    loadingTiles.remove(key)
                    if (bmp != null) tileBitmaps[key] = bmp
                }
            }
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .onSizeChanged { canvasSize = it }
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, gestureZoom, _ ->
                        centerTileX -= pan.x / TILE_SIZE_PX
                        centerTileY -= pan.y / TILE_SIZE_PX

                        if (navigating && following &&
                            (abs(pan.x) > MANUAL_PAN_BREAK_FOLLOW_PX || abs(pan.y) > MANUAL_PAN_BREAK_FOLLOW_PX)
                        ) {
                            following = false
                        }

                        if (gestureZoom != 1f) {
                            zoomAccumulator += log2(gestureZoom)
                            while (zoomAccumulator >= 1f && zoom < MAX_ZOOM) {
                                zoom++
                                centerTileX *= 2f
                                centerTileY *= 2f
                                zoomAccumulator -= 1f
                            }
                            while (zoomAccumulator <= -1f && zoom > MIN_ZOOM) {
                                zoom--
                                centerTileX /= 2f
                                centerTileY /= 2f
                                zoomAccumulator += 1f
                            }
                            // Clamp (not reset-to-zero) so a zoom-out gesture
                            // held at MAX_ZOOM can still accumulate — the old
                            // "reset whenever at a boundary" version zeroed
                            // this every frame regardless of gesture
                            // direction, so it could never reach -1 to
                            // actually step back down.
                            zoomAccumulator = zoomAccumulator.coerceIn(-1f, 1f)
                        }
                    }
                },
        ) {
            drawRect(color = BgColor, size = size)
            if (!initialized) return@Canvas

            val halfW = size.width / 2f
            val halfH = size.height / 2f
            val rotationDegrees = if (navigating) -heading else 0f

            rotate(degrees = rotationDegrees, pivot = Offset(halfW, halfH)) {
                for ((key, bitmap) in tileBitmaps) {
                    val parts = key.split("/")
                    val tz = parts[0].toInt()
                    if (tz != zoom) continue
                    val tx = parts[1].toInt()
                    val ty = parts[2].toInt()
                    val screenX = halfW + (tx - centerTileX) * TILE_SIZE_PX
                    val screenY = halfH + (ty - centerTileY) * TILE_SIZE_PX
                    drawImage(bitmap.asImageBitmap(), topLeft = Offset(screenX, screenY))
                }

                if (!routePoints.isNullOrEmpty()) {
                    val path = Path()
                    routePoints.forEachIndexed { i, (rLat, rLon) ->
                        val (rtx, rty) = lonLatToTileF(rLon, rLat, zoom)
                        val sx = halfW + (rtx - centerTileX) * TILE_SIZE_PX
                        val sy = halfH + (rty - centerTileY) * TILE_SIZE_PX
                        if (i == 0) path.moveTo(sx, sy) else path.lineTo(sx, sy)
                    }
                    drawPath(path, color = RouteColor, style = Stroke(width = 9f, cap = StrokeCap.Round))
                }

                if (destination != null) {
                    val (dtx, dty) = lonLatToTileF(destination.second, destination.first, zoom)
                    val destPoint = Offset(halfW + (dtx - centerTileX) * TILE_SIZE_PX, halfH + (dty - centerTileY) * TILE_SIZE_PX)
                    drawCircle(color = DestinationColor, radius = 10f, center = destPoint)
                    drawCircle(color = Color.White, radius = 10f, center = destPoint, style = Stroke(width = 3f))
                }

                val markerX = halfW + (markerTileX.floatValue - centerTileX) * TILE_SIZE_PX
                val markerY = halfH + (markerTileY.floatValue - centerTileY) * TILE_SIZE_PX
                val markerPoint = Offset(markerX, markerY)
                drawCircle(color = AccentColor.copy(alpha = 0.25f), radius = 22f, center = markerPoint)
                drawCircle(color = AccentColor, radius = 9f, center = markerPoint)
                drawCircle(color = Color.White, radius = 9f, center = markerPoint, style = Stroke(width = 3f))
            }
        }

        Column(
            // While navigating, the bottom stat bar (TileMapScreen's
            // NavigationBottomBar) occupies this same corner — lift the
            // recenter button clear of it instead of overlapping, and drop
            // the zoom buttons entirely (Apple/Google Maps don't show them
            // in turn-by-turn mode either; the driving zoom is automatic).
            modifier = Modifier.align(Alignment.BottomEnd).padding(bottom = if (navigating) 110.dp else 16.dp, end = 16.dp, top = 16.dp),
        ) {
            if (!navigating) {
                MapControlButton(icon = Icons.Filled.Add, contentDescription = "Zoom in", onClick = { stepZoom(1) })
                MapControlButton(icon = Icons.Filled.Remove, contentDescription = "Zoom out", onClick = { stepZoom(-1) })
            }
            MapControlButton(
                icon = if (navigating && !following) Icons.Filled.Navigation else Icons.Filled.MyLocation,
                contentDescription = "Recenter",
                tint = if (navigating && !following) AccentColor else Color.White,
                onClick = { recenter() },
            )
        }
    }
}

@Composable
private fun MapControlButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    tint: Color = Color.White,
) {
    IconButton(
        onClick = onClick,
        modifier = Modifier
            .padding(4.dp)
            .size(44.dp)
            .background(Color(0xFF171C26), CircleShape),
    ) {
        Icon(icon, contentDescription = contentDescription, tint = tint)
    }
}
