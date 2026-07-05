package com.quail.android.bugreport

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import android.view.PixelCopy
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import com.quail.android.data.network.NetworkCallLog
import java.io.File
import java.io.FileOutputStream

/** Dropped into every screen's top bar `actions`. Screenshots the current
 * Activity's window via PixelCopy — now that popups render as in-window
 * overlays (see ui/overlay/AppOverlay.kt) instead of separate-window
 * ModalBottomSheet/AlertDialog, PixelCopy captures whatever popup is open
 * along with the rest of the screen. */
@Composable
fun BugReportTopBarAction() {
    IconButton(onClick = { triggerBugReport() }) {
        Icon(Icons.Filled.BugReport, contentDescription = "Report a bug")
    }
}

/** Same capture flow as [BugReportTopBarAction], exposed standalone for
 * screens with a custom top bar button style (e.g. HomeScreen's
 * TopBarCircleButton) instead of a plain IconButton. */
fun triggerBugReport() {
    val activity = CurrentActivityHolder.current?.get() ?: return
    captureAndOpenReport(activity)
}

private fun captureAndOpenReport(activity: Activity) {
    val decorView = activity.window.decorView
    val width = decorView.width
    val height = decorView.height
    if (width <= 0 || height <= 0) return

    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    val handler = Handler(Looper.getMainLooper())
    val listener = PixelCopy.OnPixelCopyFinishedListener { result ->
        if (result == PixelCopy.SUCCESS) {
            saveAndLaunch(activity, bitmap)
        }
    }
    PixelCopy.request(activity.window, bitmap, listener, handler)
}

private fun saveAndLaunch(activity: Activity, bitmap: Bitmap) {
    runCatching {
        val file = File(activity.cacheDir, "bug_screenshot_${System.currentTimeMillis()}.png")
        FileOutputStream(file).use { out -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, out) }

        val intent = Intent(activity, BugReportActivity::class.java).apply {
            putExtra(BugReportActivity.EXTRA_SCREENSHOT_PATH, file.absolutePath)
            putExtra(BugReportActivity.EXTRA_ROUTE, NavPathHolder.current)
            putExtra(BugReportActivity.EXTRA_NETWORK_LOG, NetworkCallLog.snapshotText())
        }
        activity.startActivity(intent)
    }
}
