package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class WidgetCreditPayload(
    val used: Double = 0.0,
    val available: Double = 0.0,
    val cap: Double = 0.0,
) {
    val pct: Double get() = if (cap > 0) (used / cap).coerceIn(0.0, 1.0) else 0.0
}

@Serializable
data class WidgetTotalsPayload(
    val checking: Double = 0.0,
    val savings: Double = 0.0,
)

@Serializable
data class WidgetTodayPayload(
    @SerialName("remaining_today") val remainingToday: Double = 0.0,
    val baseline: Double = 0.0,
)

@Serializable
data class WidgetMonthPayload(
    @SerialName("free_spend_goal") val freeSpendGoal: Double = 0.0,
)

@Serializable
data class WidgetSummaryResponse(
    val ok: Boolean = false,
    val changed: Boolean = false,
    @SerialName("update_required") val updateRequired: Boolean = false,
    @SerialName("generated_at") val generatedAt: String? = null,
    @SerialName("safe_to_spend") val safeToSpend: Double = 0.0,
    @SerialName("notifications_unread") val notificationsUnread: Int = 0,
    val credit: WidgetCreditPayload = WidgetCreditPayload(),
    val totals: WidgetTotalsPayload = WidgetTotalsPayload(),
    val today: WidgetTodayPayload = WidgetTodayPayload(),
    val month: WidgetMonthPayload = WidgetMonthPayload(),
    val warming: Boolean = false,
)
