package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---- Setup Wizard: GET/POST /onboarding/* ----

@Serializable
data class OnboardingStepFlags(
    @SerialName("accounts_added") val accountsAdded: Boolean = false,
    @SerialName("starting_balances_added") val startingBalancesAdded: Boolean = false,
    @SerialName("transactions_imported") val transactionsImported: Boolean = false,
    @SerialName("pushover_user_key_set") val pushoverUserKeySet: Boolean = false,
)

@Serializable
data class OnboardingCounts(
    val accounts: Int = 0,
    @SerialName("starting_balances") val startingBalances: Int = 0,
    val transactions: Int = 0,
)

@Serializable
data class CardBenefitItem(
    @SerialName("benefit_type") val benefitType: String = "",
    @SerialName("cashback_percent") val cashbackPercent: Double = 0.0,
)

@Serializable
data class OnboardingAccountSetup(
    val complete: Boolean = false,
    @SerialName("csv_mapping_ready") val csvMappingReady: Boolean = false,
    @SerialName("parser_required") val parserRequired: Boolean = false,
    @SerialName("parser_ready") val parserReady: Boolean = false,
    val missing: List<String> = emptyList(),
)

@Serializable
data class OnboardingAccountItem(
    val id: Int,
    val institution: String? = null,
    val name: String? = null,
    val accounttype: String? = null,
    @SerialName("interest_post_day") val interestPostDay: Int? = null,
    @SerialName("credit_limit") val creditLimit: Double? = null,
    @SerialName("receives_emails") val receivesEmails: Boolean = true,
    @SerialName("is_paycheck_account") val isPaycheckAccount: Boolean = false,
    @SerialName("card_benefits") val cardBenefits: List<CardBenefitItem> = emptyList(),
    val setup: OnboardingAccountSetup = OnboardingAccountSetup(),
)

@Serializable
data class OnboardingStatusResponse(
    val ok: Boolean = true,
    @SerialName("tenant_id") val tenantId: Int = 0,
    @SerialName("can_set_starting_balance") val canSetStartingBalance: Boolean = false,
    @SerialName("wizard_completed") val wizardCompleted: Boolean = false,
    val steps: OnboardingStepFlags = OnboardingStepFlags(),
    val counts: OnboardingCounts = OnboardingCounts(),
    val accounts: List<OnboardingAccountItem> = emptyList(),
    @SerialName("next_actions") val nextActions: List<String> = emptyList(),
)

@Serializable
data class OnboardingAccountCreate(
    val institution: String,
    val name: String,
    val accounttype: String,
    @SerialName("interest_post_day") val interestPostDay: Int? = null,
    @SerialName("credit_limit") val creditLimit: Double? = null,
    @SerialName("apy_percent") val apyPercent: Double? = null,
    @SerialName("starting_balance") val startingBalance: Double? = null,
    @SerialName("starting_date") val startingDate: String? = null,
    @SerialName("card_benefits") val cardBenefits: List<CardBenefitItem>? = null,
    @SerialName("receives_emails") val receivesEmails: Boolean = true,
    @SerialName("is_paycheck_account") val isPaycheckAccount: Boolean = false,
)

@Serializable
data class OnboardingAccountResponse(
    val ok: Boolean = true,
    @SerialName("account_id") val accountId: Int = 0,
)

@Serializable
data class OnboardingAccountDeleteResponse(
    val ok: Boolean = true,
    @SerialName("account_id") val accountId: Int = 0,
    @SerialName("deleted_transactions") val deletedTransactions: Int = 0,
)

@Serializable
data class PushoverKeyRequest(@SerialName("user_key") val userKey: String? = null)

@Serializable
data class PushoverKeyResponse(
    val ok: Boolean = true,
    @SerialName("user_key_set") val userKeySet: Boolean = false,
)

@Serializable
data class PushoverTestRequest(@SerialName("user_key") val userKey: String? = null)

@Serializable
data class PushoverTestResponse(
    val ok: Boolean = true,
    val sent: Boolean = false,
)

@Serializable
data class OnboardingCompleteRequest(val completed: Boolean = true)

@Serializable
data class OnboardingCompleteResponse(
    val ok: Boolean = true,
    @SerialName("tenant_id") val tenantId: Int = 0,
    @SerialName("wizard_completed") val wizardCompleted: Boolean = false,
)
