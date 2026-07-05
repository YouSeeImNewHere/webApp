package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

enum class BugStatus(val label: String) {
    OPEN("Open"), IN_PROGRESS("In Progress"), RESOLVED("Resolved");

    companion object {
        fun fromServer(value: String): BugStatus = when (value) {
            "in_progress" -> IN_PROGRESS
            "resolved" -> RESOLVED
            else -> OPEN
        }
    }

    val serverValue: String get() = when (this) {
        OPEN -> "open"
        IN_PROGRESS -> "in_progress"
        RESOLVED -> "resolved"
    }
}

@Serializable
data class BugReportRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val title: String = "",
    val description: String = "",
    val status: String = "open",
    val route: String = "",
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class BugReportUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val title: String,
    val description: String = "",
    val status: String = "open",
    val route: String = "",
)

@Serializable
data class BugNoteRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val text: String = "",
    @SerialName("is_resolved") val isResolved: Boolean = false,
)

@Serializable
data class BugNoteUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val text: String,
    @SerialName("is_resolved") val isResolved: Boolean = false,
)
