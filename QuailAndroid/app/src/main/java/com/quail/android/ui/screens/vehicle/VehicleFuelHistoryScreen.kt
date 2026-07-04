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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale

private val fuelCurrencyFormat: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VehicleFuelHistoryScreen(viewModel: VehicleViewModel, onBack: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Fuel History", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
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
                val entries = fuelHistoryEntries(state.data.fuelRecords)
                if (entries.isEmpty()) {
                    Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                        Text("No fill-ups logged yet", color = QuailTextDim)
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(padding),
                        contentPadding = PaddingValues(12.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        items(entries) { entry -> FuelHistoryRow(entry) }
                    }
                }
            }
        }
    }
}

@Composable
private fun FuelHistoryRow(entry: FuelHistoryEntry) {
    val record = entry.record
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                Column {
                    Text(record.date, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    Text(
                        if (record.station.isBlank()) "${record.mileage} mi" else "${record.station} · ${record.mileage} mi",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                Text(
                    entry.tankMpg?.let { String.format(Locale.US, "%.1f MPG", it) } ?: "—",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            HorizontalDivider(modifier = Modifier.padding(vertical = 10.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                FuelHistoryStat("Gallons", String.format(Locale.US, "%.3f", record.gallons ?: 0.0))
                FuelHistoryStat("Miles Driven", entry.milesDriven?.toString() ?: "—")
                FuelHistoryStat("Cost", record.totalCost?.let { fuelCurrencyFormat.format(it) } ?: "—")
            }
        }
    }
}

@Composable
private fun FuelHistoryStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
    }
}
