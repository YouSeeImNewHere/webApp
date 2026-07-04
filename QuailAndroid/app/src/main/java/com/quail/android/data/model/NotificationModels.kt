package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NotificationItem(
    val id: Int,
    val kind: String? = null,
    val subject: String? = null,
    val sender: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("created_at_local") val createdAtLocal: String? = null,
    @SerialName("is_read") val isRead: Boolean = false,
)

@Serializable
data class NotificationListResponse(val items: List<NotificationItem> = emptyList())

@Serializable
data class NotificationDetail(
    val id: Int,
    val kind: String? = null,
    val subject: String? = null,
    val sender: String? = null,
    val body: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("created_at_local") val createdAtLocal: String? = null,
    @SerialName("is_read") val isRead: Boolean = false,
    val dismissed: Boolean = false,
)

@Serializable
data class OkResponse(val ok: Boolean = true)
