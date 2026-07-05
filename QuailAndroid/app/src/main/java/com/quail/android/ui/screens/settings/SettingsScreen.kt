package com.quail.android.ui.screens.settings

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.FactCheck
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Inbox
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Widgets
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.bugreport.BugReportTopBarAction

// Matches SettingsHomePageView.swift's `themes` list — only "system"/"dark"
// are real on Android today (one branded dark palette, no light/OLED/etc.
// palettes built yet); the rest are shown for structural parity and toast.
// Shared with DashboardSettingsScreen, which has its own copy of the picker.
val THEME_OPTIONS = listOf(
    "system" to "System",
    "light" to "Default (Light)",
    "dark" to "Dark",
    "oled" to "OLED Black",
    "solarized" to "Solarized",
    "forest" to "Forest",
    "midnight" to "Midnight Blue",
)
val SUPPORTED_THEMES = setOf("system", "dark")

/** Mirrors SettingsHomePageView.swift — the Cash-app-specific settings hub,
 * reached from the Cash top bar's gear icon (not the Dashboard's, which
 * opens DashboardSettingsScreen instead). No "Account"/sign-out section
 * here — that's dashboard-level, not Cash-specific, per iOS's own split. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel,
    onBack: () -> Unit,
    onOpenNotificationSettings: () -> Unit,
    onOpenCsvImportQueue: () -> Unit = {},
) {
    val context = LocalContext.current
    val cacheStatus by viewModel.cacheStatus.collectAsState()
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
                SettingsSection("Notifications") {
                    SettingsRow(
                        icon = Icons.Filled.NotificationsActive,
                        iconColor = QuailBadRed,
                        title = "Smart Notifications",
                        subtitle = "Spending power, overspending alerts, and savings nudges",
                        onClick = onOpenNotificationSettings,
                    )
                }
            }

            item {
                SettingsSection("Home") {
                    SettingsRow(
                        icon = Icons.Filled.GridView,
                        iconColor = MaterialTheme.colorScheme.primary,
                        title = "Customize Layout",
                        subtitle = "Rearrange and show/hide cards on the home screen",
                        onClick = { Toast.makeText(context, "Customize layout isn't built yet", Toast.LENGTH_SHORT).show() },
                    )
                    RowDivider()
                    SettingsRow(
                        icon = Icons.Filled.Refresh,
                        iconColor = Color(0xFFFFA726),
                        title = "Refresh Cache",
                        subtitle = cacheStatus ?: "Force the home dashboard and widget cache to recompute now",
                        onClick = { viewModel.refreshCache() },
                    )
                }
            }

            item {
                SettingsSection("Widgets") {
                    SettingsRow(
                        icon = Icons.Filled.Widgets,
                        iconColor = Color(0xFFAB47BC),
                        title = "Home Screen Widget",
                        subtitle = "Long-press your home screen, tap Widgets, and add Quail Cash",
                        onClick = {
                            Toast.makeText(context, "Long-press your home screen → Widgets → Quail Cash", Toast.LENGTH_LONG).show()
                        },
                    )
                }
            }

            item {
                SettingsSection("Initial Setup") {
                    SettingsRow(
                        icon = Icons.Filled.AutoFixHigh,
                        iconColor = Color(0xFF7E57C2),
                        title = "Setup Wizard",
                        subtitle = "Walk through the initial budget and account configuration",
                        onClick = { Toast.makeText(context, "Setup wizard isn't built yet", Toast.LENGTH_SHORT).show() },
                    )
                    RowDivider()
                    SettingsRow(
                        icon = Icons.Filled.Email,
                        iconColor = Color(0xFF26A69A),
                        title = "Email Parser Wizard",
                        subtitle = "Create and maintain live email parser rules",
                        onClick = { Toast.makeText(context, "Email parser wizard isn't built yet", Toast.LENGTH_SHORT).show() },
                    )
                    RowDivider()
                    SettingsRow(
                        icon = Icons.Filled.Inbox,
                        iconColor = Color(0xFF66BB6A),
                        title = "Import Queue",
                        subtitle = "Review CSV imports awaiting processing",
                        onClick = onOpenCsvImportQueue,
                    )
                    RowDivider()
                    SettingsRow(
                        icon = Icons.Filled.AttachMoney,
                        iconColor = Color(0xFF26C6DA),
                        title = "Income Wizard",
                        subtitle = "Set up salary or hourly income settings",
                        onClick = { Toast.makeText(context, "Income wizard isn't built yet", Toast.LENGTH_SHORT).show() },
                    )
                    RowDivider()
                    SettingsRow(
                        icon = Icons.Filled.Apps,
                        iconColor = QuailTextDim,
                        title = "External Apps",
                        subtitle = "Install required apps for widgets and push notifications",
                        onClick = { Toast.makeText(context, "External apps isn't built yet", Toast.LENGTH_SHORT).show() },
                    )
                }
            }

            item {
                SettingsSection("Rules") {
                    SettingsRow(
                        icon = Icons.Filled.FactCheck,
                        iconColor = Color(0xFF26C6DA),
                        title = "Category Rules",
                        subtitle = "View matches, test regex, re-apply, disable, or delete rules",
                        onClick = { Toast.makeText(context, "Category rules editor isn't built yet", Toast.LENGTH_SHORT).show() },
                    )
                }
            }
        }
    }
}

@Composable
fun SettingsSection(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            title.uppercase(),
            color = QuailTextDim,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(start = 4.dp),
        )
        Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
            Column { content() }
        }
    }
}

@Composable
fun RowDivider() {
    HorizontalDivider(modifier = Modifier.padding(start = 62.dp), color = QuailTextDim.copy(alpha = 0.12f))
}

@Composable
fun IconBadge(icon: ImageVector, color: Color) {
    Surface(color = color.copy(alpha = 0.18f), shape = RoundedCornerShape(9.dp), modifier = Modifier.size(36.dp)) {
        Box(contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
fun SettingsRow(
    icon: ImageVector,
    iconColor: Color,
    title: String,
    subtitle: String,
    onClick: () -> Unit,
    showChevron: Boolean = true,
) {
    Surface(onClick = onClick, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            IconBadge(icon, iconColor)
            Column(modifier = Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, maxLines = 2)
            }
            if (showChevron) {
                Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = QuailTextDim, modifier = Modifier.size(18.dp))
            }
        }
    }
}

@Composable
fun ThemeRow(selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val label = THEME_OPTIONS.firstOrNull { it.first == selected }?.second ?: "System"

    Box {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            IconBadge(Icons.Filled.Palette, MaterialTheme.colorScheme.primary)
            Column(modifier = Modifier.weight(1f)) {
                Text("Color scheme", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                Text("Controls the app's visual theme", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            Surface(onClick = { expanded = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                Text(label, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelSmall)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            THEME_OPTIONS.forEach { (value, optionLabel) ->
                DropdownMenuItem(text = { Text(optionLabel) }, onClick = { onSelect(value); expanded = false })
            }
        }
    }
}
