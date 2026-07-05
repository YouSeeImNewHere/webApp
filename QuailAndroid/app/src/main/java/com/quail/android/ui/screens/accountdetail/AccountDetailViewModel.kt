package com.quail.android.ui.screens.accountdetail

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.AccountInfoResponse
import com.quail.android.data.model.AccountTransactionsRangeResponse
import com.quail.android.data.model.ChartPoint
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.OffsetDateTime

data class AccountChartRange(val start: LocalDate, val end: LocalDate)

sealed interface AccountChartUiState {
    data object Loading : AccountChartUiState
    data class Error(val message: String) : AccountChartUiState
    data class Success(val points: List<ChartPoint>) : AccountChartUiState
}

sealed interface AccountLedgerUiState {
    data object Loading : AccountLedgerUiState
    data class Error(val message: String) : AccountLedgerUiState
    data class Success(val data: AccountTransactionsRangeResponse) : AccountLedgerUiState
}

sealed interface AddTxState {
    data object Idle : AddTxState
    data object Saving : AddTxState
    data class Error(val message: String) : AddTxState
}

sealed interface VerifyState {
    data object Idle : VerifyState
    data object Saving : VerifyState
    data class Error(val message: String) : VerifyState
}

private val TODAY: LocalDate = LocalDate.now()
private fun clampToToday(date: LocalDate): LocalDate = if (date.isAfter(TODAY)) TODAY else date

private fun quarterRangeFor(year: Int, quarter: Int): AccountChartRange {
    val startMonth = (quarter - 1) * 3 + 1
    val start = LocalDate.of(year, startMonth, 1)
    return AccountChartRange(start, clampToToday(start.plusMonths(3).minusDays(1)))
}

private fun annualRangeFor(year: Int): AccountChartRange =
    AccountChartRange(LocalDate.of(year, 1, 1), clampToToday(LocalDate.of(year, 12, 31)))

private fun monthRangeFor(year: Int, month: Int): AccountChartRange {
    val start = LocalDate.of(year, month, 1)
    return AccountChartRange(start, clampToToday(start.plusMonths(1).minusDays(1)))
}

/** Mirrors NativeAccountPage.swift (chart/ranges) plus the web app's Audit
 * mode (account.js): audit range auto-computed from last_manual_verified_at
 * to today, and per-transaction "checked" state kept purely client-side
 * (SharedPreferences here, localStorage there) — it's never sent to the
 * server, just a personal scratch pad while reconciling a statement. */
class AccountDetailViewModel(
    private val repository: HomeRepository,
    private val accountId: Int,
    appContext: Context,
) : ViewModel() {
    private val _accountInfo = MutableStateFlow<AccountInfoResponse?>(null)
    val accountInfo: StateFlow<AccountInfoResponse?> = _accountInfo.asStateFlow()

    private val _auditMode = MutableStateFlow(false)
    val auditMode: StateFlow<Boolean> = _auditMode.asStateFlow()

    private val _year = MutableStateFlow(TODAY.year)
    val year: StateFlow<Int> = _year.asStateFlow()

    private val _range = MutableStateFlow(annualRangeFor(TODAY.year))
    val range: StateFlow<AccountChartRange> = _range.asStateFlow()

    private val _projectGrowth = MutableStateFlow(false)
    val projectGrowth: StateFlow<Boolean> = _projectGrowth.asStateFlow()

    private val _chartState = MutableStateFlow<AccountChartUiState>(AccountChartUiState.Loading)
    val chartState: StateFlow<AccountChartUiState> = _chartState.asStateFlow()

    private val _ledgerState = MutableStateFlow<AccountLedgerUiState>(AccountLedgerUiState.Loading)
    val ledgerState: StateFlow<AccountLedgerUiState> = _ledgerState.asStateFlow()

    private val _addTxState = MutableStateFlow<AddTxState>(AddTxState.Idle)
    val addTxState: StateFlow<AddTxState> = _addTxState.asStateFlow()

    private val _verifyState = MutableStateFlow<VerifyState>(VerifyState.Idle)
    val verifyState: StateFlow<VerifyState> = _verifyState.asStateFlow()

    private val checkedPrefs = appContext.getSharedPreferences("account_audit_checks_$accountId", Context.MODE_PRIVATE)
    private val _checkedIds = MutableStateFlow<Set<String>>(checkedPrefs.getStringSet("checked", emptySet()) ?: emptySet())
    val checkedIds: StateFlow<Set<String>> = _checkedIds.asStateFlow()

    val canGoToNextYear: Boolean get() = _year.value < TODAY.year

    init {
        loadAccountInfo()
        loadChart()
        loadLedger()
    }

    fun toggleAuditMode() {
        _auditMode.value = !_auditMode.value
        if (_auditMode.value) {
            applyAuditRange()
        } else {
            setRange(annualRangeFor(_year.value))
        }
    }

    private fun applyAuditRange() {
        val lastVerified = _accountInfo.value?.lastManualVerifiedAt
        val start = lastVerified?.let {
            runCatching { OffsetDateTime.parse(it).toLocalDate().plusDays(1) }.getOrNull()
        } ?: LocalDate.of(2000, 1, 1)
        val end = TODAY
        _range.value = AccountChartRange(if (start.isAfter(end)) end else start, end)
        loadLedger()
    }

    fun selectQuarter(quarter: Int) = setRange(quarterRangeFor(_year.value, quarter))
    fun selectAnnual() = setRange(annualRangeFor(_year.value))
    fun selectMonth(month: Int) = setRange(monthRangeFor(_year.value, month))

    fun setCustomRange(start: LocalDate, end: LocalDate) {
        val safeEnd = clampToToday(if (end.isBefore(start)) start else end)
        setRange(AccountChartRange(start, safeEnd))
    }

    fun previousYear() {
        _year.value -= 1
        setRange(annualRangeFor(_year.value))
    }

    fun nextYear() {
        if (!canGoToNextYear) return
        _year.value += 1
        setRange(annualRangeFor(_year.value))
    }

    private fun setRange(newRange: AccountChartRange) {
        _range.value = newRange
        loadChart()
        loadLedger()
    }

    fun setProjectGrowth(enabled: Boolean) {
        _projectGrowth.value = enabled
    }

    private fun loadAccountInfo() {
        viewModelScope.launch {
            _accountInfo.value = runCatching { repository.getAccountInfo(accountId) }.getOrNull()
            if (_auditMode.value) applyAuditRange()
        }
    }

    private fun loadChart() {
        viewModelScope.launch {
            _chartState.value = AccountChartUiState.Loading
            try {
                val r = _range.value
                val points = repository.getAccountSeries(accountId, r.start, r.end)
                _chartState.value = AccountChartUiState.Success(points)
            } catch (e: Exception) {
                _chartState.value = AccountChartUiState.Error(e.message ?: "Couldn't load chart")
            }
        }
    }

    private fun loadLedger() {
        viewModelScope.launch {
            _ledgerState.value = AccountLedgerUiState.Loading
            try {
                val r = _range.value
                val data = repository.getAccountTransactionsRange(accountId, r.start, r.end, limit = 1000)
                _ledgerState.value = AccountLedgerUiState.Success(data)
            } catch (e: Exception) {
                _ledgerState.value = AccountLedgerUiState.Error(e.message ?: "Couldn't load transactions")
            }
        }
    }

    fun refreshAll() {
        loadAccountInfo()
        loadChart()
        loadLedger()
    }

    fun toggleChecked(key: String) {
        val current = _checkedIds.value.toMutableSet()
        if (!current.add(key)) current.remove(key)
        _checkedIds.value = current
        checkedPrefs.edit().putStringSet("checked", current).apply()
    }

    fun verify(date: LocalDate) {
        viewModelScope.launch {
            _verifyState.value = VerifyState.Saving
            try {
                repository.verifyBalance(accountId, date.toString())
                _verifyState.value = VerifyState.Idle
                loadAccountInfo()
                if (_auditMode.value) applyAuditRange() else loadLedger()
            } catch (e: Exception) {
                _verifyState.value = VerifyState.Error(e.message ?: "Verify failed")
            }
        }
    }

    fun addTransaction(amount: Double, merchant: String, status: String, date: LocalDate) {
        viewModelScope.launch {
            _addTxState.value = AddTxState.Saving
            try {
                repository.createTransaction(accountId, amount, merchant, status, date.toString())
                _addTxState.value = AddTxState.Idle
                loadChart()
                loadLedger()
            } catch (e: Exception) {
                _addTxState.value = AddTxState.Error(e.message ?: "Couldn't add transaction")
            }
        }
    }

    class Factory(
        private val repository: HomeRepository,
        private val accountId: Int,
        private val appContext: Context,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            AccountDetailViewModel(repository, accountId, appContext) as T
    }
}

/** Same last-8-point linear extrapolation as NetWorthChartViewModel's
 * projectedPoints(), duplicated here to keep the account chart independent
 * of the home-screen net-worth chart module. */
fun projectedAccountPoints(points: List<ChartPoint>): List<ChartPoint> {
    val sample = points.takeLast(8)
    val first = sample.firstOrNull() ?: return emptyList()
    val last = sample.lastOrNull() ?: return emptyList()
    val firstDate = runCatching { LocalDate.parse(first.date) }.getOrNull() ?: return emptyList()
    val lastDate = runCatching { LocalDate.parse(last.date) }.getOrNull() ?: return emptyList()
    val intervalDays = java.time.temporal.ChronoUnit.DAYS.between(firstDate, lastDate).toInt().coerceAtLeast(1)
    val slope = (last.value - first.value) / intervalDays

    return (1..7).map { step ->
        val date = lastDate.plusDays(step.toLong())
        ChartPoint(date = date.toString(), value = last.value + slope * step)
    }
}
