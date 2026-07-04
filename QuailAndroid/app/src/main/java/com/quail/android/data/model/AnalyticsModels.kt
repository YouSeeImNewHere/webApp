package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ReportRange(val start: String? = null, val end: String? = null)

@Serializable
data class ReportSummary(
    val income: Double = 0.0,
    val spending: Double = 0.0,
    val net: Double = 0.0,
    @SerialName("starting_balance") val startingBalance: Double = 0.0,
    @SerialName("ending_balance") val endingBalance: Double = 0.0,
)

@Serializable
data class ReportCategoryAmount(val category: String = "", val amount: Double = 0.0)

@Serializable
data class ReportAccountSummary(
    @SerialName("account_id") val accountId: Int = 0,
    val bank: String? = null,
    val name: String? = null,
    @SerialName("account_type") val accountType: String? = null,
    @SerialName("start_balance") val startBalance: Double = 0.0,
    @SerialName("end_balance") val endBalance: Double = 0.0,
    val change: Double = 0.0,
)

@Serializable
data class ReportTransaction(
    val date: String? = null,
    val merchant: String? = null,
    val category: String? = null,
    val amount: Double = 0.0,
    val account: String? = null,
)

@Serializable
data class ReportBiggestTransactions(
    val outflows: List<ReportTransaction> = emptyList(),
    val inflows: List<ReportTransaction> = emptyList(),
)

@Serializable
data class ReportRecurringSubscription(
    val merchant: String = "",
    val category: String? = null,
    val hits: Int = 0,
    val total: Double = 0.0,
)

@Serializable
data class ReportBudgetPerformance(
    @SerialName("planned_allocations") val plannedAllocations: Double = 0.0,
    @SerialName("actual_spent_on_allocated") val actualSpentOnAllocated: Double = 0.0,
    @SerialName("remaining_allocated") val remainingAllocated: Double = 0.0,
    @SerialName("free_spend_so_far") val freeSpendSoFar: Double = 0.0,
)

@Serializable
data class ReportChanges(
    @SerialName("income_prev_month") val incomePrevMonth: Double = 0.0,
    @SerialName("spending_prev_month") val spendingPrevMonth: Double = 0.0,
    @SerialName("income_change_pct") val incomeChangePct: Double? = null,
    @SerialName("spending_change_pct") val spendingChangePct: Double? = null,
    @SerialName("income_change_abs") val incomeChangeAbs: Double = 0.0,
    @SerialName("spending_change_abs") val spendingChangeAbs: Double = 0.0,
)

@Serializable
data class MonthlyReport(
    val ok: Boolean = true,
    val month: String = "",
    val range: ReportRange? = null,
    val summary: ReportSummary = ReportSummary(),
    @SerialName("category_breakdown") val categoryBreakdown: List<ReportCategoryAmount> = emptyList(),
    @SerialName("account_summary") val accountSummary: List<ReportAccountSummary> = emptyList(),
    @SerialName("biggest_transactions") val biggestTransactions: ReportBiggestTransactions = ReportBiggestTransactions(),
    @SerialName("recurring_subscriptions") val recurringSubscriptions: List<ReportRecurringSubscription> = emptyList(),
    @SerialName("budget_performance") val budgetPerformance: ReportBudgetPerformance = ReportBudgetPerformance(),
    @SerialName("changes_vs_previous_month") val changesVsPreviousMonth: ReportChanges = ReportChanges(),
)
