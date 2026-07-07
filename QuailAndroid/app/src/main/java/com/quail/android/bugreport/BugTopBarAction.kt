package com.quail.android.bugreport

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import android.view.PixelCopy
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.quail.android.data.network.NetworkCallLog
import com.quail.android.ui.theme.QuailBadRed
import java.io.File
import java.io.FileOutputStream

/** Dropped into every screen's top bar `actions`. Screenshots the current
 * Activity's window via PixelCopy — now that popups render as in-window
 * overlays (see ui/overlay/AppOverlay.kt) instead of separate-window
 * ModalBottomSheet/AlertDialog, PixelCopy captures whatever popup is open
 * along with the rest of the screen.
 *
 * Styled as a red circle (matching the original HomeScreen bug button) so
 * it looks the same everywhere instead of blending in as a plain icon on
 * some screens and standing out on others. */
@Composable
fun BugReportTopBarAction(modifier: Modifier = Modifier) {
    Surface(
        onClick = { triggerBugReport() },
        color = QuailBadRed,
        shape = CircleShape,
        modifier = modifier.size(40.dp),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.BugReport, contentDescription = "Report a bug", tint = Color.White)
        }
    }
}

/** Same capture flow as [BugReportTopBarAction], exposed standalone for
 * screens with a custom top bar button style (e.g. HomeScreen's
 * TopBarCircleButton) instead of the shared Surface above. */
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
