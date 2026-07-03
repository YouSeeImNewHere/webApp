package com.quailcash.android.ui.screens.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quailcash.android.data.model.Transaction
import com.quailcash.android.ui.theme.QuailBadRed
import com.quailcash.android.ui.theme.QuailGoodGreen
import com.quailcash.android.ui.theme.QuailSurface
import com.quailcash.android.ui.theme.QuailSurfaceRaised
import com.quailcash.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.util.Locale

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

private val AMOUNT_MODES = listOf("any" to "Any", "exact" to "Exact", "min" to "Min", "max" to "Max", "between" to "Between")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AllTransactionsTab(padding: PaddingValues, viewModel: AllTransactionsViewModel, onOpenSheet: (HomeSheet) -> Unit) {
    val state by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { viewModel.pullRefresh() },
        modifier = Modifier.fillMaxSize().padding(padding),
    ) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            top = 8.dp,
            bottom = 16.dp,
            start = 12.dp,
            end = 12.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        when (val s = state) {
            is AllTransactionsUiState.Loading -> item {
                Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            }
            is AllTransactionsUiState.Error -> item {
                Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) { Text(s.message, color = QuailTextDim) }
            }
            is AllTransactionsUiState.Success -> {
                item { FilterCard(s, onSearch = { viewModel.search(it) }, onClear = { viewModel.clearFilters() }) }
                if (s.transactions.isEmpty()) {
                    item {
                        Box(Modifier.fillMaxWidth().padding(vertical = 30.dp), contentAlignment = Alignment.Center) {
                            Text("No matching transactions.", color = QuailTextDim)
                        }
                    }
                } else {
                    items(s.transactions, key = { it.id }) { tx ->
                        AllTransactionRow(tx, onClick = { onOpenSheet(HomeSheet.TransactionDetail(tx.id)) })
                    }
                    if (s.hasMore) {
                        item {
                            Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                                if (s.loadingMore) {
                                    CircularProgressIndicator(modifier = Modifier.size(24.dp))
                                } else {
                                    Surface(onClick = { viewModel.loadMore() }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                                        Text("Load more", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.SemiBold)
                                    }
                                }
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
private fun FilterCard(state: AllTransactionsUiState.Success, onSearch: (TransactionFilters) -> Unit, onClear: () -> Unit) {
    var merchant by remember(state.filters) { mutableStateOf(state.filters.merchant) }
    var account by remember(state.filters) { mutableStateOf(state.filters.account) }
    var category by remember(state.filters) { mutableStateOf(state.filters.category) }
    var start by remember(state.filters) { mutableStateOf(state.filters.start) }
    var end by remember(state.filters) { mutableStateOf(state.filters.end) }
    var amountMode by remember(state.filters) { mutableStateOf(state.filters.amountMode) }
    var amountA by remember(state.filters) { mutableStateOf(state.filters.amountA) }
    var amountB by remember(state.filters) { mutableStateOf(state.filters.amountB) }
    var amountAbs by remember(state.filters) { mutableStateOf(state.filters.amountAbs) }

    val accountNames = remember(state.bankInfo) {
        state.bankInfo.accounts.mapNotNull { it.name } + state.bankInfo.creditCards.mapNotNull { it.name }
    }

    Surface(color = QuailSurface, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = merchant,
                onValueChange = { merchant = it },
                label = { Text("Merchant") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DropdownField("Account", account, listOf("" to "Any account") + accountNames.map { it to it }, Modifier.weight(1f)) { account = it }
                DropdownField("Category", category, listOf("" to "Any category") + state.categories.map { it to it }, Modifier.weight(1f)) { category = it }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = start, onValueChange = { start = it }, label = { Text("From (yyyy-mm-dd)") }, singleLine = true, modifier = Modifier.weight(1f))
                OutlinedTextField(value = end, onValueChange = { end = it }, label = { Text("To (yyyy-mm-dd)") }, singleLine = true, modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DropdownField("Amount", amountMode, AMOUNT_MODES, Modifier.weight(1f)) { amountMode = it }
                if (amountMode != "any") {
                    OutlinedTextField(value = amountA, onValueChange = { amountA = it }, label = { Text("Value") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                if (amountMode == "between") {
                    OutlinedTextField(value = amountB, onValueChange = { amountB = it }, label = { Text("And") }, singleLine = true, modifier = Modifier.weight(1f))
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("ABS (treat -50 and +50 the same)", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
                Switch(checked = amountAbs, onCheckedChange = { amountAbs = it })
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Surface(onClick = onClear, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                    Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) { Text("Clear", fontWeight = FontWeight.SemiBold) }
                }
                Surface(
                    onClick = {
                        onSearch(TransactionFilters(merchant, account, category, start, end, amountMode, amountA, amountB, amountAbs))
                    },
                    color = MaterialTheme.colorScheme.primary,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                        Text("Search", fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                }
            }
        }
    }
}

@Composable
private fun DropdownField(label: String, value: String, options: List<Pair<String, String>>, modifier: Modifier = Modifier, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val displayLabel = options.firstOrNull { it.first == value }?.second ?: label
    Box(modifier) {
        Surface(onClick = { expanded = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                Text(displayLabel, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (optionValue, optionLabel) ->
                DropdownMenuItem(text = { Text(optionLabel) }, onClick = { onSelect(optionValue); expanded = false })
            }
        }
    }
}

@Composable
private fun AllTransactionRow(tx: Transaction, onClick: () -> Unit) {
    Surface(onClick = onClick, color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(color = QuailSurface, shape = CircleShape, modifier = Modifier.size(38.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Text(tx.merchant?.firstOrNull()?.uppercaseChar()?.toString() ?: "?", fontWeight = FontWeight.Bold)
                }
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(tx.merchant?.uppercase() ?: "Transaction", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                val subtitle = listOfNotNull(tx.bank, tx.card).joinToString(" • ").ifBlank { tx.category ?: "" }
                Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            Text(
                currency.format(tx.amount),
                color = if (tx.amount >= 0) QuailBadRed else QuailGoodGreen,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}
