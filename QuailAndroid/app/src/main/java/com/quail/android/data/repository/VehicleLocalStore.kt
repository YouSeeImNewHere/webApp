package com.quail.android.data.repository

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.vehicleDataStore by preferencesDataStore(name = "quail_vehicle_local")

/** Mirrors QuailCarSettingsPageView's notifyToggleRow() keys/defaults — plain
 * on-device toggles on iOS too (UserDefaults, no server sync). Tires,
 * corrective repairs, and DIY procedures used to live here as local-only
 * DataStore blobs; they now sync to the backend via VehicleOfflineRepository
 * (data/vehicle/) instead, since app/routers/vehicle.py grew real tables for
 * them — this store only holds the notification toggles now. */
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

class VehicleLocalStore(private val context: Context) {
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
