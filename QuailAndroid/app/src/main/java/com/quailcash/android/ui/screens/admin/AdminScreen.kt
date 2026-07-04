package com.quailcash.android.ui.screens.admin

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quailcash.android.data.model.HomelabMetrics
import com.quailcash.android.ui.theme.QuailBadRed
import com.quailcash.android.ui.theme.QuailSurface
import com.quailcash.android.ui.theme.QuailTextDim

/** "Quail Admin" — the Admin dashboard tile's destination. Currently just
 * shows live homelab server metrics (CPU/RAM/disk/network/temp), pulled from
 * the backend's /admin/homelab-metrics endpoint, which itself proxies the
 * homelab server's local Netdata instance. More admin views can land here
 * over time (tenants, error feed, etc. — mirrors the web admin console). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdminScreen(viewModel: AdminViewModel, onBack: () -> Unit) {
    val homelabMetrics by viewModel.homelabMetrics.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Quail Admin", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                actions = {
                    IconButton(onClick = { viewModel.loadHomelabMetrics() }) {
                        Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                    }
                },
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
                AdminSection("Homelab Server") {
                    HomelabMetricsBody(homelabMetrics)
                }
            }
        }
    }
}

@Composable
private fun AdminSection(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            title.uppercase(),
            color = QuailTextDim,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(start = 4.dp),
        )
        Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) { content() }
        }
    }
}

@Composable
private fun HomelabMetricsBody(metrics: HomelabMetrics?) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        when {
            metrics == null -> Text("Loading...", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            metrics.error != null -> Text(
                "Unavailable: ${metrics.error}",
                color = QuailBadRed,
                style = MaterialTheme.typography.labelSmall,
            )
            else -> {
                metrics.cpuUsedPercent?.let {
                    MetricRow("CPU", "${"%.1f".format(it)}%")
                }
                metrics.ram?.let {
                    MetricRow(
                        "RAM",
                        "${it.usedMB?.toInt()} / ${it.totalMB?.toInt()} MB (${it.usedPercent?.let { p -> "%.1f".format(p) } ?: "-"}%)",
                    )
                }
                metrics.diskRoot?.let {
                    MetricRow(
                        "Disk (/)",
                        "${it.usedGB?.toInt()} / ${it.totalGB?.toInt()} GB (${it.usedPercent?.let { p -> "%.1f".format(p) } ?: "-"}%)",
                    )
                }
                metrics.network?.let {
                    MetricRow("Network", "in ${it.inKbps ?: "-"} / out ${it.outKbps ?: "-"} ${it.units ?: ""}")
                }
                metrics.temperatures?.forEach {
                    MetricRow("Temp (${it.label})", "${it.celsius}°C")
                }
            }
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.bodyMedium)
        Text(value, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
    }
}
