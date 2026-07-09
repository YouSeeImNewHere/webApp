package com.quail.android.data.maps

import android.graphics.Bitmap
import android.util.LruCache

/** In-memory only — tiles are already cached server-side and the server is
 * on the local network (homelab/Tailscale), so a disk cache isn't worth the
 * complexity for v1. Sized in KB (matching LruCache's `sizeOf` convention),
 * budgeted to roughly a quarter of the app's typical heap allowance. */
class TileCache {
    private val cache = object : LruCache<String, Bitmap>(48 * 1024) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.byteCount / 1024
    }

    fun key(z: Int, x: Int, y: Int) = "$z/$x/$y"

    operator fun get(z: Int, x: Int, y: Int): Bitmap? = cache.get(key(z, x, y))

    fun put(z: Int, x: Int, y: Int, bitmap: Bitmap) {
        cache.put(key(z, x, y), bitmap)
    }
}
