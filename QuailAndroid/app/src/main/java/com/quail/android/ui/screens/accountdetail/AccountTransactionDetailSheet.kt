package com.quail.android.ui.screens.accountdetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
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
import com.quail.android.data.model.TransactionDetail
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.overlay.InlineConfirmCard
import com.quail.android.ui.theme.CategoryPickerField
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.abs

private val detailCurrency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

/** Mirrors HomePopups.kt's TransactionDetailSheetContent/TransactionDetailBody
 * so accounts get the same "tap a transaction" popup as the home page's
 * transaction list — view/edit category, status, date, invert amount,
 * ignore, finance, or delete (needed for cleaning up mistakes while
 * auditing). Self-contained here since AccountDetailViewModel isn't the same
 * instance as HomeViewModel. */
@Composable
fun AccountTransactionDetailSheet(id: String, viewModel: AccountDetailViewModel, onDismiss: () -> Unit) {
    val state by viewModel.txDetailState.collectAsState()

    LaunchedEffect(id) { viewModel.loadTransactionDetail(id) }
    LaunchedEffect(state) {
        if (state is AccountTxDetailUiState.Deleted) {
            viewModel.clearTransactionDetail()
            onDismiss()
        }
    }

    val dismiss: () -> Unit = { viewModel.clearTransactionDetail(); onDismiss() }
    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            when (val s = state) {
                is AccountTxDetailUiState.Idle, is AccountTxDetailUiState.Loading -> {
                    Text("Transaction", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))
                    Box(Modifier.fillMaxWidth().padding(vertical = 32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                }
                is AccountTxDetailUiState.Error -> {
                    Text("Transaction", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))
                    Text(s.message, color = QuailBadRed, modifier = Modifier.padding(top = 16.dp, bottom = 24.dp))
                }
                is AccountTxDetailUiState.Deleted -> {}
                is AccountTxDetailUiState.Success -> {
                    val categories by viewModel.categories.collectAsState()
                    AccountTransactionDetailBody(id, s.detail, s.actionInFlight, categories, viewModel, dismiss)
                }
            }
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = dismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@Composable
private fun AccountTransactionDetailBody(
    id: String,
    tx: TransactionDetail,
    actionInFlight: Boolean,
    categories: List<String>,
    viewModel: AccountDetailViewModel,
    onDismiss: () -> Unit,
) {
    var categoryText by remember(tx.id, tx.category) { mutableStateOf(tx.category ?: "") }
    var editingMeta by remember { mutableStateOf(false) }
    var statusText by remember(tx.id) { mutableStateOf(tx.status ?: "") }
    var postedDateText by remember(tx.id) { mutableStateOf(tx.postedDate ?: "") }
    var financing by remember { mutableStateOf(false) }
    var financeLabel by remember(tx.id) { mutableStateOf(tx.merchant ?: "") }
    var financeMonths by remember { mutableStateOf("6") }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(tx.merchant ?: "Transaction", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                if (tx.financingPlanId != null) {
                    Surface(color = MaterialTheme.colorScheme.primary.copy(alpha = 0.18f), shape = RoundedCornerShape(999.dp)) {
                        Text(
                            "Financed",
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        )
                    }
                }
            }
            Text(
                listOfNotNull(detailCurrency.format(tx.amount), tx.bank, tx.card).joinToString(" • "),
                color = QuailTextDim,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
    }

    HorizontalDivider(modifier = Modifier.padding(vertical = 14.dp))

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        DetailLabeledRow("merchant", tx.merchant ?: "—")
        DetailLabeledRow("amount", detailCurrency.format(tx.amount), valueColor = if (tx.amount >= 0) QuailBadRed else QuailGoodGreen)
        DetailLabeledRow("status", tx.status ?: "—")
        DetailLabeledRow("purchase date", tx.purchaseDate ?: "—")
        DetailLabeledRow("posted date", tx.postedDate ?: "—")
        DetailLabeledRow("bank", tx.bank ?: "—")
        DetailLabeledRow("card", tx.card ?: "—")
        DetailLabeledRow("account type", tx.accountType ?: "—")
    }

    Text("category", color = QuailTextDim, modifier = Modifier.padding(top = 18.dp, bottom = 6.dp))
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CategoryPickerField(value = categoryText, onValueChange = { categoryText = it }, categories = categories, modifier = Modifier.weight(1f))
        Surface(
            onClick = { viewModel.setTransactionCategory(id, categoryText.trim()) },
            enabled = !actionInFlight,
            color = MaterialTheme.colorScheme.primary,
            shape = RoundedCornerShape(10.dp),
        ) {
            Text("Save", modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp), fontWeight = FontWeight.Bold, color = Color.Black)
        }
    }

    Text("details", color = QuailTextDim, modifier = Modifier.padding(top = 18.dp, bottom = 6.dp))
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        DetailKV("id", tx.id)
        DetailKV("account id", tx.accountId?.toString() ?: "—")
        DetailKV("category rule id", tx.categoryRuleId?.toString() ?: "—")
        DetailKV("category rule pattern", tx.categoryRulePattern ?: "—")
        DetailKV("is ignored", tx.isIgnored.toString())
    }

    Row(modifier = Modifier.padding(top = 20.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        DetailActionPill("Edit status/date", enabled = !actionInFlight) { editingMeta = !editingMeta }
        DetailActionPill("Invert amount", enabled = !actionInFlight) { viewModel.invertTransactionAmount(id) }
        DetailActionPill(if (tx.isIgnored) "Unignore" else "Ignore", enabled = !actionInFlight) {
            viewModel.setTransactionIgnored(id, !tx.isIgnored)
        }
        DetailActionPill("Delete", enabled = !actionInFlight, destructive = true) { showDeleteConfirm = true }
    }
    Row(modifier = Modifier.padding(top = 8.dp)) {
        if (tx.financingPlanId == null) {
            DetailActionPill("Finance this purchase", enabled = !actionInFlight) { financing = !financing }
        } else {
            DetailActionPill("Already financed", enabled = false) {}
        }
    }

    if (editingMeta) {
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = statusText,
                onValueChange = { statusText = it },
                label = { Text("Status (pending/posted)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = postedDateText,
                onValueChange = { postedDateText = it },
                label = { Text("Posted date (MM/DD/YYYY)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Surface(
                onClick = {
                    viewModel.updateTransactionMeta(id, statusText.ifBlank { null }, postedDateText.ifBlank { null })
                    editingMeta = false
                },
                enabled = !actionInFlight,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    Text("Save status/date", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }

    if (financing) {
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = financeLabel,
                onValueChange = { financeLabel = it },
                label = { Text("Plan label") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = financeMonths,
                onValueChange = { financeMonths = it.filter { c -> c.isDigit() } },
                label = { Text("Months") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Surface(
                onClick = {
                    val months = financeMonths.toIntOrNull() ?: 0
                    if (months > 0 && financeLabel.isNotBlank()) {
                        viewModel.createFinancingPlan(id, financeLabel.trim(), abs(tx.amount), months)
                        financing = false
                    }
                },
                enabled = !actionInFlight,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    Text("Create financing plan", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }

    if (actionInFlight) {
        Box(Modifier.fillMaxWidth().padding(top = 12.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(modifier = Modifier.size(20.dp))
        }
    }

    if (showDeleteConfirm) {
        InlineConfirmCard(
            title = "Delete transaction?",
            text = "This can't be undone.",
            confirmLabel = "Delete",
            confirmColor = QuailBadRed,
            onConfirm = {
                showDeleteConfirm = false
                viewModel.deleteTransactionDetail(id)
            },
            onCancel = { showDeleteConfirm = false },
        )
    }
}

@Composable
private fun DetailLabeledRow(label: String, value: String, valueColor: Color = Color.Unspecified) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = QuailTextDim)
        Text(value, fontWeight = FontWeight.SemiBold, color = valueColor)
    }
}

@Composable
private fun DetailKV(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("$label:", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Text(value, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun DetailActionPill(label: String, enabled: Boolean = true, destructive: Boolean = false, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        color = if (destructive) QuailBadRed.copy(alpha = 0.16f) else QuailSurfaceRaised,
        shape = RoundedCornerShape(999.dp),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = if (destructive) QuailBadRed else if (enabled) Color.Unspecified else QuailTextDim,
        )
    }
}
