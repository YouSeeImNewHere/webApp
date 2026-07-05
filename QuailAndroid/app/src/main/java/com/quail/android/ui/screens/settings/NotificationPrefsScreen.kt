package com.quail.android.ui.screens.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.bugreport.BugReportTopBarAction

/** Mirrors NotificationSettingsPageView.swift — shared/global notification
 * preferences, reachable both from Cash's SettingsHomePageView ("Smart
 * Notifications" row) and from DashboardSettingsPageView ("Notifications"
 * section), not owned by either. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotificationPrefsScreen(viewModel: SettingsViewModel, onBack: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Smart Notifications", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = isRefreshing,
            onRefresh = { viewModel.pullRefresh() },
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            when (val state = uiState) {
                is SettingsUiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                is SettingsUiState.Error -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(state.message, color = QuailTextDim) }
                is SettingsUiState.Success -> {
                    Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                        Text(
                            "Spending power, overspending alerts, and savings nudges.",
                            color = QuailTextDim,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(bottom = 10.dp),
                        )
                        Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
                            Column {
                                SettingsViewModel.PREF_LABELS.forEachIndexed { index, (key, label) ->
                                    NotificationPrefRow(
                                        label = label,
                                        checked = state.settings.prefs[key] ?: false,
                                        saving = state.savingKey == key,
                                        onToggle = { viewModel.togglePref(key, it) },
                                    )
                                    if (index != SettingsViewModel.PREF_LABELS.lastIndex) RowDivider()
                                }
                            }
                        }
                        if (state.settings.iosPushDeviceCount == 0) {
                            Text(
                                "No push devices registered.",
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(top = 10.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificationPrefRow(label: String, checked: Boolean, saving: Boolean, onToggle: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        if (saving) {
            CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp).size(20.dp), strokeWidth = 2.dp)
        }
        Switch(checked = checked, onCheckedChange = onToggle, enabled = !saving)
    }
}
