package com.quail.android.ui.screens.vehicle

import android.widget.Toast
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
import androidx.compose.material.icons.filled.CarRepair
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.TireRepair
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.DEFAULT_MAINTENANCE_TYPES
import com.quail.android.data.repository.VehicleLocalStore
import com.quail.android.data.repository.VehicleNotifyPref
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VehicleSettingsScreen(
    viewModel: VehicleViewModel,
    localStore: VehicleLocalStore,
    onBack: () -> Unit,
    onOpenNotifications: () -> Unit,
    onOpenHome: () -> Unit,
    onOpenProcedures: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    var activeSheet by remember { mutableStateOf<VehicleSheet?>(null) }
    val context = LocalContext.current

    Scaffold(
        topBar = {
            VehicleTopBar(
                title = "Settings",
                leadingIcon = Icons.Filled.ArrowBack,
                onLeadingClick = onBack,
                trailingIcon = Icons.Filled.Notifications,
                onTrailingClick = onOpenNotifications,
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
                val data = state.data
                val stubToast: () -> Unit = { Toast.makeText(context, "Not built yet", Toast.LENGTH_SHORT).show() }

                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    item {
                        CarSettingsSection("Vehicle") {
                            CarSettingsRow(
                                icon = Icons.Filled.DirectionsCar,
                                iconColor = Color(0xFFF28C1A),
                                title = "Vehicle Profile",
                                subtitle = if (data.profile.isEmpty) "Not configured" else data.profile.displayName,
                                onClick = { activeSheet = VehicleSheet.EditProfile },
                            )
                        }
                    }

                    item {
                        CarSettingsSection("Maintenance") {
                            CarSettingsRow(
                                icon = Icons.Filled.CarRepair,
                                iconColor = MaterialTheme.colorScheme.primary,
                                title = "Service Types",
                                subtitle = "${DEFAULT_MAINTENANCE_TYPES.size} built-in types",
                                onClick = stubToast,
                            )
                            HorizontalDivider(color = QuailSurfaceRaised)
                            CarSettingsRow(
                                icon = Icons.Filled.CheckCircle,
                                iconColor = QuailGoodGreen,
                                title = "Inspection Items",
                                subtitle = "${data.inspections.size} items · " +
                                    "${data.inspections.count { it.periodicityDays <= 7 }} weekly, " +
                                    "${data.inspections.count { it.periodicityDays > 7 }} monthly",
                                onClick = stubToast,
                            )
                        }
                    }

                    item {
                        CarSettingsSection("Tires") {
                            CarSettingsRow(
                                icon = Icons.Filled.TireRepair,
                                iconColor = Color(0xFF66A0F2),
                                title = "Tire Sets",
                                subtitle = data.activeTireSet?.let { "Active: ${it.displayName}" } ?: "No active set",
                                onClick = null,
                            )
                        }
                    }

                    item {
                        CarSettingsSection("Data") {
                            CarSettingsRow(
                                icon = Icons.Filled.CloudDownload,
                                iconColor = Color(0xFF33A366),
                                title = "Import History CSV",
                                subtitle = "Load fuel and oil change history from a CSV file",
                                onClick = stubToast,
                            )
                            HorizontalDivider(color = QuailSurfaceRaised)
                            CarSettingsRow(
                                icon = Icons.Filled.Link,
                                iconColor = Color(0xFF668CF2),
                                title = "Pair Transactions",
                                subtitle = "Link fuel and maintenance records to bank transactions",
                                onClick = stubToast,
                            )
                        }
                    }

                    item {
                        CarSettingsSection("Notifications") {
                            VehicleNotifyPref.entries.forEachIndexed { idx, pref ->
                                NotifyToggleRow(pref, localStore)
                                if (idx < VehicleNotifyPref.entries.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                            }
                        }
                    }
                }
            }
        }
    }

    activeSheet?.let { sheet ->
        VehicleSheetHost(sheet = sheet, viewModel = viewModel, uiState = uiState, onDismiss = { activeSheet = null })
    }
}

@Composable
private fun CarSettingsSection(title: String, content: @Composable () -> Unit) {
    Column {
        Text(
            title,
            color = QuailTextDim,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.padding(horizontal = 4.dp, bottom = 6.dp),
        )
        Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
            Column { content() }
        }
    }
}

@Composable
private fun CarSettingsRow(icon: ImageVector, iconColor: Color, title: String, subtitle: String, onClick: (() -> Unit)?) {
    val row: @Composable () -> Unit = {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Surface(color = iconColor.copy(alpha = 0.15f), shape = RoundedCornerShape(10.dp)) {
                Box(Modifier.padding(8.dp)) { Icon(icon, contentDescription = null, tint = iconColor) }
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
    if (onClick != null) {
        Surface(onClick = onClick, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) { row() }
    } else {
        row()
    }
}

@Composable
private fun NotifyToggleRow(pref: VehicleNotifyPref, localStore: VehicleLocalStore) {
    val scope = rememberCoroutineScope()
    val isOn by localStore.notifyPref(pref).collectAsState(initial = pref.defaultOn)
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(pref.title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
            Text(pref.subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
        Switch(
            checked = isOn,
            onCheckedChange = { value -> scope.launch { localStore.setNotifyPref(pref, value) } },
        )
    }
}
