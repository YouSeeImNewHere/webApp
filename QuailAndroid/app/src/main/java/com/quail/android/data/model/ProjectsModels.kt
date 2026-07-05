package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

enum class ProjectType(val label: String) {
    GENERIC("General"), CAR_BUILD("Car Build"), SOFTWARE("Software"), HOME("Home"), OTHER("Other");

    val serverValue: String get() = name.lowercase()

    companion object {
        fun fromServer(value: String): ProjectType = entries.firstOrNull { it.serverValue == value } ?: GENERIC
    }
}

enum class ProjectItemType(val label: String) {
    NOTE("Note"), DECISION("Decision"), BUDGET("Budget Item"), REFERENCE("Reference");
    // "photo" item type from iOS is intentionally omitted — no image capture/upload built yet.

    val serverValue: String get() = name.lowercase()

    companion object {
        fun fromServer(value: String): ProjectItemType = entries.firstOrNull { it.serverValue == value } ?: NOTE
    }
}

@Serializable
data class DecisionTask(val id: String, val title: String = "", val isDone: Boolean = false)

@Serializable
data class DecisionOption(
    val id: String,
    val title: String = "",
    val notes: String = "",
    val pros: List<String> = emptyList(),
    val cons: List<String> = emptyList(),
    val tasks: List<DecisionTask> = emptyList(),
    val estimatedCost: Double? = null,
    val isSelected: Boolean = false,
)

@Serializable
data class ProjectItem(
    val id: String,
    val type: String = "note",
    val title: String = "",
    val body: String = "",
    val options: List<DecisionOption> = emptyList(),
    val amount: Double? = null,
    val amountLabel: String = "",
    val url: String = "",
)

@Serializable
data class ProjectSection(
    val id: String,
    val title: String,
    val icon: String = "",
    val items: List<ProjectItem> = emptyList(),
)

@Serializable
data class ProjectRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val name: String = "",
    val type: String = "generic",
    val description: String = "",
    val sections: List<ProjectSection> = emptyList(),
) {
    val totalBudget: Double get() = sections.flatMap { it.items }.filter { it.type == "budget" }.sumOf { it.amount ?: 0.0 }
}

@Serializable
data class ProjectUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val name: String,
    val type: String = "generic",
    val description: String = "",
    val sections: List<ProjectSection> = emptyList(),
)

@Serializable
data class ProjectQuickNoteRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val title: String = "",
    val text: String = "",
)

@Serializable
data class ProjectQuickNoteUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val title: String = "",
    val text: String,
)

@Serializable
data class ChecklistItemEntry(val id: String, val text: String = "", val isChecked: Boolean = false)

@Serializable
data class ProjectChecklistRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val title: String = "",
    val items: List<ChecklistItemEntry> = emptyList(),
) {
    val completedCount: Int get() = items.count { it.isChecked }
}

@Serializable
data class ProjectChecklistUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val title: String,
    val items: List<ChecklistItemEntry> = emptyList(),
)

/** Mirrors NativeProjectsPage.swift's carBuildTemplate()/genericTemplate() —
 * new-project starting points. Ids are freshly generated per project, not
 * reused across instances, so this returns a builder rather than a constant. */
fun projectTemplateSections(type: ProjectType): List<ProjectSection> {
    fun sec(title: String, icon: String): ProjectSection =
        ProjectSection(id = java.util.UUID.randomUUID().toString(), title = title, icon = icon)

    return when (type) {
        ProjectType.CAR_BUILD -> listOf(
            sec("Frame & Chassis", "wrench"),
            sec("Engine & Drivetrain", "gear"),
            sec("Suspension", "suspension"),
            sec("Brakes", "brake"),
            sec("Interior", "car_interior"),
            sec("Exterior", "paint"),
            sec("Electrical", "bolt"),
            sec("Budget", "dollar"),
            sec("References & Inspiration", "photo"),
        )
        else -> listOf(
            sec("Overview", "doc"),
            sec("Tasks", "checklist"),
            sec("Budget", "dollar"),
            sec("References", "link"),
        )
    }
}
