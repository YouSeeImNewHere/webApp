package com.quail.android.ui.screens.settings

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.AppConfig
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.bugreport.BugReportTopBarAction

/** Mirrors DashboardSettingsPageView.swift — the Dashboard's own gear icon
 * opens this, NOT the Cash-specific SettingsScreen. It's a lightweight
 * landing page (theme, Gmail connect, a link into notification settings)
 * that itself links onward into the full Cash settings ("App Settings").
 * Sign out lives here too — it's account-wide, not a Cash-app concept, so
 * SettingsHomePageView's Android port (SettingsScreen) doesn't own it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardSettingsScreen(
    onBack: () -> Unit,
    onOpenNotificationSettings: () -> Unit,
    onOpenAppSettings: () -> Unit,
    onSignOut: () -> Unit,
) {
    val context = LocalContext.current
    var theme by remember { mutableStateOf("system") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                top = padding.calculateTopPadding() + 8.dp,
                bottom = padding.calculateBottomPadding() + 32.dp,
                start = 14.dp,
                end = 14.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item {
                SettingsSection("Appearance") {
                    ThemeRow(
                        selected = theme,
                        onSelect = { value ->
                            if (value in SUPPORTED_THEMES) {
                                theme = value
                            } else {
                                Toast.makeText(context, "That theme isn't built for Android yet — dark only for now", Toast.LENGTH_SHORT).show()
                            }
                        },
                    )
                }
            }

            item {
                SettingsSection("Google Gmail") {
                    SettingsRow(
                        icon = Icons.Filled.Email,
                        iconColor = Color(0xFFEF5350),
                        title = "Connect Gmail",
                        subtitle = "Lets receipts and bills get scanned from your inbox automatically",
                        onClick = {
                            val url = "${AppConfig.BASE_URL}/gmail/oauth/start?next=/settings"
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        },
                    )
                }
            }

            item {
                SettingsSection("Notifications") {
                    SettingsRow(
                        icon = Icons.Filled.NotificationsActive,
                        iconColor = QuailBadRed,
                        title = "Notifications",
                        subtitle = "Spending power, overspending alerts, and savings nudges",
                        onClick = onOpenNotificationSettings,
                    )
                }
            }

            item {
                SettingsSection("Advanced") {
                    SettingsRow(
                        icon = Icons.Filled.Build,
                        iconColor = MaterialTheme.colorScheme.primary,
                        title = "App Settings",
                        subtitle = "Cache, rules, setup, import, and admin tools",
                        onClick = onOpenAppSettings,
                    )
                }
            }

            item {
                SettingsSection("Account") {
                    SettingsRow(
                        icon = Icons.Filled.Logout,
                        iconColor = QuailBadRed,
                        title = "Sign out",
                        subtitle = "Sign out of this device",
                        onClick = onSignOut,
                        showChevron = false,
                    )
                }
            }
        }
    }
}
