package com.quailcash.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Transaction(
    // Not always a plain row id: attach_transfer_peers_pg() (transactions.py)
    // rewrites this into a composite string key (e.g. "6_070126_23.90_0")
    // for transfer-matched rows, so it can't be typed as Int.
    val id: String,
    @SerialName("account_id") val accountId: Int? = null,
    val postedDate: String? = null,
    val merchant: String? = null,
    val amount: Double = 0.0,
    val status: String? = null,
    val bank: String? = null,
    val card: String? = null,
    val accountType: String? = null,
    val category: String? = null,
    val dateISO: String? = null,
)

@Serializable
data class CategoryTotal(
    val category: String,
    val total: Double = 0.0,
    @SerialName("tx_count") val txCount: Int = 0,
)

@Serializable
data class CategoryTotalsMonth(
    val categories: List<CategoryTotal> = emptyList(),
    @SerialName("unassigned_all_time") val unassignedAllTime: Int = 0,
)

@Serializable
data class UnknownMerchantTotal(
    val total: Double = 0.0,
    @SerialName("tx_count") val txCount: Int = 0,
)

@Serializable
data class BankAccount(
    // Shape from accounts.py bank_totals(): {"id": int, "name": display_name,
    // "total": balance, ...}. No institution/type/verifiedDate/creditUtilization
    // fields exist here — institution is already folded into `name`.
    val id: Int,
    val name: String? = null,
    val total: Double = 0.0,
    @SerialName("last_csv_upload_at") val lastCsvUploadAt: String? = null,
    @SerialName("last_manual_verified_at") val lastManualVerifiedAt: String? = null,
    @SerialName("credit_limit") val creditLimit: Double? = null,
)

@Serializable
data class BankGroup(
    val total: Double = 0.0,
    val accounts: List<BankAccount> = emptyList(),
)

@Serializable
data class MonthBudget(
    @SerialName("safe_to_spend") val safeToSpend: Double = 0.0,
    @SerialName("daily_limit") val dailyLimit: Double = 0.0,
    @SerialName("days_left") val daysLeft: Int = 0,
    @SerialName("as_of") val asOf: String? = null,
    @SerialName("expected_income") val expectedIncome: Double = 0.0,
    @SerialName("spent_so_far") val spentSoFar: Double = 0.0,
    @SerialName("bills_remaining") val billsRemaining: Double = 0.0,
    @SerialName("extra_saved_applied") val extraSavedApplied: Double = 0.0,
    @SerialName("base_income") val baseIncome: Double = 0.0,
    @SerialName("income_basis_total") val incomeBasisTotal: Double = 0.0,
    @SerialName("income_basis_month") val incomeBasisMonth: IncomeBasisMonth? = null,
    @SerialName("income_basis_paychecks") val incomeBasisPaychecks: List<IncomeBasisPaycheck> = emptyList(),
    // Budget-page-only fields — same month_budget_home_cached() dict as
    // above, just extra keys only page_budget() consumers care about.
    @SerialName("savings_goal") val savingsGoal: Double = 0.0,
    @SerialName("allocations_total") val allocationsTotal: Double = 0.0,
    @SerialName("budgeted_spent_total") val budgetedSpentTotal: Double = 0.0,
    @SerialName("bills_total") val billsTotal: Double = 0.0,
    @SerialName("free_spend_goal") val freeSpendGoal: Double = 0.0,
    @SerialName("spent_free") val spentFree: Double = 0.0,
    @SerialName("weekday_days_left") val weekdayDaysLeft: Int = 0,
    @SerialName("weekend_days_left") val weekendDaysLeft: Int = 0,
)

@Serializable
data class DayLimit(
    val baseline: Double = 0.0,
    @SerialName("remaining_today") val remainingToday: Double = 0.0,
    @SerialName("spent_today_free") val spentTodayFree: Double = 0.0,
    val day: String? = null,
)

@Serializable
data class NotificationsUnread(
    val unread: Int = 0,
)

@Serializable
data class HomePayload(
    val transactions: List<Transaction> = emptyList(),
    @SerialName("category_totals_month") val categoryTotalsMonth: CategoryTotalsMonth? = null,
    @SerialName("unknown_merchant_total_month") val unknownMerchantTotalMonth: UnknownMerchantTotal? = null,
    // unread_count() (notifications.py) returns {"unread": <int>}, not a bare int.
    @SerialName("notifications_unread") val notificationsUnread: NotificationsUnread? = null,
    @SerialName("bank_totals") val bankTotals: Map<String, BankGroup> = emptyMap(),
    @SerialName("month_budget") val monthBudget: MonthBudget? = null,
    @SerialName("day_limit") val dayLimit: DayLimit? = null,
)

@Serializable
data class UpcomingEvent(
    val date: String,
    val merchant: String? = null,
    val amount: Double? = null,
    val type: String? = null,
    val cadence: String? = null,
    val category: String? = null,
    @SerialName("account_id") val accountId: Int? = null,
)

@Serializable
data class UpcomingResponse(
    val ok: Boolean = true,
    val start: String? = null,
    val end: String? = null,
    @SerialName("days_ahead") val daysAhead: Int = 30,
    val events: List<UpcomingEvent> = emptyList(),
)

@Serializable
data class UpcomingRequest(
    @SerialName("days_ahead") val daysAhead: Int = 30,
    @SerialName("min_occ") val minOcc: Int = 3,
    @SerialName("include_stale") val includeStale: Boolean = false,
)
