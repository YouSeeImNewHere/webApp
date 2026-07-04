package com.quail.android.data.repository

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.quail.android.data.model.CorrectiveRecord
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.data.model.TireSet
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

private val Context.vehicleDataStore by preferencesDataStore(name = "quail_vehicle_local")

/** Mirrors QuailCarSettingsPageView's notifyToggleRow() keys/defaults — plain
 * on-device toggles on iOS too (UserDefaults, no server sync). */
enum class VehicleNotifyPref(val key: String, val defaultOn: Boolean, val title: String, val subtitle: String) {
    MAINTENANCE_DUE(
        "vehicle_notify_maintenance_due", true,
        "Service Due Reminders", "Approaching oil changes, rotations, and more",
    ),
    OVERDUE(
        "vehicle_notify_overdue", true,
        "Overdue Service Alerts", "Past-due date or mileage threshold",
    ),
    INSPECTION_WEEKLY(
        "vehicle_notify_inspection_weekly", true,
        "Weekly Inspection Reminders", "Tire pressure, fluids, lights, wipers",
    ),
    INSPECTION_MONTHLY(
        "vehicle_notify_inspection_monthly", true,
        "Monthly Inspection Reminders", "Battery, belts, brake pads visual, tread depth",
    ),
    GAS_DETECTION(
        "vehicle_notify_gas_detection", true,
        "Gas Station Detection", "Prompt to log a fill-up when a gas transaction appears",
    ),
    TIRE_PRESSURE(
        "vehicle_notify_tire_pressure", false,
        "Tire Pressure Reminders", "Remind me when pressure check is overdue",
    ),
}

/** Tires, corrective repairs, and DIY procedures have no backend table (see
 * app/routers/vehicle.py) — VehicleStore.swift keeps these purely on-device
 * too, so this mirrors that with DataStore instead of iOS's local JSON files. */
class VehicleLocalStore(private val context: Context) {
    private object Keys {
        val TIRE_SETS = stringPreferencesKey("tire_sets")
        val CORRECTIVE_RECORDS = stringPreferencesKey("corrective_records")
        val PROCEDURES = stringPreferencesKey("procedures")
    }

    private val json = Json { ignoreUnknownKeys = true }

    val tireSets: Flow<List<TireSet>> = context.vehicleDataStore.data.map { prefs ->
        prefs[Keys.TIRE_SETS]?.let { runCatching { json.decodeFromString<List<TireSet>>(it) }.getOrNull() } ?: emptyList()
    }

    val correctiveRecords: Flow<List<CorrectiveRecord>> = context.vehicleDataStore.data.map { prefs ->
        prefs[Keys.CORRECTIVE_RECORDS]?.let { runCatching { json.decodeFromString<List<CorrectiveRecord>>(it) }.getOrNull() } ?: emptyList()
    }

    val procedures: Flow<List<MaintenanceProcedure>> = context.vehicleDataStore.data.map { prefs ->
        prefs[Keys.PROCEDURES]?.let { runCatching { json.decodeFromString<List<MaintenanceProcedure>>(it) }.getOrNull() } ?: emptyList()
    }

    suspend fun saveTireSets(sets: List<TireSet>) {
        context.vehicleDataStore.edit { prefs -> prefs[Keys.TIRE_SETS] = json.encodeToString(sets) }
    }

    suspend fun saveCorrectiveRecords(records: List<CorrectiveRecord>) {
        context.vehicleDataStore.edit { prefs -> prefs[Keys.CORRECTIVE_RECORDS] = json.encodeToString(records) }
    }

    suspend fun saveProcedures(procedures: List<MaintenanceProcedure>) {
        context.vehicleDataStore.edit { prefs -> prefs[Keys.PROCEDURES] = json.encodeToString(procedures) }
    }

    fun notifyPref(pref: VehicleNotifyPref): Flow<Boolean> = context.vehicleDataStore.data.map { prefs ->
        prefs[booleanPreferencesKey(pref.key)] ?: pref.defaultOn
    }

    suspend fun setNotifyPref(pref: VehicleNotifyPref, value: Boolean) {
        context.vehicleDataStore.edit { prefs -> prefs[booleanPreferencesKey(pref.key)] = value }
    }

    companion object {
        @Volatile private var instance: VehicleLocalStore? = null

        fun getInstance(context: Context): VehicleLocalStore =
            instance ?: synchronized(this) {
                instance ?: VehicleLocalStore(context.applicationContext).also { instance = it }
            }
    }
}
