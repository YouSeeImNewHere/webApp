package com.quail.android.ui.screens.vehicle

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.BatteryFull
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.FilterAlt
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Opacity
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import com.quail.android.data.model.CorrectiveRecord
import com.quail.android.data.model.DEFAULT_MAINTENANCE_TYPES
import com.quail.android.data.model.MaintenanceColor
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.data.model.MaintenanceTypeDefinition
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleIssue
import com.quail.android.data.model.VehicleMaintenanceStatus
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailText
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale

private val currencyFormat: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)
private val QuailWarnOrange = Color(0xFFF28C1A)

fun MaintenanceColor.toColor(): Color = when (this) {
    MaintenanceColor.ORANGE -> QuailWarnOrange
    MaintenanceColor.BLUE -> Color(0xFF66A0F2)
    MaintenanceColor.RED -> QuailBadRed
    MaintenanceColor.YELLOW -> Color(0xFFE6BF1A)
    MaintenanceColor.GREEN -> QuailGoodGreen
    MaintenanceColor.TEAL -> Color(0xFF26B3A6)
    MaintenanceColor.PURPLE -> Color(0xFF9454D9)
    MaintenanceColor.GRAY -> QuailTextDim
}

fun MaintenanceTypeDefinition.icon(): ImageVector = when (name) {
    "Oil Change" -> Icons.Filled.Opacity
    "Tire Rotation" -> Icons.Filled.Circle
    "Brake Pads" -> Icons.Filled.Warning
    "Brake Fluid" -> Icons.Filled.Opacity
    "Spark Plugs" -> Icons.Filled.Bolt
    "Air Filter" -> Icons.Filled.Air
    "Cabin Filter" -> Icons.Filled.FilterAlt
    "Coolant Flush" -> Icons.Filled.Thermostat
    "Transmission Fluid" -> Icons.Filled.Settings
    "Battery" -> Icons.Filled.BatteryFull
    "Timing Belt" -> Icons.Filled.Build
    else -> Icons.Filled.Build
}

sealed interface VehicleSheet {
    data object EditProfile : VehicleSheet
    data class RecordMaintenance(val typeName: String?) : VehicleSheet
    data object RecordFuel : VehicleSheet
    data object AddIssue : VehicleSheet
    data class AddCorrective(val issueId: Int?) : VehicleSheet
    data object AddTireSet : VehicleSheet
    data object TirePressureCheck : VehicleSheet
    data class EditProcedure(val existing: MaintenanceProcedure?) : VehicleSheet
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VehicleScreen(
    viewModel: VehicleViewModel,
    onOpenProcedures: () -> Unit,
    onOpenFuelHistory: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenNotifications: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    var activeSheet by remember { mutableStateOf<VehicleSheet?>(null) }

    Scaffold(
        topBar = {
            VehicleTopBar(
                title = "Quail Car",
                leadingIcon = Icons.Filled.Settings,
                onLeadingClick = onOpenSettings,
                trailingIcon = Icons.Filled.Notifications,
                onTrailingClick = onOpenNotifications,
            )
        },
        bottomBar = {
            VehicleBottomBar(
                selectedTab = VehicleTab.HOME,
                onSelectHome = {},
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
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Couldn't load Quail Car", fontWeight = FontWeight.Bold)
                    Text(state.message, color = QuailTextDim, modifier = Modifier.padding(top = 4.dp))
                }
            }
            is VehicleUiState.Success -> {
                var isRefreshing by remember { mutableStateOf(false) }
                PullToRefreshBox(
                    isRefreshing = isRefreshing,
                    onRefresh = { viewModel.refresh(); isRefreshing = false },
                    modifier = Modifier.fillMaxSize().padding(padding),
                ) {
                    VehicleContent(
                        data = state.data,
                        onOpenSheet = { activeSheet = it },
                        onCheckInspection = { viewModel.checkInspection(it) },
                        onOpenFuelHistory = onOpenFuelHistory,
                    )
                }
            }
        }
    }

    activeSheet?.let { sheet ->
        VehicleSheetHost(sheet = sheet, viewModel = viewModel, uiState = uiState, onDismiss = { activeSheet = null })
    }
}

@Composable
fun VehicleTopBar(
    title: String,
    leadingIcon: ImageVector,
    onLeadingClick: () -> Unit,
    trailingIcon: ImageVector,
    onTrailingClick: () -> Unit,
) {
    Surface(color = QuailSurface) {
        Box(
            modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 12.dp, vertical = 8.dp).height(40.dp),
        ) {
            TopCircleButton(
                icon = leadingIcon,
                modifier = Modifier.align(Alignment.CenterStart),
                onClick = onLeadingClick,
            )

            Text(title, fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.titleLarge, modifier = Modifier.align(Alignment.Center))

            TopCircleButton(
                icon = trailingIcon,
                modifier = Modifier.align(Alignment.CenterEnd),
                onClick = onTrailingClick,
            )
        }
    }
}

@Composable
fun TopCircleButton(icon: ImageVector, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = CircleShape, modifier = modifier.height(40.dp).width(40.dp)) {
        Box(contentAlignment = Alignment.Center) { Icon(icon, contentDescription = null, tint = QuailText) }
    }
}

enum class VehicleTab { HOME, PROCEDURES }

@Composable
fun VehicleBottomBar(
    selectedTab: VehicleTab?,
    onSelectHome: () -> Unit,
    onSelectProcedures: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    Surface(color = QuailSurface) {
        Row(
            modifier = Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 8.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            VehicleBottomBarTab("Home", Icons.Filled.Home, selected = selectedTab == VehicleTab.HOME, onClick = onSelectHome)
            VehicleBottomBarTab("Procedures", Icons.Filled.Description, selected = selectedTab == VehicleTab.PROCEDURES, onClick = onSelectProcedures)
            Surface(onClick = onOpenDashboard, color = MaterialTheme.colorScheme.primary, shape = RoundedCornerShape(12.dp)) {
                Row(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Filled.Dashboard, contentDescription = null, tint = Color.Black)
                    Text("Dashboard", color = Color.Black, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 6.dp))
                }
            }
        }
    }
}

@Composable
private fun VehicleBottomBarTab(label: String, icon: ImageVector, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (selected) QuailSurfaceRaised else Color.Transparent,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.width(84.dp),
    ) {
        Column(
            modifier = Modifier.padding(vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, contentDescription = label, tint = if (selected) QuailText else QuailTextDim)
            Text(label, color = if (selected) QuailText else QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun VehicleContent(
    data: VehicleData,
    onOpenSheet: (VehicleSheet) -> Unit,
    onCheckInspection: (String) -> Unit,
    onOpenFuelHistory: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { ProfileCard(data, onOpenSheet) }
        item { MaintenanceSection(data, onOpenSheet) }
        item { InspectionsSection(data, onCheckInspection) }
        item { FuelSection(data, onOpenSheet, onOpenFuelHistory) }
        item { TiresSection(data, onOpenSheet) }
        item { IssuesSection(data, onOpenSheet) }
    }
}

@Composable
fun SectionHeader(title: String, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(title, color = QuailTextDim, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
        if (actionLabel != null && onAction != null) {
            Text(
                actionLabel,
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.padding(start = 8.dp).clickable(onClick = onAction),
            )
        }
    }
}

@Composable
fun EmptyCard(text: String, actionLabel: String, onAction: () -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(text, color = QuailTextDim, modifier = Modifier.padding(bottom = 8.dp))
            Surface(onClick = onAction, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                Text(actionLabel, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
            }
        }
    }
}

// ---- Profile ----

@Composable
private fun ProfileCard(data: VehicleData, onOpenSheet: (VehicleSheet) -> Unit) {
    val profile = data.profile
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                Column {
                    if (profile.isEmpty) {
                        Text("Set up your vehicle", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text("Tap Edit to add your car's details", color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                    } else {
                        Text(profile.displayName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        if (profile.licensePlate.isNotBlank()) {
                            Text(profile.licensePlate, color = QuailTextDim, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Surface(onClick = { onOpenSheet(VehicleSheet.EditProfile) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                    Text("Edit", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp))
                }
            }

            if (!profile.isEmpty) {
                Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    ProfileStat("Mileage", "${profile.currentMileage} mi")
                    ProfileStat("VIN", profile.vin.takeLast(6).ifBlank { "—" })
                    ProfileStat("Oil", profile.oilType.ifBlank { "—" })
                }
            }
        }
    }
}

@Composable
private fun ProfileStat(label: String, value: String) {
    Column {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Text(value, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
    }
}

// ---- Maintenance ----

@Composable
private fun MaintenanceSection(data: VehicleData, onOpenSheet: (VehicleSheet) -> Unit) {
    Column {
        SectionHeader("Scheduled Maintenance")
        Surface(
            onClick = { onOpenSheet(VehicleSheet.RecordMaintenance(null)) },
            color = MaterialTheme.colorScheme.primary,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                Text("Record Maintenance", color = Color.Black, fontWeight = FontWeight.Bold)
            }
        }
        Surface(
            color = QuailSurface,
            shape = RoundedCornerShape(20.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) {
            Column {
                DEFAULT_MAINTENANCE_TYPES.forEachIndexed { idx, type ->
                    MaintenanceRow(type, data, onOpenSheet)
                    if (idx < DEFAULT_MAINTENANCE_TYPES.size - 1) {
                        androidx.compose.material3.HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }
    }
}

@Composable
private fun MaintenanceRow(type: MaintenanceTypeDefinition, data: VehicleData, onOpenSheet: (VehicleSheet) -> Unit) {
    val status = maintenanceStatus(type, data.maintenanceRecords, data.profile.currentMileage)
    val last = lastMaintenanceRecord(data.maintenanceRecords, type.name)
    Surface(onClick = { onOpenSheet(VehicleSheet.RecordMaintenance(type.name)) }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(color = type.colorName.toColor().copy(alpha = 0.15f), shape = RoundedCornerShape(10.dp)) {
                Box(Modifier.padding(8.dp)) { Icon(type.icon(), contentDescription = null, tint = type.colorName.toColor()) }
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(type.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                Text(
                    if (last == null) "Never recorded" else "Last: ${last.date}",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    nextDueDescription(type, data.maintenanceRecords, data.profile.currentMileage),
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
                StatusPill(status)
            }
        }
    }
}

@Composable
private fun StatusPill(status: VehicleMaintenanceStatus) {
    val (label, color) = when (status) {
        VehicleMaintenanceStatus.OK -> "OK" to QuailGoodGreen
        VehicleMaintenanceStatus.DUE_SOON -> "Due Soon" to QuailWarnOrange
        VehicleMaintenanceStatus.OVERDUE -> "Overdue" to QuailBadRed
        VehicleMaintenanceStatus.NEVER -> "Never" to QuailTextDim
    }
    Surface(color = if (status == VehicleMaintenanceStatus.NEVER) color.copy(alpha = 0.15f) else color, shape = RoundedCornerShape(999.dp)) {
        Text(
            label,
            color = if (status == VehicleMaintenanceStatus.NEVER) QuailTextDim else Color.White,
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp),
        )
    }
}

// ---- Inspections ----

@Composable
private fun InspectionsSection(data: VehicleData, onCheckInspection: (String) -> Unit) {
    val weekly = data.inspections.filter { it.periodicityDays <= 7 }
    val monthly = data.inspections.filter { it.periodicityDays > 7 }
    Column {
        SectionHeader("Inspections")
        if (weekly.isNotEmpty()) InspectionGroup("Weekly", weekly, onCheckInspection)
        if (monthly.isNotEmpty()) InspectionGroup("Monthly", monthly, onCheckInspection, modifier = Modifier.padding(top = 10.dp))
    }
}

@Composable
private fun InspectionGroup(
    title: String,
    items: List<com.quail.android.data.model.VehicleInspectionItem>,
    onCheckInspection: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = modifier.fillMaxWidth()) {
        Column(Modifier.padding(vertical = 8.dp)) {
            Text(title, color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
            items.forEachIndexed { idx, item ->
                val isDue = isInspectionDue(item)
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    IconButton(onClick = { item.clientId?.let(onCheckInspection) }) {
                        Icon(
                            if (isDue) Icons.Filled.Circle else Icons.Filled.CheckCircle,
                            contentDescription = null,
                            tint = if (isDue) QuailSurfaceRaised else QuailGoodGreen,
                        )
                    }
                    Column(modifier = Modifier.weight(1f)) {
                        Text(item.name, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            if (isDue) "Needs check" else "Checked ${item.lastCheckedDate ?: ""}",
                            color = if (isDue) QuailWarnOrange else QuailTextDim,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                    if (isDue) {
                        Surface(color = QuailWarnOrange, shape = RoundedCornerShape(999.dp)) {
                            Text("Due", color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
                        }
                    }
                }
                if (idx < items.size - 1) androidx.compose.material3.HorizontalDivider(color = QuailSurfaceRaised)
            }
        }
    }
}

fun isInspectionDue(item: com.quail.android.data.model.VehicleInspectionItem): Boolean {
    val last = item.lastCheckedDate ?: return true
    val date = runCatching { java.time.LocalDate.parse(last) }.getOrNull() ?: return true
    val days = java.time.temporal.ChronoUnit.DAYS.between(date, java.time.LocalDate.now())
    return days >= item.periodicityDays
}

// ---- Fuel ----

@Composable
private fun FuelSection(data: VehicleData, onOpenSheet: (VehicleSheet) -> Unit, onOpenFuelHistory: () -> Unit) {
    val mpg = averageMpg(data.fuelRecords)
    Column {
        SectionHeader("Fuel & Mileage", actionLabel = "+ Log Fill-Up") { onOpenSheet(VehicleSheet.RecordFuel) }
        Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                if (mpg != null) {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(String.format(Locale.US, "%.1f", mpg), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                        Text(" MPG avg", color = QuailTextDim, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(bottom = 4.dp))
                    }
                    androidx.compose.material3.HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(vertical = 10.dp))
                } else {
                    Text("Log at least 2 fill-ups to calculate MPG", color = QuailTextDim, modifier = Modifier.padding(bottom = 8.dp))
                }

                val recent = data.fuelRecords.sortedByDescending { it.date }.take(3)
                if (recent.isEmpty()) {
                    Text("No fill-ups logged yet", color = QuailTextDim)
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        recent.forEach { FuelRow(it) }
                    }
                }

                if (data.fuelRecords.isNotEmpty()) {
                    Surface(onClick = onOpenFuelHistory, color = Color.Transparent, modifier = Modifier.fillMaxWidth().padding(top = 10.dp)) {
                        Text(
                            "View Full History",
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.SemiBold,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun FuelRow(record: VehicleFuelRecord) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Column {
            Text(record.date, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Text(
                if (record.station.isBlank()) "${record.mileage} mi" else "${record.station} · ${record.mileage} mi",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(String.format(Locale.US, "%.3f gal", record.gallons ?: 0.0), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            record.totalCost?.let { Text(currencyFormat.format(it), color = QuailTextDim, style = MaterialTheme.typography.labelSmall) }
        }
    }
}

// ---- Tires ----

@Composable
private fun TiresSection(data: VehicleData, onOpenSheet: (VehicleSheet) -> Unit) {
    Column {
        SectionHeader("Tires", actionLabel = "+ Add Set") { onOpenSheet(VehicleSheet.AddTireSet) }
        val tires = data.activeTireSet
        if (tires == null) {
            EmptyCard("No active tire set", "Add Tires") { onOpenSheet(VehicleSheet.AddTireSet) }
        } else {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                        Column {
                            Text(tires.displayName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
                            Text("On since ${tires.installDate} · ${tires.installMileage} mi", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                        }
                        Surface(onClick = { onOpenSheet(VehicleSheet.TirePressureCheck) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                            Text("Check Pressure", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
                        }
                    }
                    androidx.compose.material3.HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(vertical = 12.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                        TireStat("Required F", "${tires.requiredPressureFront} PSI")
                        TireStat("Required R", "${tires.requiredPressureRear} PSI")
                        tires.lastPressureCheck?.let { TireStat("Last Check", it.date) }
                    }
                    tires.lastPressureCheck?.let { last ->
                        androidx.compose.material3.HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(vertical = 12.dp))
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            PressureCell("FL", last.frontLeft, tires.requiredPressureFront, Modifier.weight(1f))
                            PressureCell("FR", last.frontRight, tires.requiredPressureFront, Modifier.weight(1f))
                            PressureCell("RL", last.rearLeft, tires.requiredPressureRear, Modifier.weight(1f))
                            PressureCell("RR", last.rearRight, tires.requiredPressureRear, Modifier.weight(1f))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TireStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun PressureCell(pos: String, psi: Int, required: Int, modifier: Modifier = Modifier) {
    val delta = kotlin.math.abs(psi - required)
    val color = if (delta <= 3) QuailGoodGreen else if (delta <= 6) QuailWarnOrange else QuailBadRed
    Surface(color = color.copy(alpha = 0.12f), shape = RoundedCornerShape(10.dp), modifier = modifier) {
        Column(Modifier.padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(pos, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
            Text("$psi", color = color, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("PSI", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
    }
}

// ---- Issues & Corrective ----

@Composable
private fun IssuesSection(data: VehicleData, onOpenSheet: (VehicleSheet) -> Unit) {
    val open = data.openIssues
    val corrective = data.correctiveRecords.sortedByDescending { it.date }.take(3)
    Column {
        SectionHeader("Issues & Repairs", actionLabel = "Report Issue") { onOpenSheet(VehicleSheet.AddIssue) }
        if (open.isEmpty() && corrective.isEmpty()) {
            EmptyCard("No open issues", "Report an Issue") { onOpenSheet(VehicleSheet.AddIssue) }
        } else {
            Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(vertical = 8.dp)) {
                    if (open.isNotEmpty()) {
                        Text("OPEN ISSUES", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
                        open.forEach { issue -> IssueRow(issue, onOpenSheet) }
                        Surface(
                            onClick = { onOpenSheet(VehicleSheet.AddCorrective(null)) },
                            color = Color.Transparent,
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
                        ) {
                            Text("Record Repair", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.fillMaxWidth())
                        }
                    }
                    if (corrective.isNotEmpty()) {
                        Text("RECENT REPAIRS", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
                        corrective.forEach { CorrectiveRow(it) }
                    }
                }
            }
        }
    }
}

@Composable
private fun IssueRow(issue: VehicleIssue, onOpenSheet: (VehicleSheet) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = QuailBadRed)
        Column(modifier = Modifier.weight(1f)) {
            Text(issue.title.ifBlank { "Untitled Issue" }, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Text(
                listOfNotNull(issue.dateNoticed, issue.mileageNoticed?.let { "$it mi" }).joinToString(" · "),
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
            )
        }
        Surface(onClick = { onOpenSheet(VehicleSheet.AddCorrective(issue.id)) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
            Text("Fix", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
        }
    }
}

@Composable
private fun CorrectiveRow(rec: CorrectiveRecord) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(Icons.Filled.Build, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Column(modifier = Modifier.weight(1f)) {
            Text(rec.description.ifBlank { "Repair" }, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Text("${rec.date} · ${rec.mileage} mi", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
        if (rec.resolvedIssue) Icon(Icons.Filled.Circle, contentDescription = null, tint = QuailGoodGreen)
    }
}

