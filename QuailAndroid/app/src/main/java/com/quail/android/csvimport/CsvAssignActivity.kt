package com.quail.android.csvimport

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.repository.AuthStore
import com.quail.android.ui.theme.QuailAndroidTheme

class CsvAssignActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val uri = extractSharedUri()
        if (uri == null) {
            finish()
            return
        }
        val fileName = resolveDisplayName(uri) ?: "import.csv"

        val authStore = AuthStore.getInstance(applicationContext)
        val api = NetworkModule.create(authStore)
        val repository = CsvImportRepository(api, CsvImportDatabase.getInstance(applicationContext), applicationContext)

        setContent {
            QuailAndroidTheme {
                CsvAssignScreen(
                    api = api,
                    repository = repository,
                    uri = uri,
                    fileName = fileName,
                    onDone = { finish() },
                )
            }
        }
    }

    private fun extractSharedUri(): Uri? {
        val fromStream = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(Intent.EXTRA_STREAM)
        }
        return fromStream ?: intent.data
    }

    private fun resolveDisplayName(uri: Uri): String? {
        return runCatching {
            contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                val idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (idx >= 0 && cursor.moveToFirst()) cursor.getString(idx) else null
            }
        }.getOrNull()
    }
}
