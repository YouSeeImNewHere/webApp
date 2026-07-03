package com.quailcash.android.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.ExtraSavedDetail
import com.quailcash.android.data.model.HomePayload
import com.quailcash.android.data.model.SpentSoFarBreakdown
import com.quailcash.android.data.model.SpentSoFarTransaction
import com.quailcash.android.data.model.TransactionDetail
import com.quailcash.android.data.model.UpcomingEvent
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

sealed interface HomeUiState {
    data object Loading : HomeUiState
    data class Error(val message: String) : HomeUiState
    data class Success(val payload: HomePayload, val upcoming: List<UpcomingEvent>) : HomeUiState
}

sealed interface ExtraSavedUiState {
    data object Idle : ExtraSavedUiState
    data object Loading : ExtraSavedUiState
    data class Error(val message: String) : ExtraSavedUiState
    data class Success(val detail: ExtraSavedDetail) : ExtraSavedUiState
}

sealed interface TransactionDetailUiState {
    data object Idle : TransactionDetailUiState
    data object Loading : TransactionDetailUiState
    data class Error(val message: String) : TransactionDetailUiState
    data class Success(val detail: TransactionDetail, val actionInFlight: Boolean = false) : TransactionDetailUiState
    data object Deleted : TransactionDetailUiState
}

sealed interface VerifyBalanceUiState {
    data object Idle : VerifyBalanceUiState
    data object Loading : VerifyBalanceUiState
    data class Error(val message: String) : VerifyBalanceUiState
    data object Success : VerifyBalanceUiState
}

sealed interface SpentSoFarUiState {
    data object Idle : SpentSoFarUiState
    data object Loading : SpentSoFarUiState
    data class Error(val message: String) : SpentSoFarUiState
    data class Success(
        val breakdown: SpentSoFarBreakdown,
        val expandedCategory: String? = null,
        val categoryLoading: String? = null,
        val categoryTransactions: Map<String, List<SpentSoFarTransaction>> = emptyMap(),
    ) : SpentSoFarUiState
}

class HomeViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    private val _extraSavedState = MutableStateFlow<ExtraSavedUiState>(ExtraSavedUiState.Idle)
    val extraSavedState: StateFlow<ExtraSavedUiState> = _extraSavedState.asStateFlow()

    private val _transactionDetailState = MutableStateFlow<TransactionDetailUiState>(TransactionDetailUiState.Idle)
    val transactionDetailState: StateFlow<TransactionDetailUiState> = _transactionDetailState.asStateFlow()

    private val _verifyBalanceState = MutableStateFlow<VerifyBalanceUiState>(VerifyBalanceUiState.Idle)
    val verifyBalanceState: StateFlow<VerifyBalanceUiState> = _verifyBalanceState.asStateFlow()

    private val _spentSoFarState = MutableStateFlow<SpentSoFarUiState>(SpentSoFarUiState.Idle)
    val spentSoFarState: StateFlow<SpentSoFarUiState> = _spentSoFarState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.value = HomeUiState.Loading
            try {
                val payload = repository.getHome()
                val upcoming = runCatching { repository.getUpcoming() }.getOrDefault(emptyList())
                _uiState.value = HomeUiState.Success(payload, upcoming)
            } catch (e: Exception) {
                _uiState.value = HomeUiState.Error(e.message ?: "Something went wrong")
            }
        }
    }

    /** Pull-to-refresh: keeps the current cards on screen instead of
     * flashing the full loading state, and fails silently on error. */
    fun pullRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val payload = repository.getHome()
                val upcoming = runCatching { repository.getUpcoming() }.getOrDefault(emptyList())
                _uiState.value = HomeUiState.Success(payload, upcoming)
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    fun loadExtraSavedDetail() {
        viewModelScope.launch {
            _extraSavedState.value = ExtraSavedUiState.Loading
            try {
                _extraSavedState.value = ExtraSavedUiState.Success(repository.getExtraSavedDetail())
            } catch (e: Exception) {
                _extraSavedState.value = ExtraSavedUiState.Error(e.message ?: "Couldn't load extra saved")
            }
        }
    }

    fun loadTransactionDetail(id: String) {
        viewModelScope.launch {
            _transactionDetailState.value = TransactionDetailUiState.Loading
            try {
                _transactionDetailState.value = TransactionDetailUiState.Success(repository.getTransactionDetail(id))
            } catch (e: Exception) {
                _transactionDetailState.value = TransactionDetailUiState.Error(e.message ?: "Couldn't load transaction")
            }
        }
    }

    fun verifyBalance(accountId: Int, verifiedDate: String?) {
        viewModelScope.launch {
            _verifyBalanceState.value = VerifyBalanceUiState.Loading
            try {
                repository.verifyBalance(accountId, verifiedDate)
                _verifyBalanceState.value = VerifyBalanceUiState.Success
                refresh()
            } catch (e: Exception) {
                _verifyBalanceState.value = VerifyBalanceUiState.Error(e.message ?: "Couldn't verify balance")
            }
        }
    }

    private inline fun runTransactionAction(crossinline block: suspend () -> TransactionDetail) {
        val current = _transactionDetailState.value as? TransactionDetailUiState.Success ?: return
        viewModelScope.launch {
            _transactionDetailState.value = current.copy(actionInFlight = true)
            try {
                _transactionDetailState.value = TransactionDetailUiState.Success(block())
                refresh()
            } catch (e: Exception) {
                _transactionDetailState.value = TransactionDetailUiState.Error(e.message ?: "That action failed")
            }
        }
    }

    fun setTransactionCategory(id: String, category: String) =
        runTransactionAction { repository.setTransactionCategory(id, category) }

    fun updateTransactionMeta(id: String, status: String?, postedDate: String?) =
        runTransactionAction { repository.updateTransactionMeta(id, status, postedDate) }

    fun invertTransactionAmount(id: String) =
        runTransactionAction { repository.invertTransactionAmount(id) }

    fun setTransactionIgnored(id: String, ignored: Boolean) =
        runTransactionAction { repository.setTransactionIgnored(id, ignored) }

    fun deleteTransaction(id: String) {
        val current = _transactionDetailState.value as? TransactionDetailUiState.Success ?: return
        viewModelScope.launch {
            _transactionDetailState.value = current.copy(actionInFlight = true)
            try {
                repository.deleteTransaction(id)
                _transactionDetailState.value = TransactionDetailUiState.Deleted
                refresh()
            } catch (e: Exception) {
                _transactionDetailState.value = TransactionDetailUiState.Error(e.message ?: "Couldn't delete transaction")
            }
        }
    }

    fun createFinancingPlan(transactionId: String, label: String, totalAmount: Double, totalMonths: Int) {
        val current = _transactionDetailState.value as? TransactionDetailUiState.Success ?: return
        viewModelScope.launch {
            _transactionDetailState.value = current.copy(actionInFlight = true)
            try {
                repository.createFinancingPlan(label, totalAmount, totalMonths, transactionId)
                _transactionDetailState.value = current.copy(actionInFlight = false)
            } catch (e: Exception) {
                _transactionDetailState.value = TransactionDetailUiState.Error(e.message ?: "Couldn't create financing plan")
            }
        }
    }

    fun loadSpentSoFarBreakdown() {
        viewModelScope.launch {
            _spentSoFarState.value = SpentSoFarUiState.Loading
            try {
                val today = LocalDate.now()
                val monthStart = today.withDayOfMonth(1)
                _spentSoFarState.value = SpentSoFarUiState.Success(repository.getSpentSoFarBreakdown(monthStart, today))
            } catch (e: Exception) {
                _spentSoFarState.value = SpentSoFarUiState.Error(e.message ?: "Couldn't load spending breakdown")
            }
        }
    }

    fun toggleSpentSoFarCategory(category: String) {
        val current = _spentSoFarState.value as? SpentSoFarUiState.Success ?: return
        if (current.expandedCategory == category) {
            _spentSoFarState.value = current.copy(expandedCategory = null)
            return
        }
        _spentSoFarState.value = current.copy(expandedCategory = category)
        if (current.categoryTransactions.containsKey(category)) return
        viewModelScope.launch {
            _spentSoFarState.value = (_spentSoFarState.value as? SpentSoFarUiState.Success)?.copy(categoryLoading = category) ?: return@launch
            try {
                val today = LocalDate.now()
                val monthStart = today.withDayOfMonth(1)
                val txs = repository.getSpentSoFarTransactions(category, monthStart, today)
                val latest = _spentSoFarState.value as? SpentSoFarUiState.Success ?: return@launch
                _spentSoFarState.value = latest.copy(
                    categoryLoading = null,
                    categoryTransactions = latest.categoryTransactions + (category to txs),
                )
            } catch (e: Exception) {
                val latest = _spentSoFarState.value as? SpentSoFarUiState.Success ?: return@launch
                _spentSoFarState.value = latest.copy(categoryLoading = null)
            }
        }
    }

    fun clearExtraSaved() { _extraSavedState.value = ExtraSavedUiState.Idle }
    fun clearTransactionDetail() { _transactionDetailState.value = TransactionDetailUiState.Idle }
    fun clearVerifyBalance() { _verifyBalanceState.value = VerifyBalanceUiState.Idle }
    fun clearSpentSoFar() { _spentSoFarState.value = SpentSoFarUiState.Idle }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return HomeViewModel(repository) as T
        }
    }
}
