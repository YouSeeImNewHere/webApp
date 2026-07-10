package com.quail.android.data.maps

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.File

/** Persistent tile store on disk, separate from TileCache's in-memory LRU —
 * this is what actually makes the map usable with no network: once a tile
 * has been downloaded (individually while browsing, or in bulk via
 * MapsRepository.downloadTilePack), it's read straight from here forever
 * after, no server round-trip needed. */
class TileDiskStore(private val context: Context) {
    private fun file(z: Int, x: Int, y: Int): File = File(context.filesDir, "tiles/$z/$x/$y.png")

    fun has(z: Int, x: Int, y: Int): Boolean = file(z, x, y).exists()

    fun readBytes(z: Int, x: Int, y: Int): ByteArray? {
        val f = file(z, x, y)
        return if (f.exists()) f.readBytes() else null
    }

    fun readBitmap(z: Int, x: Int, y: Int): Bitmap? {
        val bytes = readBytes(z, x, y) ?: return null
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }

    fun write(z: Int, x: Int, y: Int, bytes: ByteArray) {
        val f = file(z, x, y)
        f.parentFile?.mkdirs()
        f.writeBytes(bytes)
    }
}
