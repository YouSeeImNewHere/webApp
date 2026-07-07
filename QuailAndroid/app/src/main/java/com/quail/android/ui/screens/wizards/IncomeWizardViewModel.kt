package com.quail.android.ui.screens.wizards

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.LESProfile
import com.quail.android.data.model.MonthBudget
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

private const val INCOME_WIZARD_PREFS = "quail_income_wizard_prefs"
private const val KEY_INCOME_TYPE = "income_type"

sealed interface LesProfileUiState {
    data object Loading : LesProfileUiState
    data class Error(val message: String) : LesProfileUiState
    data class Success(val profile: LESProfile) : LesProfileUiState
}

/** Text-backed mirror of LESProfile so the form can hold in-progress/invalid
 * numeric input without crashing on parse — same pattern as Setup Wizard's
 * AccountFormState. */
data class LesFormState(
    val paygrade: String = "E-5",
    val serviceStart: String = "2020-01-01",
    val hasDependents: Boolean = true,
    val bas: String = "465.77",
    val bahOverride: String = "",
    val submarinePay: String = "0",
    val careerSeaPay: String = "0",
    val specDutyPay: String = "0",
    val tspRate: String = "0.05",
    val filingStatus: String = "S",
    val step2MultipleJobs: Boolean = false,
    val depUnder17: String = "0",
    val otherDep: String = "0",
    val otherIncomeAnnual: String = "0",
    val otherDeductionsAnnual: String = "0",
    val extraWithholding: String = "0",
    val mealRate: String = "13.30",
    val mealEndDay: String = "31",
    val mealDeductionEnabled: Boolean = false,
    val mealDeductionStart: String = "",
    val midMonthFraction: String = "0.50",
    val allotmentsTotal: String = "0",
    val midMonthCollectionsTotal: String = "0",
    val ficaIncludeSpecialPays: Boolean = false,
)

private fun LESProfile.toFormState(): LesFormState = LesFormState(
    paygrade = paygrade,
    serviceStart = serviceStart,
    hasDependents = hasDependents,
    bas = bas.toString(),
    bahOverride = bahOverride?.toString().orEmpty(),
    submarinePay = submarinePay.toString(),
    careerSeaPay = careerSeaPay.toString(),
    specDutyPay = specDutyPay.toString(),
    tspRate = tspRate.toString(),
    filingStatus = filingStatus,
    step2MultipleJobs = step2MultipleJobs,
    depUnder17 = depUnder17.toString(),
    otherDep = otherDep.toString(),
    otherIncomeAnnual = otherIncomeAnnual.toString(),
    otherDeductionsAnnual = otherDeductionsAnnual.toString(),
    extraWithholding = extraWithholding.toString(),
    mealRate = mealRate.toString(),
    mealEndDay = mealEndDay.toString(),
    mealDeductionEnabled = mealDeductionEnabled,
    mealDeductionStart = mealDeductionStart.orEmpty(),
    midMonthFraction = midMonthFraction.toString(),
    allotmentsTotal = allotmentsTotal.toString(),
    midMonthCollectionsTotal = midMonthCollectionsTotal.toString(),
    ficaIncludeSpecialPays = ficaIncludeSpecialPays,
)

private fun LesFormState.toProfile(): LESProfile = LESProfile(
    paygrade = paygrade.ifBlank { "E-5" },
    serviceStart = serviceStart.ifBlank { "2020-01-01" },
    hasDependents = hasDependents,
    bas = bas.toDoubleOrNull() ?: 0.0,
    bahOverride = bahOverride.toDoubleOrNull(),
    submarinePay = submarinePay.toDoubleOrNull() ?: 0.0,
    careerSeaPay = careerSeaPay.toDoubleOrNull() ?: 0.0,
    specDutyPay = specDutyPay.toDoubleOrNull() ?: 0.0,
    tspRate = tspRate.toDoubleOrNull() ?: 0.0,
    filingStatus = filingStatus.ifBlank { "S" },
    step2MultipleJobs = step2MultipleJobs,
    depUnder17 = depUnder17.toIntOrNull() ?: 0,
    otherDep = otherDep.toIntOrNull() ?: 0,
    otherIncomeAnnual = otherIncomeAnnual.toDoubleOrNull() ?: 0.0,
    otherDeductionsAnnual = otherDeductionsAnnual.toDoubleOrNull() ?: 0.0,
    extraWithholding = extraWithholding.toDoubleOrNull() ?: 0.0,
    mealRate = mealRate.toDoubleOrNull() ?: 0.0,
    mealEndDay = mealEndDay.toIntOrNull() ?: 31,
    mealDeductionEnabled = mealDeductionEnabled,
    mealDeductionStart = mealDeductionStart.ifBlank { null },
    midMonthFraction = midMonthFraction.toDoubleOrNull() ?: 0.50,
    allotmentsTotal = allotmentsTotal.toDoubleOrNull() ?: 0.0,
    midMonthCollectionsTotal = midMonthCollectionsTotal.toDoubleOrNull() ?: 0.0,
    ficaIncludeSpecialPays = ficaIncludeSpecialPays,
)

/** Mirrors the web app's Income Wizard: an Income Type toggle (only LES is
 * actually implemented server-side — Salary/Hourly are scaffolded
 * "in progress" placeholders on iOS and web too, kept here for parity),
 * the LES profile form, paycheck-matching keywords, and daily spending
 * weights with a live dollar-amount preview computed from month-budget. */
class IncomeWizardViewModel(
    private val repository: HomeRepository,
    appContext: Context,
) : ViewModel() {
    private val prefs = appContext.getSharedPreferences(INCOME_WIZARD_PREFS, Context.MODE_PRIVATE)

    private val _incomeType = MutableStateFlow(prefs.getString(KEY_INCOME_TYPE, "les") ?: "les")
    val incomeType: StateFlow<String> = _incomeType.asStateFlow()

    private val _lesState = MutableStateFlow<LesProfileUiState>(LesProfileUiState.Loading)
    val lesState: StateFlow<LesProfileUiState> = _lesState.asStateFlow()

    private val _lesForm = MutableStateFlow(LesFormState())
    val lesForm: StateFlow<LesFormState> = _lesForm.asStateFlow()

    private val _savingLes = MutableStateFlow(false)
    val savingLes: StateFlow<Boolean> = _savingLes.asStateFlow()

    private val _lesMessage = MutableStateFlow<String?>(null)
    val lesMessage: StateFlow<String?> = _lesMessage.asStateFlow()

    private val _keywordsText = MutableStateFlow("")
    val keywordsText: StateFlow<String> = _keywordsText.asStateFlow()

    private val _savingKeywords = MutableStateFlow(false)
    val savingKeywords: StateFlow<Boolean> = _savingKeywords.asStateFlow()

    private val _keywordsMessage = MutableStateFlow<String?>(null)
    val keywordsMessage: StateFlow<String?> = _keywordsMessage.asStateFlow()

    private val _weekdayPointsText = MutableStateFlow("1")
    val weekdayPointsText: StateFlow<String> = _weekdayPointsText.asStateFlow()

    private val _weekendPointsText = MutableStateFlow("2")
    val weekendPointsText: StateFlow<String> = _weekendPointsText.asStateFlow()

    private val _savingWeights = MutableStateFlow(false)
    val savingWeights: StateFlow<Boolean> = _savingWeights.asStateFlow()

    private val _weightsMessage = MutableStateFlow<String?>(null)
    val weightsMessage: StateFlow<String?> = _weightsMessage.asStateFlow()

    private val _monthBudget = MutableStateFlow<MonthBudget?>(null)
    val monthBudget: StateFlow<MonthBudget?> = _monthBudget.asStateFlow()

    init {
        loadLesProfile()
        loadPaycheckMatchers()
        loadDailyWeights()
        loadMonthBudgetForPreview()
    }

    fun setIncomeType(type: String) {
        _incomeType.value = type
        prefs.edit().putString(KEY_INCOME_TYPE, type).apply()
    }

    private fun loadLesProfile() {
        viewModelScope.launch {
            _lesState.value = LesProfileUiState.Loading
            try {
                val response = repository.getLesProfile()
                _lesForm.value = response.profile.toFormState()
                _lesState.value = LesProfileUiState.Success(response.profile)
            } catch (e: Exception) {
                _lesState.value = LesProfileUiState.Error(e.message ?: "Couldn't load income profile")
            }
        }
    }

    fun updateLesForm(transform: (LesFormState) -> LesFormState) {
        _lesForm.value = transform(_lesForm.value)
    }

    fun saveLesProfile() {
        viewModelScope.launch {
            _savingLes.value = true
            _lesMessage.value = "Saving..."
            try {
                val response = repository.setLesProfile(_lesForm.value.toProfile())
                _lesForm.value = response.profile.toFormState()
                _lesState.value = LesProfileUiState.Success(response.profile)
                _lesMessage.value = "Saved."
            } catch (e: Exception) {
                _lesMessage.value = "Failed to save: ${e.message ?: "unknown error"}"
            } finally {
                _savingLes.value = false
            }
        }
    }

    fun resetLesToDefaults() {
        _lesForm.value = LESProfile().toFormState()
        saveLesProfile()
    }

    private fun loadPaycheckMatchers() {
        viewModelScope.launch {
            runCatching { repository.getPaycheckMatchers() }.onSuccess {
                _keywordsText.value = it.keywords.joinToString("\n")
            }
        }
    }

    fun setKeywordsText(text: String) { _keywordsText.value = text }

    fun saveKeywords() {
        viewModelScope.launch {
            _savingKeywords.value = true
            _keywordsMessage.value = null
            try {
                val keywords = _keywordsText.value.split("\n").map { it.trim() }.filter { it.isNotEmpty() }
                val response = repository.setPaycheckMatchers(keywords)
                _keywordsText.value = response.keywords.joinToString("\n")
                _keywordsMessage.value = "Saved."
            } catch (e: Exception) {
                _keywordsMessage.value = e.message ?: "Couldn't save keywords"
            } finally {
                _savingKeywords.value = false
            }
        }
    }

    private fun loadDailyWeights() {
        viewModelScope.launch {
            runCatching { repository.getDailyWeights() }.onSuccess {
                _weekdayPointsText.value = it.weekdayPoints.toString()
                _weekendPointsText.value = it.weekendPoints.toString()
            }
        }
    }

    fun setWeekdayPointsText(text: String) { _weekdayPointsText.value = text }
    fun setWeekendPointsText(text: String) { _weekendPointsText.value = text }

    fun saveDailyWeights() {
        val weekday = _weekdayPointsText.value.toDoubleOrNull()
        val weekend = _weekendPointsText.value.toDoubleOrNull()
        if (weekday == null || weekend == null || weekday <= 0 || weekend <= 0 || weekday > 10 || weekend > 10) {
            _weightsMessage.value = "Both values must be greater than 0 and at most 10."
            return
        }
        viewModelScope.launch {
            _savingWeights.value = true
            _weightsMessage.value = null
            try {
                val response = repository.setDailyWeights(weekday, weekend)
                _weekdayPointsText.value = response.weekdayPoints.toString()
                _weekendPointsText.value = response.weekendPoints.toString()
                _weightsMessage.value = "Saved."
            } catch (e: Exception) {
                _weightsMessage.value = e.message ?: "Couldn't save daily weights"
            } finally {
                _savingWeights.value = false
            }
        }
    }

    private fun loadMonthBudgetForPreview() {
        viewModelScope.launch {
            val today = LocalDate.now()
            runCatching { repository.getMonthBudget(today.year, today.monthValue) }.onSuccess {
                _monthBudget.value = it
            }
        }
    }

    class Factory(private val repository: HomeRepository, private val appContext: Context) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = IncomeWizardViewModel(repository, appContext) as T
    }
}
