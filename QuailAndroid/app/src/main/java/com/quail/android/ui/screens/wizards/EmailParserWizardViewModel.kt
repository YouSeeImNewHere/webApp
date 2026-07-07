package com.quail.android.ui.screens.wizards

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.ParserAccountItem
import com.quail.android.data.model.ParserConfigRequest
import com.quail.android.data.model.ParserCorrelationRequest
import com.quail.android.data.model.ParserCorrelationResponse
import com.quail.android.data.model.ParserPreviewRow
import com.quail.android.data.model.ParserSampleItem
import com.quail.android.data.model.ParserSamplesRequest
import com.quail.android.data.model.ParserTestRunRequest
import com.quail.android.data.model.ParserTestRunResponse
import com.quail.android.data.model.ParserWizardFieldMap
import com.quail.android.data.model.ParserWizardGuided
import com.quail.android.data.model.ParserWizardSetting
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed interface ParserAccountsUiState {
    data object Loading : ParserAccountsUiState
    data class Error(val message: String) : ParserAccountsUiState
    data class Success(val accounts: List<ParserAccountItem>) : ParserAccountsUiState
}

sealed interface ParserSamplesUiState {
    data object Idle : ParserSamplesUiState
    data object Loading : ParserSamplesUiState
    data class Error(val message: String) : ParserSamplesUiState
    data class Success(val items: List<ParserSampleItem>, val stale: Boolean, val warning: String?) : ParserSamplesUiState
}

sealed interface ParserPreviewUiState {
    data object Idle : ParserPreviewUiState
    data object Loading : ParserPreviewUiState
    data class Error(val message: String) : ParserPreviewUiState
    data class Success(val rows: List<ParserPreviewRow>, val matched: Int) : ParserPreviewUiState
}

sealed interface ParserTestRunUiState {
    data object Idle : ParserTestRunUiState
    data object Loading : ParserTestRunUiState
    data class Error(val message: String) : ParserTestRunUiState
    data class Success(val response: ParserTestRunResponse) : ParserTestRunUiState
}

sealed interface ParserCorrelationUiState {
    data object Idle : ParserCorrelationUiState
    data object Loading : ParserCorrelationUiState
    data class Error(val message: String) : ParserCorrelationUiState
    data class Success(val response: ParserCorrelationResponse) : ParserCorrelationUiState
}

/** Step 1: which account/sender/subject/date-range/sample-limit to fetch
 * candidate emails for. */
data class ScopeFormState(
    val accountId: Int? = null,
    val senderQuery: String = "",
    val subjectQuery: String = "",
    val lookbackDays: String = "30",
    val limit: String = "10",
    val tryHtmlFallback: Boolean = false,
)

/** Step 3: the parser rule itself — guided (label + end-delimiter) or
 * advanced (regex + capture groups). Numeric fields are text-backed so the
 * form can hold in-progress input, mirroring the other two wizards' forms. */
data class RuleFormState(
    val editingDraftId: Int? = null,
    val name: String = "",
    val mode: String = "guided",
    val senderPattern: String = "",
    val subjectContains: String = "",
    val bodyRegex: String = "",
    val flags: String = "i",
    val amountGroup: String = "1",
    val merchantGroup: String = "2",
    val dateGroup: String = "3",
    val timeGroup: String = "0",
    val amountLabel: String = "",
    val merchantLabel: String = "",
    val dateLabel: String = "",
    val timeLabel: String = "",
    val amountOrder: String = "1",
    val merchantOrder: String = "2",
    val dateOrder: String = "3",
    val timeOrder: String = "0",
    val accountBefore: String = "",
    val accountExact: String = "",
    val parserSlot: String = "parser_1",
    val overrideOnPrimary: Boolean = false,
    val backupAssumeUnknown: Boolean = false,
    val invertAmountSign: Boolean = false,
    val pendingTtlMinutes: String = "30",
)

private fun ParserWizardSetting.toFormState(): RuleFormState = RuleFormState(
    editingDraftId = draftId,
    name = name,
    mode = parserMode,
    senderPattern = senderPattern,
    subjectContains = subjectContains,
    bodyRegex = bodyRegex,
    flags = flags,
    amountGroup = fieldMap.amountGroup.toString(),
    merchantGroup = fieldMap.merchantGroup.toString(),
    dateGroup = fieldMap.dateGroup.toString(),
    timeGroup = fieldMap.timeGroup.toString(),
    amountLabel = guided.amountLabel,
    merchantLabel = guided.merchantLabel,
    dateLabel = guided.dateLabel,
    timeLabel = guided.timeLabel,
    amountOrder = guided.amountOrder.toString(),
    merchantOrder = guided.merchantOrder.toString(),
    dateOrder = guided.dateOrder.toString(),
    timeOrder = guided.timeOrder.toString(),
    accountBefore = guided.accountBefore,
    accountExact = guided.accountExact,
    parserSlot = parserSlot,
    overrideOnPrimary = overrideOnPrimary,
    backupAssumeUnknown = backupAssumeUnknown,
    invertAmountSign = invertAmountSign,
    pendingTtlMinutes = pendingTtlMinutes.toString(),
)

private fun RuleFormState.toConfigRequest(accountId: Int, sampleIds: List<String>): ParserConfigRequest = ParserConfigRequest(
    name = name,
    parserMode = mode,
    parsingMethod = "guided_blocks",
    accountId = accountId,
    senderPattern = senderPattern,
    subjectContains = subjectContains,
    bodyRegex = bodyRegex,
    flags = flags.ifBlank { "i" },
    fieldMap = ParserWizardFieldMap(
        amountGroup = amountGroup.toIntOrNull() ?: 1,
        merchantGroup = merchantGroup.toIntOrNull() ?: 2,
        dateGroup = dateGroup.toIntOrNull() ?: 3,
        timeGroup = timeGroup.toIntOrNull() ?: 0,
    ),
    guided = ParserWizardGuided(
        amountLabel = amountLabel,
        merchantLabel = merchantLabel,
        dateLabel = dateLabel,
        timeLabel = timeLabel,
        amountOrder = amountOrder.toIntOrNull() ?: 1,
        merchantOrder = merchantOrder.toIntOrNull() ?: 2,
        dateOrder = dateOrder.toIntOrNull() ?: 3,
        timeOrder = timeOrder.toIntOrNull() ?: 0,
        accountBefore = accountBefore,
        accountExact = accountExact,
    ),
    sampleIds = sampleIds,
    parserSlot = parserSlot,
    overrideOnPrimary = overrideOnPrimary,
    backupAssumeUnknown = backupAssumeUnknown,
    invertAmountSign = invertAmountSign,
    pendingTtlMinutes = pendingTtlMinutes.toIntOrNull() ?: 30,
)

/** Mirrors the web app's Email Parser Wizard: pick an account + Gmail
 * search scope, fetch candidate sample emails, configure a guided or regex
 * extraction rule, preview/test it against the samples (and, once two
 * parsers exist for an account, a correlation preview simulating both
 * running together), then save. The guided/regex extraction itself runs
 * server-side (via /preview, /test-run, /correlation-preview) — this
 * ViewModel just orchestrates calls and renders results, it doesn't
 * reimplement the extraction engine on-device. */
class EmailParserWizardViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _accountsState = MutableStateFlow<ParserAccountsUiState>(ParserAccountsUiState.Loading)
    val accountsState: StateFlow<ParserAccountsUiState> = _accountsState.asStateFlow()

    private val _scopeForm = MutableStateFlow(ScopeFormState())
    val scopeForm: StateFlow<ScopeFormState> = _scopeForm.asStateFlow()

    private val _samplesState = MutableStateFlow<ParserSamplesUiState>(ParserSamplesUiState.Idle)
    val samplesState: StateFlow<ParserSamplesUiState> = _samplesState.asStateFlow()

    private val _selectedSampleIds = MutableStateFlow<Set<String>>(emptySet())
    val selectedSampleIds: StateFlow<Set<String>> = _selectedSampleIds.asStateFlow()

    private val _primarySampleId = MutableStateFlow<String?>(null)
    val primarySampleId: StateFlow<String?> = _primarySampleId.asStateFlow()

    private val _ruleForm = MutableStateFlow(RuleFormState())
    val ruleForm: StateFlow<RuleFormState> = _ruleForm.asStateFlow()

    private val _existingSettings = MutableStateFlow<List<ParserWizardSetting>>(emptyList())
    val existingSettings: StateFlow<List<ParserWizardSetting>> = _existingSettings.asStateFlow()

    private val _previewState = MutableStateFlow<ParserPreviewUiState>(ParserPreviewUiState.Idle)
    val previewState: StateFlow<ParserPreviewUiState> = _previewState.asStateFlow()

    private val _testRunState = MutableStateFlow<ParserTestRunUiState>(ParserTestRunUiState.Idle)
    val testRunState: StateFlow<ParserTestRunUiState> = _testRunState.asStateFlow()

    private val _correlationState = MutableStateFlow<ParserCorrelationUiState>(ParserCorrelationUiState.Idle)
    val correlationState: StateFlow<ParserCorrelationUiState> = _correlationState.asStateFlow()

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving.asStateFlow()

    private val _saveMessage = MutableStateFlow<String?>(null)
    val saveMessage: StateFlow<String?> = _saveMessage.asStateFlow()

    /** The full sample the user is building the rule against — surfaced so
     * the screen can show the actual email text next to the rule fields
     * instead of making the user scroll back up to "Candidate Samples" to
     * remember what's in it. */
    val primarySample: StateFlow<ParserSampleItem?> = combine(_samplesState, _primarySampleId) { state, id ->
        (state as? ParserSamplesUiState.Success)?.items?.firstOrNull { it.sampleId == id }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    private val _livePreviewRow = MutableStateFlow<ParserPreviewRow?>(null)
    val livePreviewRow: StateFlow<ParserPreviewRow?> = _livePreviewRow.asStateFlow()

    private val _livePreviewLoading = MutableStateFlow(false)
    val livePreviewLoading: StateFlow<Boolean> = _livePreviewLoading.asStateFlow()

    init {
        loadAccounts()
        observeLivePreview()
    }

    /** Re-runs /preview against just the primary sample every time the rule
     * form changes, debounced so it doesn't fire on every keystroke — this
     * is what lets the reference-email card show live highlighted matches
     * as fields are edited, instead of requiring a manual "Preview" tap. */
    private fun observeLivePreview() {
        viewModelScope.launch {
            combine(_ruleForm, _primarySampleId, _scopeForm) { rule, primaryId, scope -> Triple(rule, primaryId, scope.accountId) }
                .debounce(500)
                .collectLatest { (rule, primaryId, accountId) ->
                    if (primaryId == null || accountId == null) {
                        _livePreviewRow.value = null
                        return@collectLatest
                    }
                    _livePreviewLoading.value = true
                    try {
                        val response = repository.previewParserConfig(rule.toConfigRequest(accountId, listOf(primaryId)))
                        _livePreviewRow.value = response.rows.firstOrNull()
                    } catch (e: Exception) {
                        _livePreviewRow.value = null
                    } finally {
                        _livePreviewLoading.value = false
                    }
                }
        }
    }

    fun loadAccounts() {
        viewModelScope.launch {
            _accountsState.value = ParserAccountsUiState.Loading
            try {
                _accountsState.value = ParserAccountsUiState.Success(repository.getParserAccounts().accounts)
            } catch (e: Exception) {
                _accountsState.value = ParserAccountsUiState.Error(e.message ?: "Couldn't load accounts")
            }
        }
    }

    fun updateScopeForm(transform: (ScopeFormState) -> ScopeFormState) {
        _scopeForm.value = transform(_scopeForm.value)
    }

    fun selectAccount(accountId: Int) {
        _scopeForm.value = _scopeForm.value.copy(accountId = accountId)
        loadExistingSettings(accountId)
    }

    private fun loadExistingSettings(accountId: Int) {
        viewModelScope.launch {
            runCatching { repository.getParserAccountSettings(accountId) }.onSuccess {
                _existingSettings.value = it.settings
            }
        }
    }

    fun loadSamples() {
        val form = _scopeForm.value
        val accountId = form.accountId
        if (accountId == null || form.senderQuery.isBlank()) {
            _samplesState.value = ParserSamplesUiState.Error("Pick an account and enter a sender filter.")
            return
        }
        viewModelScope.launch {
            _samplesState.value = ParserSamplesUiState.Loading
            try {
                val response = repository.getParserSamples(
                    ParserSamplesRequest(
                        accountId = accountId,
                        senderQuery = form.senderQuery.trim(),
                        subjectQuery = form.subjectQuery.trim(),
                        tryHtmlOnMissingFields = form.tryHtmlFallback,
                        lookbackDays = form.lookbackDays.toIntOrNull() ?: 30,
                        limit = form.limit.toIntOrNull() ?: 10,
                    ),
                )
                _samplesState.value = ParserSamplesUiState.Success(response.items, response.stale, response.warning)
                _selectedSampleIds.value = response.items.map { it.sampleId }.toSet()
                _primarySampleId.value = response.items.firstOrNull()?.sampleId
            } catch (e: Exception) {
                _samplesState.value = ParserSamplesUiState.Error(e.message ?: "Couldn't load samples")
            }
        }
    }

    fun toggleSampleSelected(sampleId: String) {
        val current = _selectedSampleIds.value
        _selectedSampleIds.value = if (sampleId in current) current - sampleId else current + sampleId
    }

    fun setPrimarySample(sampleId: String) { _primarySampleId.value = sampleId }

    fun updateRuleForm(transform: (RuleFormState) -> RuleFormState) {
        _ruleForm.value = transform(_ruleForm.value)
    }

    fun loadExistingRule(setting: ParserWizardSetting) {
        _ruleForm.value = setting.toFormState()
    }

    fun runPreview() {
        val accountId = _scopeForm.value.accountId ?: return
        val sampleIds = _selectedSampleIds.value.toList()
        if (sampleIds.isEmpty()) {
            _previewState.value = ParserPreviewUiState.Error("Select at least one sample to preview.")
            return
        }
        viewModelScope.launch {
            _previewState.value = ParserPreviewUiState.Loading
            try {
                val response = repository.previewParserConfig(_ruleForm.value.toConfigRequest(accountId, sampleIds))
                _previewState.value = ParserPreviewUiState.Success(response.rows, response.matched)
            } catch (e: Exception) {
                _previewState.value = ParserPreviewUiState.Error(e.message ?: "Preview failed")
            }
        }
    }

    fun runTestAll() {
        val form = _scopeForm.value
        viewModelScope.launch {
            _testRunState.value = ParserTestRunUiState.Loading
            try {
                val response = repository.runParserTest(
                    ParserTestRunRequest(
                        senderQuery = form.senderQuery.trim(),
                        subjectQuery = form.subjectQuery.trim(),
                        tryHtmlOnMissingFields = form.tryHtmlFallback,
                        lookbackDays = 7,
                        limit = 40,
                    ),
                )
                _testRunState.value = ParserTestRunUiState.Success(response)
            } catch (e: Exception) {
                _testRunState.value = ParserTestRunUiState.Error(e.message ?: "Test run failed")
            }
        }
    }

    fun runCorrelationPreview(primaryDraftId: Int, secondaryDraftId: Int?) {
        val accountId = _scopeForm.value.accountId ?: return
        val sampleIds = _selectedSampleIds.value.toList()
        viewModelScope.launch {
            _correlationState.value = ParserCorrelationUiState.Loading
            try {
                val response = repository.previewParserCorrelation(
                    ParserCorrelationRequest(accountId, primaryDraftId, secondaryDraftId, sampleIds),
                )
                _correlationState.value = ParserCorrelationUiState.Success(response)
            } catch (e: Exception) {
                _correlationState.value = ParserCorrelationUiState.Error(e.message ?: "Correlation preview failed")
            }
        }
    }

    fun saveRule() {
        val accountId = _scopeForm.value.accountId ?: return
        val form = _ruleForm.value
        if (form.name.isBlank()) {
            _saveMessage.value = "Enter a name for this parser."
            return
        }
        viewModelScope.launch {
            _saving.value = true
            _saveMessage.value = null
            try {
                repository.saveParserConfig(form.toConfigRequest(accountId, emptyList()))
                _saveMessage.value = "Saved."
                loadExistingSettings(accountId)
            } catch (e: Exception) {
                _saveMessage.value = e.message ?: "Couldn't save parser"
            } finally {
                _saving.value = false
            }
        }
    }

    fun deleteRule(parserSlot: String) {
        val accountId = _scopeForm.value.accountId ?: return
        viewModelScope.launch {
            runCatching { repository.deleteParserDraft(accountId, parserSlot) }
            loadExistingSettings(accountId)
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = EmailParserWizardViewModel(repository) as T
    }
}
