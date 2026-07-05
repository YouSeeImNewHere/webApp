package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AccountInfoResponse(
    val id: Int = 0,
    val institution: String? = null,
    val name: String? = null,
    val accounttype: String? = null,
    @SerialName("last_csv_upload_at") val lastCsvUploadAt: String? = null,
    @SerialName("last_manual_verified_at") val lastManualVerifiedAt: String? = null,
    @SerialName("audit_updated_at") val auditUpdatedAt: String? = null,
    val error: String? = null,
)

@Serializable
data class AccountLedgerTransaction(
    val id: String = "",
    @SerialName("account_id") val accountId: Int = 0,
    val effectiveDate: String? = null,
    val dateISO: String? = null,
    val merchant: String? = null,
    val amount: Double = 0.0,
    @SerialName("is_ignored") val isIgnored: Boolean = false,
    val category: String? = null,
    val status: String = "posted",
    val postedDate: String? = null,
    val purchaseDate: String? = null,
    val time: String? = null,
    @SerialName("balance_after") val balanceAfter: Double? = null,
    @SerialName("transfer_peer") val transferPeer: String? = null,
    @SerialName("transfer_dir") val transferDir: String? = null,
)

@Serializable
data class AccountTransactionsRangeResponse(
    val ok: Boolean = true,
    @SerialName("account_id") val accountId: Int = 0,
    val start: String = "",
    val end: String = "",
    @SerialName("pending_balance_multiplier") val pendingBalanceMultiplier: Int = -1,
    @SerialName("starting_balance") val startingBalance: Double = 0.0,
    @SerialName("ending_balance") val endingBalance: Double = 0.0,
    val transactions: List<AccountLedgerTransaction> = emptyList(),
)

@Serializable
data class TransactionCreateRequest(
    @SerialName("account_id") val accountId: Int,
    val amount: Double,
    val merchant: String = "",
    val status: String = "posted",
    val date: String? = null,
    val source: String = "Manual",
)

@Serializable
data class TransactionCreateResponse(
    val ok: Boolean = false,
    val id: String = "",
    @SerialName("account_id") val accountId: Int = 0,
    val amount: Double = 0.0,
    val merchant: String = "",
    val category: String? = null,
    val status: String = "posted",
    val purchaseDate: String? = null,
    val postedDate: String? = null,
)
