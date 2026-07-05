package com.quail.android.ui.screens.vehicle

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailTextDim

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VehicleIssuesScreen(
    viewModel: VehicleViewModel,
    onOpenHome: () -> Unit,
    onOpenProcedures: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenNotifications: () -> Unit,
    onOpenDashboard: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    var activeSheet by remember { mutableStateOf<VehicleSheet?>(null) }

    Scaffold(
        topBar = {
            VehicleTopBar(
                title = "Issues & Repairs",
                leadingIcon = Icons.Filled.Settings,
                onLeadingClick = onOpenSettings,
                trailingIcon = Icons.Filled.Notifications,
                onTrailingClick = onOpenNotifications,
            )
        },
        bottomBar = {
            VehicleBottomBar(
                selectedTab = VehicleTab.ISSUES,
                onSelectHome = onOpenHome,
                onSelectProcedures = onOpenProcedures,
                onSelectIssues = {},
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
                val open = data.openIssues
                val resolved = data.issues.filter { it.isResolved }.sortedByDescending { it.resolvedDate ?: it.dateNoticed }
                val corrective = data.correctiveRecords.sortedByDescending { it.date }

                if (open.isEmpty() && resolved.isEmpty() && corrective.isEmpty()) {
                    Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                        EmptyCard("No issues or repairs logged yet", "Report an Issue") { activeSheet = VehicleSheet.AddIssue }
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(padding),
                        contentPadding = PaddingValues(12.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        item { SectionHeader("Open Issues", actionLabel = "Report Issue") { activeSheet = VehicleSheet.AddIssue } }
                        if (open.isEmpty()) {
                            item { EmptyCard("No open issues", "Report an Issue") { activeSheet = VehicleSheet.AddIssue } }
                        } else {
                            item {
                                Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(vertical = 8.dp)) {
                                        open.forEach { issue -> IssueRow(issue, onOpenSheet = { activeSheet = it }) }
                                    }
                                }
                            }
                        }

                        item { SectionHeader("Repairs", actionLabel = "Record Repair") { activeSheet = VehicleSheet.AddCorrective(null) } }
                        if (corrective.isEmpty()) {
                            item { Text("No repairs logged yet", color = QuailTextDim, modifier = Modifier.padding(horizontal = 4.dp)) }
                        } else {
                            item {
                                Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(vertical = 8.dp)) {
                                        corrective.forEach { rec -> CorrectiveRow(rec) }
                                    }
                                }
                            }
                        }

                        if (resolved.isNotEmpty()) {
                            item { SectionHeader("Resolved Issues") }
                            item {
                                Surface(color = QuailSurface, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(vertical = 8.dp)) {
                                        resolved.forEach { issue -> IssueRow(issue, onOpenSheet = { activeSheet = it }) }
                                    }
                                }
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
