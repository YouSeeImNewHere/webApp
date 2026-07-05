package com.quail.android.csvimport

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
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.ui.theme.QuailWarnYellow
import com.quail.android.bugreport.BugReportTopBarAction

private fun statusLabel(status: String): String = when (status) {
    CsvImportStatus.ASSIGNED -> "Queued"
    CsvImportStatus.PROCESSING -> "Processing"
    CsvImportStatus.IMPORTED -> "Imported"
    CsvImportStatus.NEEDS_REVIEW -> "Needs Review"
    CsvImportStatus.FAILED -> "Failed"
    else -> status
}

private fun statusColor(status: String): Color = when (status) {
    CsvImportStatus.IMPORTED -> QuailGoodGreen
    CsvImportStatus.NEEDS_REVIEW -> QuailWarnYellow
    CsvImportStatus.FAILED -> QuailBadRed
    else -> QuailTextDim
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CsvImportQueueScreen(
    viewModel: CsvImportViewModel,
    onBack: () -> Unit,
    onSetupMapping: (CsvImportQueueEntity) -> Unit,
) {
    val items by viewModel.items.collectAsState()
    val processing by viewModel.processing.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("CSV Import Queue", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Column(Modifier.fillMaxWidth().padding(16.dp)) {
                Button(
                    onClick = { viewModel.processAll() },
                    enabled = processing == null && items.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (processing != null) "Processing…" else "Process All", fontWeight = FontWeight.Bold)
                }
                processing?.let { progress ->
                    Box(Modifier.fillMaxWidth().padding(top = 10.dp)) {
                        Column {
                            LinearProgressIndicator(
                                progress = { if (progress.total > 0) progress.processed / progress.total.toFloat() else 0f },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Text(
                                progress.statusText,
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(top = 6.dp),
                            )
                        }
                    }
                }
            }

            if (items.isEmpty()) {
                Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                    Text(
                        "No CSVs queued. Share a bank export to Quail Cash to assign it to an account.",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(items, key = { it.id }) { item ->
                        CsvQueueRow(
                            item = item,
                            onDelete = { viewModel.deleteItem(item.id) },
                            onSetupMapping = { onSetupMapping(item) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun CsvQueueRow(item: CsvImportQueueEntity, onDelete: () -> Unit, onSetupMapping: () -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(item.originalFileName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    Text(item.accountLabel, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Surface(color = statusColor(item.status), shape = RoundedCornerShape(999.dp)) {
                        Text(
                            statusLabel(item.status),
                            color = Color.Black,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        )
                    }
                    Surface(onClick = onDelete, color = androidx.compose.ui.graphics.Color.Transparent) {
                        Icon(Icons.Filled.Close, contentDescription = "Remove", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
                    }
                }
            }
            if (item.detail.isNotBlank()) {
                Text(item.detail, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 6.dp))
            }
            if (item.status == CsvImportStatus.NEEDS_REVIEW) {
                Surface(
                    onClick = onSetupMapping,
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                ) {
                    Text(
                        "Set up mapping",
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(vertical = 8.dp).fillMaxWidth(),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                }
            }
        }
    }
}
