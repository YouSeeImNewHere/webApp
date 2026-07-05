package com.quail.android.ui.screens.budget

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
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
import com.quail.android.data.model.BudgetGroup
import com.quail.android.data.model.BudgetSpentCategory
import com.quail.android.data.model.MonthBudget
import com.quail.android.data.model.SinkingFund
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailText
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.Month
import java.time.format.TextStyle
import java.util.Locale
import com.quail.android.bugreport.BugReportTopBarAction

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)
private val FUND_CADENCES = listOf("monthly" to "Monthly", "weekly" to "Weekly", "paycheck" to "Per paycheck", "custom" to "Custom")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BudgetScreen(viewModel: BudgetViewModel, onBack: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Budget", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = isRefreshing,
            onRefresh = { viewModel.pullRefresh() },
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            when (val s = uiState) {
                is BudgetUiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                is BudgetUiState.Error -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(s.message, color = QuailTextDim)
                }
                is BudgetUiState.Success -> BudgetContent(s, viewModel)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BudgetContent(state: BudgetUiState.Success, viewModel: BudgetViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            top = 8.dp,
            bottom = 24.dp,
            start = 12.dp,
            end = 12.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MonthNavRow(state.year, state.month, onPrev = { viewModel.shiftMonth(-1) }, onNext = { viewModel.shiftMonth(1) }) }
        item { KpiGrid(state, viewModel) }
        item { BudgetGroupsCard(state.payload.groups, onAdd = { viewModel.openGroupEditor(null) }, onEdit = { viewModel.openGroupEditor(it) }, onDelete = { viewModel.deleteGroup(it) }) }
        item { SinkingFundsCard(state.payload.funds, viewModel) }
        if (state.payload.spentCategories.isNotEmpty()) {
            item { SpentCategoriesCard(state.payload.spentCategories) }
        }
        if (state.trend.isNotEmpty()) {
            item { TrendCard(state.trend) }
        }
        item { RoundUpsCard(state.roundUps.enabled, onToggle = { viewModel.toggleRoundUps(it) }) }
    }

    state.editingGroup?.let { draft ->
        val content: @Composable () -> Unit = {
            BudgetGroupEditorContent(draft, busy = state.busy, onSave = { viewModel.saveGroup(it) }, onCancel = { viewModel.closeGroupEditor() })
        }
        SideEffect { AppOverlayHost.showBottomSheet(onDismissed = { viewModel.closeGroupEditor() }, content = content) }
        DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
    }
    state.editingFund?.let { draft ->
        val content: @Composable () -> Unit = {
            FundEditorContent(draft, busy = state.busy, onSave = { viewModel.saveFund(it) }, onCancel = { viewModel.closeFundEditor() })
        }
        SideEffect { AppOverlayHost.showBottomSheet(onDismissed = { viewModel.closeFundEditor() }, content = content) }
        DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
    }
    state.adjustingFund?.let { adjust ->
        val content: @Composable () -> Unit = {
            FundAdjustContent(
                adjust,
                busy = state.busy,
                onConfirm = { amount, note -> viewModel.adjustFund(adjust.fund, amount, adjust.isAdd, note) },
                onCancel = { viewModel.closeFundAdjustment() },
            )
        }
        SideEffect { AppOverlayHost.showBottomSheet(onDismissed = { viewModel.closeFundAdjustment() }, content = content) }
        DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
    }
}

@Composable
private fun MonthNavRow(year: Int, month: Int, onPrev: () -> Unit, onNext: () -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        SmallButton("Previous", onClick = onPrev)
        Text(
            "${Month.of(month).getDisplayName(TextStyle.FULL, Locale.US)} $year",
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.titleMedium,
        )
        SmallButton("Next", onClick = onNext)
    }
}

@Composable
private fun SmallButton(label: String, enabled: Boolean = true, onClick: () -> Unit) {
    Surface(onClick = onClick, enabled = enabled, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp)) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelMedium,
            color = if (enabled) Color.Unspecified else QuailTextDim,
        )
    }
}

@Composable
private fun KpiCard(label: String, value: String, valueColor: Color = Color.Unspecified, modifier: Modifier = Modifier) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = valueColor)
        }
    }
}

@Composable
private fun KpiGrid(state: BudgetUiState.Success, viewModel: BudgetViewModel) {
    val mb: MonthBudget? = state.payload.month
    val allocatedTotal = state.payload.groups.sumOf { it.allocated }
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                KpiCard("Income", currency.format(mb?.expectedIncome ?: 0.0), modifier = Modifier.weight(1f))
                KpiCard("Remaining bills", currency.format(mb?.billsRemaining ?: 0.0), modifier = Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                KpiCard("Spent so far", currency.format(mb?.spentSoFar ?: 0.0), modifier = Modifier.weight(1f))
                KpiCard("Allocated", currency.format(allocatedTotal), modifier = Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                KpiCard(
                    "Safe to spend",
                    currency.format(mb?.safeToSpend ?: 0.0),
                    valueColor = if ((mb?.safeToSpend ?: 0.0) < 0) QuailBadRed else QuailText,
                    modifier = Modifier.weight(1f),
                )
                Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.weight(1f)) {
                    Column(Modifier.padding(12.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Left today", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            if (viewModel.isCurrentMonth) {
                                Text(
                                    "Recalc",
                                    color = MaterialTheme.colorScheme.primary,
                                    fontWeight = FontWeight.Bold,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier
                                        .padding(start = 4.dp)
                                        .clickable { viewModel.load(recalc = true) },
                                )
                            }
                        }
                        Text(
                            if (viewModel.isCurrentMonth) currency.format(mb?.dailyLimit ?: 0.0) else "—",
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleMedium,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun BudgetGroupsCard(groups: List<BudgetGroup>, onAdd: () -> Unit, onEdit: (BudgetGroup) -> Unit, onDelete: (BudgetGroup) -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Budgets", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                SmallButton("Add group", onClick = onAdd)
            }
            if (groups.isEmpty()) {
                Text("No budget groups yet.", color = QuailTextDim, modifier = Modifier.padding(top = 10.dp))
            } else {
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    groups.forEach { group -> BudgetGroupRow(group, onEdit = { onEdit(group) }, onDelete = { onDelete(group) }) }
                }
            }
        }
    }
}

@Composable
private fun BudgetGroupRow(group: BudgetGroup, onEdit: () -> Unit, onDelete: () -> Unit) {
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(group.name, fontWeight = FontWeight.Bold)
                    if (group.readOnly) {
                        Text("Read only", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                MiniKV("Allocated", currency.format(group.allocated))
                MiniKV("Cap", group.cap?.let { currency.format(it) } ?: "—")
            }
            Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                MiniKV("Spent", currency.format(group.spent))
                MiniKV(
                    "Remaining",
                    currency.format(group.remaining),
                    valueColor = if (group.remaining < 0 || group.overCap) QuailBadRed else Color.Unspecified,
                )
            }
            if (group.categories.isNotEmpty()) {
                Text(
                    group.categories.joinToString(", "),
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SmallButton(if (group.syntheticKind == "savings_goal") "Save goal" else "Edit", onClick = onEdit)
                if (!group.readOnly) SmallButton("Delete", onClick = onDelete)
            }
        }
    }
}

@Composable
private fun MiniKV(label: String, value: String, valueColor: Color = Color.Unspecified) {
    Column {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Text(value, fontWeight = FontWeight.SemiBold, color = valueColor)
    }
}

@Composable
private fun SinkingFundsCard(funds: List<SinkingFund>, viewModel: BudgetViewModel) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Sinking funds", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                SmallButton("Add fund", onClick = { viewModel.openFundEditor(null) })
            }
            Text(
                "Set money aside for big future expenses so it's not accidentally spendable.",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 4.dp),
            )
            if (funds.isEmpty()) {
                Text("No sinking funds yet.", color = QuailTextDim, modifier = Modifier.padding(top = 10.dp))
            } else {
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    funds.forEach { fund -> SinkingFundRow(fund, viewModel) }
                }
            }
        }
    }
}

@Composable
private fun SinkingFundRow(fund: SinkingFund, viewModel: BudgetViewModel) {
    val progress = if (fund.targetAmount > 0) (fund.reservedBalance / fund.targetAmount).coerceIn(0.0, 1.0) else 0.0
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(fund.name, fontWeight = FontWeight.Bold)
                Text(currency.format(fund.reservedBalance), fontWeight = FontWeight.Bold)
            }
            Text(
                if (fund.targetAmount > 0) "${currency.format(fund.reservedBalance)} / ${currency.format(fund.targetAmount)}" else "${currency.format(fund.reservedBalance)} set aside",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
            )
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp)
                    .height(10.dp)
                    .background(QuailSurface, RoundedCornerShape(8.dp)),
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(fraction = progress.toFloat().coerceIn(0f, 1f))
                        .height(10.dp)
                        .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp)),
                )
            }
            if (fund.neededPerDay != null && fund.targetDate != null) {
                Text(
                    "${currency.format(fund.neededPerDay)} / day to hit by ${fund.targetDate}",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(top = 6.dp),
                )
            } else if (!fund.targetDate.isNullOrBlank()) {
                Text("Target date: ${fund.targetDate}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 6.dp))
            }
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SmallButton("Add money", onClick = { viewModel.openFundAdjustment(fund, true) })
                SmallButton("Use money", onClick = { viewModel.openFundAdjustment(fund, false) })
                SmallButton("Edit", onClick = { viewModel.openFundEditor(fund) })
                SmallButton("Delete", onClick = { viewModel.deleteFund(fund) })
            }
        }
    }
}

@Composable
private fun SpentCategoriesCard(categories: List<BudgetSpentCategory>) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("Categories spent", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(
                "This is read-only. Add a group above only for categories you want to allocate.",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
            )
            categories.sortedByDescending { it.spent }.forEach { cat ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(cat.category, style = MaterialTheme.typography.bodyMedium)
                    Text(currency.format(cat.spent), fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun TrendCard(trend: List<TrendRow>) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("Budget trend (last 6 months)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(
                "Positive means you stayed under allocated budgets. Negative means you overspent allocations.",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
            )
            trend.forEach { row ->
                val delta = row.allocated - row.spent
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text(
                            "${Month.of(row.month).getDisplayName(TextStyle.SHORT, Locale.US)} ${row.year}",
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            "Allocated ${currency.format(row.allocated)} • Spent ${currency.format(row.spent)}",
                            color = QuailTextDim,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                    Text(
                        (if (delta >= 0) "+" else "") + currency.format(delta),
                        fontWeight = FontWeight.Bold,
                        color = if (delta >= 0) QuailGoodGreen else QuailBadRed,
                    )
                }
            }
        }
    }
}

@Composable
private fun RoundUpsCard(enabled: Boolean, onToggle: (Boolean) -> Unit) {
    Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("Round-ups", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(
                "Round purchases up to the next dollar and count the difference as spending in a Round-ups category.",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Enable round-ups")
                Switch(checked = enabled, onCheckedChange = onToggle)
            }
        }
    }
}

// ---- Editor sheets ----

@Composable
private fun BudgetGroupEditorContent(draft: BudgetGroupDraft, busy: Boolean, onSave: (BudgetGroupDraft) -> Unit, onCancel: () -> Unit) {
    var name by remember(draft) { mutableStateOf(draft.name) }
    var allocated by remember(draft) { mutableStateOf(draft.allocated) }
    var capEnabled by remember(draft) { mutableStateOf(draft.capEnabled) }
    var cap by remember(draft) { mutableStateOf(draft.cap) }
    var categoriesText by remember(draft) { mutableStateOf(draft.categoriesText) }

    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Text(if (draft.originalName == null) "Add group" else "Edit group", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Name") },
                enabled = !draft.readOnly,
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = allocated,
                onValueChange = { allocated = it },
                label = { Text("Allocated") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Cap")
                Switch(checked = capEnabled, onCheckedChange = { capEnabled = it }, enabled = !draft.readOnly)
            }
            if (capEnabled) {
                OutlinedTextField(
                    value = cap,
                    onValueChange = { cap = it },
                    label = { Text("Cap amount") },
                    enabled = !draft.readOnly,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (draft.syntheticKind != "savings_goal") {
                OutlinedTextField(
                    value = categoriesText,
                    onValueChange = { categoriesText = it },
                    label = { Text("Categories (comma-separated)") },
                    enabled = !draft.readOnly,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
        Row(Modifier.padding(top = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Surface(onClick = onCancel, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) { Text("Cancel", fontWeight = FontWeight.SemiBold) }
            }
            Surface(
                onClick = { onSave(draft.copy(name = name, allocated = allocated, capEnabled = capEnabled, cap = cap, categoriesText = categoriesText)) },
                enabled = !busy,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.weight(1f),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    if (busy) CircularProgressIndicator(modifier = Modifier.size(20.dp)) else Text("Save", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FundEditorContent(draft: FundDraft, busy: Boolean, onSave: (FundDraft) -> Unit, onCancel: () -> Unit) {
    var name by remember(draft) { mutableStateOf(draft.name) }
    var targetAmount by remember(draft) { mutableStateOf(draft.targetAmount) }
    var targetDate by remember(draft) { mutableStateOf(draft.targetDate) }
    var cadence by remember(draft) { mutableStateOf(draft.cadence) }
    var contribAmount by remember(draft) { mutableStateOf(draft.contribAmount) }
    var showCadenceMenu by remember { mutableStateOf(false) }

    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Text(if (draft.id == null) "Add fund" else "Edit fund", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(value = targetAmount, onValueChange = { targetAmount = it }, label = { Text("Target amount") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(value = targetDate, onValueChange = { targetDate = it }, label = { Text("Target date (YYYY-MM-DD)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Box {
                Surface(onClick = { showCadenceMenu = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
                        Text("Cadence", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                        Text(FUND_CADENCES.firstOrNull { it.first == cadence }?.second ?: cadence, fontWeight = FontWeight.SemiBold)
                    }
                }
                DropdownMenu(expanded = showCadenceMenu, onDismissRequest = { showCadenceMenu = false }) {
                    FUND_CADENCES.forEach { (value, label) ->
                        DropdownMenuItem(text = { Text(label) }, onClick = { cadence = value; showCadenceMenu = false })
                    }
                }
            }
            OutlinedTextField(value = contribAmount, onValueChange = { contribAmount = it }, label = { Text("Planned contribution") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        }
        Row(Modifier.padding(top = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Surface(onClick = onCancel, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) { Text("Cancel", fontWeight = FontWeight.SemiBold) }
            }
            Surface(
                onClick = { onSave(draft.copy(name = name, targetAmount = targetAmount, targetDate = targetDate, cadence = cadence, contribAmount = contribAmount)) },
                enabled = !busy,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.weight(1f),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    if (busy) CircularProgressIndicator(modifier = Modifier.size(20.dp)) else Text("Save", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }
}

@Composable
private fun FundAdjustContent(draft: FundAdjustDraft, busy: Boolean, onConfirm: (Double, String) -> Unit, onCancel: () -> Unit) {
    var amount by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }

    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Text(if (draft.isAdd) "Add money" else "Use money", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(draft.fund.name, color = QuailTextDim, modifier = Modifier.padding(top = 4.dp, bottom = 14.dp))
        OutlinedTextField(value = amount, onValueChange = { amount = it }, label = { Text("Amount") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("Note") }, modifier = Modifier.fillMaxWidth().padding(top = 10.dp))
        Row(Modifier.padding(top = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Surface(onClick = onCancel, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) { Text("Cancel", fontWeight = FontWeight.SemiBold) }
            }
            Surface(
                onClick = { amount.toDoubleOrNull()?.let { onConfirm(it, note) } },
                enabled = !busy,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.weight(1f),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                    if (busy) CircularProgressIndicator(modifier = Modifier.size(20.dp)) else Text("Confirm", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }
}
