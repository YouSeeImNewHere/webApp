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
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VehicleProceduresScreen(
    viewModel: VehicleViewModel,
    onOpenHome: () -> Unit,
    onOpenIssues: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenNotifications: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    var activeSheet by remember { mutableStateOf<VehicleSheet?>(null) }

    Scaffold(
        topBar = {
            VehicleTopBar(
                title = "DIY Procedures",
                leadingIcon = Icons.Filled.Settings,
                onLeadingClick = onOpenSettings,
                trailingIcon = Icons.Filled.Notifications,
                onTrailingClick = onOpenNotifications,
            )
        },
        bottomBar = {
            VehicleBottomBar(
                selectedTab = VehicleTab.PROCEDURES,
                onSelectHome = onOpenHome,
                onSelectProcedures = {},
                onSelectIssues = onOpenIssues,
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
                    Text("Couldn't load procedures", fontWeight = FontWeight.Bold)
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
                    ProceduresList(state.data.procedures, onOpenSheet = { activeSheet = it })
                }
            }
        }
    }

    activeSheet?.let { sheet ->
        VehicleSheetHost(sheet = sheet, viewModel = viewModel, uiState = uiState, onDismiss = { activeSheet = null })
    }
}

@Composable
private fun ProceduresList(procedures: List<MaintenanceProcedure>, onOpenSheet: (VehicleSheet) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Surface(
                onClick = { onOpenSheet(VehicleSheet.EditProcedure(null)) },
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    Text("New Procedure", color = Color.Black, fontWeight = FontWeight.Bold)
                }
            }
        }
        if (procedures.isEmpty()) {
            item { EmptyCard("No procedures saved", "Write a Procedure") { onOpenSheet(VehicleSheet.EditProcedure(null)) } }
        } else {
            item {
                Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                    Column {
                        procedures.forEachIndexed { idx, proc ->
                            Surface(
                                onClick = { onOpenSheet(VehicleSheet.EditProcedure(proc)) },
                                color = Color.Transparent,
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                                ) {
                                    Icon(Icons.Filled.Description, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(proc.title.ifBlank { "Untitled" }, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                        Text(
                                            "${proc.steps.size} steps · ${proc.tools.size} tools",
                                            color = QuailTextDim,
                                            style = MaterialTheme.typography.labelSmall,
                                        )
                                        if (proc.relatedTypeName.isNotBlank()) {
                                            Text(proc.relatedTypeName, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                                        }
                                    }
                                }
                            }
                            if (idx < procedures.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                        }
                    }
                }
            }
        }
    }
}
