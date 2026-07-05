package com.quail.android.csvimport

import android.net.Uri
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.CsvPreviewResponse
import com.quail.android.data.network.QuailApi
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.launch
import com.quail.android.bugreport.BugReportTopBarAction

private data class AccountOption(val id: Int, val label: String)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CsvAssignScreen(
    api: QuailApi,
    repository: CsvImportRepository,
    uri: Uri,
    fileName: String,
    onDone: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var preview by remember { mutableStateOf<CsvPreviewResponse?>(null) }
    var fileBytes by remember { mutableStateOf<ByteArray?>(null) }
    var headerSignature by remember { mutableStateOf("") }
    var accounts by remember { mutableStateOf<List<AccountOption>>(emptyList()) }
    var selectedAccount by remember { mutableStateOf<AccountOption?>(null) }
    var submitting by remember { mutableStateOf(false) }

    LaunchedEffect(uri) {
        try {
            val bytes = repository.readUriBytes(uri)
            fileBytes = bytes
            val previewResp = repository.fetchPreviewFromBytes(bytes, fileName)
            preview = previewResp
            val signature = csvHeaderSignature(previewResp.columns)
            headerSignature = signature

            val bankInfo = api.getBankInfo()
            val opts = bankInfo.accounts.map { AccountOption(it.accountId, "${it.bank.orEmpty()} - ${it.name.orEmpty()}") } +
                bankInfo.creditCards.map { AccountOption(it.cardId, "${it.bank.orEmpty()} - ${it.name.orEmpty()} (credit)") }
            accounts = opts

            val suggestedId = repository.suggestedAccountId(signature)
            selectedAccount = opts.find { it.id == suggestedId } ?: opts.firstOrNull()
        } catch (e: Exception) {
            error = e.message ?: "Could not read this file"
        } finally {
            loading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Assign CSV", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onDone) { Icon(Icons.Filled.Close, contentDescription = "Cancel") } },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
            Text(fileName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyLarge)
            Box(Modifier.fillMaxWidth().padding(top = 4.dp))

            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) { CircularProgressIndicator() }
                error != null -> {
                    Text(error ?: "Error", color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 16.dp))
                }
                else -> {
                    Text(
                        "Preview",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(top = 16.dp, bottom = 6.dp),
                    )
                    CsvPreviewTable(preview)

                    Text(
                        "Assign to account",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(top = 20.dp, bottom = 6.dp),
                    )
                    AccountDropdown(accounts, selectedAccount, onSelect = { selectedAccount = it })

                    Box(Modifier.fillMaxWidth().padding(top = 24.dp)) {
                        Button(
                            enabled = selectedAccount != null && !submitting && fileBytes != null,
                            onClick = {
                                val account = selectedAccount ?: return@Button
                                val bytes = fileBytes ?: return@Button
                                submitting = true
                                scope.launch {
                                    try {
                                        repository.enqueueBytes(bytes, fileName, account.id, account.label, headerSignature)
                                        repository.rememberAccountForSignature(headerSignature, account.id)
                                    } finally {
                                        submitting = false
                                        onDone()
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(if (submitting) "Assigning…" else "Assign & Queue", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CsvPreviewTable(preview: CsvPreviewResponse?) {
    if (preview == null) return
    Surface(color = QuailSurface, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp).horizontalScroll(rememberScrollState())) {
            Row {
                preview.columns.forEach { col ->
                    Text(
                        col.label,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.width(110.dp).padding(4.dp),
                    )
                }
            }
            preview.previewRows.take(5).forEach { row ->
                Row {
                    row.cells.forEach { cell ->
                        Text(
                            cell,
                            color = QuailTextDim,
                            style = MaterialTheme.typography.labelSmall,
                            maxLines = 1,
                            modifier = Modifier.width(110.dp).padding(4.dp),
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountDropdown(accounts: List<AccountOption>, selected: AccountOption?, onSelect: (AccountOption) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = selected?.label ?: "Select account",
            onValueChange = {},
            readOnly = true,
            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable, enabled = true),
        )
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            accounts.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.label) },
                    onClick = {
                        onSelect(option)
                        expanded = false
                    },
                )
            }
        }
    }
}
