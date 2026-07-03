package com.quailcash.android.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.BankInfoOptions
import com.quailcash.android.data.model.Transaction
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private const val PAGE_SIZE = 50

data class TransactionFilters(
    val merchant: String = "",
    val account: String = "",
    val category: String = "",
    val start: String = "",
    val end: String = "",
    val amountMode: String = "any", // any/exact/min/max/between
    val amountA: String = "",
    val amountB: String = "",
    val amountAbs: Boolean = true,
)

sealed interface AllTransactionsUiState {
    data object Loading : AllTransactionsUiState
    data class Error(val message: String) : AllTransactionsUiState
    data class Success(
        val transactions: List<Transaction>,
        val hasMore: Boolean,
        val loadingMore: Boolean = false,
        val bankInfo: BankInfoOptions = BankInfoOptions(),
        val categories: List<String> = emptyList(),
        val filters: TransactionFilters = TransactionFilters(),
    ) : AllTransactionsUiState
}

class AllTransactionsViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<AllTransactionsUiState>(AllTransactionsUiState.Loading)
    val uiState: StateFlow<AllTransactionsUiState> = _uiState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        viewModelScope.launch {
            val bankInfo = runCatching { repository.getBankInfo() }.getOrDefault(BankInfoOptions())
            val categories = runCatching { repository.getCategories() }.getOrDefault(emptyList())
            loadInternal(TransactionFilters(), bankInfo, categories)
        }
    }

    fun search(filters: TransactionFilters) {
        val current = _uiState.value as? AllTransactionsUiState.Success
        viewModelScope.launch {
            loadInternal(filters, current?.bankInfo ?: BankInfoOptions(), current?.categories ?: emptyList())
        }
    }

    fun clearFilters() = search(TransactionFilters())

    /** Pull-to-refresh: re-runs the first page with the current filters,
     * keeping whatever's on screen visible instead of flashing Loading. */
    fun pullRefresh() {
        val current = _uiState.value as? AllTransactionsUiState.Success ?: return
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val f = current.filters
                val page = repository.getTransactionsAll(
                    limit = PAGE_SIZE,
                    offset = 0,
                    merchant = f.merchant,
                    account = f.account,
                    category = f.category,
                    start = f.start,
                    end = f.end,
                    amtMin = amountMinFor(f),
                    amtMax = amountMaxFor(f),
                    amtAbs = f.amountAbs,
                )
                _uiState.value = current.copy(transactions = page, hasMore = page.size >= PAGE_SIZE)
            } catch (e: Exception) {
                // Keep whatever was already showing.
            }
            _isRefreshing.value = false
        }
    }

    fun loadMore() {
        val current = _uiState.value as? AllTransactionsUiState.Success ?: return
        if (!current.hasMore || current.loadingMore) return
        _uiState.value = current.copy(loadingMore = true)
        viewModelScope.launch {
            try {
                val f = current.filters
                val amtMin = amountMinFor(f)
                val amtMax = amountMaxFor(f)
                val page = repository.getTransactionsAll(
                    limit = PAGE_SIZE,
                    offset = current.transactions.size,
                    merchant = f.merchant,
                    account = f.account,
                    category = f.category,
                    start = f.start,
                    end = f.end,
                    amtMin = amtMin,
                    amtMax = amtMax,
                    amtAbs = f.amountAbs,
                )
                val latest = _uiState.value as? AllTransactionsUiState.Success ?: return@launch
                _uiState.value = latest.copy(
                    transactions = latest.transactions + page,
                    hasMore = page.size >= PAGE_SIZE,
                    loadingMore = false,
                )
            } catch (e: Exception) {
                val latest = _uiState.value as? AllTransactionsUiState.Success ?: return@launch
                _uiState.value = latest.copy(loadingMore = false)
            }
        }
    }

    private suspend fun loadInternal(filters: TransactionFilters, bankInfo: BankInfoOptions, categories: List<String>) {
        _uiState.value = AllTransactionsUiState.Loading
        try {
            val amtMin = amountMinFor(filters)
            val amtMax = amountMaxFor(filters)
            val page = repository.getTransactionsAll(
                limit = PAGE_SIZE,
                offset = 0,
                merchant = filters.merchant,
                account = filters.account,
                category = filters.category,
                start = filters.start,
                end = filters.end,
                amtMin = amtMin,
                amtMax = amtMax,
                amtAbs = filters.amountAbs,
            )
            _uiState.value = AllTransactionsUiState.Success(
                transactions = page,
                hasMore = page.size >= PAGE_SIZE,
                bankInfo = bankInfo,
                categories = categories,
                filters = filters,
            )
        } catch (e: Exception) {
            _uiState.value = AllTransactionsUiState.Error(e.message ?: "Couldn't load transactions")
        }
    }

    private fun amountMinFor(f: TransactionFilters): Double? = when (f.amountMode) {
        "exact", "min", "between" -> f.amountA.toDoubleOrNull()
        else -> null
    }

    private fun amountMaxFor(f: TransactionFilters): Double? = when (f.amountMode) {
        "exact" -> f.amountA.toDoubleOrNull()
        "max" -> f.amountA.toDoubleOrNull()
        "between" -> f.amountB.toDoubleOrNull()
        else -> null
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return AllTransactionsViewModel(repository) as T
        }
    }
}
