package com.quailcash.android.ui.screens.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quailcash.android.data.model.UnassignedTransaction
import com.quailcash.android.ui.theme.QuailBadRed
import com.quailcash.android.ui.theme.QuailSurfaceRaised
import com.quailcash.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UnassignedWizardSheet(viewModel: UnassignedWizardViewModel, onDismiss: () -> Unit) {
    ModalBottomSheet(
        onDismissRequest = { viewModel.requestClose(onDismiss) },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        val state by viewModel.state.collectAsState()
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Create rule", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Surface(onClick = { viewModel.requestClose(onDismiss) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                    Text("Close", modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp), fontWeight = FontWeight.SemiBold)
                }
            }

            when (val s = state) {
                is UnassignedUiState.Loading -> Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                is UnassignedUiState.Error -> Text(s.message, color = QuailBadRed, modifier = Modifier.padding(top = 20.dp))
                is UnassignedUiState.Ready -> UnassignedWizardBody(s, viewModel)
            }
        }
    }
}

@Composable
private fun UnassignedWizardBody(s: UnassignedUiState.Ready, viewModel: UnassignedWizardViewModel) {
    Row(Modifier.padding(top = 16.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        ModeTab("Most frequent", selected = s.mode == "freq") { viewModel.setMode("freq") }
        ModeTab("Most recent", selected = s.mode == "recent") { viewModel.setMode("recent") }
    }

    val current = s.rows.getOrNull(s.index)

    if (current == null) {
        Text(
            s.statusMessage ?: "No unassigned transactions right now.",
            color = QuailTextDim,
            modifier = Modifier.padding(top = 24.dp, bottom = 24.dp),
        )
        return
    }

    Text("Current transaction", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 20.dp, bottom = 8.dp))
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            KV("Merchant", current.merchant ?: "Unknown")
            KV("Account", listOfNotNull(current.bank, current.card).joinToString(" • ").ifBlank { "—" })
            KV("Amount", currency.format(current.amount))
            KV("Date", current.postedDate ?: "—")
            current.usageCount?.let { KV("Matches", it.toString()) }
        }
    }

    Text("Create rule", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 20.dp, bottom = 8.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text("Defer apply until close", style = MaterialTheme.typography.bodyMedium)
        Switch(checked = s.deferApplyUntilClose, onCheckedChange = { viewModel.setDeferApplyUntilClose(it) })
    }

    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = s.categoryText,
            onValueChange = { viewModel.setCategoryText(it) },
            label = { Text("Category") },
            placeholder = { Text("Start typing…") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        var showCategoryMenu by remember { mutableStateOf(false) }
        Box {
            Surface(onClick = { showCategoryMenu = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp)) {
                Text("Choose", modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp), fontWeight = FontWeight.SemiBold)
            }
            DropdownMenu(expanded = showCategoryMenu, onDismissRequest = { showCategoryMenu = false }) {
                s.categories.forEach { category ->
                    DropdownMenuItem(text = { Text(category) }, onClick = {
                        viewModel.setCategoryText(category)
                        showCategoryMenu = false
                    })
                }
            }
        }
    }

    val merchantKeywordChoices = remember(current.merchant) {
        (current.merchant ?: "")
            .lowercase()
            .split(Regex("[^a-z0-9]+"))
            .map { it.trim() }
            .filter { it.length >= 2 }
            .distinct()
    }

    Text("Keywords (comma separated)", color = QuailTextDim, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp), style = MaterialTheme.typography.labelSmall)
    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = s.keywordsText,
            onValueChange = { viewModel.setKeywordsText(it) },
            placeholder = { Text("amazon, prime") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        if (merchantKeywordChoices.isNotEmpty()) {
            var showKeywordMenu by remember { mutableStateOf(false) }
            Box {
                Surface(onClick = { showKeywordMenu = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp)) {
                    Text("Choose", modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp), fontWeight = FontWeight.SemiBold)
                }
                DropdownMenu(expanded = showKeywordMenu, onDismissRequest = { showKeywordMenu = false }) {
                    merchantKeywordChoices.forEach { word ->
                        DropdownMenuItem(text = { Text(word) }, onClick = {
                            viewModel.appendKeyword(word)
                            showKeywordMenu = false
                        })
                    }
                }
            }
        }
    }

    s.statusMessage?.let {
        Text(it, color = QuailTextDim, modifier = Modifier.padding(top = 10.dp), style = MaterialTheme.typography.labelSmall)
    }

    Column(Modifier.padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            WizardButton("Skip", modifier = Modifier.weight(1f), enabled = !s.saving) { viewModel.skipCurrent() }
            WizardButton("View skipped (${s.skipped.size})", modifier = Modifier.weight(1f), enabled = true) { viewModel.toggleShowSkipped() }
            WizardButton("Save rule", modifier = Modifier.weight(1f), enabled = !s.saving, primary = true) { viewModel.saveRule() }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            WizardButton("Prev", enabled = s.index > 0 && s.rows.isNotEmpty()) { viewModel.move(-1) }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    if (s.rows.isEmpty()) "0 / 0" else "${s.index + 1} / ${s.rows.size}",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                if (s.pendingDeferredRules.isNotEmpty()) {
                    Text("Queued ${s.pendingDeferredRules.size}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            WizardButton("Next", enabled = s.rows.isNotEmpty()) { viewModel.move(1) }
        }

        if (s.showSkipped) {
            if (s.skipped.isEmpty()) {
                Text("No skipped transactions.", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    s.skipped.forEachIndexed { i, tx -> SkippedRow(tx) { viewModel.restoreSkipped(i) } }
                }
            }
        }
    }

    if (s.saving || s.closing) {
        Box(Modifier.fillMaxWidth().padding(top = 12.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
    }
}

@Composable
private fun ModeTab(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(999.dp),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
            fontWeight = FontWeight.SemiBold,
            color = if (selected) androidx.compose.ui.graphics.Color.Black else androidx.compose.ui.graphics.Color.Unspecified,
        )
    }
}

@Composable
private fun KV(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Text(value, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun WizardButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, primary: Boolean = false, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        color = if (primary) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier,
    ) {
        Box(Modifier.padding(horizontal = 12.dp, vertical = 12.dp), contentAlignment = Alignment.Center) {
            Text(
                label,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.labelMedium,
                color = when {
                    !enabled -> QuailTextDim
                    primary -> androidx.compose.ui.graphics.Color.Black
                    else -> androidx.compose.ui.graphics.Color.Unspecified
                },
            )
        }
    }
}

@Composable
private fun SkippedRow(tx: UnassignedTransaction, onUse: () -> Unit) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(tx.merchant ?: "Unknown", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                Text(
                    listOfNotNull(currency.format(tx.amount), tx.postedDate).joinToString(" • "),
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Surface(onClick = onUse, color = MaterialTheme.colorScheme.primary, shape = RoundedCornerShape(999.dp)) {
                Text("Use", modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp), fontWeight = FontWeight.Bold, color = androidx.compose.ui.graphics.Color.Black)
            }
        }
    }
}
