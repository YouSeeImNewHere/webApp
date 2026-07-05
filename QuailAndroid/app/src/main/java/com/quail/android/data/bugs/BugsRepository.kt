package com.quail.android.data.bugs

import android.content.Context
import com.quail.android.data.model.BugNoteRecord
import com.quail.android.data.model.BugNoteUpsertRequest
import com.quail.android.data.model.BugReportRecord
import com.quail.android.data.model.BugReportUpsertRequest
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.util.UUID

private fun BugReportEntity.toRecord(): BugReportRecord = BugReportRecord(
    id = serverId ?: 0, clientId = clientId, title = title, description = description, status = status, route = route,
)

private fun BugReportRecord.toEntity(pendingSync: Boolean = true): BugReportEntity = BugReportEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, title = title, description = description, status = status, route = route,
    pendingSync = pendingSync,
)

private fun BugNoteEntity.toRecord(): BugNoteRecord = BugNoteRecord(id = serverId ?: 0, clientId = clientId, text = text, isResolved = isResolved)

private fun BugNoteRecord.toEntity(pendingSync: Boolean = true): BugNoteEntity = BugNoteEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, text = text, isResolved = isResolved, pendingSync = pendingSync,
)

class BugsRepository(
    private val api: QuailApi,
    private val db: BugsDatabase,
    private val context: Context,
) {
    companion object {
        fun newClientId(): String = UUID.randomUUID().toString()
    }

    val reports: Flow<List<BugReportRecord>> = db.bugReportDao().observeAll().map { list -> list.map { it.toRecord() } }
    val notes: Flow<List<BugNoteRecord>> = db.bugNoteDao().observeAll().map { list -> list.map { it.toRecord() } }

    suspend fun saveReport(report: BugReportRecord) {
        db.bugReportDao().upsert(report.toEntity())
        BugsSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteReport(clientId: String) {
        db.bugReportDao().markPendingDelete(clientId)
        BugsSyncScheduler.scheduleSync(context)
    }

    suspend fun saveNote(note: BugNoteRecord) {
        db.bugNoteDao().upsert(note.toEntity())
        BugsSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteNote(clientId: String) {
        db.bugNoteDao().markPendingDelete(clientId)
        BugsSyncScheduler.scheduleSync(context)
    }

    suspend fun pushPending() {
        val reportDao = db.bugReportDao()
        reportDao.getPendingSync().forEach { entity ->
            runCatching {
                val saved = api.upsertBugReport(BugReportUpsertRequest(entity.clientId, entity.title, entity.description, entity.status, entity.route))
                reportDao.markSynced(entity.clientId, saved.id)
            }
        }
        reportDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteBugReport(entity.serverId)
                reportDao.hardDelete(entity.clientId)
            }
        }

        val noteDao = db.bugNoteDao()
        noteDao.getPendingSync().forEach { entity ->
            runCatching {
                val saved = api.upsertBugNote(BugNoteUpsertRequest(entity.clientId, entity.text, entity.isResolved))
                noteDao.markSynced(entity.clientId, saved.id)
            }
        }
        noteDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteBugNote(entity.serverId)
                noteDao.hardDelete(entity.clientId)
            }
        }
    }

    suspend fun pullFromServer() {
        runCatching { api.getBugReports().forEach { db.bugReportDao().upsert(it.toEntity(pendingSync = false)) } }
        runCatching { api.getBugNotes().forEach { db.bugNoteDao().upsert(it.toEntity(pendingSync = false)) } }
    }
}
