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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
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
import com.quail.android.data.model.DecisionOption
import com.quail.android.data.model.ProjectItem
import com.quail.android.data.model.ProjectItemType
import com.quail.android.data.model.ProjectSection
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale
import java.util.UUID

private val detailCurrency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectDetailScreen(viewModel: ProjectsViewModel, clientId: String, onBack: () -> Unit) {
    val data by viewModel.uiState.collectAsState()
    val project = data?.projects?.firstOrNull { it.clientId == clientId }
    var addItemSection by remember { mutableStateOf<ProjectSection?>(null) }
    var editingItem by remember { mutableStateOf<Pair<ProjectSection, ProjectItem>?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(project?.name ?: "Project", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
            )
        },
    ) { padding ->
        if (project == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                items(project.sections, key = { it.id }) { section ->
                    SectionCard(
                        section = section,
                        onAddItem = { addItemSection = section },
                        onItemClick = { item -> editingItem = section to item },
                        onDeleteItem = { item ->
                            viewModel.updateSection(project, section.copy(items = section.items.filter { it.id != item.id }))
                        },
                    )
                }
            }
        }
    }

    addItemSection?.let { section ->
        AddItemSheet(
            existing = null,
            onDismiss = { addItemSection = null },
            onSave = { item ->
                project?.let { viewModel.updateSection(it, section.copy(items = section.items + item)) }
            },
        )
    }
    editingItem?.let { (section, item) ->
        AddItemSheet(
            existing = item,
            onDismiss = { editingItem = null },
            onSave = { updated ->
                project?.let { viewModel.updateSection(it, section.copy(items = section.items.map { if (it.id == updated.id) updated else it })) }
            },
        )
    }
}

@Composable
private fun SectionCard(section: ProjectSection, onAddItem: () -> Unit, onItemClick: (ProjectItem) -> Unit, onDeleteItem: (ProjectItem) -> Unit) {
    Column {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(section.title, color = QuailTextDim, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelLarge)
            Surface(onClick = onAddItem, color = Color.Transparent) {
                Text("+ Add Item", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
            }
        }
        if (section.items.isEmpty()) {
            Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                Text("No items yet", color = QuailTextDim, modifier = Modifier.fillMaxWidth().padding(16.dp))
            }
        } else {
            Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                Column {
                    section.items.forEachIndexed { idx, item ->
                        ProjectItemRow(item, onClick = { onItemClick(item) }, onDelete = { onDeleteItem(item) })
                        if (idx < section.items.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                    }
                }
            }
        }
    }
}

@Composable
private fun ProjectItemRow(item: ProjectItem, onClick: () -> Unit, onDelete: () -> Unit) {
    Surface(onClick = onClick, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(item.title.ifBlank { "Untitled" }, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                val subtitle = when (item.type) {
                    "decision" -> "${item.options.size} options" + (item.options.firstOrNull { it.isSelected }?.let { " · chose ${it.title}" } ?: "")
                    "budget" -> "${item.amountLabel.ifBlank { "Amount" }}: ${item.amount?.let { detailCurrency.format(it) } ?: "—"}"
                    "reference" -> item.url.ifBlank { "No URL" }
                    else -> item.body.take(60)
                }
                if (subtitle.isNotBlank()) Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, maxLines = 2)
            }
            Surface(onClick = onDelete, color = Color.Transparent) {
                Icon(Icons.Filled.Close, contentDescription = "Delete", tint = QuailTextDim, modifier = Modifier.padding(4.dp))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddItemSheet(existing: ProjectItem?, onDismiss: () -> Unit, onSave: (ProjectItem) -> Unit) {
    var type by remember { mutableStateOf(existing?.let { ProjectItemType.fromServer(it.type) } ?: ProjectItemType.NOTE) }
    var title by remember { mutableStateOf(existing?.title ?: "") }
    var body by remember { mutableStateOf(existing?.body ?: "") }
    var amount by remember { mutableStateOf(existing?.amount?.toString() ?: "") }
    var amountLabel by remember { mutableStateOf(existing?.amountLabel ?: "Estimated") }
    var url by remember { mutableStateOf(existing?.url ?: "") }
    var options by remember { mutableStateOf(existing?.options ?: emptyList()) }
    var newOption by remember { mutableStateOf("") }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(if (existing == null) "Add Item" else "Edit Item", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
            }

            if (existing == null) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    ProjectItemType.entries.forEach { option ->
                        Surface(
                            onClick = { type = option },
                            color = if (type == option) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                            shape = RoundedCornerShape(999.dp),
                        ) {
                            Text(
                                option.label,
                                color = if (type == option) Color.Black else QuailTextDim,
                                fontWeight = FontWeight.SemiBold,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                            )
                        }
                    }
                }
            }

            OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 12.dp))

            when (type) {
                ProjectItemType.NOTE -> OutlinedTextField(
                    value = body, onValueChange = { body = it }, label = { Text("Notes") },
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                )
                ProjectItemType.BUDGET -> {
                    OutlinedTextField(
                        value = amountLabel, onValueChange = { amountLabel = it }, label = { Text("Label (e.g. Estimated, Actual)") },
                        singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    )
                    OutlinedTextField(
                        value = amount, onValueChange = { amount = it.filter { c -> c.isDigit() || c == '.' } }, label = { Text("Amount") },
                        singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    )
                }
                ProjectItemType.REFERENCE -> OutlinedTextField(
                    value = url, onValueChange = { url = it }, label = { Text("URL") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                )
                ProjectItemType.DECISION -> {
                    Column(modifier = Modifier.padding(top = 12.dp)) {
                        Text("Options", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
                        options.forEach { option ->
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Surface(
                                    onClick = { options = options.map { it.copy(isSelected = it.id == option.id) } },
                                    color = if (option.isSelected) QuailGoodGreen.copy(alpha = 0.15f) else QuailSurfaceRaised,
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.weight(1f),
                                ) {
                                    Text(
                                        option.title,
                                        color = if (option.isSelected) QuailGoodGreen else Color.Unspecified,
                                        fontWeight = if (option.isSelected) FontWeight.Bold else FontWeight.Normal,
                                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                                    )
                                }
                                Surface(onClick = { options = options.filter { it.id != option.id } }, color = Color.Transparent) {
                                    Icon(Icons.Filled.Close, contentDescription = "Remove", tint = QuailTextDim, modifier = Modifier.padding(8.dp))
                                }
                            }
                        }
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(value = newOption, onValueChange = { newOption = it }, label = { Text("Add option...") }, singleLine = true, modifier = Modifier.weight(1f))
                            Surface(
                                onClick = {
                                    if (newOption.isNotBlank()) {
                                        options = options + DecisionOption(id = UUID.randomUUID().toString(), title = newOption.trim())
                                        newOption = ""
                                    }
                                },
                                color = QuailSurfaceRaised,
                                shape = RoundedCornerShape(10.dp),
                            ) { Icon(Icons.Filled.Add, contentDescription = "Add", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(10.dp)) }
                        }
                    }
                }
            }

            Surface(
                onClick = {
                    if (title.isNotBlank()) {
                        onSave(
                            ProjectItem(
                                id = existing?.id ?: UUID.randomUUID().toString(),
                                type = type.serverValue,
                                title = title,
                                body = body,
                                options = options,
                                amount = amount.toDoubleOrNull(),
                                amountLabel = amountLabel,
                                url = url,
                            ),
                        )
                        onDismiss()
                    }
                },
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
