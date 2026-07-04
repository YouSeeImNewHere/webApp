package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BankInfoAccount(
    @SerialName("account_id") val accountId: Int = 0,
    val bank: String? = null,
    val name: String? = null,
    val type: String? = null,
    // Percent (e.g. 3.54), not a decimal fraction — see accounts.py's
    // bank_info() as_percent() helper.
    val apy: Double? = null,
    val notes: String? = null,
)

@Serializable
data class BankInfoCardBenefit(
    val categories: List<String> = emptyList(),
    @SerialName("cashback_percent") val cashbackPercent: Double = 0.0,
)

@Serializable
data class BankInfoCard(
    @SerialName("card_id") val cardId: Int = 0,
    val bank: String? = null,
    val name: String? = null,
    val apr: Double? = null,
    @SerialName("credit_limit") val creditLimit: Double? = null,
    val benefits: List<BankInfoCardBenefit> = emptyList(),
)

@Serializable
data class BankInfoOptions(
    val accounts: List<BankInfoAccount> = emptyList(),
    @SerialName("credit_cards") val creditCards: List<BankInfoCard> = emptyList(),
    @SerialName("last_updated") val lastUpdated: String? = null,
)

@Serializable
data class InterestRateUpsertRequest(
    @SerialName("account_id") val accountId: Int,
    @SerialName("rate_percent") val ratePercent: Double,
    @SerialName("effective_date") val effectiveDate: String? = null,
    val note: String? = null,
)

@Serializable
data class InterestRateUpsertResponse(
    val ok: Boolean = false,
    @SerialName("account_id") val accountId: Int = 0,
    @SerialName("effective_date") val effectiveDate: String? = null,
    @SerialName("rate_percent") val ratePercent: Double = 0.0,
)
