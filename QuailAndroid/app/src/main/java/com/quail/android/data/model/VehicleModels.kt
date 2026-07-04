package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---- Profile ----

@Serializable
data class VehicleProfile(
    val id: Int? = null,
    val make: String = "",
    val model: String = "",
    val year: Int? = null,
    val vin: String = "",
    @SerialName("license_plate") val licensePlate: String = "",
    @SerialName("oil_type") val oilType: String = "",
    @SerialName("oil_capacity_with_filter") val oilCapacityWithFilter: Double? = null,
    @SerialName("oil_capacity_without_filter") val oilCapacityWithoutFilter: Double? = null,
    @SerialName("transmission_fluid_type") val transmissionFluidType: String = "",
    @SerialName("transmission_fluid_capacity") val transmissionFluidCapacity: Double? = null,
    @SerialName("coolant_type") val coolantType: String = "",
    @SerialName("current_mileage") val currentMileage: Int = 0,
    @SerialName("tank_capacity_gallons") val tankCapacityGallons: Double? = null,
    val notes: String = "",
) {
    val isEmpty: Boolean get() = make.isBlank() && model.isBlank()
    val displayName: String get() {
        val parts = listOfNotNull(year?.toString(), make.takeIf { it.isNotBlank() }, model.takeIf { it.isNotBlank() })
        return if (parts.isEmpty()) "My Vehicle" else parts.joinToString(" ")
    }
}

@Serializable
data class VehicleProfileUpdateRequest(
    val make: String = "",
    val model: String = "",
    val year: Int? = null,
    val vin: String = "",
    @SerialName("license_plate") val licensePlate: String = "",
    @SerialName("oil_type") val oilType: String = "",
    @SerialName("oil_capacity_with_filter") val oilCapacityWithFilter: Double? = null,
    @SerialName("oil_capacity_without_filter") val oilCapacityWithoutFilter: Double? = null,
    @SerialName("transmission_fluid_type") val transmissionFluidType: String = "",
    @SerialName("transmission_fluid_capacity") val transmissionFluidCapacity: Double? = null,
    @SerialName("coolant_type") val coolantType: String = "",
    @SerialName("current_mileage") val currentMileage: Int = 0,
    @SerialName("tank_capacity_gallons") val tankCapacityGallons: Double? = null,
    val notes: String = "",
)

@Serializable
data class VehicleMileageUpdateRequest(@SerialName("current_mileage") val currentMileage: Int)

// ---- Fuel ----

@Serializable
data class VehicleFuelRecord(
    val id: Int = 0,
    val date: String = "",
    val mileage: Int = 0,
    val gallons: Double? = null,
    @SerialName("price_per_gallon") val pricePerGallon: Double? = null,
    @SerialName("total_cost") val totalCost: Double? = null,
    val station: String = "",
    val notes: String = "",
)

@Serializable
data class VehicleFuelListResponse(val records: List<VehicleFuelRecord> = emptyList(), val total: Int = 0)

@Serializable
data class VehicleFuelCreateRequest(
    val date: String,
    val mileage: Int,
    val gallons: Double? = null,
    @SerialName("price_per_gallon") val pricePerGallon: Double? = null,
    @SerialName("total_cost") val totalCost: Double? = null,
    val station: String = "",
    val notes: String = "",
)

// ---- Maintenance ----

@Serializable
data class VehicleMaintenanceRecord(
    val id: Int = 0,
    @SerialName("type_name") val typeName: String = "",
    val date: String = "",
    val mileage: Int = 0,
    val cost: Double? = null,
    @SerialName("is_shop_performed") val isShopPerformed: Boolean = false,
    @SerialName("shop_name") val shopName: String = "",
    val notes: String = "",
)

@Serializable
data class VehicleMaintenanceListResponse(val records: List<VehicleMaintenanceRecord> = emptyList(), val total: Int = 0)

@Serializable
data class VehicleMaintenanceCreateRequest(
    @SerialName("type_name") val typeName: String,
    val date: String,
    val mileage: Int,
    val cost: Double? = null,
    @SerialName("is_shop_performed") val isShopPerformed: Boolean = false,
    @SerialName("shop_name") val shopName: String = "",
    val notes: String = "",
)

// ---- Issues ----

@Serializable
data class VehicleIssue(
    val id: Int = 0,
    val title: String = "",
    val description: String = "",
    val severity: String = "medium",
    @SerialName("mileage_noticed") val mileageNoticed: Int? = null,
    @SerialName("date_noticed") val dateNoticed: String? = null,
    @SerialName("is_resolved") val isResolved: Boolean = false,
    @SerialName("resolved_date") val resolvedDate: String? = null,
    val notes: String = "",
)

@Serializable
data class VehicleIssueResolveRequest(@SerialName("resolved_date") val resolvedDate: String? = null)

@Serializable
data class VehicleIssueCreateRequest(
    val title: String,
    val description: String = "",
    val severity: String = "medium",
    @SerialName("mileage_noticed") val mileageNoticed: Int? = null,
    @SerialName("date_noticed") val dateNoticed: String? = null,
    val notes: String = "",
)

// ---- Inspections ----

@Serializable
data class VehicleInspectionItem(
    val id: Int = 0,
    val name: String = "",
    @SerialName("periodicity_days") val periodicityDays: Int = 30,
    @SerialName("last_checked_date") val lastCheckedDate: String? = null,
    @SerialName("is_built_in") val isBuiltIn: Boolean = false,
)

@Serializable
data class VehicleInspectionCreateRequest(
    val name: String,
    @SerialName("periodicity_days") val periodicityDays: Int = 30,
    @SerialName("is_built_in") val isBuiltIn: Boolean = false,
)

// ---- Locally-stored entities (no backend table) ----

@Serializable
data class TirePressureCheck(
    val id: String,
    val date: String,
    val mileage: Int,
    val frontLeft: Int,
    val frontRight: Int,
    val rearLeft: Int,
    val rearRight: Int,
    val notes: String = "",
)

@Serializable
data class TireSet(
    val id: String,
    val brand: String = "",
    val model: String = "",
    val size: String = "",
    val installDate: String,
    val installMileage: Int = 0,
    val requiredPressureFront: Int = 35,
    val requiredPressureRear: Int = 35,
    val pressureChecks: List<TirePressureCheck> = emptyList(),
    val isActive: Boolean = true,
) {
    val displayName: String get() {
        val parts = listOf(brand, model, size).filter { it.isNotBlank() }
        return if (parts.isEmpty()) "Unnamed Tires" else parts.joinToString(" ")
    }
    val lastPressureCheck: TirePressureCheck? get() = pressureChecks.maxByOrNull { it.date }
}

@Serializable
data class CorrectiveRecord(
    val id: String,
    val date: String,
    val mileage: Int = 0,
    val description: String = "",
    val reason: String = "",
    val partsReplaced: List<String> = emptyList(),
    val cost: Double? = null,
    val resolvedIssue: Boolean = false,
    val linkedIssueId: Int? = null,
    val notes: String = "",
)

@Serializable
data class ProcedureStep(val id: String, val text: String = "")

@Serializable
data class MaintenanceProcedure(
    val id: String,
    val title: String = "",
    val relatedTypeName: String = "",
    val tools: List<String> = emptyList(),
    val parts: List<String> = emptyList(),
    val steps: List<ProcedureStep> = emptyList(),
    val notes: String = "",
    val lastUpdated: String = "",
)

// ---- Maintenance type definitions (hardcoded built-ins, matches iOS defaults) ----

enum class MaintenanceColor { ORANGE, BLUE, RED, YELLOW, GREEN, TEAL, PURPLE, GRAY }

data class MaintenanceTypeDefinition(
    val name: String,
    val monthInterval: Int? = null,
    val mileageInterval: Int? = null,
    val colorName: MaintenanceColor,
)

enum class VehicleMaintenanceStatus { OK, DUE_SOON, OVERDUE, NEVER }

val DEFAULT_MAINTENANCE_TYPES = listOf(
    MaintenanceTypeDefinition("Oil Change", monthInterval = 6, mileageInterval = 5000, colorName = MaintenanceColor.ORANGE),
    MaintenanceTypeDefinition("Tire Rotation", monthInterval = 6, mileageInterval = 7500, colorName = MaintenanceColor.BLUE),
    MaintenanceTypeDefinition("Brake Pads", mileageInterval = 50000, colorName = MaintenanceColor.RED),
    MaintenanceTypeDefinition("Brake Fluid", monthInterval = 24, colorName = MaintenanceColor.RED),
    MaintenanceTypeDefinition("Spark Plugs", mileageInterval = 30000, colorName = MaintenanceColor.YELLOW),
    MaintenanceTypeDefinition("Air Filter", monthInterval = 12, mileageInterval = 15000, colorName = MaintenanceColor.GREEN),
    MaintenanceTypeDefinition("Cabin Filter", monthInterval = 12, mileageInterval = 15000, colorName = MaintenanceColor.TEAL),
    MaintenanceTypeDefinition("Coolant Flush", monthInterval = 24, mileageInterval = 30000, colorName = MaintenanceColor.BLUE),
    MaintenanceTypeDefinition("Transmission Fluid", mileageInterval = 30000, colorName = MaintenanceColor.PURPLE),
    MaintenanceTypeDefinition("Battery", monthInterval = 48, colorName = MaintenanceColor.GREEN),
    MaintenanceTypeDefinition("Timing Belt", mileageInterval = 60000, colorName = MaintenanceColor.GRAY),
)

val DEFAULT_INSPECTION_ITEMS = listOf(
    "Tire Pressure" to 7,
    "Fluid Levels" to 7,
    "Lights" to 7,
    "Wipers" to 7,
    "Battery Terminals" to 30,
    "Belts & Hoses" to 30,
    "Brake Pad Visual" to 30,
    "Tire Tread Depth" to 30,
)
