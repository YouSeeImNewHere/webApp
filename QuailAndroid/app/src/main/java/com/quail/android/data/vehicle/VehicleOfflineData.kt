package com.quail.android.data.vehicle

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/** Offline-first local cache + sync queue for the three Quail Car entities
 * that used to be DataStore-only with zero backend (tires, corrective repairs,
 * DIY procedures) — see app/routers/vehicle.py's tires/corrective/procedures
 * endpoints. Mirrors the same pattern as data/fitness, data/bugs, data/projects. */

@Entity(tableName = "vehicle_tire_sets")
data class TireSetEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val brand: String = "",
    val model: String = "",
    val size: String = "",
    val installDate: String = "",
    val installMileage: Int = 0,
    val requiredPressureFront: Int = 35,
    val requiredPressureRear: Int = 35,
    val pressureChecksJson: String = "[]",
    val isActive: Boolean = true,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "vehicle_corrective_records")
data class CorrectiveRecordEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val date: String,
    val mileage: Int = 0,
    val description: String = "",
    val reason: String = "",
    val partsReplacedJson: String = "[]",
    val cost: Double? = null,
    val resolvedIssue: Boolean = false,
    val linkedIssueId: Int? = null,
    val notes: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "vehicle_procedures")
data class VehicleProcedureEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String,
    val relatedTypeName: String = "",
    val toolsJson: String = "[]",
    val partsJson: String = "[]",
    val stepsJson: String = "[]",
    val notes: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Dao
interface TireSetDao {
    @Query("SELECT * FROM vehicle_tire_sets WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<TireSetEntity>>

    @Query("SELECT * FROM vehicle_tire_sets WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<TireSetEntity>

    @Query("SELECT * FROM vehicle_tire_sets WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<TireSetEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: TireSetEntity)

    @Query("UPDATE vehicle_tire_sets SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_tire_sets SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_tire_sets WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface CorrectiveRecordDao {
    @Query("SELECT * FROM vehicle_corrective_records WHERE pendingDelete = 0 ORDER BY date DESC")
    fun observeAll(): Flow<List<CorrectiveRecordEntity>>

    @Query("SELECT * FROM vehicle_corrective_records WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<CorrectiveRecordEntity>

    @Query("SELECT * FROM vehicle_corrective_records WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<CorrectiveRecordEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: CorrectiveRecordEntity)

    @Query("UPDATE vehicle_corrective_records SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_corrective_records SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_corrective_records WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Entity(tableName = "vehicle_fuel_offline")
data class FuelRecordEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val date: String,
    val mileage: Int = 0,
    val gallons: Double? = null,
    val pricePerGallon: Double? = null,
    val totalCost: Double? = null,
    val station: String = "",
    val notes: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "vehicle_maintenance_offline")
data class MaintenanceRecordEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val typeName: String = "",
    val date: String,
    val mileage: Int = 0,
    val cost: Double? = null,
    val isShopPerformed: Boolean = false,
    val shopName: String = "",
    val notes: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "vehicle_issues_offline")
data class IssueEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String = "",
    val description: String = "",
    val severity: String = "medium",
    val mileageNoticed: Int? = null,
    val dateNoticed: String? = null,
    val isResolved: Boolean = false,
    val resolvedDate: String? = null,
    val notes: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "vehicle_inspection_offline")
data class InspectionItemEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val name: String = "",
    val periodicityDays: Int = 30,
    val lastCheckedDate: String? = null,
    val isBuiltIn: Boolean = false,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Dao
interface VehicleProcedureDao {
    @Query("SELECT * FROM vehicle_procedures WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<VehicleProcedureEntity>>

    @Query("SELECT * FROM vehicle_procedures WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<VehicleProcedureEntity>

    @Query("SELECT * FROM vehicle_procedures WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<VehicleProcedureEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: VehicleProcedureEntity)

    @Query("UPDATE vehicle_procedures SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_procedures SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_procedures WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface FuelRecordDao {
    @Query("SELECT * FROM vehicle_fuel_offline WHERE pendingDelete = 0 ORDER BY date DESC, mileage DESC")
    fun observeAll(): Flow<List<FuelRecordEntity>>

    @Query("SELECT * FROM vehicle_fuel_offline WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<FuelRecordEntity>

    @Query("SELECT * FROM vehicle_fuel_offline WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<FuelRecordEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: FuelRecordEntity)

    @Query("UPDATE vehicle_fuel_offline SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_fuel_offline SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_fuel_offline WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface MaintenanceRecordDao {
    @Query("SELECT * FROM vehicle_maintenance_offline WHERE pendingDelete = 0 ORDER BY date DESC, mileage DESC")
    fun observeAll(): Flow<List<MaintenanceRecordEntity>>

    @Query("SELECT * FROM vehicle_maintenance_offline WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<MaintenanceRecordEntity>

    @Query("SELECT * FROM vehicle_maintenance_offline WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<MaintenanceRecordEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: MaintenanceRecordEntity)

    @Query("UPDATE vehicle_maintenance_offline SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_maintenance_offline SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_maintenance_offline WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface IssueDao {
    @Query("SELECT * FROM vehicle_issues_offline WHERE pendingDelete = 0 ORDER BY isResolved ASC, dateNoticed DESC")
    fun observeAll(): Flow<List<IssueEntity>>

    @Query("SELECT * FROM vehicle_issues_offline WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<IssueEntity>

    @Query("SELECT * FROM vehicle_issues_offline WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<IssueEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: IssueEntity)

    @Query("SELECT * FROM vehicle_issues_offline WHERE clientId = :clientId LIMIT 1")
    suspend fun getByClientId(clientId: String): IssueEntity?

    @Query("UPDATE vehicle_issues_offline SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_issues_offline SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_issues_offline WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface InspectionItemDao {
    @Query("SELECT * FROM vehicle_inspection_offline WHERE pendingDelete = 0 ORDER BY name")
    fun observeAll(): Flow<List<InspectionItemEntity>>

    @Query("SELECT * FROM vehicle_inspection_offline WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<InspectionItemEntity>

    @Query("SELECT * FROM vehicle_inspection_offline WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<InspectionItemEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: InspectionItemEntity)

    @Query("SELECT * FROM vehicle_inspection_offline WHERE clientId = :clientId LIMIT 1")
    suspend fun getByClientId(clientId: String): InspectionItemEntity?

    @Query("UPDATE vehicle_inspection_offline SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE vehicle_inspection_offline SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM vehicle_inspection_offline WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

/** Single-row cache for vehicle_profiles — profile edits and mileage bumps used
 * to go straight to the network with no queue at all, so a save attempted with
 * zero signal was silently lost. This mirrors the same Room-is-source-of-truth
 * pattern as the list-based entities above, just with a fixed id=0 row since
 * there's only ever one profile per tenant. */
@Entity(tableName = "vehicle_profile_cache")
data class VehicleProfileEntity(
    @PrimaryKey val id: Int = 0,
    val profileJson: String,
    val pendingSync: Boolean = false,
)

@Dao
interface VehicleProfileDao {
    @Query("SELECT * FROM vehicle_profile_cache WHERE id = 0")
    fun observe(): Flow<VehicleProfileEntity?>

    @Query("SELECT * FROM vehicle_profile_cache WHERE id = 0")
    suspend fun get(): VehicleProfileEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: VehicleProfileEntity)
}

@Database(
    entities = [
        TireSetEntity::class, CorrectiveRecordEntity::class, VehicleProcedureEntity::class,
        FuelRecordEntity::class, MaintenanceRecordEntity::class, IssueEntity::class, InspectionItemEntity::class,
        VehicleProfileEntity::class,
    ],
    version = 3,
    exportSchema = false,
)
abstract class VehicleOfflineDatabase : RoomDatabase() {
    abstract fun tireSetDao(): TireSetDao
    abstract fun correctiveRecordDao(): CorrectiveRecordDao
    abstract fun procedureDao(): VehicleProcedureDao
    abstract fun fuelRecordDao(): FuelRecordDao
    abstract fun maintenanceRecordDao(): MaintenanceRecordDao
    abstract fun issueDao(): IssueDao
    abstract fun inspectionItemDao(): InspectionItemDao
    abstract fun profileDao(): VehicleProfileDao

    companion object {
        @Volatile private var instance: VehicleOfflineDatabase? = null

        fun getInstance(context: Context): VehicleOfflineDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, VehicleOfflineDatabase::class.java, "quail_vehicle_offline.db")
                    .fallbackToDestructiveMigration()
                    .build()
                    .also { instance = it }
            }
    }
}
