package com.quail.android.ui.screens.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
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
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.overlay.InlineConfirmCard
import com.quail.android.ui.theme.CategoryPickerField
import com.quail.android.data.model.BankAccount
import com.quail.android.data.model.ExtraSavedDay
import com.quail.android.data.model.IncomeBasisPaycheck
import com.quail.android.data.model.MonthBudget
import com.quail.android.data.model.SpentSoFarCategory
import com.quail.android.data.model.SpentSoFarTransaction
import com.quail.android.data.model.TransactionDetail
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.Locale
import kotlin.math.abs

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

private fun LocalDate.toUtcMillis(): Long = atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
private fun Long.toLocalDateUtc(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate()

sealed interface HomeSheet {
    data class Income(val budget: MonthBudget) : HomeSheet
    data object ExtraSaved : HomeSheet
    data object SpentSoFar : HomeSheet
    data class VerifyBalance(val accountId: Int, val accountName: String) : HomeSheet
    data class TransactionDetail(val id: String) : HomeSheet
    data object BankInfo : HomeSheet
    data class AccountAudit(val account: BankAccount) : HomeSheet
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeSheetHost(sheet: HomeSheet, viewModel: HomeViewModel, onDismiss: () -> Unit) {
    val content: @Composable () -> Unit = {
        when (sheet) {
            is HomeSheet.Income -> IncomeSheetContent(sheet.budget)
            is HomeSheet.ExtraSaved -> ExtraSavedSheetContent(viewModel)
            is HomeSheet.SpentSoFar -> SpentSoFarSheetContent(viewModel)
            is HomeSheet.VerifyBalance -> VerifyBalanceSheetContent(sheet, viewModel, onDismiss)
            is HomeSheet.TransactionDetail -> TransactionDetailSheetContent(sheet.id, viewModel, onDismiss)
            is HomeSheet.BankInfo -> BankInfoSheetContent(viewModel)
            is HomeSheet.AccountAudit -> AccountAuditSheetContent(sheet.account)
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@Composable
private fun SheetTitle(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(bottom = 12.dp),
    )
}

@Composable
private fun LabeledRow(label: String, value: String, valueColor: Color = Color.Unspecified) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = QuailTextDim)
        Text(value, fontWeight = FontWeight.SemiBold, color = valueColor)
    }
}

@Composable
private fun SheetLoading() {
    Box(Modifier.fillMaxWidth().padding(vertical = 32.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun SheetError(message: String) {
    Text(message, color = QuailBadRed, modifier = Modifier.padding(top = 16.dp, bottom = 24.dp))
}

@Composable
private fun ActionPill(label: String, enabled: Boolean = true, destructive: Boolean = false, onClick: () -> Unit) {
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

// ---- Income ----

@Composable
private fun IncomeSheetContent(budget: MonthBudget) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        SheetTitle("Income")
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            LabeledRow("Expected this month", currency.format(budget.expectedIncome))
            LabeledRow("Base income", currency.format(budget.baseIncome))
            LabeledRow("Paycheck basis total", currency.format(budget.incomeBasisTotal))
            budget.incomeBasisMonth?.label?.let { LabeledRow("Basis month", it) }
        }
        if (budget.incomeBasisPaychecks.isNotEmpty()) {
            HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))
            Text("Paychecks counted", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                budget.incomeBasisPaychecks.forEach { paycheck -> PaycheckRow(paycheck) }
            }
        }
    }
}

@Composable
private fun PaycheckRow(paycheck: IncomeBasisPaycheck) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(paycheck.merchant ?: "Paycheck", fontWeight = FontWeight.SemiBold)
                paycheck.date?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall) }
            }
            Text(currency.format(paycheck.amount), fontWeight = FontWeight.Bold, color = QuailGoodGreen)
        }
    }
}

// ---- Extra saved ----

@Composable
private fun ExtraSavedSheetContent(viewModel: HomeViewModel) {
    val state by viewModel.extraSavedState.collectAsState()
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        SheetTitle("Extra saved")
        when (val s = state) {
            is ExtraSavedUiState.Idle, is ExtraSavedUiState.Loading -> SheetLoading()
            is ExtraSavedUiState.Error -> SheetError(s.message)
            is ExtraSavedUiState.Success -> {
                val detail = s.detail
                Text(
                    currency.format(detail.totalExtraSaved),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (detail.totalExtraSaved >= 0) QuailGoodGreen else QuailBadRed,
                )
                Text("Total this month", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Column(Modifier.padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    detail.days.sortedByDescending { it.day }.forEach { day -> ExtraSavedDayRow(day) }
                }
            }
        }
    }
}

@Composable
private fun ExtraSavedDayRow(day: ExtraSavedDay) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(day.day, fontWeight = FontWeight.SemiBold)
                Text("baseline ${currency.format(day.baseline)}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            Text(
                currency.format(day.appliedToExtraSaved),
                fontWeight = FontWeight.Bold,
                color = if (day.appliedToExtraSaved >= 0) QuailGoodGreen else QuailBadRed,
            )
        }
    }
}

// ---- Spent so far ----

@Composable
private fun SpentSoFarSheetContent(viewModel: HomeViewModel) {
    val state by viewModel.spentSoFarState.collectAsState()
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        SheetTitle("Spent so far")
        when (val s = state) {
            is SpentSoFarUiState.Idle, is SpentSoFarUiState.Loading -> SheetLoading()
            is SpentSoFarUiState.Error -> SheetError(s.message)
            is SpentSoFarUiState.Success -> {
                val breakdown = s.breakdown
                Text(
                    currency.format(breakdown.total),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text("Free spend this month", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)

                if (breakdown.included.isNotEmpty()) {
                    Text(
                        "Included categories",
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(top = 20.dp, bottom = 8.dp),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        breakdown.included.sortedByDescending { it.total }.forEach { cat ->
                            SpentSoFarCategoryRow(
                                cat = cat,
                                expanded = s.expandedCategory == cat.category,
                                loading = s.categoryLoading == cat.category,
                                transactions = s.categoryTransactions[cat.category],
                                onClick = { viewModel.toggleSpentSoFarCategory(cat.category) },
                            )
                        }
                    }
                }

                if (breakdown.excluded.isNotEmpty()) {
                    Text(
                        "Excluded categories",
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(top = 20.dp, bottom = 8.dp),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        breakdown.excluded.sortedByDescending { it.total }.forEach { cat ->
                            Surface(color = QuailSurfaceRaised.copy(alpha = 0.6f), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                                Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text(cat.category, color = QuailTextDim)
                                    Text(currency.format(cat.total), color = QuailTextDim, fontWeight = FontWeight.SemiBold)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SpentSoFarCategoryRow(
    cat: SpentSoFarCategory,
    expanded: Boolean,
    loading: Boolean,
    transactions: List<SpentSoFarTransaction>?,
    onClick: () -> Unit,
) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(cat.category, fontWeight = FontWeight.SemiBold)
                Text(currency.format(cat.total), fontWeight = FontWeight.Bold)
            }
            if (expanded) {
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (loading) {
                        SheetLoading()
                    } else if (transactions.isNullOrEmpty()) {
                        Text("No transactions found.", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                    } else {
                        transactions.forEach { tx ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Column {
                                    Text(tx.merchant ?: "Transaction", style = MaterialTheme.typography.bodyMedium)
                                    tx.date?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall) }
                                }
                                Text(currency.format(tx.amount), fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                }
            }
        }
    }
}

// ---- Verify balance ----

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun VerifyBalanceSheetContent(sheet: HomeSheet.VerifyBalance, viewModel: HomeViewModel, onDismiss: () -> Unit) {
    val state by viewModel.verifyBalanceState.collectAsState()
    var selectedDate by remember { mutableStateOf(LocalDate.now().minusDays(1)) }
    var showDatePicker by remember { mutableStateOf(false) }

    LaunchedEffect(state) {
        if (state is VerifyBalanceUiState.Success) onDismiss()
    }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        SheetTitle("Verify balance")
        Text(sheet.accountName, color = QuailTextDim, modifier = Modifier.padding(bottom = 16.dp))
        Surface(
            onClick = { showDatePicker = true },
            color = QuailSurfaceRaised,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Verified as of", color = QuailTextDim)
                Text(selectedDate.toString(), fontWeight = FontWeight.SemiBold)
            }
        }
        if (state is VerifyBalanceUiState.Error) {
            SheetError((state as VerifyBalanceUiState.Error).message)
        }
        Surface(
            onClick = { viewModel.verifyBalance(sheet.accountId, selectedDate.toString()) },
            color = MaterialTheme.colorScheme.primary,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
        ) {
            Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                if (state is VerifyBalanceUiState.Loading) {
                    CircularProgressIndicator(modifier = Modifier.padding(2.dp))
                } else {
                    Text("Confirm", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }

    if (showDatePicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = selectedDate.toUtcMillis())
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { selectedDate = it.toLocalDateUtc() }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } },
        ) {
            DatePicker(state = pickerState)
        }
    }
}

// ---- Transaction detail ----

@Composable
private fun TransactionDetailSheetContent(id: String, viewModel: HomeViewModel, onDismiss: () -> Unit) {
    val state by viewModel.transactionDetailState.collectAsState()

    LaunchedEffect(state) {
        if (state is TransactionDetailUiState.Deleted) onDismiss()
    }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        when (val s = state) {
            is TransactionDetailUiState.Idle, is TransactionDetailUiState.Loading -> {
                SheetTitle("Transaction")
                SheetLoading()
            }
            is TransactionDetailUiState.Error -> {
                SheetTitle("Transaction")
                SheetError(s.message)
            }
            is TransactionDetailUiState.Deleted -> {}
            is TransactionDetailUiState.Success -> {
                val categories by viewModel.categories.collectAsState()
                TransactionDetailBody(id, s.detail, s.actionInFlight, categories, viewModel, onDismiss)
            }
        }
    }
}

@Composable
private fun TransactionDetailBody(
    id: String,
    tx: TransactionDetail,
    actionInFlight: Boolean,
    categories: List<String>,
    viewModel: HomeViewModel,
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
            Text(tx.merchant ?: "Transaction", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(
                listOfNotNull(currency.format(tx.amount), tx.bank, tx.card).joinToString(" • "),
                color = QuailTextDim,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        IconButton(onClick = onDismiss) {
            Icon(Icons.Filled.Close, contentDescription = "Close")
        }
    }

    HorizontalDivider(modifier = Modifier.padding(vertical = 14.dp))

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        LabeledRow("merchant", tx.merchant ?: "—")
        LabeledRow("amount", currency.format(tx.amount), valueColor = if (tx.amount >= 0) QuailBadRed else QuailGoodGreen)
        LabeledRow("status", tx.status ?: "—")
        LabeledRow("purchase date", tx.purchaseDate ?: "—")
        LabeledRow("posted date", tx.postedDate ?: "—")
        LabeledRow("bank", tx.bank ?: "—")
        LabeledRow("card", tx.card ?: "—")
        LabeledRow("account type", tx.accountType ?: "—")
    }

    Text("category", color = QuailTextDim, modifier = Modifier.padding(top = 18.dp, bottom = 6.dp))
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CategoryPickerField(
            value = categoryText,
            onValueChange = { categoryText = it },
            categories = categories,
            modifier = Modifier.weight(1f),
        )
        Surface(
            onClick = { viewModel.setTransactionCategory(id, categoryText.trim()) },
            enabled = !actionInFlight,
            color = MaterialTheme.colorScheme.primary,
            shape = RoundedCornerShape(10.dp),
        ) {
            Text(
                "Save",
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp),
                fontWeight = FontWeight.Bold,
                color = Color.Black,
            )
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

    Row(
        modifier = Modifier.padding(top = 20.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ActionPill("Edit status/date", enabled = !actionInFlight) { editingMeta = !editingMeta }
        ActionPill("Invert amount", enabled = !actionInFlight) { viewModel.invertTransactionAmount(id) }
        ActionPill(if (tx.isIgnored) "Unignore" else "Ignore", enabled = !actionInFlight) {
            viewModel.setTransactionIgnored(id, !tx.isIgnored)
        }
        ActionPill("Delete", enabled = !actionInFlight, destructive = true) { showDeleteConfirm = true }
    }
    Row(modifier = Modifier.padding(top = 8.dp)) {
        ActionPill("Finance this purchase", enabled = !actionInFlight) { financing = !financing }
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
                viewModel.deleteTransaction(id)
            },
            onCancel = { showDeleteConfirm = false },
        )
    }
}

@Composable
private fun DetailKV(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("$label:", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Text(value, style = MaterialTheme.typography.labelSmall)
    }
}

// ---- Bank info ----

@Composable
private fun BankInfoSheetContent(viewModel: HomeViewModel) {
    val state by viewModel.bankInfoState.collectAsState()
    LaunchedEffect(Unit) { viewModel.loadBankInfo() }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        SheetTitle("Bank info")
        when (val s = state) {
            is BankInfoUiState.Idle, is BankInfoUiState.Loading -> SheetLoading()
            is BankInfoUiState.Error -> SheetError(s.message)
            is BankInfoUiState.Success -> BankInfoBody(s, viewModel)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BankInfoBody(state: BankInfoUiState.Success, viewModel: HomeViewModel) {
    val info = state.info
    val choices = remember(info) {
        info.accounts.map { it.accountId to "${it.bank.orEmpty()} — ${it.name.orEmpty()} (APY)" } +
            info.creditCards.map { it.cardId to "${it.bank.orEmpty()} — ${it.name.orEmpty()} (APR)" }
    }
    var selectedId by remember(choices) { mutableStateOf(choices.firstOrNull()?.first ?: 0) }
    var ratePercent by remember { mutableStateOf("") }
    var effectiveDate by remember { mutableStateOf(LocalDate.now()) }
    var showDatePicker by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }

    Text("Set a new rate", fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 10.dp))

    BankInfoDropdown(
        label = "Account",
        value = selectedId,
        options = choices,
        onSelect = { selectedId = it },
    )
    OutlinedTextField(
        value = ratePercent,
        onValueChange = { ratePercent = it },
        label = { Text("Rate (%) e.g. 3.54") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
    )
    Surface(
        onClick = { showDatePicker = true },
        color = QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Effective date", color = QuailTextDim)
            Text(effectiveDate.toString(), fontWeight = FontWeight.SemiBold)
        }
    }
    OutlinedTextField(
        value = note,
        onValueChange = { note = it },
        label = { Text("Note (optional)") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
    )

    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 14.dp)) {
        Surface(
            onClick = {
                val rate = ratePercent.toDoubleOrNull()
                if (selectedId != 0 && rate != null) {
                    viewModel.saveInterestRate(selectedId, rate, effectiveDate.toString(), note.ifBlank { null })
                }
            },
            color = MaterialTheme.colorScheme.primary,
            shape = RoundedCornerShape(12.dp),
        ) {
            Box(Modifier.padding(horizontal = 20.dp, vertical = 12.dp), contentAlignment = Alignment.Center) {
                if (state.isSaving) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp))
                } else {
                    Text("Save rate", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
        state.saveMessage?.let {
            Text(it, color = QuailTextDim, modifier = Modifier.padding(start = 12.dp), style = MaterialTheme.typography.labelSmall)
        }
    }

    if (info.accounts.isNotEmpty()) {
        HorizontalDivider(modifier = Modifier.padding(vertical = 18.dp))
        Text("Accounts", fontWeight = FontWeight.Bold)
        Text("Savings & checking", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 10.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            info.accounts.forEach { account ->
                Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        LabeledRow("${account.bank.orEmpty()} — ${account.name.orEmpty()}", account.apy?.let { "%.2f%%".format(it) } ?: "—")
                        LabeledRow("Type", account.type?.uppercase() ?: "—")
                        account.notes?.takeIf { it.isNotBlank() }?.let { LabeledRow("Notes", it) }
                    }
                }
            }
        }
    }

    if (info.creditCards.isNotEmpty()) {
        HorizontalDivider(modifier = Modifier.padding(vertical = 18.dp))
        Text("Credit cards", fontWeight = FontWeight.Bold)
        Text("APR, limits & rewards", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 10.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            info.creditCards.forEach { card ->
                Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        LabeledRow("${card.bank.orEmpty()} — ${card.name.orEmpty()}", card.apr?.let { "%.2f%%".format(it) } ?: "—")
                        card.creditLimit?.let { LabeledRow("Limit", currency.format(it)) }
                        card.benefits.forEach { benefit ->
                            LabeledRow(
                                benefit.categories.joinToString(", ").ifBlank { "Cash back" },
                                "%.2f%%".format(benefit.cashbackPercent),
                            )
                        }
                    }
                }
            }
        }
    }

    if (showDatePicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = effectiveDate.toUtcMillis())
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { effectiveDate = it.toLocalDateUtc() }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } },
        ) {
            DatePicker(state = pickerState)
        }
    }
}

@Composable
private fun BankInfoDropdown(label: String, value: Int, options: List<Pair<Int, String>>, onSelect: (Int) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val displayLabel = options.firstOrNull { it.first == value }?.second ?: label
    Box(Modifier.fillMaxWidth()) {
        Surface(onClick = { expanded = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(displayLabel, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (optionId, optionLabel) ->
                DropdownMenuItem(text = { Text(optionLabel) }, onClick = { onSelect(optionId); expanded = false })
            }
        }
    }
}

// ---- Account audit ----

@Composable
private fun AccountAuditSheetContent(account: BankAccount) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        SheetTitle("Account audit")
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            LabeledRow("Account", account.name ?: "—")
            LabeledRow("Balance", currency.format(account.total))
            LabeledRow("CSV", account.lastCsvUploadAt ?: "—")
            LabeledRow("Verified", account.lastManualVerifiedAt ?: "—")
            LabeledRow("Credit limit", account.creditLimit?.let { currency.format(it) } ?: "—")
        }
    }
}
