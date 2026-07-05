package com.quail.android.bugreport

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.lifecycleScope
import com.quail.android.data.bugs.BugsDatabase
import com.quail.android.data.bugs.BugsRepository
import com.quail.android.data.model.BugReportRecord
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.repository.AuthStore
import com.quail.android.ui.theme.QuailAndroidTheme
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream

/** Standalone Activity (not part of the main NavHost) launched directly from
 * the floating overlay button, so it can open on top of whatever screen
 * (including one of this app's own popups) the user tapped the button from. */
class BugReportActivity : ComponentActivity() {
    companion object {
        const val EXTRA_SCREENSHOT_PATH = "screenshot_path"
        const val EXTRA_ROUTE = "route"
        const val EXTRA_NETWORK_LOG = "network_log"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val screenshotPath = intent.getStringExtra(EXTRA_SCREENSHOT_PATH).orEmpty()
        val route = intent.getStringExtra(EXTRA_ROUTE).orEmpty()
        val networkLog = intent.getStringExtra(EXTRA_NETWORK_LOG).orEmpty()
        val screenshot = runCatching { BitmapFactory.decodeFile(screenshotPath) }.getOrNull()

        val authStore = AuthStore.getInstance(applicationContext)
        val api = NetworkModule.create(authStore)
        val repository = BugsRepository(api, BugsDatabase.getInstance(applicationContext), applicationContext)

        setContent {
            QuailAndroidTheme {
                BugReportScreen(
                    screenshot = screenshot,
                    route = route,
                    networkLog = networkLog,
                    onSubmit = { description, annotatedBitmap ->
                        lifecycleScope.launch {
                            submitReport(repository, description, route, networkLog, annotatedBitmap)
                            runCatching { File(screenshotPath).delete() }
                            finish()
                        }
                    },
                    onCancel = {
                        runCatching { File(screenshotPath).delete() }
                        finish()
                    },
                )
            }
        }
    }

    private suspend fun submitReport(
        repository: BugsRepository,
        description: String,
        route: String,
        networkLog: String,
        annotatedBitmap: Bitmap?,
    ) {
        val clientId = BugsRepository.newClientId()
        var localScreenshotPath: String? = null
        if (annotatedBitmap != null) {
            runCatching {
                val outFile = File(cacheDir, "bug_report_$clientId.png")
                FileOutputStream(outFile).use { out -> annotatedBitmap.compress(Bitmap.CompressFormat.PNG, 100, out) }
                localScreenshotPath = outFile.absolutePath
            }
        }

        val title = description.trim().ifBlank { "Bug report" }.take(80)
        repository.saveReport(
            BugReportRecord(
                clientId = clientId,
                title = title,
                description = description.trim(),
                status = "open",
                route = route,
                networkLog = networkLog,
            ),
            localScreenshotPath = localScreenshotPath,
        )
    }
}
