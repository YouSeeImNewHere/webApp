package com.quail.android.ui.screens.bugs

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.quail.android.bugreport.BugOverlayManager
import com.quail.android.data.model.BugNoteRecord
import com.quail.android.data.model.BugReportRecord
import com.quail.android.data.model.BugStatus
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.ui.theme.QuailWarnYellow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BugsScreen(viewModel: BugsViewModel, onBack: () -> Unit) {
    val data by viewModel.uiState.collectAsState()
    var filter by remember { mutableStateOf<BugStatus?>(null) }
    var showAddReport by remember { mutableStateOf(false) }
    var editingReport by remember { mutableStateOf<BugReportRecord?>(null) }

    val context = LocalContext.current
    var overlayGranted by remember { mutableStateOf(BugOverlayManager.hasPermission(context)) }
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                overlayGranted = BugOverlayManager.hasPermission(context)
                if (overlayGranted) BugOverlayManager.ensureShown(context.applicationContext)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Quail Bugs", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showAddReport = true }) { Icon(Icons.Filled.Add, contentDescription = "Report Bug") }
        },
    ) { padding ->
        if (data == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        } else {
            val current = data!!
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                if (!overlayGranted) {
                    item {
                        Surface(
                            onClick = { BugOverlayManager.requestPermission(context) },
                            color = QuailSurfaceRaised,
                            shape = RoundedCornerShape(16.dp),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Column(Modifier.padding(14.dp)) {
                                Text("Enable the floating bug button", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                                Text(
                                    "Grant \"display over other apps\" so you can report a bug from anywhere, even over a popup. Tap to open settings.",
                                    color = QuailTextDim,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.padding(top = 4.dp),
                                )
                            }
                        }
                    }
                }
                item {
                    Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip("All", filter == null) { filter = null }
                        BugStatus.entries.forEach { status ->
                            FilterChip(status.label, filter == status) { filter = status }
                        }
                    }
                }
                val filtered = current.reports.filter { filter == null || it.status == filter!!.serverValue }
                if (filtered.isEmpty()) {
                    item {
                        Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                            Text("No bug reports", color = QuailTextDim, modifier = Modifier.fillMaxWidth().padding(24.dp))
                        }
                    }
                } else {
                    items(filtered) { report ->
                        BugReportRow(report, onClick = { editingReport = report }, onDelete = { viewModel.deleteReport(report.clientId) })
                    }
                }
                item { QuickNotesSection(current.notes, viewModel) }
            }
        }
    }

    if (showAddReport) {
        BugReportSheet(existing = null, viewModel = viewModel, onDismiss = { showAddReport = false }, onSave = { title, desc -> viewModel.addReport(title, desc) })
    }
    editingReport?.let { report ->
        BugReportSheet(
            existing = report,
            viewModel = viewModel,
            onDismiss = { editingReport = null },
            onSave = { title, desc -> viewModel.updateReport(report, title, desc) },
            onStatusChange = { status -> viewModel.updateReportStatus(report, status) },
        )
    }
}

@Composable
private fun FilterChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(999.dp),
    ) {
        Text(
            label,
            color = if (selected) Color.Black else QuailTextDim,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
        )
    }
}

@Composable
private fun statusColor(status: String): Color = when (status) {
    "in_progress" -> QuailWarnYellow
    "resolved" -> QuailGoodGreen
    else -> QuailBadRed
}

@Composable
private fun BugReportRow(report: BugReportRecord, onClick: () -> Unit, onDelete: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(report.title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                if (report.description.isNotBlank()) {
                    Text(report.description, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, maxLines = 2)
                }
                if (report.hasScreenshot || report.route.isNotBlank()) {
                    Text(
                        listOfNotNull(
                            if (report.hasScreenshot) "Screenshot attached" else null,
                            report.route.takeIf { it.isNotBlank() },
                        ).joinToString("  ·  "),
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                        maxLines = 1,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Surface(color = statusColor(report.status), shape = RoundedCornerShape(999.dp)) {
                    Text(
                        BugStatus.fromServer(report.status).label,
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    )
                }
                Surface(onClick = onDelete, color = Color.Transparent) {
                    Icon(Icons.Filled.Close, contentDescription = "Delete", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
                }
            }
        }
    }
}

@Composable
private fun QuickNotesSection(notes: List<BugNoteRecord>, viewModel: BugsViewModel) {
    var newText by remember { mutableStateOf("") }
    Column {
        Text("Quick Notes", color = QuailTextDim, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 6.dp))
        Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = newText, onValueChange = { newText = it }, label = { Text("Add a note...") }, singleLine = true, modifier = Modifier.weight(1f))
                    Surface(
                        onClick = { if (newText.isNotBlank()) { viewModel.addNote(newText); newText = "" } },
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(10.dp),
                    ) { Icon(Icons.Filled.Add, contentDescription = "Add", tint = Color.Black, modifier = Modifier.padding(10.dp)) }
                }
                notes.forEachIndexed { idx, note ->
                    HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(vertical = 8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Row(modifier = Modifier.weight(1f).padding(end = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            IconButton(onClick = { viewModel.toggleNote(note) }) {
                                Icon(Icons.Filled.Check, contentDescription = "Toggle", tint = if (note.isResolved) QuailGoodGreen else QuailTextDim)
                            }
                            Text(
                                note.text,
                                style = MaterialTheme.typography.bodyMedium,
                                color = if (note.isResolved) QuailTextDim else Color.Unspecified,
                            )
                        }
                        Surface(onClick = { viewModel.deleteNote(note.clientId) }, color = Color.Transparent) {
                            Icon(Icons.Filled.Close, contentDescription = "Delete", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BugReportSheet(
    existing: BugReportRecord?,
    viewModel: BugsViewModel,
    onDismiss: () -> Unit,
    onSave: (String, String) -> Unit,
    onStatusChange: ((BugStatus) -> Unit)? = null,
) {
    var title by remember { mutableStateOf(existing?.title ?: "") }
    var description by remember { mutableStateOf(existing?.description ?: "") }
    var showNetworkLog by remember { mutableStateOf(false) }

    val screenshotBitmap by produceState<android.graphics.Bitmap?>(initialValue = null, key1 = existing?.id) {
        if (existing != null && existing.hasScreenshot && existing.id != 0) {
            val bytes = viewModel.fetchScreenshotBytes(existing.id)
            value = bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(if (existing == null) "Report Bug" else "Edit Bug", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
            }
            OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                label = { Text("Description (optional)") },
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )
            if (existing != null && onStatusChange != null) {
                Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    BugStatus.entries.forEach { status ->
                        val selected = existing.status == status.serverValue
                        Surface(
                            onClick = { onStatusChange(status) },
                            color = if (selected) statusColor(status.serverValue) else QuailSurfaceRaised,
                            shape = RoundedCornerShape(999.dp),
                        ) {
                            Text(
                                status.label,
                                color = if (selected) Color.White else QuailTextDim,
                                fontWeight = FontWeight.SemiBold,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                            )
                        }
                    }
                }
            }
            if (existing != null && screenshotBitmap != null) {
                Text("Screenshot", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 16.dp, bottom = 6.dp))
                Image(
                    bitmap = screenshotBitmap!!.asImageBitmap(),
                    contentDescription = "Bug screenshot",
                    modifier = Modifier.fillMaxWidth().height(220.dp),
                )
            }
            if (existing != null && existing.route.isNotBlank()) {
                Text(
                    "Screen path: ${existing.route}",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
            if (existing != null && existing.networkLog.isNotBlank()) {
                Surface(
                    onClick = { showNetworkLog = !showNetworkLog },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Text(
                            if (showNetworkLog) "Hide recent network calls" else "Show recent network calls",
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.labelMedium,
                        )
                        if (showNetworkLog) {
                            Text(
                                existing.networkLog,
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(top = 8.dp),
                            )
                        }
                    }
                }
            }
            Surface(
                onClick = { if (title.isNotBlank()) { onSave(title, description); onDismiss() } },
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            ) {
                Text(
                    "Save",
                    fontWeight = FontWeight.Bold,
                    color = Color.Black,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
                )
            }
        }
    }
}
