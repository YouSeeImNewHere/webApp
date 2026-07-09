package com.quail.android.data.fitness

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import android.content.Context
import kotlinx.coroutines.flow.Flow

/** Offline-first local cache for Quail Fitness. Every write lands here first
 * (so the app is fully usable with no connection); `pendingSync`/`pendingDelete`
 * mark rows that still need to reach the backend. FitnessSyncWorker drains
 * these whenever the device has a network connection (see FitnessSyncScheduler),
 * per the "store locally, push once connected" requirement. */

@Entity(tableName = "workout_sessions")
data class WorkoutSessionEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val date: String,
    val durationMinutes: Int = 0,
    val bodyweightKg: Double? = null,
    val notes: String = "",
    val exercisesJson: String = "[]",
    val distanceKm: Double? = null,
    val avgPaceSecPerKm: Int? = null,
    val avgHeartRate: Int? = null,
    val calories: Int? = null,
    val source: String = "manual",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "routines")
data class RoutineEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val name: String,
    val exercisesJson: String = "[]",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "fitness_goals")
data class GoalEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String,
    val goalType: String,
    val targetExerciseId: String? = null,
    val targetReps: Int? = null,
    val targetDurationSeconds: Int? = null,
    val targetDate: String? = null,
    val notes: String = "",
    val targetDistanceKm: Double? = null,
    val targetPaceSecPerMile: Int? = null,
    val baselineValue: Double? = null,
    val baselineCapturedAt: String? = null,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "fitness_milestones")
data class MilestoneEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String,
    val date: String,
    val exerciseId: String? = null,
    val notes: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "bodyweight_logs")
data class BodyweightEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val date: String,
    val weightKg: Double,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "fitness_custom_exercises")
data class CustomExerciseEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val name: String,
    val category: String = "PUSH",
    val muscleGroupsJson: String = "[]",
    val difficulty: String = "BEGINNER",
    val instructionsJson: String = "[]",
    val videoUrl: String? = null,
    val isTimedExercise: Boolean = false,
    val defaultSets: Int = 3,
    val defaultReps: Int = 10,
    val defaultDurationSeconds: Int = 30,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Dao
interface WorkoutSessionDao {
    @Query("SELECT * FROM workout_sessions WHERE pendingDelete = 0 ORDER BY date DESC, createdAtMillis DESC")
    fun observeAll(): Flow<List<WorkoutSessionEntity>>

    @Query("SELECT * FROM workout_sessions WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<WorkoutSessionEntity>

    @Query("SELECT * FROM workout_sessions WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<WorkoutSessionEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: WorkoutSessionEntity)

    @Query("UPDATE workout_sessions SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE workout_sessions SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM workout_sessions WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface RoutineDao {
    @Query("SELECT * FROM routines WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<RoutineEntity>>

    @Query("SELECT * FROM routines WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<RoutineEntity>

    @Query("SELECT * FROM routines WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<RoutineEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: RoutineEntity)

    @Query("UPDATE routines SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE routines SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM routines WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface GoalDao {
    @Query("SELECT * FROM fitness_goals WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<GoalEntity>>

    @Query("SELECT * FROM fitness_goals WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<GoalEntity>

    @Query("SELECT * FROM fitness_goals WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<GoalEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: GoalEntity)

    @Query("UPDATE fitness_goals SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE fitness_goals SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM fitness_goals WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface MilestoneDao {
    @Query("SELECT * FROM fitness_milestones WHERE pendingDelete = 0 ORDER BY date DESC")
    fun observeAll(): Flow<List<MilestoneEntity>>

    @Query("SELECT * FROM fitness_milestones WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<MilestoneEntity>

    @Query("SELECT * FROM fitness_milestones WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<MilestoneEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: MilestoneEntity)

    @Query("UPDATE fitness_milestones SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE fitness_milestones SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM fitness_milestones WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface BodyweightDao {
    @Query("SELECT * FROM bodyweight_logs WHERE pendingDelete = 0 ORDER BY date DESC")
    fun observeAll(): Flow<List<BodyweightEntity>>

    @Query("SELECT * FROM bodyweight_logs WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<BodyweightEntity>

    @Query("SELECT * FROM bodyweight_logs WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<BodyweightEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: BodyweightEntity)

    @Query("UPDATE bodyweight_logs SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE bodyweight_logs SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM bodyweight_logs WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface CustomExerciseDao {
    @Query("SELECT * FROM fitness_custom_exercises WHERE pendingDelete = 0 ORDER BY name")
    fun observeAll(): Flow<List<CustomExerciseEntity>>

    @Query("SELECT * FROM fitness_custom_exercises WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<CustomExerciseEntity>

    @Query("SELECT * FROM fitness_custom_exercises WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<CustomExerciseEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: CustomExerciseEntity)

    @Query("UPDATE fitness_custom_exercises SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE fitness_custom_exercises SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM fitness_custom_exercises WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Database(
    entities = [
        WorkoutSessionEntity::class,
        RoutineEntity::class,
        GoalEntity::class,
        MilestoneEntity::class,
        BodyweightEntity::class,
        CustomExerciseEntity::class,
    ],
    version = 3,
    exportSchema = false,
)
abstract class FitnessDatabase : RoomDatabase() {
    abstract fun workoutSessionDao(): WorkoutSessionDao
    abstract fun routineDao(): RoutineDao
    abstract fun goalDao(): GoalDao
    abstract fun milestoneDao(): MilestoneDao
    abstract fun bodyweightDao(): BodyweightDao
    abstract fun customExerciseDao(): CustomExerciseDao

    companion object {
        @Volatile private var instance: FitnessDatabase? = null

        fun getInstance(context: Context): FitnessDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, FitnessDatabase::class.java, "quail_fitness.db")
                    .fallbackToDestructiveMigration()
                    .build()
                    .also { instance = it }
            }
    }
}
