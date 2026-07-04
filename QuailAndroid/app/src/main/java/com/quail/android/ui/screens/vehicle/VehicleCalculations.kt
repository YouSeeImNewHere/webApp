package com.quail.android.ui.screens.vehicle

import com.quail.android.data.model.MaintenanceTypeDefinition
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleMaintenanceRecord
import com.quail.android.data.model.VehicleMaintenanceStatus
import java.time.LocalDate
import java.time.temporal.ChronoUnit

/** Mirrors VehicleStore.swift's lastRecord/status/nextDueDescription/averageMPG
 * (Quail Car has no server-side notion of "maintenance type" or "due" status —
 * those are computed client-side from the plain maintenance record history). */

fun lastMaintenanceRecord(records: List<VehicleMaintenanceRecord>, typeName: String): VehicleMaintenanceRecord? =
    records.filter { it.typeName.equals(typeName, ignoreCase = true) }
        .maxByOrNull { runCatching { LocalDate.parse(it.date) }.getOrNull() ?: LocalDate.MIN }

fun maintenanceStatus(type: MaintenanceTypeDefinition, records: List<VehicleMaintenanceRecord>, currentMileage: Int): VehicleMaintenanceStatus {
    if (type.monthInterval == null && type.mileageInterval == null) return VehicleMaintenanceStatus.OK
    val last = lastMaintenanceRecord(records, type.name) ?: return VehicleMaintenanceStatus.NEVER

    var overdue = false
    var dueSoon = false

    type.mileageInterval?.let { mi ->
        val remaining = (last.mileage + mi) - currentMileage
        if (remaining <= 0) overdue = true else if (remaining <= maxOf(300, mi / 10)) dueSoon = true
    }

    type.monthInterval?.let { months ->
        val lastDate = runCatching { LocalDate.parse(last.date) }.getOrNull()
        if (lastDate != null) {
            val next = lastDate.plusMonths(months.toLong())
            val days = ChronoUnit.DAYS.between(LocalDate.now(), next)
            if (days < 0) overdue = true else if (days <= 30) dueSoon = true
        }
    }

    return when {
        overdue -> VehicleMaintenanceStatus.OVERDUE
        dueSoon -> VehicleMaintenanceStatus.DUE_SOON
        else -> VehicleMaintenanceStatus.OK
    }
}

fun nextDueDescription(type: MaintenanceTypeDefinition, records: List<VehicleMaintenanceRecord>, currentMileage: Int): String {
    val last = lastMaintenanceRecord(records, type.name)
    val parts = mutableListOf<String>()

    type.mileageInterval?.let { mi ->
        val base = last?.mileage ?: currentMileage
        parts += "${base + mi} mi"
    }

    type.monthInterval?.let { months ->
        val lastDate = last?.let { runCatching { LocalDate.parse(it.date) }.getOrNull() }
        if (lastDate != null) parts += lastDate.plusMonths(months.toLong()).toString()
    }

    if (parts.isEmpty()) return if (last == null) "Never done" else "OK"
    return parts.joinToString(" · ")
}

fun averageMpg(fuelRecords: List<VehicleFuelRecord>, last: Int = 20): Double? {
    val sorted = fuelRecords.sortedByDescending { it.date }
    if (sorted.size < 2) return null
    val slice = sorted.take(last + 1)
    var totalMiles = 0
    var totalGallons = 0.0
    for (i in 0 until slice.size - 1) {
        val miles = slice[i].mileage - slice[i + 1].mileage
        if (miles <= 0) continue
        totalMiles += miles
        totalGallons += slice[i].gallons ?: 0.0
    }
    if (totalGallons <= 0 || totalMiles <= 0) return null
    return totalMiles / totalGallons
}
