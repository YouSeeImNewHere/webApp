package com.quail.android.ui.screens.vehicle

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.DEFAULT_MAINTENANCE_TYPES
import com.quail.android.data.model.VehicleMaintenanceStatus
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

private enum class AlertSeverity(val order: Int) { CRITICAL(0), WARNING(1) }

private data class CarAlert(
    val icon: ImageVector,
    val iconColor: Color,
    val title: String,
    val subtitle: String,
    val severity: AlertSeverity,
)

private val QuailWarnOrange2 = Color(0xFFF28C1A)

private fun buildCarAlerts(data: VehicleData): List<CarAlert> {
    val alerts = mutableListOf<CarAlert>()

    for (type in DEFAULT_MAINTENANCE_TYPES) {
        when (maintenanceStatus(type, data.maintenanceRecords, data.profile.currentMileage)) {
            VehicleMaintenanceStatus.OVERDUE -> alerts += CarAlert(
                icon = type.icon(),
                iconColor = type.colorName.toColor(),
                title = "${type.name} Overdue",
                subtitle = "Next due: ${nextDueDescription(type, data.maintenanceRecords, data.profile.currentMileage)}",
                severity = AlertSeverity.CRITICAL,
            )
            VehicleMaintenanceStatus.DUE_SOON -> alerts += CarAlert(
                icon = type.icon(),
                iconColor = type.colorName.toColor(),
                title = "${type.name} Due Soon",
                subtitle = "Next due: ${nextDueDescription(type, data.maintenanceRecords, data.profile.currentMileage)}",
                severity = AlertSeverity.WARNING,
            )
            else -> {}
        }
    }

    for (item in data.inspections) {
        if (isInspectionDue(item)) {
            alerts += CarAlert(
                icon = Icons.Filled.CheckCircle,
                iconColor = Color(0xFF3399F2),
                title = "${item.name} Inspection Due",
                subtitle = if (item.lastCheckedDate == null) "Never completed" else if (item.periodicityDays <= 7) "Periodicity: Weekly" else "Periodicity: Monthly",
                severity = AlertSeverity.WARNING,
            )
        }
    }

    for (issue in data.openIssues) {
        alerts += CarAlert(
            icon = Icons.Filled.Warning,
            iconColor = QuailBadRed,
            title = "Open Issue: ${issue.title.ifBlank { "Untitled" }}",
            subtitle = issue.description.ifBlank { "Reported ${issue.dateNoticed ?: "recently"}" },
            severity = AlertSeverity.CRITICAL,
        )
    }

    return alerts.sortedBy { it.severity.order }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VehicleNotificationsScreen(
    viewModel: VehicleViewModel,
    onBack: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenHome: () -> Unit,
    onOpenProcedures: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            VehicleTopBar(
                title = "Notifications",
                leadingIcon = Icons.Filled.ArrowBack,
                onLeadingClick = onBack,
                trailingIcon = Icons.Filled.Settings,
                onTrailingClick = onOpenSettings,
            )
        },
        bottomBar = {
            VehicleBottomBar(
                selectedTab = null,
                onSelectHome = onOpenHome,
                onSelectProcedures = onOpenProcedures,
                onOpenDashboard = onOpenDashboard,
            )
        },
    ) { padding ->
        when (val state = uiState) {
            is VehicleUiState.Loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            is VehicleUiState.Error -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(state.message, color = QuailTextDim)
            }
            is VehicleUiState.Success -> {
                var isRefreshing by remember { mutableStateOf(false) }
                PullToRefreshBox(
                    isRefreshing = isRefreshing,
                    onRefresh = { viewModel.refresh(); isRefreshing = false },
                    modifier = Modifier.fillMaxSize().padding(padding),
                ) {
                    val alerts = buildCarAlerts(state.data)
                    if (alerts.isEmpty()) {
                        Column(
                            modifier = Modifier.fillMaxSize().padding(32.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                        ) {
                            Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = QuailGoodGreen, modifier = Modifier.padding(bottom = 8.dp))
                            Text("All clear", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                            Text(
                                "No overdue maintenance, open issues, or pending reminders.",
                                color = QuailTextDim,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                modifier = Modifier.padding(top = 4.dp),
                            )
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(12.dp),
                        ) {
                            item {
                                Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                                    Column {
                                        alerts.forEachIndexed { idx, alert ->
                                            AlertRow(alert)
                                            if (idx < alerts.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AlertRow(alert: CarAlert) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Surface(color = alert.iconColor.copy(alpha = 0.15f), shape = RoundedCornerShape(10.dp)) {
            Box(Modifier.padding(8.dp)) { Icon(alert.icon, contentDescription = null, tint = alert.iconColor) }
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(alert.title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
            Text(alert.subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, maxLines = 2)
        }
        val (label, color) = when (alert.severity) {
            AlertSeverity.CRITICAL -> "Urgent" to QuailBadRed
            AlertSeverity.WARNING -> "Soon" to QuailWarnOrange2
        }
        Surface(color = color, shape = RoundedCornerShape(999.dp)) {
            Text(label, color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
        }
    }
}
