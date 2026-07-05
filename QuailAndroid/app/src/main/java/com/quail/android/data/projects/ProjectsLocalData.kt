package com.quail.android.data.projects

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

@Entity(tableName = "projects")
data class ProjectEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val name: String,
    val type: String = "generic",
    val description: String = "",
    val sectionsJson: String = "[]",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
    val updatedAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "project_quick_notes")
data class ProjectQuickNoteEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String = "",
    val text: String,
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Entity(tableName = "project_checklists")
data class ProjectChecklistEntity(
    @PrimaryKey val clientId: String,
    val serverId: Int? = null,
    val title: String,
    val itemsJson: String = "[]",
    val pendingSync: Boolean = true,
    val pendingDelete: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
)

@Dao
interface ProjectDao {
    @Query("SELECT * FROM projects WHERE pendingDelete = 0 ORDER BY updatedAtMillis DESC")
    fun observeAll(): Flow<List<ProjectEntity>>

    @Query("SELECT * FROM projects WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<ProjectEntity>

    @Query("SELECT * FROM projects WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<ProjectEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: ProjectEntity)

    @Query("UPDATE projects SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE projects SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM projects WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface ProjectQuickNoteDao {
    @Query("SELECT * FROM project_quick_notes WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<ProjectQuickNoteEntity>>

    @Query("SELECT * FROM project_quick_notes WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<ProjectQuickNoteEntity>

    @Query("SELECT * FROM project_quick_notes WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<ProjectQuickNoteEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: ProjectQuickNoteEntity)

    @Query("UPDATE project_quick_notes SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE project_quick_notes SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM project_quick_notes WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Dao
interface ProjectChecklistDao {
    @Query("SELECT * FROM project_checklists WHERE pendingDelete = 0 ORDER BY createdAtMillis DESC")
    fun observeAll(): Flow<List<ProjectChecklistEntity>>

    @Query("SELECT * FROM project_checklists WHERE pendingSync = 1 AND pendingDelete = 0")
    suspend fun getPendingSync(): List<ProjectChecklistEntity>

    @Query("SELECT * FROM project_checklists WHERE pendingDelete = 1")
    suspend fun getPendingDelete(): List<ProjectChecklistEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: ProjectChecklistEntity)

    @Query("UPDATE project_checklists SET serverId = :serverId, pendingSync = 0 WHERE clientId = :clientId")
    suspend fun markSynced(clientId: String, serverId: Int)

    @Query("UPDATE project_checklists SET pendingDelete = 1 WHERE clientId = :clientId")
    suspend fun markPendingDelete(clientId: String)

    @Query("DELETE FROM project_checklists WHERE clientId = :clientId")
    suspend fun hardDelete(clientId: String)
}

@Database(
    entities = [ProjectEntity::class, ProjectQuickNoteEntity::class, ProjectChecklistEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class ProjectsDatabase : RoomDatabase() {
    abstract fun projectDao(): ProjectDao
    abstract fun quickNoteDao(): ProjectQuickNoteDao
    abstract fun checklistDao(): ProjectChecklistDao

    companion object {
        @Volatile private var instance: ProjectsDatabase? = null

        fun getInstance(context: Context): ProjectsDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, ProjectsDatabase::class.java, "quail_projects.db")
                    .build()
                    .also { instance = it }
            }
    }
}
