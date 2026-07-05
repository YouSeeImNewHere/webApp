package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Backend-synced counterparts of TireSet/CorrectiveRecord/MaintenanceProcedure
 * (see VehicleModels.kt) — those are the domain types the UI renders; these
 * *Record types are the wire format for app/routers/vehicle.py's tires/
 * corrective/procedures endpoints, added so this data actually reaches the
 * database instead of living only in on-device DataStore. */

@Serializable
data class TireSetRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val brand: String = "",
    val model: String = "",
    val size: String = "",
    @SerialName("install_date") val installDate: String? = null,
    @SerialName("install_mileage") val installMileage: Int = 0,
    @SerialName("required_pressure_front") val requiredPressureFront: Int = 35,
    @SerialName("required_pressure_rear") val requiredPressureRear: Int = 35,
    @SerialName("pressure_checks") val pressureChecks: List<TirePressureCheck> = emptyList(),
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class TireSetUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val brand: String = "",
    val model: String = "",
    val size: String = "",
    @SerialName("install_date") val installDate: String? = null,
    @SerialName("install_mileage") val installMileage: Int = 0,
    @SerialName("required_pressure_front") val requiredPressureFront: Int = 35,
    @SerialName("required_pressure_rear") val requiredPressureRear: Int = 35,
    @SerialName("pressure_checks") val pressureChecks: List<TirePressureCheck> = emptyList(),
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class CorrectiveRecordRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val date: String = "",
    val mileage: Int = 0,
    val description: String = "",
    val reason: String = "",
    @SerialName("parts_replaced") val partsReplaced: List<String> = emptyList(),
    val cost: Double? = null,
    @SerialName("resolved_issue") val resolvedIssue: Boolean = false,
    @SerialName("linked_issue_id") val linkedIssueId: Int? = null,
    val notes: String = "",
)

@Serializable
data class CorrectiveRecordUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val date: String,
    val mileage: Int = 0,
    val description: String = "",
    val reason: String = "",
    @SerialName("parts_replaced") val partsReplaced: List<String> = emptyList(),
    val cost: Double? = null,
    @SerialName("resolved_issue") val resolvedIssue: Boolean = false,
    @SerialName("linked_issue_id") val linkedIssueId: Int? = null,
    val notes: String = "",
)

@Serializable
data class VehicleProcedureRecord(
    val id: Int = 0,
    @SerialName("client_id") val clientId: String = "",
    val title: String = "",
    @SerialName("related_type_name") val relatedTypeName: String = "",
    val tools: List<String> = emptyList(),
    val parts: List<String> = emptyList(),
    val steps: List<ProcedureStep> = emptyList(),
    val notes: String = "",
)

@Serializable
data class VehicleProcedureUpsertRequest(
    @SerialName("client_id") val clientId: String,
    val title: String,
    @SerialName("related_type_name") val relatedTypeName: String = "",
    val tools: List<String> = emptyList(),
    val parts: List<String> = emptyList(),
    val steps: List<ProcedureStep> = emptyList(),
    val notes: String = "",
)
