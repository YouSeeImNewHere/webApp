package com.quail.android.data.repository

import android.content.Context
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

    companion object {
        @Volatile private var instance: VehicleLocalStore? = null

        fun getInstance(context: Context): VehicleLocalStore =
            instance ?: synchronized(this) {
                instance ?: VehicleLocalStore(context.applicationContext).also { instance = it }
            }
    }
}
