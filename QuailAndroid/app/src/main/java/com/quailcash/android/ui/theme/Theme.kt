package com.quailcash.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val QuailDarkColors = darkColorScheme(
    background = QuailBackground,
    surface = QuailSurface,
    surfaceVariant = QuailSurfaceRaised,
    primary = QuailAccent,
    onPrimary = QuailText,
    onBackground = QuailText,
    onSurface = QuailText,
    error = QuailBadRed,
    outline = QuailBorder,
)

@Composable
fun QuailAndroidTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    // Always dark, matching QuailCash's dark theme regardless of system
    // setting — the iOS app defaults here too and this screen should look
    // like the same app.
    MaterialTheme(
        colorScheme = QuailDarkColors,
        typography = QuailTypography,
        content = content,
    )
}
