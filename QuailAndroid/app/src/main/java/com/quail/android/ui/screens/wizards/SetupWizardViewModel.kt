package com.quail.android.ui.screens.wizards

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.CardBenefitItem
import com.quail.android.data.model.OnboardingAccountCreate
import com.quail.android.data.model.OnboardingAccountItem
import com.quail.android.data.model.OnboardingStatusResponse
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface SetupWizardUiState {
    data object Loading : SetupWizardUiState
    data class Error(val message: String) : SetupWizardUiState
    data class Success(val status: OnboardingStatusResponse) : SetupWizardUiState
}

/** Draft state for the add/edit account form — mirrors OnboardingAccountCreate
 * but keeps numeric fields as text so the form can hold invalid/in-progress
 * input without crashing on parse. */
data class AccountFormState(
    val editingAccountId: Int? = null,
    val institution: String = "",
    val name: String = "",
    val accounttype: String = "checking",
    val interestPostDay: String = "",
    val creditLimit: String = "",
    val apyPercent: String = "",
    val startingBalance: String = "",
    val startingDate: String = "",
    val cardBenefits: List<CardBenefitItem> = emptyList(),
    val receivesEmails: Boolean = true,
    val isPaycheckAccount: Boolean = false,
    val saving: Boolean = false,
    val error: String? = null,
)

/** Mirrors the web app's /setup page: create/edit/delete accounts, track
 * per-account CSV-import + email-parser readiness, save/test a Pushover key,
 * and mark the wizard complete. CSV import itself is handed off to the
 * existing CsvImportRepository/CsvImportQueueScreen pipeline (see
 * MainActivity's onImportCsvForAccount) rather than reimplemented here. */
class SetupWizardViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _state = MutableStateFlow<SetupWizardUiState>(SetupWizardUiState.Loading)
    val state: StateFlow<SetupWizardUiState> = _state.asStateFlow()

    private val _accountForm = MutableStateFlow<AccountFormState?>(null)
    val accountForm: StateFlow<AccountFormState?> = _accountForm.asStateFlow()

    private val _pushoverKeyText = MutableStateFlow("")
    val pushoverKeyText: StateFlow<String> = _pushoverKeyText.asStateFlow()

    private val _pushoverBusy = MutableStateFlow(false)
    val pushoverBusy: StateFlow<Boolean> = _pushoverBusy.asStateFlow()

    private val _pushoverMessage = MutableStateFlow<String?>(null)
    val pushoverMessage: StateFlow<String?> = _pushoverMessage.asStateFlow()

    private val _completing = MutableStateFlow(false)
    val completing: StateFlow<Boolean> = _completing.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.value = SetupWizardUiState.Loading
            try {
                _state.value = SetupWizardUiState.Success(repository.getOnboardingStatus())
            } catch (e: Exception) {
                _state.value = SetupWizardUiState.Error(e.message ?: "Couldn't load setup status")
            }
        }
    }

    fun startAddAccount() { _accountForm.value = AccountFormState() }

    fun startEditAccount(account: OnboardingAccountItem) {
        _accountForm.value = AccountFormState(
            editingAccountId = account.id,
            institution = account.institution.orEmpty(),
            name = account.name.orEmpty(),
            accounttype = account.accounttype ?: "checking",
            interestPostDay = account.interestPostDay?.toString().orEmpty(),
            creditLimit = account.creditLimit?.toString().orEmpty(),
            cardBenefits = account.cardBenefits,
            receivesEmails = account.receivesEmails,
            isPaycheckAccount = account.isPaycheckAccount,
        )
    }

    fun cancelAccountForm() { _accountForm.value = null }

    fun updateAccountForm(transform: (AccountFormState) -> AccountFormState) {
        _accountForm.value = _accountForm.value?.let(transform)
    }

    fun saveAccountForm() {
        val form = _accountForm.value ?: return
        if (form.institution.isBlank() || form.name.isBlank()) {
            _accountForm.value = form.copy(error = "Institution and name are required.")
            return
        }
        _accountForm.value = form.copy(saving = true, error = null)
        viewModelScope.launch {
            try {
                val request = OnboardingAccountCreate(
                    institution = form.institution.trim(),
                    name = form.name.trim(),
                    accounttype = form.accounttype,
                    interestPostDay = form.interestPostDay.toIntOrNull(),
                    creditLimit = if (form.accounttype == "credit") form.creditLimit.toDoubleOrNull() else null,
                    apyPercent = form.apyPercent.toDoubleOrNull(),
                    startingBalance = form.startingBalance.toDoubleOrNull(),
                    startingDate = form.startingDate.ifBlank { null },
                    cardBenefits = if (form.accounttype == "credit") form.cardBenefits else null,
                    receivesEmails = form.receivesEmails,
                    isPaycheckAccount = form.isPaycheckAccount,
                )
                val editingId = form.editingAccountId
                if (editingId != null) {
                    repository.updateOnboardingAccount(editingId, request)
                } else {
                    repository.createOnboardingAccount(request)
                }
                _accountForm.value = null
                refresh()
            } catch (e: Exception) {
                _accountForm.value = (_accountForm.value ?: form).copy(saving = false, error = e.message ?: "Couldn't save account")
            }
        }
    }

    fun deleteAccount(accountId: Int) {
        viewModelScope.launch {
            runCatching { repository.deleteOnboardingAccount(accountId) }
            refresh()
        }
    }

    fun setPushoverKeyText(text: String) { _pushoverKeyText.value = text }

    fun savePushoverKey() {
        viewModelScope.launch {
            _pushoverBusy.value = true
            _pushoverMessage.value = null
            try {
                repository.setOnboardingPushoverKey(_pushoverKeyText.value.ifBlank { null })
                _pushoverMessage.value = "Saved."
                refresh()
            } catch (e: Exception) {
                _pushoverMessage.value = e.message ?: "Couldn't save Pushover key"
            } finally {
                _pushoverBusy.value = false
            }
        }
    }

    fun testPushover() {
        viewModelScope.launch {
            _pushoverBusy.value = true
            _pushoverMessage.value = null
            try {
                val result = repository.testOnboardingPushover(_pushoverKeyText.value.ifBlank { null })
                _pushoverMessage.value = if (result.sent) "Test notification sent." else "Notification wasn't sent."
            } catch (e: Exception) {
                _pushoverMessage.value = e.message ?: "Couldn't send test notification"
            } finally {
                _pushoverBusy.value = false
            }
        }
    }

    fun markComplete(onDone: () -> Unit) {
        viewModelScope.launch {
            _completing.value = true
            try {
                repository.completeOnboarding()
                onDone()
            } catch (e: Exception) {
                _pushoverMessage.value = e.message ?: "Couldn't mark setup complete"
            } finally {
                _completing.value = false
            }
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = SetupWizardViewModel(repository) as T
    }
}
