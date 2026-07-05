package com.quail.android.data.bugs

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

@Entity(tableName = "bug_reports")
data class BugReportEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String,
    val description: String = "",
    val status: String = "open",
    val route: String = "",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "bug_notes")
data class BugNoteEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val text: String,
    val isResolved: Boolean = false,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Dao
interface BugReportDao {
    @Query("SELECT * FROM bug_reports WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<BugReportEntity>>

    @Query("SELECT * FROM bug_reports WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<BugReportEntity>

    @Query("SELECT * FROM bug_reports WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<BugReportEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: BugReportEntity)

    @Query("UPDATE bug_reports SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE bug_reports SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM bug_reports WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface BugNoteDao {
    @Query("SELECT * FROM bug_notes WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<BugNoteEntity>>

    @Query("SELECT * FROM bug_notes WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<BugNoteEntity>

    @Query("SELECT * FROM bug_notes WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<BugNoteEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: BugNoteEntity)

    @Query("UPDATE bug_notes SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE bug_notes SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM bug_notes WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Database(entities = [BugReportEntity::class, BugNoteEntity::class], version = 1, exportSchema = false)
abstract class BugsDatabase : RoomDatabase() {
    abstract fun bugReportDao(): BugReportDao
    abstract fun bugNoteDao(): BugNoteDao

    companion object {
        @Volatile private var instance: BugsDatabase? = null

        fun getInstance(context: Context): BugsDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, BugsDatabase::class.java, "quail_bugs.db")
                    .build()
                    .also { instance = it }
            }
    }
}
