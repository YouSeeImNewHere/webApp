package com.quail.android.csvimport

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.CsvMappingPreset
import com.quail.android.data.model.CsvMappingPresetUpsertRequest
import com.quail.android.data.model.CsvPreviewColumn
import com.quail.android.data.model.CsvPreviewResponse
import com.quail.android.data.network.QuailApi
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.launch

private enum class AmountMode { SINGLE, DEBIT_CREDIT }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CsvMappingSetupScreen(
    api: QuailApi,
    repository: CsvImportRepository,
    item: CsvImportQueueEntity,
    onBack: () -> Unit,
    onSaved: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var preview by remember { mutableStateOf<CsvPreviewResponse?>(null) }
    var saving by remember { mutableStateOf(false) }

    var purchaseCol by remember { mutableStateOf<Int?>(null) }
    var merchantCol by remember { mutableStateOf<Int?>(null) }
    var amountMode by remember { mutableStateOf(AmountMode.SINGLE) }
    var amountCol by remember { mutableStateOf<Int?>(null) }
    var debitCol by remember { mutableStateOf<Int?>(null) }
    var creditCol by remember { mutableStateOf<Int?>(null) }
    var postedCol by remember { mutableStateOf<Int?>(null) }
    var categoryCol by remember { mutableStateOf<Int?>(null) }
    var invertAmount by remember { mutableStateOf(false) }

    LaunchedEffect(item.id) {
        try {
            val file = repository.storedFile(item)
            preview = repository.fetchPreviewFromFile(file)
        } catch (e: Exception) {
            error = e.message ?: "Could not read this file"
        } finally {
            loading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Map Columns", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
            )
        },
    ) { padding ->
        when {
            loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            error != null -> Box(Modifier.fillMaxSize().padding(padding).padding(16.dp)) { Text(error ?: "Error", color = MaterialTheme.colorScheme.error) }
            else -> {
                val columns = preview?.columns.orEmpty()
                Column(Modifier.fillMaxSize().padding(padding).padding(16.dp).verticalScroll(rememberScrollState())) {
                    Text(item.originalFileName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyLarge)
                    Text(item.accountLabel, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 12.dp))

                    Surface(color = QuailSurface, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(10.dp).horizontalScroll(rememberScrollState())) {
                            Row {
                                columns.forEach { col ->
                                    Text(col.label, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.width(110.dp).padding(4.dp))
                                }
                            }
                            preview?.previewRows?.take(3)?.forEach { row ->
                                Row {
                                    row.cells.forEach { cell ->
                                        Text(cell, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, maxLines = 1, modifier = Modifier.width(110.dp).padding(4.dp))
                                    }
                                }
                            }
                        }
                    }

                    ColumnPickerRow("Transaction date (required)", columns, purchaseCol) { purchaseCol = it }
                    ColumnPickerRow("Merchant (required)", columns, merchantCol) { merchantCol = it }
                    ColumnPickerRow("Posted date (optional)", columns, postedCol, allowNone = true) { postedCol = it }
                    ColumnPickerRow("Category (optional)", columns, categoryCol, allowNone = true) { categoryCol = it }

                    Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Use separate debit/credit columns", modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                        Switch(
                            checked = amountMode == AmountMode.DEBIT_CREDIT,
                            onCheckedChange = { amountMode = if (it) AmountMode.DEBIT_CREDIT else AmountMode.SINGLE },
                        )
                    }

                    if (amountMode == AmountMode.SINGLE) {
                        ColumnPickerRow("Amount (required)", columns, amountCol) { amountCol = it }
                    } else {
                        ColumnPickerRow("Debit column (required)", columns, debitCol) { debitCol = it }
                        ColumnPickerRow("Credit column (required)", columns, creditCol) { creditCol = it }
                    }

                    Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Flip amount sign", modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                        Switch(checked = invertAmount, onCheckedChange = { invertAmount = it })
                    }

                    val canSave = purchaseCol != null && merchantCol != null &&
                        (if (amountMode == AmountMode.SINGLE) amountCol != null else (debitCol != null && creditCol != null))

                    Button(
                        enabled = canSave && !saving,
                        onClick = {
                            saving = true
                            scope.launch {
                                try {
                                    val preset = CsvMappingPreset(
                                        purchaseCol = purchaseCol,
                                        postedCol = postedCol,
                                        amountCol = if (amountMode == AmountMode.SINGLE) amountCol else null,
                                        debitCol = if (amountMode == AmountMode.DEBIT_CREDIT) debitCol else null,
                                        creditCol = if (amountMode == AmountMode.DEBIT_CREDIT) creditCol else null,
                                        merchantCol = merchantCol,
                                        categoryCol = categoryCol,
                                        creditIndicatorValue = "credit",
                                        invertAmount = invertAmount,
                                        headerSignature = csvHeaderSignature(columns),
                                    )
                                    api.saveCsvMappingPreset(
                                        CsvMappingPresetUpsertRequest(accountId = item.accountId, preset = preset),
                                    )
                                    repository.updateStatus(item.id, CsvImportStatus.ASSIGNED, "Mapping saved. Ready for batch processing.")
                                } finally {
                                    saving = false
                                    onSaved()
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 24.dp),
                    ) {
                        Text(if (saving) "Saving…" else "Save Mapping", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ColumnPickerRow(
    label: String,
    columns: List<CsvPreviewColumn>,
    selected: Int?,
    allowNone: Boolean = false,
    onSelect: (Int?) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedLabel = columns.find { it.index == selected }?.let { "Column ${it.index + 1}: ${it.label}" } ?: "Not set"

    Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 4.dp))
        ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
            OutlinedTextField(
                value = selectedLabel,
                onValueChange = {},
                readOnly = true,
                modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable, enabled = true),
            )
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                if (allowNone) {
                    DropdownMenuItem(text = { Text("Not set") }, onClick = { onSelect(null); expanded = false })
                }
                columns.forEach { col ->
                    DropdownMenuItem(
                        text = { Text("Column ${col.index + 1}: ${col.label}") },
                        onClick = { onSelect(col.index); expanded = false },
                    )
                }
            }
        }
    }
}
