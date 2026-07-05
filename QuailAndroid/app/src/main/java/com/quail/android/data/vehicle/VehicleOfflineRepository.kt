package com.quail.android.data.vehicle

import android.content.Context
import com.quail.android.data.model.CorrectiveRecord
import com.quail.android.data.model.CorrectiveRecordUpsertRequest
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.data.model.ProcedureStep
import com.quail.android.data.model.TirePressureCheck
import com.quail.android.data.model.TireSet
import com.quail.android.data.model.TireSetUpsertRequest
import com.quail.android.data.model.VehicleFuelCreateRequest
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleInspectionCreateRequest
import com.quail.android.data.model.VehicleInspectionItem
import com.quail.android.data.model.VehicleIssue
import com.quail.android.data.model.VehicleIssueCreateRequest
import com.quail.android.data.model.VehicleMaintenanceCreateRequest
import com.quail.android.data.model.VehicleMaintenanceRecord
import com.quail.android.data.model.VehicleProcedureUpsertRequest
import com.quail.android.data.model.VehicleProfile
import com.quail.android.data.model.VehicleProfileUpdateRequest
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.UUID

private val vehicleJson = Json { ignoreUnknownKeys = true }

private fun TireSetEntity.toDomain(): TireSet = TireSet(
    id = clientId, brand = brand, model = model, size = size, installDate = installDate, installMileage = installMileage,
    requiredPressureFront = requiredPressureFront, requiredPressureRear = requiredPressureRear,
    pressureChecks = runCatching { vehicleJson.decodeFromString<List<TirePressureCheck>>(pressureChecksJson) }.getOrDefault(emptyList()),
    isActive = isActive,
)

private fun TireSet.toEntity(serverId: Int? = null, pendingSync: Boolean = true): TireSetEntity = TireSetEntity(
    clientId = id, serverId = serverId, brand = brand, model = model, size = size, installDate = installDate, installMileage = installMileage,
    requiredPressureFront = requiredPressureFront, requiredPressureRear = requiredPressureRear,
    pressureChecksJson = vehicleJson.encodeToString(pressureChecks), isActive = isActive, pendingSync = pendingSync,
)

private fun CorrectiveRecordEntity.toDomain(): CorrectiveRecord = CorrectiveRecord(
    id = clientId, date = date, mileage = mileage, description = description, reason = reason,
    partsReplaced = runCatching { vehicleJson.decodeFromString<List<String>>(partsReplacedJson) }.getOrDefault(emptyList()),
    cost = cost, resolvedIssue = resolvedIssue, linkedIssueId = linkedIssueId, notes = notes,
)

private fun CorrectiveRecord.toEntity(serverId: Int? = null, pendingSync: Boolean = true): CorrectiveRecordEntity = CorrectiveRecordEntity(
    clientId = id, serverId = serverId, date = date, mileage = mileage, description = description, reason = reason,
    partsReplacedJson = vehicleJson.encodeToString(partsReplaced), cost = cost, resolvedIssue = resolvedIssue,
    linkedIssueId = linkedIssueId, notes = notes, pendingSync = pendingSync,
)

private fun VehicleProcedureEntity.toDomain(): MaintenanceProcedure = MaintenanceProcedure(
    id = clientId, title = title, relatedTypeName = relatedTypeName,
    tools = runCatching { vehicleJson.decodeFromString<List<String>>(toolsJson) }.getOrDefault(emptyList()),
    parts = runCatching { vehicleJson.decodeFromString<List<String>>(partsJson) }.getOrDefault(emptyList()),
    steps = runCatching { vehicleJson.decodeFromString<List<ProcedureStep>>(stepsJson) }.getOrDefault(emptyList()),
    notes = notes, lastUpdated = "",
)

private fun MaintenanceProcedure.toEntity(serverId: Int? = null, pendingSync: Boolean = true): VehicleProcedureEntity = VehicleProcedureEntity(
    clientId = id, serverId = serverId, title = title, relatedTypeName = relatedTypeName,
    toolsJson = vehicleJson.encodeToString(tools), partsJson = vehicleJson.encodeToString(parts),
    stepsJson = vehicleJson.encodeToString(steps), notes = notes, pendingSync = pendingSync,
)

private fun FuelRecordEntity.toDomain(): VehicleFuelRecord = VehicleFuelRecord(
    id = serverId ?: 0, date = date, mileage = mileage, gallons = gallons, pricePerGallon = pricePerGallon,
    totalCost = totalCost, station = station, notes = notes, clientId = clientId,
)

private fun VehicleFuelRecord.toEntity(pendingSync: Boolean = true): FuelRecordEntity = FuelRecordEntity(
    clientId = clientId ?: "server-$id", serverId = id.takeIf { it != 0 }, date = date, mileage = mileage,
    gallons = gallons, pricePerGallon = pricePerGallon, totalCost = totalCost, station = station, notes = notes,
    pendingSync = pendingSync,
)

private fun MaintenanceRecordEntity.toDomain(): VehicleMaintenanceRecord = VehicleMaintenanceRecord(
    id = serverId ?: 0, typeName = typeName, date = date, mileage = mileage, cost = cost,
    isShopPerformed = isShopPerformed, shopName = shopName, notes = notes, clientId = clientId,
)

private fun VehicleMaintenanceRecord.toEntity(pendingSync: Boolean = true): MaintenanceRecordEntity = MaintenanceRecordEntity(
    clientId = clientId ?: "server-$id", serverId = id.takeIf { it != 0 }, typeName = typeName, date = date,
    mileage = mileage, cost = cost, isShopPerformed = isShopPerformed, shopName = shopName, notes = notes,
    pendingSync = pendingSync,
)

private fun IssueEntity.toDomain(): VehicleIssue = VehicleIssue(
    id = serverId ?: 0, title = title, description = description, severity = severity,
    mileageNoticed = mileageNoticed, dateNoticed = dateNoticed, isResolved = isResolved,
    resolvedDate = resolvedDate, notes = notes, clientId = clientId,
)

private fun VehicleIssue.toEntity(pendingSync: Boolean = true): IssueEntity = IssueEntity(
    clientId = clientId ?: "server-$id", serverId = id.takeIf { it != 0 }, title = title, description = description,
    severity = severity, mileageNoticed = mileageNoticed, dateNoticed = dateNoticed, isResolved = isResolved,
    resolvedDate = resolvedDate, notes = notes, pendingSync = pendingSync,
)

private fun InspectionItemEntity.toDomain(): VehicleInspectionItem = VehicleInspectionItem(
    id = serverId ?: 0, name = name, periodicityDays = periodicityDays,
    lastCheckedDate = lastCheckedDate, isBuiltIn = isBuiltIn, clientId = clientId,
)

private fun VehicleInspectionItem.toEntity(pendingSync: Boolean = true): InspectionItemEntity = InspectionItemEntity(
    clientId = clientId ?: "server-$id", serverId = id.takeIf { it != 0 }, name = name,
    periodicityDays = periodicityDays, lastCheckedDate = lastCheckedDate, isBuiltIn = isBuiltIn,
    pendingSync = pendingSync,
)

class VehicleOfflineRepository(
    private val api: QuailApi,
    private val db: VehicleOfflineDatabase,
    private val context: Context,
) {
    val tireSets: Flow<List<TireSet>> = db.tireSetDao().observeAll().map { list -> list.map { it.toDomain() } }
    val correctiveRecords: Flow<List<CorrectiveRecord>> = db.correctiveRecordDao().observeAll().map { list -> list.map { it.toDomain() } }
    val procedures: Flow<List<MaintenanceProcedure>> = db.procedureDao().observeAll().map { list -> list.map { it.toDomain() } }
    val fuelRecords: Flow<List<VehicleFuelRecord>> = db.fuelRecordDao().observeAll().map { list -> list.map { it.toDomain() } }
    val maintenanceRecords: Flow<List<VehicleMaintenanceRecord>> = db.maintenanceRecordDao().observeAll().map { list -> list.map { it.toDomain() } }
    val issues: Flow<List<VehicleIssue>> = db.issueDao().observeAll().map { list -> list.map { it.toDomain() } }
    val inspectionItems: Flow<List<VehicleInspectionItem>> = db.inspectionItemDao().observeAll().map { list -> list.map { it.toDomain() } }
    val profile: Flow<VehicleProfile> = db.profileDao().observe().map { entity ->
        entity?.let { runCatching { vehicleJson.decodeFromString<VehicleProfile>(it.profileJson) }.getOrNull() } ?: VehicleProfile()
    }

    suspend fun saveTireSet(tireSet: TireSet) {
        db.tireSetDao().upsert(tireSet.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveCorrectiveRecord(record: CorrectiveRecord) {
        db.correctiveRecordDao().upsert(record.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveProcedure(procedure: MaintenanceProcedure) {
        db.procedureDao().upsert(procedure.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteProcedure(clientId: String) {
        db.procedureDao().markPendingDelete(clientId)
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveFuelRecord(record: VehicleFuelRecord): VehicleFuelRecord {
        val withId = if (record.clientId == null) record.copy(clientId = UUID.randomUUID().toString()) else record
        db.fuelRecordDao().upsert(withId.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
        return withId
    }

    suspend fun deleteFuelRecord(clientId: String) {
        db.fuelRecordDao().markPendingDelete(clientId)
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveMaintenanceRecord(record: VehicleMaintenanceRecord): VehicleMaintenanceRecord {
        val withId = if (record.clientId == null) record.copy(clientId = UUID.randomUUID().toString()) else record
        db.maintenanceRecordDao().upsert(withId.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
        return withId
    }

    suspend fun deleteMaintenanceRecord(clientId: String) {
        db.maintenanceRecordDao().markPendingDelete(clientId)
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveIssue(issue: VehicleIssue): VehicleIssue {
        val withId = if (issue.clientId == null) issue.copy(clientId = UUID.randomUUID().toString()) else issue
        db.issueDao().upsert(withId.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
        return withId
    }

    suspend fun deleteIssue(clientId: String) {
        db.issueDao().markPendingDelete(clientId)
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    /** Resolving is just re-saving the issue with isResolved=true — the backend
     * upserts by client_id, so there's no separate "resolve" call to queue. */
    suspend fun resolveIssue(clientId: String, resolvedDate: String) {
        val entity = db.issueDao().getByClientId(clientId) ?: return
        db.issueDao().upsert(entity.copy(isResolved = true, resolvedDate = resolvedDate, pendingSync = true))
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveInspectionItem(item: VehicleInspectionItem): VehicleInspectionItem {
        val withId = if (item.clientId == null) item.copy(clientId = UUID.randomUUID().toString()) else item
        db.inspectionItemDao().upsert(withId.toEntity())
        VehicleOfflineSyncScheduler.scheduleSync(context)
        return withId
    }

    /** Checking off an inspection is a re-save with a bumped lastCheckedDate —
     * same upsert-by-client_id path as everything else here. */
    suspend fun checkInspectionItem(clientId: String, checkedDate: String) {
        val entity = db.inspectionItemDao().getByClientId(clientId) ?: return
        db.inspectionItemDao().upsert(entity.copy(lastCheckedDate = checkedDate, pendingSync = true))
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun saveProfile(request: VehicleProfileUpdateRequest) {
        val existingId = runCatching { vehicleJson.decodeFromString<VehicleProfile>(db.profileDao().get()?.profileJson ?: "") }.getOrNull()?.id
        val snapshot = VehicleProfile(
            id = existingId, make = request.make, model = request.model, year = request.year, vin = request.vin,
            licensePlate = request.licensePlate, oilType = request.oilType, oilCapacityWithFilter = request.oilCapacityWithFilter,
            oilCapacityWithoutFilter = request.oilCapacityWithoutFilter, transmissionFluidType = request.transmissionFluidType,
            transmissionFluidCapacity = request.transmissionFluidCapacity, coolantType = request.coolantType,
            currentMileage = request.currentMileage, tankCapacityGallons = request.tankCapacityGallons, notes = request.notes,
        )
        db.profileDao().upsert(VehicleProfileEntity(profileJson = vehicleJson.encodeToString(snapshot), pendingSync = true))
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    suspend fun bumpMileage(mileage: Int) {
        val cached = db.profileDao().get() ?: return
        val current = runCatching { vehicleJson.decodeFromString<VehicleProfile>(cached.profileJson) }.getOrNull() ?: return
        val updated = current.copy(currentMileage = mileage)
        db.profileDao().upsert(VehicleProfileEntity(profileJson = vehicleJson.encodeToString(updated), pendingSync = true))
        VehicleOfflineSyncScheduler.scheduleSync(context)
    }

    /** Best-effort network refresh of the profile cache, called opportunistically
     * from the UI on screen load. Never overwrites an unsynced local edit, and
     * no-ops silently if there's no connection. */
    suspend fun refreshProfileIfOnline() {
        runCatching {
            val cached = db.profileDao().get()
            if (cached == null || !cached.pendingSync) {
                val remote = api.getVehicleProfile()
                db.profileDao().upsert(VehicleProfileEntity(profileJson = vehicleJson.encodeToString(remote), pendingSync = false))
            }
        }
    }

    suspend fun pushPending() {
        val tireDao = db.tireSetDao()
        tireDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = TireSetUpsertRequest(
                    entity.clientId, domain.brand, domain.model, domain.size, domain.installDate.ifBlank { null },
                    domain.installMileage, domain.requiredPressureFront, domain.requiredPressureRear, domain.pressureChecks, domain.isActive,
                )
                val saved = api.upsertTireSet(req)
                tireDao.markSynced(entity.clientId, saved.id)
            }
        }
        tireDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteTireSet(entity.serverId)
                tireDao.hardDelete(entity.clientId)
            }
        }

        val correctiveDao = db.correctiveRecordDao()
        correctiveDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = CorrectiveRecordUpsertRequest(
                    entity.clientId, domain.date, domain.mileage, domain.description, domain.reason,
                    domain.partsReplaced, domain.cost, domain.resolvedIssue, domain.linkedIssueId, domain.notes,
                )
                val saved = api.upsertCorrectiveRecord(req)
                correctiveDao.markSynced(entity.clientId, saved.id)
            }
        }
        correctiveDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteCorrectiveRecord(entity.serverId)
                correctiveDao.hardDelete(entity.clientId)
            }
        }

        val procedureDao = db.procedureDao()
        procedureDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = VehicleProcedureUpsertRequest(entity.clientId, domain.title, domain.relatedTypeName, domain.tools, domain.parts, domain.steps, domain.notes)
                val saved = api.upsertVehicleProcedure(req)
                procedureDao.markSynced(entity.clientId, saved.id)
            }
        }
        procedureDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteVehicleProcedure(entity.serverId)
                procedureDao.hardDelete(entity.clientId)
            }
        }

        val fuelDao = db.fuelRecordDao()
        fuelDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = VehicleFuelCreateRequest(domain.date, domain.mileage, domain.gallons, domain.pricePerGallon, domain.totalCost, domain.station, domain.notes, entity.clientId)
                val saved = api.addVehicleFuel(req)
                fuelDao.markSynced(entity.clientId, saved.id)
            }
        }
        fuelDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteVehicleFuel(entity.serverId)
                fuelDao.hardDelete(entity.clientId)
            }
        }

        val maintenanceDao = db.maintenanceRecordDao()
        maintenanceDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = VehicleMaintenanceCreateRequest(domain.typeName, domain.date, domain.mileage, domain.cost, domain.isShopPerformed, domain.shopName, domain.notes, entity.clientId)
                val saved = api.addVehicleMaintenance(req)
                maintenanceDao.markSynced(entity.clientId, saved.id)
            }
        }
        maintenanceDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteVehicleMaintenance(entity.serverId)
                maintenanceDao.hardDelete(entity.clientId)
            }
        }

        val issueDao = db.issueDao()
        issueDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = VehicleIssueCreateRequest(
                    domain.title, domain.description, domain.severity, domain.mileageNoticed, domain.dateNoticed,
                    domain.notes, domain.isResolved, domain.resolvedDate, entity.clientId,
                )
                val saved = api.addVehicleIssue(req)
                issueDao.markSynced(entity.clientId, saved.id)
            }
        }
        issueDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteVehicleIssue(entity.serverId)
                issueDao.hardDelete(entity.clientId)
            }
        }

        val inspectionDao = db.inspectionItemDao()
        inspectionDao.getPendingSync().forEach { entity ->
            runCatching {
                val domain = entity.toDomain()
                val req = VehicleInspectionCreateRequest(domain.name, domain.periodicityDays, domain.isBuiltIn, domain.lastCheckedDate, entity.clientId)
                val saved = api.addVehicleInspection(req)
                inspectionDao.markSynced(entity.clientId, saved.id)
            }
        }

        db.profileDao().get()?.let { entity ->
            if (entity.pendingSync) {
                runCatching {
                    val snapshot = vehicleJson.decodeFromString<VehicleProfile>(entity.profileJson)
                    val req = VehicleProfileUpdateRequest(
                        snapshot.make, snapshot.model, snapshot.year, snapshot.vin, snapshot.licensePlate, snapshot.oilType,
                        snapshot.oilCapacityWithFilter, snapshot.oilCapacityWithoutFilter, snapshot.transmissionFluidType,
                        snapshot.transmissionFluidCapacity, snapshot.coolantType, snapshot.currentMileage,
                        snapshot.tankCapacityGallons, snapshot.notes,
                    )
                    val saved = api.putVehicleProfile(req)
                    db.profileDao().upsert(VehicleProfileEntity(profileJson = vehicleJson.encodeToString(saved), pendingSync = false))
                }
            }
        }
    }

    suspend fun pullFromServer() {
        runCatching {
            api.getTireSets().forEach { record ->
                db.tireSetDao().upsert(
                    TireSet(
                        id = record.clientId, brand = record.brand, model = record.model, size = record.size,
                        installDate = record.installDate ?: "", installMileage = record.installMileage,
                        requiredPressureFront = record.requiredPressureFront, requiredPressureRear = record.requiredPressureRear,
                        pressureChecks = record.pressureChecks, isActive = record.isActive,
                    ).toEntity(serverId = record.id, pendingSync = false),
                )
            }
        }
        runCatching {
            api.getCorrectiveRecords().forEach { record ->
                db.correctiveRecordDao().upsert(
                    CorrectiveRecord(
                        id = record.clientId, date = record.date, mileage = record.mileage, description = record.description,
                        reason = record.reason, partsReplaced = record.partsReplaced, cost = record.cost,
                        resolvedIssue = record.resolvedIssue, linkedIssueId = record.linkedIssueId, notes = record.notes,
                    ).toEntity(serverId = record.id, pendingSync = false),
                )
            }
        }
        runCatching {
            api.getVehicleProcedures().forEach { record ->
                db.procedureDao().upsert(
                    MaintenanceProcedure(
                        id = record.clientId, title = record.title, relatedTypeName = record.relatedTypeName,
                        tools = record.tools, parts = record.parts, steps = record.steps, notes = record.notes,
                    ).toEntity(serverId = record.id, pendingSync = false),
                )
            }
        }
        runCatching {
            api.getVehicleFuel().records.forEach { record ->
                db.fuelRecordDao().upsert(record.toEntity(pendingSync = false))
            }
        }
        runCatching {
            api.getVehicleMaintenance().records.forEach { record ->
                db.maintenanceRecordDao().upsert(record.toEntity(pendingSync = false))
            }
        }
        runCatching {
            api.getVehicleIssues().forEach { record ->
                db.issueDao().upsert(record.toEntity(pendingSync = false))
            }
        }
        runCatching {
            api.getVehicleInspections().forEach { record ->
                db.inspectionItemDao().upsert(record.toEntity(pendingSync = false))
            }
        }
        runCatching {
            val cached = db.profileDao().get()
            if (cached == null || !cached.pendingSync) {
                val remote = api.getVehicleProfile()
                db.profileDao().upsert(VehicleProfileEntity(profileJson = vehicleJson.encodeToString(remote), pendingSync = false))
            }
        }
    }
}
