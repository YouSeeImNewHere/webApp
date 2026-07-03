package com.quailcash.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Order + labels mirror settings.py's DEFAULT_NOTIFICATION_PREFS (13 keys).
val NOTIFICATION_PREF_LABELS: List<Pair<String, String>> = listOf(
    "disable_all" to "Disable all notifications",
    "ios_push" to "Push notifications",
    "credit_usage" to "Credit card usage",
    "credit_usage_total" to "Total credit usage",
    "budget_over" to "Over budget",
    "safe_to_spend_daily" to "Daily safe-to-spend",
    "category_drift" to "Category drift",
    "runway_warning" to "Runway warning",
    "savings_streak" to "Savings streak",
    "subscription_creep" to "Subscription creep",
    "high_spend_cooldown" to "High spend cooldown",
    "small_win_reinforcement" to "Small win reinforcement",
    "user_signup_pending" to "Pending signup approval",
    "cron_error" to "Background job errors",
)

@Serializable
data class NotificationSettingsResponse(
    val prefs: Map<String, Boolean> = emptyMap(),
    @SerialName("pushover_user_key_set") val pushoverUserKeySet: Boolean = false,
    @SerialName("pushover_user_key") val pushoverUserKey: String? = null,
    @SerialName("ios_push_device_count") val iosPushDeviceCount: Int = 0,
    @SerialName("ios_push_configured") val iosPushConfigured: Boolean = false,
)

@Serializable
data class RefreshCacheResponse(
    val ok: Boolean = true,
    @SerialName("tenant_id") val tenantId: Int = 0,
    @SerialName("home_snapshot_version") val homeSnapshotVersion: Int = 0,
    @SerialName("home_cache_warmed") val homeCacheWarmed: Boolean = false,
    @SerialName("widget_version") val widgetVersion: Int = 0,
)
