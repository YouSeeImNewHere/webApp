package com.quailcash.android.ui.screens.budget

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.BudgetGroup
import com.quailcash.android.data.model.PageBudgetResponse
import com.quailcash.android.data.model.RoundUpSettings
import com.quailcash.android.data.model.SinkingFund
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

data class TrendRow(val year: Int, val month: Int, val allocated: Double, val spent: Double)

data class BudgetGroupDraft(
    val originalName: String?,
    val name: String = "",
    val allocated: String = "0",
    val capEnabled: Boolean = false,
    val cap: String = "",
    val categoriesText: String = "",
    val readOnly: Boolean = false,
    val syntheticKind: String? = null,
    val savingsMode: String = "percent",
)

data class FundDraft(
    val id: Int?,
    val name: String = "",
    val targetAmount: String = "0",
    val targetDate: String = "",
    val cadence: String = "monthly",
    val contribAmount: String = "0",
)

data class FundAdjustDraft(val fund: SinkingFund, val isAdd: Boolean)

sealed interface BudgetUiState {
    data object Loading : BudgetUiState
    data class Error(val message: String) : BudgetUiState
    data class Success(
        val year: Int,
        val month: Int,
        val payload: PageBudgetResponse,
        val roundUps: RoundUpSettings = RoundUpSettings(),
        val trend: List<TrendRow> = emptyList(),
        val busy: Boolean = false,
        val editingGroup: BudgetGroupDraft? = null,
        val editingFund: FundDraft? = null,
        val adjustingFund: FundAdjustDraft? = null,
        val errorMessage: String? = null,
    ) : BudgetUiState
}

class BudgetViewModel(private val repository: HomeRepository) : ViewModel() {
    private val today = LocalDate.now()
    private var year = today.year
    private var month = today.monthValue

    private val _uiState = MutableStateFlow<BudgetUiState>(BudgetUiState.Loading)
    val uiState: StateFlow<BudgetUiState> = _uiState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        load()
    }

    val isCurrentMonth: Boolean get() = year == today.year && month == today.monthValue

    fun shiftMonth(delta: Int) {
        val total = (year * 12 + (month - 1)) + delta
        year = total / 12
        month = total % 12 + 1
        load()
    }

    fun load(recalc: Boolean = false) {
        viewModelScope.launch {
            _uiState.value = BudgetUiState.Loading
            try {
                val payload = repository.getPageBudget(year, month, recalc)
                val roundUps = runCatching { repository.getRoundUps() }.getOrDefault(RoundUpSettings())
                _uiState.value = BudgetUiState.Success(year, month, payload, roundUps)
                loadTrend()
            } catch (e: Exception) {
                _uiState.value = BudgetUiState.Error(e.message ?: "Couldn't load budget")
            }
        }
    }

    /** Pull-to-refresh: reloads the visible month, keeping current content
     * on screen instead of flashing Loading. */
    fun pullRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val payload = repository.getPageBudget(year, month)
                val roundUps = runCatching { repository.getRoundUps() }.getOrDefault(RoundUpSettings())
                _uiState.value = BudgetUiState.Success(year, month, payload, roundUps)
                loadTrend()
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    private fun loadTrend() {
        viewModelScope.launch {
            val rows = mutableListOf<TrendRow>()
            var y = year
            var m = month
            repeat(6) {
                try {
                    val mb = repository.getMonthBudget(y, m)
                    rows.add(0, TrendRow(y, m, mb.allocationsTotal, mb.budgetedSpentTotal))
                } catch (e: Exception) {
                    // Skip months that fail to load — trend is best-effort.
                }
                val total = y * 12 + (m - 1) - 1
                y = total / 12
                m = total % 12 + 1
            }
            val current = _uiState.value as? BudgetUiState.Success ?: return@launch
            _uiState.value = current.copy(trend = rows)
        }
    }

    fun openGroupEditor(group: BudgetGroup?) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        val draft = if (group == null) {
            BudgetGroupDraft(originalName = null)
        } else {
            BudgetGroupDraft(
                originalName = group.name,
                name = group.name,
                allocated = group.allocated.toString(),
                capEnabled = group.cap != null,
                cap = group.cap?.toString() ?: "",
                categoriesText = group.categories.joinToString(", "),
                readOnly = group.readOnly,
                syntheticKind = group.syntheticKind,
                savingsMode = current.payload.savingsGoalCfg?.mode ?: "percent",
            )
        }
        _uiState.value = current.copy(editingGroup = draft)
    }

    fun closeGroupEditor() {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        _uiState.value = current.copy(editingGroup = null)
    }

    fun saveGroup(draft: BudgetGroupDraft) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        val allocated = draft.allocated.toDoubleOrNull() ?: 0.0
        _uiState.value = current.copy(busy = true)
        viewModelScope.launch {
            try {
                if (draft.syntheticKind == "savings_goal") {
                    repository.setSavingsGoal(draft.savingsMode, allocated)
                } else {
                    val cap = if (draft.capEnabled) draft.cap.toDoubleOrNull() else null
                    val categories = draft.categoriesText.split(",").map { it.trim() }.filter { it.isNotEmpty() }
                    repository.upsertBudgetGroup(year, month, draft.name.trim(), allocated, cap, categories)
                }
                load()
            } catch (e: Exception) {
                _uiState.value = current.copy(busy = false, errorMessage = e.message ?: "Couldn't save group")
            }
        }
    }

    fun deleteGroup(group: BudgetGroup) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        _uiState.value = current.copy(busy = true)
        viewModelScope.launch {
            try {
                repository.deleteBudgetGroup(year, month, group.name)
                load()
            } catch (e: Exception) {
                _uiState.value = current.copy(busy = false, errorMessage = e.message ?: "Couldn't delete group")
            }
        }
    }

    fun openFundEditor(fund: SinkingFund?) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        val draft = if (fund == null) {
            FundDraft(id = null)
        } else {
            FundDraft(
                id = fund.id,
                name = fund.name,
                targetAmount = fund.targetAmount.toString(),
                targetDate = fund.targetDate ?: "",
                cadence = fund.cadence,
                contribAmount = fund.contribAmount.toString(),
            )
        }
        _uiState.value = current.copy(editingFund = draft)
    }

    fun closeFundEditor() {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        _uiState.value = current.copy(editingFund = null)
    }

    fun saveFund(draft: FundDraft) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        val targetAmount = draft.targetAmount.toDoubleOrNull() ?: 0.0
        val contribAmount = draft.contribAmount.toDoubleOrNull() ?: 0.0
        val targetDate = draft.targetDate.trim().ifEmpty { null }
        _uiState.value = current.copy(busy = true)
        viewModelScope.launch {
            try {
                if (draft.id != null) {
                    repository.updateFund(draft.id, draft.name.trim(), targetAmount, targetDate, draft.cadence, contribAmount)
                } else {
                    repository.createFund(draft.name.trim(), targetAmount, targetDate, draft.cadence, contribAmount)
                }
                load()
            } catch (e: Exception) {
                _uiState.value = current.copy(busy = false, errorMessage = e.message ?: "Couldn't save fund")
            }
        }
    }

    fun deleteFund(fund: SinkingFund) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        _uiState.value = current.copy(busy = true)
        viewModelScope.launch {
            try {
                repository.deleteFund(fund.id)
                load()
            } catch (e: Exception) {
                _uiState.value = current.copy(busy = false, errorMessage = e.message ?: "Couldn't delete fund")
            }
        }
    }

    fun openFundAdjustment(fund: SinkingFund, isAdd: Boolean) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        _uiState.value = current.copy(adjustingFund = FundAdjustDraft(fund, isAdd))
    }

    fun closeFundAdjustment() {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        _uiState.value = current.copy(adjustingFund = null)
    }

    fun adjustFund(fund: SinkingFund, amount: Double, isAdd: Boolean, note: String) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        val signed = if (isAdd) kotlin.math.abs(amount) else -kotlin.math.abs(amount)
        _uiState.value = current.copy(busy = true)
        viewModelScope.launch {
            try {
                repository.adjustFund(fund.id, signed, note)
                load()
            } catch (e: Exception) {
                _uiState.value = current.copy(busy = false, errorMessage = e.message ?: "Couldn't adjust fund")
            }
        }
    }

    fun toggleRoundUps(enabled: Boolean) {
        val current = _uiState.value as? BudgetUiState.Success ?: return
        viewModelScope.launch {
            try {
                val result = repository.setRoundUps(enabled)
                _uiState.value = current.copy(roundUps = result)
            } catch (e: Exception) {
                // Ignore — toggle reverts visually on next load.
            }
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return BudgetViewModel(repository) as T
        }
    }
}
