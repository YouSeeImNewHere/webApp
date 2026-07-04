package com.quail.android.ui.screens.vehicle

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.CorrectiveRecord
import com.quail.android.data.model.DEFAULT_INSPECTION_ITEMS
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.data.model.TirePressureCheck
import com.quail.android.data.model.TireSet
import com.quail.android.data.model.VehicleFuelCreateRequest
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleInspectionCreateRequest
import com.quail.android.data.model.VehicleInspectionItem
import com.quail.android.data.model.VehicleIssue
import com.quail.android.data.model.VehicleIssueCreateRequest
import com.quail.android.data.model.VehicleMaintenanceCreateRequest
import com.quail.android.data.model.VehicleMaintenanceRecord
import com.quail.android.data.model.VehicleProfile
import com.quail.android.data.model.VehicleProfileUpdateRequest
import com.quail.android.data.repository.HomeRepository
import com.quail.android.data.repository.VehicleLocalStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.UUID

data class VehicleData(
    val profile: VehicleProfile,
    val maintenanceRecords: List<VehicleMaintenanceRecord>,
    val inspections: List<VehicleInspectionItem>,
    val fuelRecords: List<VehicleFuelRecord>,
    val issues: List<VehicleIssue>,
    val tireSets: List<TireSet>,
    val correctiveRecords: List<CorrectiveRecord>,
    val procedures: List<MaintenanceProcedure>,
) {
    val activeTireSet: TireSet? get() = tireSets.firstOrNull { it.isActive }
    val openIssues: List<VehicleIssue> get() = issues.filter { !it.isResolved }
}

sealed interface VehicleUiState {
    data object Loading : VehicleUiState
    data class Error(val message: String) : VehicleUiState
    data class Success(val data: VehicleData) : VehicleUiState
}

class VehicleViewModel(
    private val repository: HomeRepository,
    private val localStore: VehicleLocalStore,
) : ViewModel() {
    private val _uiState = MutableStateFlow<VehicleUiState>(VehicleUiState.Loading)
    val uiState: StateFlow<VehicleUiState> = _uiState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            try {
                val profile = repository.getVehicleProfile()
                val maintenance = repository.getVehicleMaintenance()
                val inspections = loadOrSeedInspections()
                val fuel = repository.getVehicleFuel()
                val issues = repository.getVehicleIssues()
                val tireSets = localStore.tireSets.first()
                val correctiveRecords = localStore.correctiveRecords.first()
                val procedures = localStore.procedures.first()
                _uiState.value = VehicleUiState.Success(
                    VehicleData(profile, maintenance, inspections, fuel, issues, tireSets, correctiveRecords, procedures),
                )
            } catch (e: Exception) {
                _uiState.value = VehicleUiState.Error(e.message ?: "Couldn't load vehicle data")
            }
        }
    }

    /** vehicle_inspection_items starts empty for every tenant — seed the same
     * built-in weekly/monthly checklist iOS ships as local defaults so the
     * Inspections section isn't blank on first run. */
    private suspend fun loadOrSeedInspections(): List<VehicleInspectionItem> {
        val existing = repository.getVehicleInspections()
        if (existing.isNotEmpty()) return existing
        DEFAULT_INSPECTION_ITEMS.forEach { (name, days) ->
            runCatching { repository.addVehicleInspection(VehicleInspectionCreateRequest(name, days, isBuiltIn = true)) }
        }
        return repository.getVehicleInspections()
    }

    private fun currentMileage(): Int = (_uiState.value as? VehicleUiState.Success)?.data?.profile?.currentMileage ?: 0

    fun saveProfile(request: VehicleProfileUpdateRequest) {
        viewModelScope.launch {
            runCatching { repository.putVehicleProfile(request) }
            refresh()
        }
    }

    fun addMaintenanceRecord(typeName: String, date: String, mileage: Int, cost: Double?, isShop: Boolean, shopName: String, notes: String) {
        viewModelScope.launch {
            runCatching { repository.addVehicleMaintenance(VehicleMaintenanceCreateRequest(typeName, date, mileage, cost, isShop, shopName, notes)) }
            bumpMileageIfNeeded(mileage)
            refresh()
        }
    }

    fun addFuelRecord(date: String, mileage: Int, gallons: Double, pricePerGallon: Double?, station: String, notes: String) {
        viewModelScope.launch {
            val totalCost = pricePerGallon?.let { it * gallons }
            runCatching { repository.addVehicleFuel(VehicleFuelCreateRequest(date, mileage, gallons, pricePerGallon, totalCost, station, notes)) }
            bumpMileageIfNeeded(mileage)
            refresh()
        }
    }

    fun checkInspection(id: Int) {
        viewModelScope.launch {
            runCatching { repository.checkVehicleInspection(id) }
            refresh()
        }
    }

    fun addIssue(title: String, description: String, dateNoticed: String, mileageNoticed: Int, howOccurred: String) {
        viewModelScope.launch {
            val notes = howOccurred.takeIf { it.isNotBlank() }?.let { "Occurred: $it" } ?: ""
            runCatching { repository.addVehicleIssue(VehicleIssueCreateRequest(title, description, "medium", mileageNoticed, dateNoticed, notes)) }
            refresh()
        }
    }

    fun addCorrectiveRecord(record: CorrectiveRecord) {
        viewModelScope.launch {
            val current = localStore.correctiveRecords.first()
            localStore.saveCorrectiveRecords(current + record)
            if (record.resolvedIssue && record.linkedIssueId != null) {
                runCatching { repository.resolveVehicleIssue(record.linkedIssueId) }
            }
            bumpMileageIfNeeded(record.mileage)
            refresh()
        }
    }

    fun addTireSet(set: TireSet) {
        viewModelScope.launch {
            var sets = localStore.tireSets.first()
            if (set.isActive) sets = sets.map { it.copy(isActive = false) }
            localStore.saveTireSets(sets + set)
            refresh()
        }
    }

    fun addPressureCheck(tireId: String, check: TirePressureCheck) {
        viewModelScope.launch {
            val sets = localStore.tireSets.first()
            localStore.saveTireSets(
                sets.map { if (it.id == tireId) it.copy(pressureChecks = it.pressureChecks + check) else it },
            )
            bumpMileageIfNeeded(check.mileage)
            refresh()
        }
    }

    fun saveProcedure(procedure: MaintenanceProcedure) {
        viewModelScope.launch {
            val existing = localStore.procedures.first()
            val next = if (existing.any { it.id == procedure.id }) {
                existing.map { if (it.id == procedure.id) procedure else it }
            } else {
                existing + procedure
            }
            localStore.saveProcedures(next)
            refresh()
        }
    }

    private suspend fun bumpMileageIfNeeded(mileage: Int) {
        if (mileage > currentMileage()) {
            runCatching { repository.updateVehicleMileage(mileage) }
        }
    }

    companion object {
        fun newId(): String = UUID.randomUUID().toString()
    }

    class Factory(private val repository: HomeRepository, private val localStore: VehicleLocalStore) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return VehicleViewModel(repository, localStore) as T
        }
    }
}
