package com.quail.android.ui.screens.maps

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize
import com.quail.android.data.maps.MapsRepository
import kotlinx.coroutines.launch
import kotlin.math.floor
import kotlin.math.log2
import kotlin.math.pow

private const val TILE_SIZE_PX = 256f
private const val MIN_ZOOM = 11
private const val MAX_ZOOM = 18
private const val DEFAULT_ZOOM = 15

private val BgColor = Color(0xFF0A0D13)
private val AccentColor = Color(0xFF2B6CFF)

private fun lonLatToTileF(lon: Double, lat: Double, zoom: Int): Pair<Float, Float> {
    val latRad = Math.toRadians(lat)
    val n = 2.0.pow(zoom)
    val x = (lon + 180.0) / 360.0 * n
    val y = (1.0 - Math.log(Math.tan(latRad) + 1.0 / Math.cos(latRad)) / Math.PI) / 2.0 * n
    return x.toFloat() to y.toFloat()
}

/** A standard slippy map: the client only ever fetches/draws the handful of
 * 256x256 tiles actually visible, at the current integer zoom level —
 * replaces the earlier whole-extract vector renderer, which drew every road
 * in the downloaded area on every frame and reliably ANR'd against a real
 * metro-area's edge count regardless of how much that renderer's per-frame
 * cost was optimized. [initialLat]/[initialLon] both center the view and
 * mark the "you are here" pin (a fixed point — this doesn't track a live
 * position as you pan, same as the pin only reflecting where you were when
 * the map was opened). */
@Composable
fun TileMapView(
    repository: MapsRepository,
    initialLat: Double,
    initialLon: Double,
    modifier: Modifier = Modifier,
) {
    var canvasSize by remember { mutableStateOf(IntSize.Zero) }
    var zoom by remember { mutableIntStateOf(DEFAULT_ZOOM) }
    var centerTileX by remember { mutableFloatStateOf(0f) }
    var centerTileY by remember { mutableFloatStateOf(0f) }
    var zoomAccumulator by remember { mutableFloatStateOf(0f) }
    var initialized by remember { mutableStateOf(false) }

    val markerTileX = remember { mutableFloatStateOf(0f) }
    val markerTileY = remember { mutableFloatStateOf(0f) }

    LaunchedEffect(initialLat, initialLon) {
        val (tx, ty) = lonLatToTileF(initialLon, initialLat, DEFAULT_ZOOM)
        centerTileX = tx
        centerTileY = ty
        initialized = true
    }

    val tileBitmaps = remember { mutableStateMapOf<String, Bitmap>() }
    val loadingTiles = remember { mutableSetOf<String>() }

    val centerTileXFloor = floor(centerTileX).toInt()
    val centerTileYFloor = floor(centerTileY).toInt()

    LaunchedEffect(zoom, centerTileXFloor, centerTileYFloor, canvasSize) {
        if (!initialized || canvasSize.width == 0 || canvasSize.height == 0) return@LaunchedEffect

        // Marker position at this zoom, recomputed whenever zoom changes.
        val (mx, my) = lonLatToTileF(initialLon, initialLat, zoom)
        markerTileX.floatValue = mx
        markerTileY.floatValue = my

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

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .onSizeChanged { canvasSize = it }
            .pointerInput(Unit) {
                detectTransformGestures { _, pan, gestureZoom, _ ->
                    centerTileX -= pan.x / TILE_SIZE_PX
                    centerTileY -= pan.y / TILE_SIZE_PX

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
                        if (zoom == MIN_ZOOM || zoom == MAX_ZOOM) zoomAccumulator = 0f
                    }
                }
            },
    ) {
        drawRect(color = BgColor, size = size)
        if (!initialized) return@Canvas

        val halfW = size.width / 2f
        val halfH = size.height / 2f

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

        val markerX = halfW + (markerTileX.floatValue - centerTileX) * TILE_SIZE_PX
        val markerY = halfH + (markerTileY.floatValue - centerTileY) * TILE_SIZE_PX
        val markerPoint = Offset(markerX, markerY)
        drawCircle(color = AccentColor.copy(alpha = 0.25f), radius = 22f, center = markerPoint)
        drawCircle(color = AccentColor, radius = 9f, center = markerPoint)
        drawCircle(color = Color.White, radius = 9f, center = markerPoint, style = Stroke(width = 3f))
    }
}
