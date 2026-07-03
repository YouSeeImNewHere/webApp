package com.quailcash.android.ui.screens.dashboard

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AdminPanelSettings
import androidx.compose.material.icons.filled.Assignment
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quailcash.android.data.model.MonthBudget
import com.quailcash.android.ui.theme.QuailSurface
import com.quailcash.android.ui.theme.QuailSurfaceRaised
import com.quailcash.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale

private val currencyFormat: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

private data class DashboardTile(
    val label: String,
    val icon: ImageVector,
    val enabled: Boolean,
)

private val TILES = listOf(
    DashboardTile("Cash", Icons.Filled.AttachMoney, enabled = true),
    DashboardTile("Car", Icons.Filled.DirectionsCar, enabled = false),
    DashboardTile("Fitness", Icons.Filled.FitnessCenter, enabled = false),
    DashboardTile("Maps", Icons.Filled.Map, enabled = false),
    DashboardTile("Admin", Icons.Filled.AdminPanelSettings, enabled = false),
    DashboardTile("Bugs", Icons.Filled.BugReport, enabled = false),
    DashboardTile("Projects", Icons.Filled.Assignment, enabled = false),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    viewModel: DashboardViewModel,
    onOpenCash: () -> Unit,
    onOpenSettings: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()
    val context = LocalContext.current

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Quail", fontWeight = FontWeight.ExtraBold) },
                navigationIcon = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Filled.Settings, contentDescription = "Settings")
                    }
                },
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = isRefreshing,
            onRefresh = { viewModel.pullRefresh() },
            modifier = Modifier.fillMaxSize().padding(top = padding.calculateTopPadding()),
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                val cashSnapshot = (uiState as? DashboardUiState.Success)?.cashSnapshot
                val isLoading = uiState is DashboardUiState.Loading

                GlanceStrip(cashSnapshot = cashSnapshot, isLoading = isLoading)

                LazyVerticalGrid(
                    columns = GridCells.Fixed(4),
                    contentPadding = PaddingValues(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize(),
                ) {
                    items(TILES) { tile ->
                        TileButton(tile) {
                            if (tile.enabled) {
                                onOpenCash()
                            } else {
                                Toast.makeText(context, "${tile.label} isn't built yet", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GlanceStrip(cashSnapshot: MonthBudget?, isLoading: Boolean) {
    LazyRow(
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            GlanceCard(title = "Cash") {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                } else if (cashSnapshot != null) {
                    Text(
                        currencyFormat.format(cashSnapshot.safeToSpend),
                        fontWeight = FontWeight.ExtraBold,
                        style = MaterialTheme.typography.titleLarge,
                    )
                    Text(
                        "${cashSnapshot.daysLeft} days left · ${currencyFormat.format(cashSnapshot.billsRemaining)} bills",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                    )
                } else {
                    Text("Unavailable", color = QuailTextDim, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        item { GlanceCard(title = "Car") { ComingSoonBody() } }
        item { GlanceCard(title = "Fitness") { ComingSoonBody() } }
    }
}

@Composable
private fun ComingSoonBody() {
    Text("Coming soon", color = QuailTextDim, style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun GlanceCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        color = QuailSurface,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.width(180.dp).height(90.dp),
    ) {
        Column(Modifier.padding(14.dp).fillMaxSize(), verticalArrangement = Arrangement.Center) {
            Text(title, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            content()
        }
    }
}

@Composable
private fun TileButton(tile: DashboardTile, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (tile.enabled) QuailSurfaceRaised else QuailSurface,
        shape = RoundedCornerShape(18.dp),
        modifier = Modifier
            .fillMaxWidth()
            .height(84.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(4.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    tile.icon,
                    contentDescription = tile.label,
                    tint = if (tile.enabled) MaterialTheme.colorScheme.primary else QuailTextDim,
                )
                Text(
                    tile.label,
                    color = if (tile.enabled) MaterialTheme.colorScheme.onSurface else QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}
