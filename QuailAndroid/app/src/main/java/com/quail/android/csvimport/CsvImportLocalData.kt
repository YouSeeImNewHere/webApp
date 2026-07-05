package com.quail.android.csvimport

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

object CsvImportStatus {
    const val ASSIGNED = "assigned"
    const val PROCESSING = "processing"
    const val IMPORTED = "imported"
    const val NEEDS_REVIEW = "needs_review"
    const val FAILED = "failed"
}

@Entity(tableName = "csv_import_queue")
data class CsvImportQueueEntity(
    @PrimaryKey val id: String,
    val originalFileName: String,
    val storedFileName: String,
    val accountId: Int,
    val accountLabel: String,
    val headerSignature: String,
    val status: String,
    val detail: String,
    val queuedAtMillis: Long = System.currentTimeMillis(),
)

@Dao
interface CsvImportQueueDao {
    @Query("SELECT * FROM csv_import_queue ORDER BY queuedAtMillis DESC")
    fun observeAll(): Flow<List<CsvImportQueueEntity>>

    @Query("SELECT * FROM csv_import_queue ORDER BY queuedAtMillis DESC")
    suspend fun getAll(): List<CsvImportQueueEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: CsvImportQueueEntity)

    @Query("UPDATE csv_import_queue SET status = :status, detail = :detail WHERE id = :id")
    suspend fun updateStatus(id: String, status: String, detail: String)

    @Query("DELETE FROM csv_import_queue WHERE id = :id")
    suspend fun delete(id: String)
}

@Database(entities = [CsvImportQueueEntity::class], version = 1, exportSchema = false)
abstract class CsvImportDatabase : RoomDatabase() {
    abstract fun csvImportQueueDao(): CsvImportQueueDao

    companion object {
        @Volatile private var instance: CsvImportDatabase? = null

        fun getInstance(context: Context): CsvImportDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, CsvImportDatabase::class.java, "quail_csv_import.db")
                    .build()
                    .also { instance = it }
            }
    }
}
