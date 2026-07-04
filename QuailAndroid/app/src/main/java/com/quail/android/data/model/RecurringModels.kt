package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class RecurringTx(
    // Composite string id for transfer-matched rows (e.g. "3_013026_301.00_0"),
    // same as Transaction.id — see attach_transfer_peers_pg() in transactions.py.
    val id: String = "",
    val date: String? = null,
    val amount: Double = 0.0,
    val merchant: String? = null,
    @SerialName("account_id") val accountId: Int? = null,
    val category: String? = null,
)

@Serializable
data class RecurringPattern(
    val merchant: String? = null,
    @SerialName("merchant_norm") val merchantNorm: String? = null,
    val amount: Double = 0.0,
    val cadence: String? = null,
    val occurrences: Int = 0,
    @SerialName("first_seen") val firstSeen: String? = null,
    @SerialName("last_seen") val lastSeen: String? = null,
    @SerialName("common_gap_days") val commonGapDays: Int? = null,
    @SerialName("account_id") val accountId: Int? = null,
    val kind: String? = null,
    val active: Boolean = true,
    @SerialName("days_since_last") val daysSinceLast: Int? = null,
    @SerialName("cycle_days") val cycleDays: Int? = null,
    val tx: List<RecurringTx> = emptyList(),
    @SerialName("merchant_display") val merchantDisplay: String? = null,
) {
    // The backend never emits a stable id/key for a pattern (confirmed: iOS
    // falls back to a random UUID). Build a synthetic one for list diffing.
    val syntheticKey: String
        get() = "$merchant|$cadence|$amount|$accountId"
}

@Serializable
data class RecurringGroup(
    val merchant: String = "",
    @SerialName("last_seen") val lastSeen: String? = null,
    val active: Boolean = true,
    @SerialName("merchant_display") val merchantDisplay: String? = null,
    val patterns: List<RecurringPattern> = emptyList(),
)

@Serializable
data class RecurringCalendarEvent(
    val date: String = "",
    val merchant: String = "",
    @SerialName("merchant_display") val merchantDisplay: String? = null,
    val category: String? = null,
    val amount: Double = 0.0,
    val cadence: String? = null,
    // Only present on the synthetic interest-income events this endpoint
    // injects — real recurring withdrawal events never set it.
    val type: String? = null,
    val kind: String? = null,
    @SerialName("account_id") val accountId: Int? = null,
) {
    val isIncome: Boolean get() = type == "income" || cadence == "paycheck"
}

@Serializable
data class RecurringCalendarResponse(
    val ok: Boolean = true,
    val year: Int = 0,
    val month: Int = 0,
    val start: String? = null,
    val end: String? = null,
    val events: List<RecurringCalendarEvent> = emptyList(),
)
