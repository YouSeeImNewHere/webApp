package com.quail.android.ui.screens.home

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Payments
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Repeat
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.quail.android.bugreport.BugReportTopBarAction
import com.quail.android.data.model.BankAccount
import com.quail.android.data.model.BankGroup
import com.quail.android.data.model.CategoryTotalsMonth
import com.quail.android.data.model.DayLimit
import com.quail.android.data.model.HomePayload
import com.quail.android.data.model.MonthBudget
import com.quail.android.data.model.Transaction
import com.quail.android.data.model.UpcomingEvent
import com.quail.android.data.repository.HomeRepository
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailText
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.ui.theme.categoryIcon
import java.text.NumberFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

private val currencyFormat: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

private val ACCOUNT_TYPE_ORDER = listOf("checking", "savings", "credit", "investment", "other")
private val ACCOUNT_TYPE_LABELS = mapOf(
    "checking" to "Checking",
    "savings" to "Savings",
    "investment" to "Investment",
    "credit" to "Credit",
    "other" to "Other",
)

private enum class CashTab(val label: String, val icon: ImageVector) {
    HOME("Home", Icons.Filled.Home),
    SPENDING("Spending", Icons.Filled.Payments),
    ALL("All", Icons.Filled.Search),
    ANALYTICS("Analytics", Icons.Filled.BarChart),
    RECURRING("Recurring", Icons.Filled.Repeat),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    chartViewModel: NetWorthChartViewModel,
    repository: HomeRepository,
    onOpenDashboard: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenNotifications: () -> Unit,
    onOpenBudget: () -> Unit,
    onOpenAccountDetail: (accountId: Int, auditMode: Boolean) -> Unit = { _, _ -> },
) {
    val uiState by viewModel.uiState.collectAsState()
    var selectedTab by remember { mutableStateOf(CashTab.HOME) }
    var activeSheet by remember { mutableStateOf<HomeSheet?>(null) }
    var showUnassignedWizard by remember { mutableStateOf(false) }
    val unreadCount = (uiState as? HomeUiState.Success)?.payload?.notificationsUnread?.unread ?: 0

    val onOpenSheet: (HomeSheet) -> Unit = { sheet ->
        activeSheet = sheet
        when (sheet) {
            is HomeSheet.ExtraSaved -> viewModel.loadExtraSavedDetail()
            is HomeSheet.SpentSoFar -> viewModel.loadSpentSoFarBreakdown()
            is HomeSheet.TransactionDetail -> viewModel.loadTransactionDetail(sheet.id)
            else -> {}
        }
    }
    val onDismissSheet: () -> Unit = {
        activeSheet = null
        viewModel.clearExtraSaved()
        viewModel.clearSpentSoFar()
        viewModel.clearTransactionDetail()
        viewModel.clearVerifyBalance()
        viewModel.clearBankInfo()
    }

    Scaffold(
        topBar = { QuailTopBar(unreadCount, onOpenSettings, onOpenNotifications) },
        bottomBar = {
            QuailBottomBar(
                selectedTab = selectedTab,
                onSelectTab = { selectedTab = it },
                onOpenDashboard = onOpenDashboard,
            )
        },
    ) { padding ->
        when (selectedTab) {
            CashTab.SPENDING -> ComingSoonTab(padding, selectedTab.label)
            CashTab.ALL -> {
                val allViewModel: com.quail.android.ui.screens.home.AllTransactionsViewModel = viewModel(
                    factory = AllTransactionsViewModel.Factory(repository),
                )
                AllTransactionsTab(padding, allViewModel, onOpenSheet)
            }
            CashTab.ANALYTICS -> {
                val analyticsViewModel: AnalyticsViewModel = viewModel(factory = AnalyticsViewModel.Factory(repository))
                AnalyticsTab(padding, analyticsViewModel)
            }
            CashTab.RECURRING -> {
                val recurringViewModel: RecurringViewModel = viewModel(factory = RecurringViewModel.Factory(repository))
                RecurringTab(padding, recurringViewModel)
            }
            CashTab.HOME -> {
                val isRefreshing by viewModel.isRefreshing.collectAsState()
                PullToRefreshBox(
                    isRefreshing = isRefreshing,
                    onRefresh = { viewModel.pullRefresh() },
                    modifier = Modifier.fillMaxSize().padding(padding),
                ) {
                    when (val state = uiState) {
                        is HomeUiState.Loading -> LoadingView(PaddingValues(0.dp))
                        is HomeUiState.Error -> ErrorView(PaddingValues(0.dp), state.message, onRetry = { viewModel.refresh() })
                        is HomeUiState.Success -> HomeContent(
                            PaddingValues(0.dp),
                            state.payload,
                            state.upcoming,
                            chartViewModel,
                            onOpenSheet,
                            onOpenUnassignedWizard = { showUnassignedWizard = true },
                            onOpenBudget = onOpenBudget,
                            onOpenAccountDetail = onOpenAccountDetail,
                        )
                    }
                }
            }
        }
    }

    activeSheet?.let { sheet ->
        HomeSheetHost(sheet = sheet, viewModel = viewModel, onDismiss = onDismissSheet)
    }

    if (showUnassignedWizard) {
        val wizardViewModel: UnassignedWizardViewModel = viewModel(
            factory = UnassignedWizardViewModel.Factory(repository, onRuleApplied = { viewModel.refresh() }),
        )
        UnassignedWizardSheet(viewModel = wizardViewModel, onDismiss = { showUnassignedWizard = false })
    }
}

@Composable
private fun QuailTopBar(unreadCount: Int, onOpenSettings: () -> Unit, onOpenNotifications: () -> Unit) {
    Surface(color = QuailSurface) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 12.dp, vertical = 8.dp)
                .height(40.dp),
        ) {
            TopBarCircleButton(
                icon = Icons.Filled.Settings,
                modifier = Modifier.align(Alignment.CenterStart),
                onClick = onOpenSettings,
            )

            Text(
                "Quail Cash",
                fontWeight = FontWeight.ExtraBold,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.align(Alignment.Center),
            )

            Row(
                modifier = Modifier.align(Alignment.CenterEnd),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                BugReportTopBarAction()

                Box {
                    TopBarCircleButton(icon = Icons.Filled.Notifications, onClick = onOpenNotifications)
                    if (unreadCount > 0) {
                        Surface(
                            color = QuailBadRed,
                            shape = CircleShape,
                            modifier = Modifier
                                .align(Alignment.TopEnd)
                                .offset(x = 4.dp, y = (-4).dp)
                                .size(18.dp),
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text(
                                    if (unreadCount > 9) "9+" else "$unreadCount",
                                    color = Color.White,
                                    fontSize = 9.sp,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TopBarCircleButton(
    icon: ImageVector,
    background: Color = QuailSurfaceRaised,
    tint: Color = QuailText,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Surface(onClick = onClick, color = background, shape = CircleShape, modifier = modifier.size(40.dp)) {
        Box(contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = tint)
        }
    }
}

@Composable
private fun QuailBottomBar(
    selectedTab: CashTab,
    onSelectTab: (CashTab) -> Unit,
    onOpenDashboard: () -> Unit,
) {
    Surface(color = QuailSurface) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .navigationBarsPadding()
                .padding(vertical = 8.dp),
        ) {
            CashTab.entries.forEach { tab ->
                BottomBarItem(
                    icon = tab.icon,
                    label = tab.label,
                    selected = selectedTab == tab,
                    onClick = { onSelectTab(tab) },
                )
            }
            BottomBarItem(
                icon = Icons.Filled.Dashboard,
                label = "Dashboard",
                selected = false,
                onClick = onOpenDashboard,
            )
        }
    }
}

@Composable
private fun BottomBarItem(icon: ImageVector, label: String, selected: Boolean, onClick: () -> Unit) {
    val color = if (selected) MaterialTheme.colorScheme.primary else QuailTextDim
    Column(
        modifier = Modifier
            .width(76.dp)
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = onClick,
            )
            .padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, contentDescription = label, tint = color)
        Text(label, color = color, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun ComingSoonTab(padding: PaddingValues, label: String) {
    Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
        Text("$label isn't built yet", color = QuailTextDim)
    }
}

@Composable
private fun LoadingView(padding: PaddingValues) {
    Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun ErrorView(padding: PaddingValues, message: String, onRetry: () -> Unit) {
    Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Couldn't load your dashboard", fontWeight = FontWeight.Bold)
            Text(message, color = QuailTextDim, modifier = Modifier.padding(top = 4.dp, bottom = 16.dp))
            IconButton(onClick = onRetry) {
                Icon(Icons.Filled.Refresh, contentDescription = "Retry")
            }
        }
    }
}

@Composable
private fun HomeContent(
    padding: PaddingValues,
    payload: HomePayload,
    upcoming: List<UpcomingEvent>,
    chartViewModel: NetWorthChartViewModel,
    onOpenSheet: (HomeSheet) -> Unit,
    onOpenUnassignedWizard: () -> Unit,
    onOpenBudget: () -> Unit,
    onOpenAccountDetail: (accountId: Int, auditMode: Boolean) -> Unit = { _, _ -> },
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            top = padding.calculateTopPadding() + 8.dp,
            // Scaffold's bottom inset already accounts for the custom
            // QuailBottomBar's real height — a flat 32.dp under-counted it
            // and let the bar cover the last card(s).
            bottom = padding.calculateBottomPadding() + 16.dp,
            start = 12.dp,
            end = 12.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { NetWorthChartCard(chartViewModel) }
        if (payload.monthBudget != null) {
            item { MonthlySnapshotCard(payload.monthBudget, payload.dayLimit, onOpenSheet, onOpenBudget) }
        }
        val categoryTotalsMonth = payload.categoryTotalsMonth
        if ((categoryTotalsMonth?.categories?.isNotEmpty() == true) || (categoryTotalsMonth?.unassignedAllTime ?: 0) > 0) {
            item { MonthlySpendingCard(categoryTotalsMonth ?: CategoryTotalsMonth(), onOpenUnassignedWizard) }
        }
        if (payload.bankTotals.isNotEmpty()) {
            item { BankTotalsCard(payload.bankTotals, onOpenSheet, onOpenAccountDetail) }
        }
        if (upcoming.isNotEmpty()) {
            item { UpcomingCard(upcoming) }
        }
        if (payload.transactions.isNotEmpty()) {
            item { RecentTransactionsCard(payload.transactions, onOpenSheet) }
        }
    }
}

/** Card shell shared by every section on the real Home screen: centered
 * bold title + chevron, whole header tappable to expand/collapse. */
@Composable
private fun ExpandableCard(
    title: String,
    initiallyExpanded: Boolean = true,
    headerActions: (@Composable () -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    var expanded by remember { mutableStateOf(initiallyExpanded) }
    Surface(
        onClick = { expanded = !expanded },
        color = QuailSurface,
        shape = RoundedCornerShape(18.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.weight(1f))
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Box(Modifier.weight(1f), contentAlignment = Alignment.CenterEnd) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        headerActions?.invoke()
                        Icon(
                            if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                            contentDescription = if (expanded) "Collapse" else "Expand",
                            tint = QuailTextDim,
                        )
                    }
                }
            }
            AnimatedVisibility(
                visible = expanded,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically(),
            ) {
                Column(Modifier.padding(top = 12.dp)) {
                    content()
                }
            }
        }
    }
}

@Composable
private fun SnapshotRow(label: String, value: String, onClick: (() -> Unit)? = null) {
    val rowContent: @Composable () -> Unit = {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Text(value, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
        }
    }
    if (onClick != null) {
        Surface(
            onClick = onClick,
            color = QuailSurfaceRaised.copy(alpha = 0.92f),
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth(),
        ) { rowContent() }
    } else {
        Surface(
            color = QuailSurfaceRaised.copy(alpha = 0.92f),
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth(),
        ) { rowContent() }
    }
}

@Composable
private fun MonthlySnapshotCard(budget: MonthBudget, dayLimit: DayLimit?, onOpenSheet: (HomeSheet) -> Unit, onOpenBudget: () -> Unit) {
    ExpandableCard(
        title = "This month",
        headerActions = {
            IconButton(
                onClick = onOpenBudget,
                modifier = Modifier.size(28.dp),
            ) {
                Icon(
                    Icons.Filled.BarChart,
                    contentDescription = "Budget",
                    tint = QuailTextDim,
                    modifier = Modifier.size(18.dp),
                )
            }
        },
    ) {
        Row(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Safe to spend", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(
                    currencyFormat.format(budget.safeToSpend),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    // HomeView.swift line 428: negative gets the red/negative
                    // color, non-negative just uses the default text color.
                    color = if (budget.safeToSpend < 0) QuailBadRed else QuailText,
                )
                Text(
                    "${budget.daysLeft} days left" + (budget.asOf?.let { " · as of $it" } ?: ""),
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Column(modifier = Modifier.weight(1f)) {
                Text("Today left", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(
                    currencyFormat.format(dayLimit?.remainingToday ?: budget.dailyLimit),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                if (dayLimit != null) {
                    Text(
                        "baseline ${currencyFormat.format(dayLimit.baseline)}",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }

        Column(modifier = Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SnapshotRow(
                "Income",
                currencyFormat.format(budget.expectedIncome),
                onClick = { onOpenSheet(HomeSheet.Income(budget)) },
            )
            SnapshotRow(
                "Spent so far",
                currencyFormat.format(budget.spentSoFar),
                onClick = { onOpenSheet(HomeSheet.SpentSoFar) },
            )
            // Matches HomeView.swift:473-478 — "Remaining bills" has no
            // breakdown popup on iOS either (tappable: false, action: nil).
            SnapshotRow("Remaining bills", currencyFormat.format(budget.billsRemaining))
            SnapshotRow(
                "Extra saved",
                currencyFormat.format(budget.extraSavedApplied),
                onClick = { onOpenSheet(HomeSheet.ExtraSaved) },
            )
        }
    }
}

@Composable
private fun MonthlySpendingCard(categoryTotalsMonth: CategoryTotalsMonth, onOpenUnassignedWizard: () -> Unit) {
    ExpandableCard(title = "Monthly Spending") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            categoryTotalsMonth.categories.sortedByDescending { it.total }.forEach { cat ->
                Surface(
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(cat.category, fontWeight = FontWeight.SemiBold)
                            CountPill(cat.txCount)
                        }
                        Text(currencyFormat.format(cat.total), fontWeight = FontWeight.Bold)
                    }
                }
            }
            if (categoryTotalsMonth.unassignedAllTime > 0) {
                Surface(
                    onClick = onOpenUnassignedWizard,
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text("Unassigned", fontWeight = FontWeight.SemiBold)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("+ Rule", color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                            CountPill(categoryTotalsMonth.unassignedAllTime)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CountPill(count: Int) {
    Surface(color = MaterialTheme.colorScheme.primary.copy(alpha = 0.18f), shape = CircleShape) {
        Text(
            "$count",
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun BankTotalsCard(
    bankTotals: Map<String, BankGroup>,
    onOpenSheet: (HomeSheet) -> Unit,
    onOpenAccountDetail: (accountId: Int, auditMode: Boolean) -> Unit,
) {
    val context = LocalContext.current
    ExpandableCard(title = "Bank Totals") {
        Row(
            modifier = Modifier.padding(bottom = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            HeaderActionButton("Import CSV/Excel", primary = true) {
                Toast.makeText(context, "Share a bank CSV to Quail Cash, or open Settings → Import Queue", Toast.LENGTH_LONG).show()
            }
            HeaderActionButton("Bank Info", primary = false) { onOpenSheet(HomeSheet.BankInfo) }
        }
        val orderedTypes = ACCOUNT_TYPE_ORDER.filter { bankTotals.containsKey(it) } +
            bankTotals.keys.filter { it !in ACCOUNT_TYPE_ORDER }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            orderedTypes.forEach { type ->
                val group = bankTotals.getValue(type)
                if (group.accounts.isNotEmpty()) {
                    BankTypeSection(type, group, onOpenSheet, onOpenAccountDetail)
                }
            }
        }
    }
}

@Composable
private fun HeaderActionButton(label: String, primary: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (primary) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = if (primary) Color.Black else QuailText,
        )
    }
}

/** bank_totals() keeps credit balances as a signed raw value (negative =
 * debt, see accounts.py's comment), but the Account Detail screen's
 * account-transactions-range endpoint flips credit balances so debt reads
 * as positive — the more intuitive convention for "how much do I owe".
 * Flipped here at display time only, so this card matches Account Detail
 * without touching the debt-magnitude math in creditUsageSubtitle() below
 * (which already expects the raw negative-is-debt sign). */
private fun creditDisplayTotal(type: String, total: Double): Double = if (type == "credit") -total else total

/** Sum of positive credit_limit values vs. sum of debt (negative `total`,
 * see accounts.py's bank_totals() "signed raw value" comment) — mirrors
 * HomeView.swift's creditUsageSummaryPct(). Only shown for the credit
 * group, and only when at least one account has a limit on file. */
private fun creditUsageSubtitle(type: String, group: BankGroup): String? {
    if (type != "credit") return null
    val totalLimit = group.accounts.mapNotNull { it.creditLimit }.filter { it > 0 }.sum()
    if (totalLimit <= 0) return null
    val used = group.accounts.sumOf { maxOf(0.0, -it.total) }
    val pct = ((used / totalLimit) * 100).roundToInt()
    return "Limit ${currencyFormat.format(totalLimit)} · $pct% used"
}

@Composable
private fun BankTypeSection(
    type: String,
    group: BankGroup,
    onOpenSheet: (HomeSheet) -> Unit,
    onOpenAccountDetail: (accountId: Int, auditMode: Boolean) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Surface(
        onClick = { expanded = !expanded },
        color = if (expanded) QuailSurfaceRaised else QuailSurface,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(ACCOUNT_TYPE_LABELS[type] ?: type.replaceFirstChar { it.uppercase() }, fontWeight = FontWeight.SemiBold)
                    Text("(${group.accounts.size})", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Column(horizontalAlignment = Alignment.End) {
                        Text(currencyFormat.format(creditDisplayTotal(type, group.total)), fontWeight = FontWeight.Bold)
                        creditUsageSubtitle(type, group)?.let {
                            Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    Icon(
                        if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                        contentDescription = null,
                        tint = QuailTextDim,
                    )
                }
            }
            AnimatedVisibility(
                visible = expanded,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically(),
            ) {
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    group.accounts.forEach { account -> BankAccountRow(type, account, onOpenSheet, onOpenAccountDetail) }
                }
            }
        }
    }
}

@Composable
private fun BankAccountRow(
    type: String,
    account: BankAccount,
    onOpenSheet: (HomeSheet) -> Unit,
    onOpenAccountDetail: (accountId: Int, auditMode: Boolean) -> Unit,
) {
    Surface(
        onClick = { onOpenAccountDetail(account.id, false) },
        color = QuailSurface,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(account.name ?: "Account", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                account.lastCsvUploadAt?.let {
                    Text("CSV: ${formatRelativeDays(it)}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
                account.lastManualVerifiedAt?.let {
                    Text("Verified: ${formatRelativeDays(it)}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(currencyFormat.format(creditDisplayTotal(type, account.total)), fontWeight = FontWeight.Bold)
                Row(modifier = Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    SmallPillButton("Verified") {
                        onOpenSheet(HomeSheet.VerifyBalance(account.id, account.name ?: "Account"))
                    }
                    SmallPillButton("Audit") {
                        onOpenAccountDetail(account.id, true)
                    }
                }
            }
        }
    }
}

@Composable
private fun SmallPillButton(label: String, onClick: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** Backend sends ISO-8601 offset datetimes for audit timestamps (e.g.
 * "2026-06-11T23:59:59+00:00") — show them as relative time instead. */
private fun formatRelativeDays(iso: String): String {
    return try {
        val date = java.time.OffsetDateTime.parse(iso).toLocalDate()
        val days = java.time.temporal.ChronoUnit.DAYS.between(date, LocalDate.now())
        when {
            days <= 0 -> "today"
            days == 1L -> "yesterday"
            days < 30 -> "$days days ago"
            days < 365 -> {
                val months = days / 30
                "$months month${if (months > 1) "s" else ""} ago"
            }
            else -> {
                val years = days / 365
                "$years year${if (years > 1) "s" else ""} ago"
            }
        }
    } catch (e: Exception) {
        iso
    }
}

private data class CategoryAmount(val category: String, val amount: Double, val isIncome: Boolean)
private data class DaySummary(val weekday: String, val shortDate: String, val categoryTotals: List<CategoryAmount>)

private fun buildDaySummaries(events: List<UpcomingEvent>): List<DaySummary> {
    return events.groupBy { it.date }
        .toSortedMap()
        .map { (date, dayEvents) ->
            val categoryTotals = dayEvents
                .groupBy { it.category ?: it.merchant ?: "Other" }
                .map { (cat, evs) ->
                    CategoryAmount(
                        category = cat,
                        amount = evs.sumOf { it.amount ?: 0.0 },
                        // Explicit "type" field, same as HomeView.swift's isIncome()
                        // check — amount sign alone isn't a reliable income/expense signal.
                        isIncome = evs.firstOrNull()?.type == "income",
                    )
                }
                .sortedByDescending { abs(it.amount) }
            val parsed = runCatching { LocalDate.parse(date) }.getOrNull()
            DaySummary(
                weekday = parsed?.dayOfWeek?.getDisplayName(TextStyle.SHORT, Locale.US) ?: "",
                shortDate = parsed?.format(DateTimeFormatter.ofPattern("MMM d", Locale.US)) ?: date,
                categoryTotals = categoryTotals,
            )
        }
}

@Composable
private fun UpcomingCard(events: List<UpcomingEvent>) {
    ExpandableCard(title = "Upcoming transactions") {
        val days = remember(events) { buildDaySummaries(events) }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            items(days) { day -> UpcomingDayCard(day) }
        }
    }
}

@Composable
private fun UpcomingDayCard(day: DaySummary) {
    Surface(
        color = QuailSurfaceRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.width(200.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(day.weekday, fontWeight = FontWeight.Bold)
                Text(day.shortDate, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            if (day.categoryTotals.isEmpty()) {
                Text("—", color = QuailTextDim, modifier = Modifier.padding(top = 6.dp))
            } else {
                Column(modifier = Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    day.categoryTotals.take(2).forEach { entry ->
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(entry.category, style = MaterialTheme.typography.bodyMedium)
                            Text(
                                currencyFormat.format(entry.amount),
                                fontWeight = FontWeight.Bold,
                                color = if (entry.isIncome) QuailGoodGreen else QuailBadRed,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                    if (day.categoryTotals.size > 2) {
                        Text(
                            "+${day.categoryTotals.size - 2} more",
                            color = QuailTextDim,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun RecentTransactionsCard(transactions: List<Transaction>, onOpenSheet: (HomeSheet) -> Unit) {
    ExpandableCard(title = "Recent transactions") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            transactions.take(8).forEach { tx -> TransactionRow(tx, onOpenSheet) }
        }
    }
}

@Composable
private fun TransactionRow(tx: Transaction, onOpenSheet: (HomeSheet) -> Unit) {
    Surface(
        onClick = { onOpenSheet(HomeSheet.TransactionDetail(tx.id)) },
        color = QuailSurfaceRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(color = QuailSurface, shape = CircleShape, modifier = Modifier.size(38.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(categoryIcon(tx.category), contentDescription = tx.category, tint = QuailTextDim)
                }
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    tx.merchant?.uppercase() ?: "Transaction",
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium,
                )
                val subtitle = listOfNotNull(tx.bank, tx.card).joinToString(" • ").ifBlank { tx.category ?: "" }
                Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    currencyFormat.format(tx.amount),
                    // HomeView.swift line 1988: amount >= 0 is a debit/expense (red);
                    // negative is a credit/income (green) — opposite of the naive guess.
                    color = if (tx.amount >= 0) QuailBadRed else QuailGoodGreen,
                    fontWeight = FontWeight.Bold,
                )
                (tx.dateISO ?: tx.postedDate)?.let {
                    Text(formatTransactionDate(it), color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

/** dateISO is a plain "YYYY-MM-DD" (see transactions.py's `d AS "dateISO"`);
 * postedDate can be "MM/DD/YY" or "MM/DD/YYYY" (or "unknown") — try dateISO
 * first since it's the normalized column. */
private fun formatTransactionDate(raw: String): String {
    val date = runCatching { LocalDate.parse(raw) }.getOrNull()
        ?: runCatching { LocalDate.parse(raw, DateTimeFormatter.ofPattern("MM/dd/yyyy", Locale.US)) }.getOrNull()
        ?: runCatching { LocalDate.parse(raw, DateTimeFormatter.ofPattern("MM/dd/yy", Locale.US)) }.getOrNull()
        ?: return raw

    val today = LocalDate.now()
    return when (date) {
        today -> "Today"
        today.minusDays(1) -> "Yesterday"
        else -> date.format(DateTimeFormatter.ofPattern("M/d", Locale.US))
    }
}
