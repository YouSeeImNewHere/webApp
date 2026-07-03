package com.quailcash.android.ui.screens.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import com.quailcash.android.data.model.MonthlyReport
import com.quailcash.android.data.model.ReportAccountSummary
import com.quailcash.android.data.model.ReportTransaction
import com.quailcash.android.ui.theme.QuailBadRed
import com.quailcash.android.ui.theme.QuailGoodGreen
import com.quailcash.android.ui.theme.QuailSurface
import com.quailcash.android.ui.theme.QuailSurfaceRaised
import com.quailcash.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.Month
import java.time.format.TextStyle
import java.util.Locale

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AnalyticsTab(padding: PaddingValues, viewModel: AnalyticsViewModel) {
    val state by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { viewModel.pullRefresh() },
        modifier = Modifier.fillMaxSize().padding(padding),
    ) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(
                top = 8.dp,
                bottom = 16.dp,
                start = 12.dp,
                end = 12.dp,
            ),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        when (val s = state) {
            is AnalyticsUiState.Loading -> Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            is AnalyticsUiState.Error -> Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                Text(s.message, color = QuailTextDim)
            }
            is AnalyticsUiState.Success -> {
                MonthPickerRow(s.year, s.month, onSelect = { y, m -> viewModel.selectMonth(y, m) })
                HeroCard(s.report)
                MonthSummaryCard(s.report)
                if (s.report.categoryBreakdown.isNotEmpty()) CategoryBreakdownCard(s.report)
                AccountsCard(s.report)
                BiggestTransactionsCard(s.report)
                if (s.report.recurringSubscriptions.isNotEmpty()) RecurringSubscriptionsCard(s.report)
                BudgetPerformanceCard(s.report)
                ChangesCard(s.report)
            }
        }
    }
    }
}

@Composable
private fun MonthPickerRow(year: Int, month: Int, onSelect: (Int, Int) -> Unit) {
    var showMonthMenu by remember { mutableStateOf(false) }
    var showYearMenu by remember { mutableStateOf(false) }
    val years = (year - 5..year + 1).toList().reversed()

    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.weight(1f)) {
            Surface(onClick = { showMonthMenu = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(
                    Month.of(month).getDisplayName(TextStyle.FULL, Locale.US),
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp),
                    fontWeight = FontWeight.SemiBold,
                )
            }
            DropdownMenu(expanded = showMonthMenu, onDismissRequest = { showMonthMenu = false }) {
                (1..12).forEach { m ->
                    DropdownMenuItem(
                        text = { Text(Month.of(m).getDisplayName(TextStyle.FULL, Locale.US)) },
                        onClick = { onSelect(year, m); showMonthMenu = false },
                    )
                }
            }
        }
        Box {
            Surface(onClick = { showYearMenu = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp)) {
                Text("$year", modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp), fontWeight = FontWeight.SemiBold)
            }
            DropdownMenu(expanded = showYearMenu, onDismissRequest = { showYearMenu = false }) {
                years.forEach { y ->
                    DropdownMenuItem(text = { Text("$y") }, onClick = { onSelect(y, month); showYearMenu = false })
                }
            }
        }
    }
}

@Composable
private fun AnalyticsCard(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Column(Modifier.padding(top = 10.dp)) { content() }
        }
    }
}

@Composable
private fun KV(label: String, value: String, valueColor: androidx.compose.ui.graphics.Color = androidx.compose.ui.graphics.Color.Unspecified) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.bodyMedium)
        Text(value, fontWeight = FontWeight.SemiBold, color = valueColor)
    }
}

@Composable
private fun HeroCard(report: MonthlyReport) {
    AnalyticsCard(title = report.month) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text("Net", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(
                    currency.format(report.summary.net),
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = if (report.summary.net >= 0) QuailGoodGreen else QuailBadRed,
                )
            }
            Column {
                Text("Income", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(currency.format(report.summary.income), fontWeight = FontWeight.Bold, color = QuailGoodGreen)
            }
            Column {
                Text("Spending", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(currency.format(report.summary.spending), fontWeight = FontWeight.Bold, color = QuailBadRed)
            }
        }
    }
}

@Composable
private fun MonthSummaryCard(report: MonthlyReport) {
    AnalyticsCard(title = "Month summary") {
        KV("Income", currency.format(report.summary.income))
        KV("Spending", currency.format(report.summary.spending))
        KV("Net", currency.format(report.summary.net))
        KV("Starting balance", currency.format(report.summary.startingBalance))
        KV("Ending balance", currency.format(report.summary.endingBalance))
    }
}

@Composable
private fun CategoryBreakdownCard(report: MonthlyReport) {
    AnalyticsCard(title = "Category breakdown") {
        report.categoryBreakdown.forEach { KV(it.category, currency.format(it.amount)) }
    }
}

@Composable
private fun AccountsCard(report: MonthlyReport) {
    val savings = report.accountSummary.filter { it.accountType == "savings" }
    val liquid = report.accountSummary.filter { it.accountType in setOf("checking", "debit", "cash") }
    val debt = report.accountSummary.filter { it.accountType == "credit" }

    if (savings.isEmpty() && liquid.isEmpty() && debt.isEmpty()) return

    AnalyticsCard(title = "Accounts") {
        if (liquid.isNotEmpty()) {
            Text("Liquid", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
            liquid.forEach { AccountRow(it) }
        }
        if (savings.isNotEmpty()) {
            Text("Savings", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
            savings.forEach { AccountRow(it) }
        }
        if (debt.isNotEmpty()) {
            Text("Debt", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
            debt.forEach { AccountRow(it) }
        }
    }
}

@Composable
private fun AccountRow(account: ReportAccountSummary) {
    KV(
        listOfNotNull(account.bank, account.name).joinToString(" "),
        currency.format(account.endBalance),
        valueColor = if (account.change >= 0) QuailGoodGreen else QuailBadRed,
    )
}

@Composable
private fun BiggestTransactionsCard(report: MonthlyReport) {
    val outflows = report.biggestTransactions.outflows
    val inflows = report.biggestTransactions.inflows
    if (outflows.isEmpty() && inflows.isEmpty()) return

    AnalyticsCard(title = "Biggest transactions") {
        if (outflows.isNotEmpty()) {
            Text("Outflows", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            outflows.forEach { BiggestTxRow(it, QuailBadRed) }
        }
        if (inflows.isNotEmpty()) {
            Text("Inflows", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
            inflows.forEach { BiggestTxRow(it, QuailGoodGreen) }
        }
    }
}

@Composable
private fun BiggestTxRow(tx: ReportTransaction, amountColor: androidx.compose.ui.graphics.Color) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Column {
            Text(tx.merchant ?: "Transaction", style = MaterialTheme.typography.bodyMedium)
            Text(listOfNotNull(tx.date, tx.category).joinToString(" • "), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
        Text(currency.format(tx.amount), fontWeight = FontWeight.SemiBold, color = amountColor)
    }
}

@Composable
private fun RecurringSubscriptionsCard(report: MonthlyReport) {
    AnalyticsCard(title = "Recurring & subscriptions") {
        report.recurringSubscriptions.forEach { sub ->
            KV("${sub.merchant} (${sub.hits}x)", currency.format(sub.total))
        }
    }
}

@Composable
private fun BudgetPerformanceCard(report: MonthlyReport) {
    val bp = report.budgetPerformance
    AnalyticsCard(title = "Budget performance") {
        KV("Planned", currency.format(bp.plannedAllocations))
        KV("Actual", currency.format(bp.actualSpentOnAllocated))
        KV("Remaining", currency.format(bp.remainingAllocated), valueColor = if (bp.remainingAllocated >= 0) QuailGoodGreen else QuailBadRed)
        KV("Free spend so far", currency.format(bp.freeSpendSoFar))
    }
}

@Composable
private fun ChangesCard(report: MonthlyReport) {
    val c = report.changesVsPreviousMonth
    AnalyticsCard(title = "Changes vs previous month") {
        KV("Income (prev)", currency.format(c.incomePrevMonth))
        KV(
            "Income change",
            c.incomeChangePct?.let { "${if (it >= 0) "+" else ""}${"%.1f".format(it)}%" } ?: "—",
            valueColor = if ((c.incomeChangePct ?: 0.0) >= 0) QuailGoodGreen else QuailBadRed,
        )
        KV("Spending (prev)", currency.format(c.spendingPrevMonth))
        KV(
            "Spending change",
            c.spendingChangePct?.let { "${if (it >= 0) "+" else ""}${"%.1f".format(it)}%" } ?: "—",
            valueColor = if ((c.spendingChangePct ?: 0.0) <= 0) QuailGoodGreen else QuailBadRed,
        )
    }
}
