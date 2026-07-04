package com.quail.android.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.UnassignedTransaction
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PendingRule(val category: String, val keywords: List<String>)

sealed interface UnassignedUiState {
    data object Loading : UnassignedUiState
    data class Error(val message: String) : UnassignedUiState
    data class Ready(
        val mode: String = "freq",
        val rows: List<UnassignedTransaction> = emptyList(),
        val index: Int = 0,
        val skipped: List<UnassignedTransaction> = emptyList(),
        val showSkipped: Boolean = false,
        val deferApplyUntilClose: Boolean = false,
        val pendingDeferredRules: List<PendingRule> = emptyList(),
        val categories: List<String> = emptyList(),
        val categoryText: String = "",
        val keywordsText: String = "",
        val saving: Boolean = false,
        val statusMessage: String? = null,
        val closing: Boolean = false,
    ) : UnassignedUiState
}

/** Mirrors HomeView.swift's UnassignedWizardSheetView: Skip/Save rule are
 * local queue operations against a fetched batch of up to 25 candidates;
 * only "Save rule" (when not deferred) and the deferred-rule flush on close
 * hit the network. */
class UnassignedWizardViewModel(
    private val repository: HomeRepository,
    private val onRuleApplied: () -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow<UnassignedUiState>(UnassignedUiState.Loading)
    val state: StateFlow<UnassignedUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val categories = runCatching { repository.getCategories() }.getOrDefault(emptyList())
            val rows = try {
                repository.getUnassigned(limit = 25, mode = "freq")
            } catch (e: Exception) {
                _state.value = UnassignedUiState.Error(e.message ?: "Couldn't load unassigned transactions")
                return@launch
            }
            _state.value = UnassignedUiState.Ready(rows = rows, categories = categories)
        }
    }

    private fun ready(): UnassignedUiState.Ready? = _state.value as? UnassignedUiState.Ready

    fun setMode(mode: String) {
        val s = ready() ?: return
        if (s.mode == mode) return
        _state.value = s.copy(mode = mode, saving = true)
        viewModelScope.launch {
            val rows = try {
                repository.getUnassigned(limit = 25, mode = mode)
            } catch (e: Exception) {
                _state.value = (ready() ?: s).copy(saving = false, statusMessage = e.message ?: "Couldn't load")
                return@launch
            }
            _state.value = (ready() ?: s).copy(rows = rows, index = 0, saving = false)
        }
    }

    fun move(delta: Int) {
        val s = ready() ?: return
        if (s.rows.isEmpty()) return
        _state.value = s.copy(index = (s.index + delta).coerceIn(0, s.rows.size - 1))
    }

    fun setCategoryText(text: String) { ready()?.let { _state.value = it.copy(categoryText = text) } }
    fun setKeywordsText(text: String) { ready()?.let { _state.value = it.copy(keywordsText = text) } }

    fun appendKeyword(word: String) {
        val s = ready() ?: return
        val existing = parseKeywords(s.keywordsText)
        if (existing.contains(word)) return
        val next = if (existing.isEmpty()) word else existing.joinToString(", ") + ", " + word
        _state.value = s.copy(keywordsText = next)
    }

    fun toggleShowSkipped() { ready()?.let { _state.value = it.copy(showSkipped = !it.showSkipped) } }
    fun setDeferApplyUntilClose(defer: Boolean) { ready()?.let { _state.value = it.copy(deferApplyUntilClose = defer) } }

    private fun parseKeywords(text: String): List<String> =
        text.split(",").map { it.trim() }.filter { it.isNotEmpty() }

    private fun removeCurrentAndAdvance() {
        val s = ready() ?: return
        if (s.rows.isEmpty()) return
        val nextRows = s.rows.toMutableList().apply { removeAt(s.index) }
        val nextIndex = if (s.index >= nextRows.size) (nextRows.size - 1).coerceAtLeast(0) else s.index
        _state.value = s.copy(rows = nextRows, index = nextIndex, categoryText = "", keywordsText = "")
        if (nextRows.isEmpty()) {
            viewModelScope.launch {
                val refreshed = runCatching { repository.getUnassigned(limit = 25, mode = s.mode) }.getOrDefault(emptyList())
                val latest = ready() ?: return@launch
                _state.value = latest.copy(
                    rows = refreshed,
                    index = 0,
                    statusMessage = if (refreshed.isEmpty()) "No additional unassigned transactions right now." else null,
                )
            }
        }
    }

    fun skipCurrent() {
        val s = ready() ?: return
        val current = s.rows.getOrNull(s.index) ?: return
        _state.value = s.copy(skipped = s.skipped + current)
        removeCurrentAndAdvance()
    }

    fun restoreSkipped(atIndex: Int) {
        val s = ready() ?: return
        if (atIndex !in s.skipped.indices) return
        val tx = s.skipped[atIndex]
        val nextSkipped = s.skipped.toMutableList().apply { removeAt(atIndex) }
        val insertAt = s.index.coerceAtMost(s.rows.size)
        val nextRows = s.rows.toMutableList().apply { add(insertAt, tx) }
        _state.value = s.copy(rows = nextRows, skipped = nextSkipped, index = s.index.coerceAtMost(nextRows.size - 1))
    }

    fun saveRule() {
        val s = ready() ?: return
        val category = s.categoryText.trim()
        val keywords = parseKeywords(s.keywordsText)
        if (category.isEmpty()) {
            _state.value = s.copy(statusMessage = "Enter a category.")
            return
        }
        if (keywords.isEmpty()) {
            _state.value = s.copy(statusMessage = "Enter at least one keyword.")
            return
        }
        if (s.deferApplyUntilClose) {
            val queued = s.pendingDeferredRules + PendingRule(category, keywords)
            _state.value = s.copy(pendingDeferredRules = queued, statusMessage = "Queued ${queued.size} rule(s) for apply on close.")
            removeCurrentAndAdvance()
            return
        }
        _state.value = s.copy(saving = true, statusMessage = "Saving...")
        viewModelScope.launch {
            try {
                applyRuleAndWait(category, keywords)
                onRuleApplied()
                val latest = ready() ?: return@launch
                _state.value = latest.copy(saving = false)
                removeCurrentAndAdvance()
                val after = ready()
                if (after != null && after.rows.isNotEmpty()) {
                    _state.value = after.copy(statusMessage = "Rule saved.")
                }
            } catch (e: Exception) {
                val latest = ready() ?: return@launch
                _state.value = latest.copy(saving = false, statusMessage = e.message ?: "Couldn't save rule")
            }
        }
    }

    private suspend fun applyRuleAndWait(category: String, keywords: List<String>) {
        val created = repository.createCategoryRule(category, keywords, applyNow = true)
        val jobId = created.applyJob?.id ?: return
        val deadline = System.currentTimeMillis() + 90_000
        while (System.currentTimeMillis() < deadline) {
            val job = repository.getCategoryRuleApplyJob(jobId)
            when (job.status?.lowercase()) {
                "completed" -> return
                "failed" -> throw RuntimeException(job.error ?: "Rule apply failed.")
                else -> delay(1_200)
            }
        }
        throw RuntimeException("Rule apply timed out.")
    }

    /** Mirrors HomeView.swift's close(): save any in-progress rule, flush
     * deferred rules, then let the UI dismiss. */
    fun requestClose(onDone: () -> Unit) {
        val s = ready()
        if (s == null) {
            onDone()
            return
        }
        val hasPendingEntry = s.categoryText.trim().isNotEmpty() && parseKeywords(s.keywordsText).isNotEmpty()
        if (hasPendingEntry && !s.deferApplyUntilClose) {
            saveRule()
        }
        if (s.pendingDeferredRules.isEmpty()) {
            onDone()
            return
        }
        _state.value = s.copy(closing = true, statusMessage = "Saving ${s.pendingDeferredRules.size} deferred rule(s)...")
        viewModelScope.launch {
            val queued = (ready() ?: s).pendingDeferredRules
            val failures = mutableListOf<PendingRule>()
            for (rule in queued) {
                try {
                    applyRuleAndWait(rule.category, rule.keywords)
                } catch (e: Exception) {
                    failures.add(rule)
                }
            }
            if (failures.isNotEmpty()) {
                val latest = ready() ?: s
                _state.value = latest.copy(
                    closing = false,
                    pendingDeferredRules = failures,
                    statusMessage = "Failed to save ${failures.size} deferred rule(s).",
                )
                return@launch
            }
            onRuleApplied()
            onDone()
        }
    }

    class Factory(private val repository: HomeRepository, private val onRuleApplied: () -> Unit) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return UnassignedWizardViewModel(repository, onRuleApplied) as T
        }
    }
}
