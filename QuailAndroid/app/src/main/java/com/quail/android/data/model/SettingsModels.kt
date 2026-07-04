package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Order + labels mirror settings.py's DEFAULT_NOTIFICATION_PREFS (14 keys).
val NOTIFICATION_PREF_LABELS: List<Pair<String, String>> = listOf(
    "disable_all" to "Disable all notifications",
    "ios_push" to "iOS push notifications",
    "android_push" to "Push notifications",
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
    @SerialName("android_push_device_count") val androidPushDeviceCount: Int = 0,
    @SerialName("android_push_configured") val androidPushConfigured: Boolean = false,
)

@Serializable
data class AndroidPushDeviceBody(
    val token: String,
    @SerialName("device_name") val deviceName: String? = null,
    @SerialName("app_version") val appVersion: String? = null,
)

@Serializable
data class AndroidPushDeviceResponse(
    val ok: Boolean = true,
    @SerialName("device_count") val deviceCount: Int = 0,
    @SerialName("revoked") val revoked: Boolean? = null,
)

@Serializable
data class HomelabRamMetrics(
    @SerialName("usedMB") val usedMB: Double? = null,
    @SerialName("totalMB") val totalMB: Double? = null,
    @SerialName("usedPercent") val usedPercent: Double? = null,
)

@Serializable
data class HomelabDiskMetrics(
    @SerialName("usedGB") val usedGB: Double? = null,
    @SerialName("totalGB") val totalGB: Double? = null,
    @SerialName("usedPercent") val usedPercent: Double? = null,
)

@Serializable
data class HomelabNetworkMetrics(
    @SerialName("inKbps") val inKbps: Double? = null,
    @SerialName("outKbps") val outKbps: Double? = null,
    val units: String? = null,
)

@Serializable
data class HomelabTemperature(
    val label: String,
    val celsius: Double,
)

@Serializable
data class HomelabMetrics(
    @SerialName("cpuUsedPercent") val cpuUsedPercent: Double? = null,
    val ram: HomelabRamMetrics? = null,
    @SerialName("diskRoot") val diskRoot: HomelabDiskMetrics? = null,
    val network: HomelabNetworkMetrics? = null,
    val temperatures: List<HomelabTemperature>? = null,
    val error: String? = null,
)

@Serializable
data class HomelabMetricsResponse(
    val homelab: HomelabMetrics = HomelabMetrics(),
)

@Serializable
data class RefreshCacheResponse(
    val ok: Boolean = true,
    @SerialName("tenant_id") val tenantId: Int = 0,
    @SerialName("home_snapshot_version") val homeSnapshotVersion: Int = 0,
    @SerialName("home_cache_warmed") val homeCacheWarmed: Boolean = false,
    @SerialName("widget_version") val widgetVersion: Int = 0,
)
