package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---- Income breakdown (reuses month_budget fields, no separate endpoint) ----

@Serializable
data class IncomeBasisMonth(
    val year: Int = 0,
    val month: Int = 0,
    val label: String? = null,
)

@Serializable
data class IncomeBasisPaycheck(
    val date: String? = null,
    val merchant: String? = null,
    val amount: Double = 0.0,
    @SerialName("account_id") val accountId: Int? = null,
)

// ---- Extra saved breakdown: GET /extra-saved-detail ----

@Serializable
data class ExtraSavedDay(
    val day: String,
    val baseline: Double = 0.0,
    @SerialName("spent_today_total") val spentTodayTotal: Double = 0.0,
    @SerialName("spent_today_budgeted") val spentTodayBudgeted: Double = 0.0,
    @SerialName("spent_today_free") val spentTodayFree: Double = 0.0,
    val leftover: Double = 0.0,
    @SerialName("applied_to_extra_saved") val appliedToExtraSaved: Double = 0.0,
    @SerialName("extra_saved_after_day") val extraSavedAfterDay: Double = 0.0,
)

@Serializable
data class ExtraSavedDetail(
    val ok: Boolean = true,
    @SerialName("month_start") val monthStart: String? = null,
    val today: String? = null,
    @SerialName("total_extra_saved") val totalExtraSaved: Double = 0.0,
    val days: List<ExtraSavedDay> = emptyList(),
)

// ---- Transaction detail: GET /transaction/{id} ----

@Serializable
data class TransactionDetail(
    val id: String,
    @SerialName("account_id") val accountId: Int? = null,
    val postedDate: String? = null,
    val purchaseDate: String? = null,
    val merchant: String? = null,
    val amount: Double = 0.0,
    val status: String? = null,
    val bank: String? = null,
    val card: String? = null,
    val accountType: String? = null,
    val category: String? = null,
    @SerialName("is_ignored") val isIgnored: Boolean = false,
    @SerialName("category_rule_id") val categoryRuleId: Int? = null,
    @SerialName("category_rule_pattern") val categoryRulePattern: String? = null,
)

@Serializable
data class TransactionDetailResponse(
    val ok: Boolean = true,
    val transaction: TransactionDetail,
)

// ---- Transaction mutations: transactions_feeds.py ----

@Serializable
data class TxCategoryUpdateRequest(val category: String = "")

@Serializable
data class TxCategoryUpdateResponse(val ok: Boolean = true, val id: String = "", val category: String = "")

@Serializable
data class TxMetaUpdateRequest(val status: String? = null, val postedDate: String? = null)

@Serializable
data class TxMetaUpdateResponse(val ok: Boolean = true, val id: String = "", val status: String? = null, val postedDate: String? = null)

@Serializable
data class TxInvertAmountResponse(val ok: Boolean = true, val id: String = "", val amount: Double = 0.0)

@Serializable
data class TxIgnoreUpdateRequest(val ignored: Boolean)

@Serializable
data class TxIgnoreUpdateResponse(val ok: Boolean = true, val id: String = "", @SerialName("is_ignored") val isIgnored: Boolean = false)

@Serializable
data class TxDeleteResponse(val ok: Boolean = true, val deleted: String = "")

// ---- Verify balance: POST /account/{id}/balance-verified ----

@Serializable
data class VerifyBalanceRequest(
    @SerialName("verified_date") val verifiedDate: String? = null,
)

@Serializable
data class VerifyBalanceResponse(
    val ok: Boolean = true,
    @SerialName("account_id") val accountId: Int = 0,
    @SerialName("last_csv_upload_at") val lastCsvUploadAt: String? = null,
    @SerialName("last_manual_verified_at") val lastManualVerifiedAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

// ---- Spent so far: GET /spent-so-far-breakdown, GET /spent-so-far-transactions ----

@Serializable
data class SpentSoFarCategory(
    val category: String = "",
    val total: Double = 0.0,
)

@Serializable
data class SpentSoFarBreakdown(
    val total: Double = 0.0,
    @SerialName("total_all") val totalAll: Double = 0.0,
    val excluded: List<SpentSoFarCategory> = emptyList(),
    val included: List<SpentSoFarCategory> = emptyList(),
    val start: String? = null,
    val end: String? = null,
    @SerialName("roundups_total") val roundupsTotal: Double = 0.0,
)

@Serializable
data class SpentSoFarTransaction(
    val id: String,
    val date: String? = null,
    val amount: Double = 0.0,
    val merchant: String? = null,
    val category: String? = null,
    val bank: String? = null,
    val card: String? = null,
)

@Serializable
data class SpentSoFarTransactionsResponse(
    val ok: Boolean = true,
    val transactions: List<SpentSoFarTransaction> = emptyList(),
)

// ---- Unassigned wizard: GET /unassigned, POST /category-rules ----

@Serializable
data class UnassignedTransaction(
    val id: String,
    val postedDate: String? = null,
    val merchant: String? = null,
    val amount: Double = 0.0,
    val bank: String? = null,
    val card: String? = null,
    @SerialName("usage_count") val usageCount: Int? = null,
)

@Serializable
data class CategoryRuleCreateRequest(
    val category: String,
    val keywords: List<String> = emptyList(),
    @SerialName("apply_now") val applyNow: Boolean = true,
)

@Serializable
data class CategoryRuleApplyJob(
    val id: Int = 0,
    val status: String? = null,
    @SerialName("total_applied") val totalApplied: Int = 0,
    val error: String? = null,
)

@Serializable
data class CategoryRuleApplyJobResponse(
    val ok: Boolean = true,
    val job: CategoryRuleApplyJob,
)

@Serializable
data class CategoryRuleCreateResponse(
    val ok: Boolean = true,
    val pattern: String? = null,
    val applied: Int = 0,
    @SerialName("apply_job") val applyJob: CategoryRuleApplyJob? = null,
)

// ---- Finance this purchase: POST /financing/plans ----

@Serializable
data class FinancingPlanCreateRequest(
    val label: String,
    @SerialName("total_amount") val totalAmount: Double,
    @SerialName("total_months") val totalMonths: Int,
    @SerialName("transaction_id") val transactionId: String? = null,
)

@Serializable
data class FinancingPlanResponse(
    val id: Int = 0,
    val label: String = "",
    @SerialName("total_amount") val totalAmount: Double = 0.0,
    @SerialName("monthly_payment") val monthlyPayment: Double = 0.0,
    @SerialName("total_months") val totalMonths: Int = 0,
    @SerialName("months_paid") val monthsPaid: Int = 0,
    @SerialName("months_remaining") val monthsRemaining: Int = 0,
    @SerialName("amount_paid") val amountPaid: Double = 0.0,
    @SerialName("amount_remaining") val amountRemaining: Double = 0.0,
    @SerialName("is_complete") val isComplete: Boolean = false,
    @SerialName("start_date") val startDate: String? = null,
    @SerialName("transaction_id") val transactionId: String? = null,
)

@Serializable
data class FinancingPlanPayResponse(
    @SerialName("months_paid") val monthsPaid: Int = 0,
    @SerialName("is_complete") val isComplete: Boolean = false,
)
