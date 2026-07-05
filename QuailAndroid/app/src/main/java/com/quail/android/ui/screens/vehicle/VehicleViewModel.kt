package com.quail.android.ui.screens.vehicle

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.CorrectiveRecord
import com.quail.android.data.model.DEFAULT_INSPECTION_ITEMS
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.data.model.TirePressureCheck
import com.quail.android.data.model.TireSet
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleInspectionItem
import com.quail.android.data.model.VehicleIssue
import com.quail.android.data.model.VehicleMaintenanceRecord
import com.quail.android.data.model.VehicleProfile
import com.quail.android.data.model.VehicleProfileUpdateRequest
import com.quail.android.data.repository.HomeRepository
import com.quail.android.data.vehicle.VehicleOfflineRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.time.LocalDate
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
    private val offlineRepository: VehicleOfflineRepository,
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
                val maintenance = offlineRepository.maintenanceRecords.first()
                val inspections = loadOrSeedInspections()
                val fuel = offlineRepository.fuelRecords.first()
                val issues = offlineRepository.issues.first()
                val tireSets = offlineRepository.tireSets.first()
                val correctiveRecords = offlineRepository.correctiveRecords.first()
                val procedures = offlineRepository.procedures.first()
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
     * Inspections section isn't blank on first run. Seeded locally first so
     * this works even with no connection on first launch. */
    private suspend fun loadOrSeedInspections(): List<VehicleInspectionItem> {
        val existing = offlineRepository.inspectionItems.first()
        if (existing.isNotEmpty()) return existing
        DEFAULT_INSPECTION_ITEMS.forEach { (name, days) ->
            offlineRepository.saveInspectionItem(VehicleInspectionItem(name = name, periodicityDays = days, isBuiltIn = true))
        }
        return offlineRepository.inspectionItems.first()
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
            offlineRepository.saveMaintenanceRecord(
                VehicleMaintenanceRecord(typeName = typeName, date = date, mileage = mileage, cost = cost, isShopPerformed = isShop, shopName = shopName, notes = notes),
            )
            bumpMileageIfNeeded(mileage)
            refresh()
        }
    }

    fun addFuelRecord(date: String, mileage: Int, gallons: Double, pricePerGallon: Double?, station: String, notes: String) {
        viewModelScope.launch {
            val totalCost = pricePerGallon?.let { it * gallons }
            offlineRepository.saveFuelRecord(
                VehicleFuelRecord(date = date, mileage = mileage, gallons = gallons, pricePerGallon = pricePerGallon, totalCost = totalCost, station = station, notes = notes),
            )
            bumpMileageIfNeeded(mileage)
            refresh()
        }
    }

    fun checkInspection(clientId: String) {
        viewModelScope.launch {
            offlineRepository.checkInspectionItem(clientId, LocalDate.now().toString())
            refresh()
        }
    }

    fun addIssue(title: String, description: String, dateNoticed: String, mileageNoticed: Int, howOccurred: String) {
        viewModelScope.launch {
            val notes = howOccurred.takeIf { it.isNotBlank() }?.let { "Occurred: $it" } ?: ""
            offlineRepository.saveIssue(
                VehicleIssue(title = title, description = description, severity = "medium", mileageNoticed = mileageNoticed, dateNoticed = dateNoticed, notes = notes),
            )
            refresh()
        }
    }

    fun addCorrectiveRecord(record: CorrectiveRecord) {
        viewModelScope.launch {
            offlineRepository.saveCorrectiveRecord(record)
            if (record.resolvedIssue && record.linkedIssueId != null) {
                val linkedIssue = offlineRepository.issues.first().firstOrNull { it.id == record.linkedIssueId }
                linkedIssue?.clientId?.let { offlineRepository.resolveIssue(it, LocalDate.now().toString()) }
            }
            bumpMileageIfNeeded(record.mileage)
            refresh()
        }
    }

    fun addTireSet(set: TireSet) {
        viewModelScope.launch {
            if (set.isActive) {
                val current = offlineRepository.tireSets.first()
                current.filter { it.isActive }.forEach { offlineRepository.saveTireSet(it.copy(isActive = false)) }
            }
            offlineRepository.saveTireSet(set)
            refresh()
        }
    }

    fun addPressureCheck(tireId: String, check: TirePressureCheck) {
        viewModelScope.launch {
            val target = offlineRepository.tireSets.first().firstOrNull { it.id == tireId } ?: return@launch
            offlineRepository.saveTireSet(target.copy(pressureChecks = target.pressureChecks + check))
            bumpMileageIfNeeded(check.mileage)
            refresh()
        }
    }

    fun saveProcedure(procedure: MaintenanceProcedure) {
        viewModelScope.launch {
            offlineRepository.saveProcedure(procedure)
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

    class Factory(private val repository: HomeRepository, private val offlineRepository: VehicleOfflineRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return VehicleViewModel(repository, offlineRepository) as T
        }
    }
}
