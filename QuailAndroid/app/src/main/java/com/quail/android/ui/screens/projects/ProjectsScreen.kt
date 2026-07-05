package com.quail.android.ui.screens.projects

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Folder
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
import com.quail.android.data.model.ProjectChecklistRecord
import com.quail.android.data.model.ProjectQuickNoteRecord
import com.quail.android.data.model.ProjectRecord
import com.quail.android.data.model.ProjectType
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale

private val projectsCurrency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectsScreen(viewModel: ProjectsViewModel, onOpenProject: (String) -> Unit, onBack: () -> Unit) {
    val data by viewModel.uiState.collectAsState()
    var showNewProject by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Quail Projects", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showNewProject = true }) { Icon(Icons.Filled.Add, contentDescription = "New Project") }
        },
    ) { padding ->
        if (data == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        } else {
            val current = data!!
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                item { QuickNotesSection(current.quickNotes, viewModel) }
                item { ChecklistsSection(current.checklists, viewModel) }
                item {
                    Column {
                        Text("Projects", color = QuailTextDim, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 6.dp))
                        if (current.projects.isEmpty()) {
                            Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                                Column(modifier = Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                                    Icon(Icons.Filled.Folder, contentDescription = null, tint = QuailTextDim)
                                    Text("No projects yet", color = QuailTextDim, modifier = Modifier.padding(top = 6.dp))
                                }
                            }
                        } else {
                            Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                                Column {
                                    current.projects.forEachIndexed { idx, project ->
                                        ProjectRow(project, onClick = { onOpenProject(project.clientId) }, onDelete = { viewModel.deleteProject(project.clientId) })
                                        if (idx < current.projects.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showNewProject) {
        NewProjectSheet(onDismiss = { showNewProject = false }, onCreate = { name, type -> viewModel.createProject(name, type) })
    }
}

@Composable
private fun ProjectRow(project: ProjectRecord, onClick: () -> Unit, onDelete: () -> Unit) {
    Surface(onClick = onClick, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(project.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                val typeLabel = ProjectType.entries.firstOrNull { it.serverValue == project.type }?.label ?: project.type
                Text(
                    if (project.totalBudget > 0) "$typeLabel · ${projectsCurrency.format(project.totalBudget)} budgeted" else typeLabel,
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Surface(onClick = onDelete, color = Color.Transparent) {
                Icon(Icons.Filled.Close, contentDescription = "Delete", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
            }
        }
    }
}

@Composable
private fun QuickNotesSection(notes: List<ProjectQuickNoteRecord>, viewModel: ProjectsViewModel) {
    var newTitle by remember { mutableStateOf("") }
    var newText by remember { mutableStateOf("") }
    Column {
        Text("Quick Notes", color = QuailTextDim, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 6.dp))
        Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                OutlinedTextField(value = newTitle, onValueChange = { newTitle = it }, label = { Text("Title (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = newText, onValueChange = { newText = it }, label = { Text("Note") }, modifier = Modifier.weight(1f))
                    Surface(
                        onClick = { if (newText.isNotBlank()) { viewModel.addQuickNote(newTitle, newText); newTitle = ""; newText = "" } },
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(10.dp),
                    ) { Icon(Icons.Filled.Add, contentDescription = "Add", tint = Color.Black, modifier = Modifier.padding(10.dp)) }
                }
                notes.forEachIndexed { idx, note ->
                    HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(vertical = 8.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column(modifier = Modifier.weight(1f)) {
                            if (note.title.isNotBlank()) Text(note.title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelMedium)
                            Text(note.text, style = MaterialTheme.typography.bodyMedium, maxLines = 3)
                        }
                        Surface(onClick = { viewModel.deleteQuickNote(note.clientId) }, color = Color.Transparent) {
                            Icon(Icons.Filled.Close, contentDescription = "Delete", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ChecklistsSection(checklists: List<ProjectChecklistRecord>, viewModel: ProjectsViewModel) {
    var newTitle by remember { mutableStateOf("") }
    Column {
        Text("Checklists", color = QuailTextDim, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 6.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            checklists.forEach { checklist -> ChecklistCard(checklist, viewModel) }
            Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                Row(modifier = Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = newTitle, onValueChange = { newTitle = it }, label = { Text("New checklist...") }, singleLine = true, modifier = Modifier.weight(1f))
                    Surface(
                        onClick = { if (newTitle.isNotBlank()) { viewModel.addChecklist(newTitle); newTitle = "" } },
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(10.dp),
                    ) { Icon(Icons.Filled.Add, contentDescription = "Add", tint = Color.Black, modifier = Modifier.padding(10.dp)) }
                }
            }
        }
    }
}

@Composable
private fun ChecklistCard(checklist: ProjectChecklistRecord, viewModel: ProjectsViewModel) {
    var newItem by remember { mutableStateOf("") }
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("${checklist.title} (${checklist.completedCount}/${checklist.items.size})", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                Surface(onClick = { viewModel.deleteChecklist(checklist.clientId) }, color = Color.Transparent) {
                    Icon(Icons.Filled.Close, contentDescription = "Delete", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
                }
            }
            checklist.items.forEach { item ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    IconButton(onClick = { viewModel.toggleChecklistItem(checklist, item.id) }) {
                        Icon(Icons.Filled.Check, contentDescription = "Toggle", tint = if (item.isChecked) QuailGoodGreen else QuailTextDim)
                    }
                    Text(item.text, style = MaterialTheme.typography.bodyMedium, color = if (item.isChecked) QuailTextDim else Color.Unspecified)
                }
            }
            Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = newItem, onValueChange = { newItem = it }, label = { Text("Add item...") }, singleLine = true, modifier = Modifier.weight(1f))
                Surface(
                    onClick = { if (newItem.isNotBlank()) { viewModel.addChecklistItem(checklist, newItem); newItem = "" } },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(10.dp),
                ) { Icon(Icons.Filled.Add, contentDescription = "Add", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(10.dp)) }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NewProjectSheet(onDismiss: () -> Unit, onCreate: (String, ProjectType) -> Unit) {
    var name by remember { mutableStateOf("") }
    var type by remember { mutableStateOf(ProjectType.GENERIC) }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text("New Project", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))
            OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Column(modifier = Modifier.padding(top = 12.dp)) {
                Text("Type", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
                ProjectType.entries.forEach { option ->
                    Surface(
                        onClick = { type = option },
                        color = if (type == option) QuailSurfaceRaised else Color.Transparent,
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(option.label, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                    }
                }
            }
            Surface(
                onClick = { if (name.isNotBlank()) { onCreate(name, type); onDismiss() } },
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            ) {
                Text(
                    "Create",
                    fontWeight = FontWeight.Bold,
                    color = Color.Black,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
                )
            }
        }
    }
}
