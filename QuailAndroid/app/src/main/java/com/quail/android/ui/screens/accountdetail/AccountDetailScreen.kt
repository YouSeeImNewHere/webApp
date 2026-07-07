package com.quail.android.ui.screens.accountdetail

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.KeyboardArrowLeft
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.AccountLedgerTransaction
import com.quail.android.data.model.BankInfoOptions
import com.quail.android.data.model.ChartPoint
import com.quail.android.data.network.QuailApi
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.categoryIcon
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.Month
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.roundToInt
import com.quail.android.bugreport.BugReportTopBarAction

private val currencyFormat: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)
private val axisFormat: NumberFormat = NumberFormat.getIntegerInstance(Locale.US)
private val chipDateFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)
private val headerDateFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("EEE, MMM d", Locale.US)

private fun LocalDate.toUtcMillis(): Long = atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
private fun Long.toLocalDateUtc(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate()

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountDetailScreen(
    api: QuailApi,
    viewModel: AccountDetailViewModel,
    accountName: String,
    onBack: () -> Unit,
    onSwitchAccount: (accountId: Int, auditMode: Boolean) -> Unit,
    onShareCsv: (List<AccountLedgerTransaction>, String) -> Unit,
) {
    val auditMode by viewModel.auditMode.collectAsState()
    val accountInfo by viewModel.accountInfo.collectAsState()
    val year by viewModel.year.collectAsState()
    val range by viewModel.range.collectAsState()
    val projectGrowth by viewModel.projectGrowth.collectAsState()
    val chartState by viewModel.chartState.collectAsState()
    val ledgerState by viewModel.ledgerState.collectAsState()
    val checkedIds by viewModel.checkedIds.collectAsState()
    val addTxState by viewModel.addTxState.collectAsState()
    val verifyState by viewModel.verifyState.collectAsState()

    var showMenu by remember { mutableStateOf(false) }
    var showSwitcher by remember { mutableStateOf(false) }
    var showGlobalVerify by remember { mutableStateOf(false) }
    var showAddTransaction by remember { mutableStateOf(false) }
    var bankInfo by remember { mutableStateOf(BankInfoOptions()) }
    var selectedTxId by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        bankInfo = runCatching { api.getBankInfo() }.getOrDefault(BankInfoOptions())
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(accountName, fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
                actions = {
                    BugReportTopBarAction()
                    IconButton(onClick = { showSwitcher = true }) { Icon(Icons.Filled.SwapHoriz, contentDescription = "Switch account") }
                    IconButton(onClick = { viewModel.toggleAuditMode() }) {
                        Icon(
                            Icons.Filled.Fingerprint,
                            contentDescription = if (auditMode) "Exit audit mode" else "Audit mode",
                            tint = if (auditMode) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                        )
                    }
                    IconButton(onClick = { showMenu = true }) { Icon(Icons.Filled.MoreVert, contentDescription = "More") }
                    DropdownMenu(expanded = showMenu, onDismissRequest = { showMenu = false }) {
                        DropdownMenuItem(text = { Text("Verify balance on date…") }, onClick = { showMenu = false; showGlobalVerify = true })
                        DropdownMenuItem(
                            text = { Text("Download / share transactions") },
                            onClick = {
                                showMenu = false
                                val txs = (ledgerState as? AccountLedgerUiState.Success)?.data?.transactions ?: emptyList()
                                onShareCsv(txs, accountName)
                            },
                        )
                    }
                },
            )
        },
    ) { padding ->
        var isRefreshing by remember { mutableStateOf(false) }
        androidx.compose.material3.pulltorefresh.PullToRefreshBox(
            isRefreshing = isRefreshing,
            onRefresh = { viewModel.refreshAll(); isRefreshing = false },
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (auditMode) {
                item { AuditBanner(accountInfo?.lastManualVerifiedAt) }
            } else {
                item {
                    AccountChartCard(
                        year = year,
                        range = range,
                        projectGrowth = projectGrowth,
                        chartState = chartState,
                        canGoToNextYear = viewModel.canGoToNextYear,
                        onApplyRange = { s, e -> viewModel.setCustomRange(s, e) },
                        onSelectQuarter = { viewModel.selectQuarter(it) },
                        onSelectAnnual = { viewModel.selectAnnual() },
                        onSelectMonth = { viewModel.selectMonth(it) },
                        onPreviousYear = { viewModel.previousYear() },
                        onNextYear = { viewModel.nextYear() },
                        onSetProjectGrowth = { viewModel.setProjectGrowth(it) },
                    )
                }
            }

            when (val ls = ledgerState) {
                is AccountLedgerUiState.Loading -> item {
                    Box(Modifier.fillMaxWidth().padding(vertical = 30.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                }
                is AccountLedgerUiState.Error -> item {
                    Box(Modifier.fillMaxWidth().padding(vertical = 30.dp), contentAlignment = Alignment.Center) { Text(ls.message, color = QuailTextDim) }
                }
                is AccountLedgerUiState.Success -> {
                    item { BalanceSummaryRow(ls.data.startingBalance, ls.data.endingBalance) }

                    item {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            AccountActionButton("Add Transaction", active = showAddTransaction, modifier = Modifier.weight(1f)) {
                                showAddTransaction = !showAddTransaction
                            }
                            AccountActionButton("Verified", modifier = Modifier.weight(1f)) { showGlobalVerify = true }
                            AccountActionButton("Audit", active = auditMode, modifier = Modifier.weight(1f)) { viewModel.toggleAuditMode() }
                        }
                    }

                    if (showAddTransaction) {
                        item {
                            AddTransactionCard(
                                expanded = true,
                                state = addTxState,
                                onSubmit = { amount, merchant, status, date -> viewModel.addTransaction(amount, merchant, status, date) },
                                onDone = { showAddTransaction = false },
                            )
                        }
                    }

                    val pending = ls.data.transactions.filter { it.status == "pending" }
                    val posted = ls.data.transactions.filter { it.status != "pending" }
                    val groupedByDay = posted.groupBy { it.dateISO ?: it.effectiveDate ?: "" }
                        .toSortedMap(compareByDescending { it })

                    if (pending.isNotEmpty()) {
                        item {
                            DayHeader(
                                label = "Pending",
                                auditMode = false,
                                onVerify = {},
                            )
                        }
                        items(pending, key = { "pending-${it.id}" }) { tx ->
                            LedgerRow(
                                tx = tx,
                                auditMode = auditMode,
                                checked = checkedIds.contains(tx.id),
                                onToggleChecked = { viewModel.toggleChecked(tx.id) },
                                onOpenDetail = { selectedTxId = tx.id },
                            )
                        }
                    }

                    groupedByDay.forEach { (day, txs) ->
                        item(key = "header-$day") {
                            DayHeader(
                                label = runCatching { LocalDate.parse(day).format(headerDateFormat) }.getOrDefault(day),
                                auditMode = auditMode,
                                // txs preserves the backend's dateISO DESC, id DESC order, so the
                                // first row for this day is the last one folded into the running
                                // balance — i.e. the actual end-of-day total.
                                endOfDayBalance = txs.firstOrNull()?.balanceAfter,
                                onVerify = { runCatching { LocalDate.parse(day) }.getOrNull()?.let { viewModel.verify(it) } },
                            )
                        }
                        items(txs, key = { "$day-${it.id}" }) { tx ->
                            LedgerRow(
                                tx = tx,
                                auditMode = auditMode,
                                checked = checkedIds.contains(tx.id),
                                onToggleChecked = { viewModel.toggleChecked(tx.id) },
                                onOpenDetail = { selectedTxId = tx.id },
                            )
                        }
                    }

                    if (pending.isEmpty() && groupedByDay.isEmpty()) {
                        item {
                            Box(Modifier.fillMaxWidth().padding(vertical = 30.dp), contentAlignment = Alignment.Center) {
                                Text(if (auditMode) "Nothing left to audit — you're all caught up." else "No transactions in this range.", color = QuailTextDim)
                            }
                        }
                    }

                    if (auditMode) {
                        item { AuditStartAnchor(ls.data.startingBalance, accountInfo?.lastManualVerifiedAt) }
                    }
                }
            }
        }
        }
    }

    if (showSwitcher) {
        AccountSwitcherSheet(
            bankInfo = bankInfo,
            onDismiss = { showSwitcher = false },
            onSelect = { id ->
                showSwitcher = false
                onSwitchAccount(id, auditMode)
            },
        )
    }

    if (showGlobalVerify) {
        GlobalVerifyDialog(
            state = verifyState,
            onDismiss = { showGlobalVerify = false },
            onConfirm = { date -> viewModel.verify(date); showGlobalVerify = false },
        )
    }

    selectedTxId?.let { id ->
        AccountTransactionDetailSheet(id = id, viewModel = viewModel, onDismiss = { selectedTxId = null })
    }
}

@Composable
private fun AuditBanner(lastVerifiedIso: String?) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("Audit mode", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
            Text(
                "Showing everything since you last verified. Check off each transaction as you confirm it against your statement, then tap Verify on the day the balance matches.",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 6.dp),
            )
            val subtitle = lastVerifiedIso?.let { "Last verified: ${runCatching { java.time.OffsetDateTime.parse(it).toLocalDate() }.getOrNull() ?: it}" }
                ?: "Never verified — showing everything since 2000-01-01."
            Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun BalanceSummaryRow(starting: Double, ending: Double) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Surface(color = QuailSurface, shape = RoundedCornerShape(14.dp), modifier = Modifier.weight(1f)) {
            Column(Modifier.padding(12.dp)) {
                Text("Starting", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(currencyFormat.format(starting), fontWeight = FontWeight.Bold)
            }
        }
        Surface(color = QuailSurface, shape = RoundedCornerShape(14.dp), modifier = Modifier.weight(1f)) {
            Column(Modifier.padding(12.dp)) {
                Text("Ending", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(currencyFormat.format(ending), fontWeight = FontWeight.Bold)
            }
        }
    }
}

/** Shown as the last item in the audit-mode list (chronologically the
 * oldest point, since rows are newest-first) — the running balance right
 * after the last verified date, i.e. the number to start reconciling from. */
@Composable
private fun AuditStartAnchor(startingBalance: Double, lastVerifiedIso: String?) {
    val dateLabel = lastVerifiedIso?.let {
        runCatching { java.time.OffsetDateTime.parse(it).toLocalDate().format(headerDateFormat) }.getOrNull()
    } ?: "the beginning"
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
        Column(Modifier.padding(14.dp)) {
            Text("Audit starts here", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
            Text(
                "Balance as of $dateLabel (your last verified date):",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 4.dp),
            )
            Text(currencyFormat.format(startingBalance), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 2.dp))
        }
    }
}

@Composable
private fun DayHeader(label: String, auditMode: Boolean, endOfDayBalance: Double? = null, onVerify: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = QuailTextDim, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (auditMode && label != "Pending") {
                Surface(onClick = onVerify, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                    Text(
                        "Verify",
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            if (endOfDayBalance != null) {
                Text(
                    currencyFormat.format(endOfDayBalance),
                    color = QuailTextDim,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
        }
    }
}

@Composable
private fun LedgerRow(
    tx: AccountLedgerTransaction,
    auditMode: Boolean,
    checked: Boolean,
    onToggleChecked: () -> Unit,
    onOpenDetail: () -> Unit,
) {
    Surface(
        onClick = { if (auditMode) onToggleChecked() else onOpenDetail() },
        color = if (checked) QuailSurfaceRaised else QuailSurface,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (auditMode) {
                Icon(
                    if (checked) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
                    contentDescription = if (checked) "Checked" else "Not checked",
                    tint = if (checked) QuailGoodGreen else QuailTextDim,
                )
            } else {
                Surface(color = QuailSurfaceRaised, shape = CircleShape, modifier = Modifier.size(36.dp)) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(categoryIcon(tx.category), contentDescription = tx.category, tint = QuailTextDim)
                    }
                }
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(tx.merchant?.ifBlank { "Transaction" } ?: "Transaction", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                val subtitle = listOfNotNull(
                    tx.category?.takeIf { it.isNotBlank() },
                    tx.transferDir?.let { "transfer $it" },
                ).joinToString(" • ")
                if (subtitle.isNotBlank()) {
                    Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    currencyFormat.format(tx.amount),
                    color = if (tx.amount >= 0) QuailBadRed else QuailGoodGreen,
                    fontWeight = FontWeight.Bold,
                )
                tx.balanceAfter?.let {
                    Text(currencyFormat.format(it), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            if (auditMode) {
                IconButton(onClick = onOpenDetail, modifier = Modifier.size(28.dp)) {
                    Icon(Icons.Filled.Info, contentDescription = "View details", tint = QuailTextDim, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
private fun AddTransactionCard(expanded: Boolean, state: AddTxState, onSubmit: (Double, String, String, LocalDate) -> Unit, onDone: () -> Unit) {
    if (!expanded) return
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("Add Transaction", fontWeight = FontWeight.Bold)
            run {
                var merchant by remember { mutableStateOf("") }
                var amount by remember { mutableStateOf("") }
                var status by remember { mutableStateOf("posted") }
                var date by remember { mutableStateOf(LocalDate.now()) }
                var showDatePicker by remember { mutableStateOf(false) }

                OutlinedTextField(
                    value = merchant,
                    onValueChange = { merchant = it },
                    label = { Text("Merchant") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                )
                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Amount (+expense / -income)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                )
                Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("posted" to "Posted", "pending" to "Pending").forEach { (value, label) ->
                        Surface(
                            onClick = { status = value },
                            color = if (status == value) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                            shape = RoundedCornerShape(999.dp),
                        ) {
                            Text(
                                label,
                                color = if (status == value) Color.Black else QuailTextDim,
                                fontWeight = FontWeight.SemiBold,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                            )
                        }
                    }
                    Surface(onClick = { showDatePicker = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                        Text(
                            date.format(chipDateFormat),
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        )
                    }
                }
                if (state is AddTxState.Error) {
                    Text(state.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
                }
                Button(
                    enabled = state !is AddTxState.Saving && amount.toDoubleOrNull() != null && merchant.isNotBlank(),
                    onClick = {
                        val amt = amount.toDoubleOrNull() ?: return@Button
                        onSubmit(amt, merchant, status, date)
                        merchant = ""
                        amount = ""
                        onDone()
                    },
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                ) {
                    Text(if (state is AddTxState.Saving) "Saving…" else "Save Transaction", fontWeight = FontWeight.Bold)
                }

                if (showDatePicker) {
                    DatePickerModal(initial = date, onDismiss = { showDatePicker = false }, onConfirm = { date = it; showDatePicker = false })
                }
            }
        }
    }
}

@Composable
private fun AccountSwitcherSheet(bankInfo: BankInfoOptions, onDismiss: () -> Unit, onSelect: (Int) -> Unit) {
    val content: @Composable () -> Unit = {
        Column(Modifier.padding(bottom = 24.dp)) {
            Text("Switch account", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(start = 20.dp, end = 20.dp, bottom = 8.dp))
            bankInfo.accounts.forEach { acc ->
                DropdownMenuItem(text = { Text("${acc.bank.orEmpty()} - ${acc.name.orEmpty()}") }, onClick = { onSelect(acc.accountId) })
            }
            bankInfo.creditCards.forEach { card ->
                DropdownMenuItem(text = { Text("${card.bank.orEmpty()} - ${card.name.orEmpty()} (credit)") }, onClick = { onSelect(card.cardId) })
            }
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GlobalVerifyDialog(state: VerifyState, onDismiss: () -> Unit, onConfirm: (LocalDate) -> Unit) {
    var date by remember { mutableStateOf(LocalDate.now().minusDays(1)) }
    DatePickerModal(
        initial = date,
        onDismiss = onDismiss,
        onConfirm = { date = it; onConfirm(date) },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DatePickerModal(initial: LocalDate, onDismiss: () -> Unit, onConfirm: (LocalDate) -> Unit) {
    val state = rememberDatePickerState(initialSelectedDateMillis = initial.toUtcMillis())
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                val millis = state.selectedDateMillis
                if (millis != null) onConfirm(millis.toLocalDateUtc()) else onDismiss()
            }) { Text("OK") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    ) {
        DatePicker(state = state)
    }
}

@Composable
private fun AccountChartCard(
    year: Int,
    range: AccountChartRange,
    projectGrowth: Boolean,
    chartState: AccountChartUiState,
    canGoToNextYear: Boolean,
    onApplyRange: (LocalDate, LocalDate) -> Unit,
    onSelectQuarter: (Int) -> Unit,
    onSelectAnnual: () -> Unit,
    onSelectMonth: (Int) -> Unit,
    onPreviousYear: () -> Unit,
    onNextYear: () -> Unit,
    onSetProjectGrowth: (Boolean) -> Unit,
) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("Balance", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            AccountDateRangeControls(range = range, onApply = onApplyRange)

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    modifier = Modifier.weight(1f, fill = false).horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    (1..4).forEach { q -> AccountChipButton("Q$q") { onSelectQuarter(q) } }
                    AccountChipButton("YTD") { onSelectAnnual() }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onPreviousYear, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Filled.KeyboardArrowLeft, contentDescription = "Previous year")
                    }
                    Text("$year", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    IconButton(onClick = onNextYear, enabled = canGoToNextYear, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Filled.KeyboardArrowRight, contentDescription = "Next year")
                    }
                }
            }

            androidx.compose.foundation.lazy.LazyRow(
                modifier = Modifier.padding(top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(12) { i ->
                    val month = i + 1
                    AccountChipButton(Month.of(month).getDisplayName(TextStyle.SHORT, Locale.US)) { onSelectMonth(month) }
                }
            }

            Box(modifier = Modifier.padding(top = 12.dp)) {
                when (chartState) {
                    is AccountChartUiState.Loading -> Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        Text("Loading…", color = QuailTextDim)
                    }
                    is AccountChartUiState.Error -> Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        Text(chartState.message, color = QuailTextDim)
                    }
                    is AccountChartUiState.Success -> Column {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                            Text("Project Growth", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            Switch(checked = projectGrowth, onCheckedChange = onSetProjectGrowth)
                        }
                        AccountChartCanvas(
                            points = chartState.points,
                            projected = if (projectGrowth) projectedAccountPoints(chartState.points) else emptyList(),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AccountActionButton(label: String, active: Boolean = false, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (active) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier,
    ) {
        Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
            Text(
                label,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.labelMedium,
                color = if (active) Color.Black else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun AccountChipButton(label: String, onClick: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
        Text(
            label,
            modifier = Modifier.widthIn(min = 30.dp).padding(horizontal = 9.dp, vertical = 6.dp),
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

@Composable
private fun AccountDateRangeControls(range: AccountChartRange, onApply: (LocalDate, LocalDate) -> Unit) {
    var pendingStart by remember(range) { mutableStateOf(range.start) }
    var pendingEnd by remember(range) { mutableStateOf(range.end) }
    var showStartPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }

    Row(modifier = Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Start", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            AccountChipButton(pendingStart.format(chipDateFormat)) { showStartPicker = true }
        }
        Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("End", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            AccountChipButton(pendingEnd.format(chipDateFormat)) { showEndPicker = true }
        }
        Column(modifier = Modifier.padding(top = 18.dp)) {
            Surface(onClick = { onApply(pendingStart, pendingEnd) }, color = MaterialTheme.colorScheme.primary, shape = RoundedCornerShape(12.dp)) {
                Text(
                    "Update",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                    color = Color.Black,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }

    if (showStartPicker) DatePickerModal(initial = pendingStart, onDismiss = { showStartPicker = false }, onConfirm = { pendingStart = it; showStartPicker = false })
    if (showEndPicker) DatePickerModal(initial = pendingEnd, onDismiss = { showEndPicker = false }, onConfirm = { pendingEnd = it; showEndPicker = false })
}

private fun nearestIndex(x: Float, widthPx: Float, count: Int): Int {
    if (count <= 1) return 0
    return (x / widthPx * (count - 1)).roundToInt().coerceIn(0, count - 1)
}

@Composable
private fun AccountChartCanvas(points: List<ChartPoint>, projected: List<ChartPoint>) {
    var selectedIndex by remember(points) { mutableStateOf<Int?>(null) }

    if (points.size < 2) {
        Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) { Text("Not enough data yet", color = QuailTextDim) }
        return
    }

    val allValues = points.map { it.value } + projected.map { it.value }
    val minValue = allValues.min()
    val maxValue = allValues.max()
    val rawSpan = (maxValue - minValue).let { if (it == 0.0) kotlin.math.abs(maxValue).coerceAtLeast(1.0) else it }
    val paddedSpan = rawSpan * 1.12
    val paddedMin = minValue - (paddedSpan - rawSpan) / 2.0
    val accentColor = MaterialTheme.colorScheme.primary

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(200.dp)
            .pointerInput(points) {
                detectTapGestures(onTap = { offset -> selectedIndex = nearestIndex(offset.x, size.width.toFloat(), points.size) })
            }
            .pointerInput(points) {
                detectDragGestures(onDrag = { change, _ ->
                    change.consume()
                    selectedIndex = nearestIndex(change.position.x, size.width.toFloat(), points.size)
                })
            },
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            val totalCount = points.size + projected.size
            fun xFor(i: Int) = if (totalCount <= 1) 0f else w * i / (totalCount - 1)
            fun yFor(v: Double) = h - ((v - paddedMin) / paddedSpan * h).toFloat()

            val gridColor = Color.White.copy(alpha = 0.08f)
            for (i in 0..3) {
                val y = h * i / 3f
                drawLine(gridColor, Offset(0f, y), Offset(w, y), strokeWidth = 1f)
            }

            val linePath = Path()
            points.forEachIndexed { i, p ->
                val x = xFor(i)
                val y = yFor(p.value)
                if (i == 0) linePath.moveTo(x, y) else linePath.lineTo(x, y)
            }
            val areaPath = Path().apply {
                addPath(linePath)
                lineTo(xFor(points.size - 1), h)
                lineTo(xFor(0), h)
                close()
            }
            drawPath(areaPath, brush = Brush.verticalGradient(listOf(accentColor.copy(alpha = 0.18f), accentColor.copy(alpha = 0.02f))))
            drawPath(linePath, color = accentColor, style = Stroke(width = 2.8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))

            if (projected.isNotEmpty()) {
                val projPath = Path()
                projPath.moveTo(xFor(points.size - 1), yFor(points.last().value))
                projected.forEachIndexed { j, p -> projPath.lineTo(xFor(points.size + j), yFor(p.value)) }
                drawPath(
                    projPath,
                    color = accentColor.copy(alpha = 0.55f),
                    style = Stroke(width = 2.1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 8f))),
                )
            }

            selectedIndex?.let { idx ->
                if (idx in points.indices) {
                    val x = xFor(idx)
                    val y = yFor(points[idx].value)
                    drawLine(Color.White.copy(alpha = 0.25f), Offset(x, 0f), Offset(x, h), strokeWidth = 1f)
                    drawCircle(accentColor, radius = 5.dp.toPx(), center = Offset(x, y))
                    drawCircle(Color.White, radius = 5.dp.toPx(), center = Offset(x, y), style = Stroke(width = 2.dp.toPx()))
                }
            }
        }

        Column(modifier = Modifier.fillMaxSize().padding(vertical = 2.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Text(axisFormat.format(maxValue), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Text(axisFormat.format(minValue), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }

        selectedIndex?.let { idx ->
            if (idx in points.indices) {
                val point = points[idx]
                Surface(
                    color = Color.Black.copy(alpha = 0.82f),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.align(Alignment.BottomEnd).padding(8.dp).widthIn(max = 180.dp),
                ) {
                    Column(Modifier.padding(10.dp)) {
                        Text(point.date, color = Color.White, style = MaterialTheme.typography.labelSmall)
                        Text(currencyFormat.format(point.value), color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
