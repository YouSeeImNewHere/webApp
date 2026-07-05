package com.quail.android.data.projects

import android.content.Context
import com.quail.android.data.model.ChecklistItemEntry
import com.quail.android.data.model.ProjectChecklistRecord
import com.quail.android.data.model.ProjectChecklistUpsertRequest
import com.quail.android.data.model.ProjectQuickNoteRecord
import com.quail.android.data.model.ProjectQuickNoteUpsertRequest
import com.quail.android.data.model.ProjectRecord
import com.quail.android.data.model.ProjectSection
import com.quail.android.data.model.ProjectUpsertRequest
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.UUID

private val projectsJson = Json { ignoreUnknownKeys = true }

private fun ProjectEntity.toRecord(): ProjectRecord = ProjectRecord(
    id = serverId ?: 0,
    clientId = clientId,
    name = name,
    type = type,
    description = description,
    sections = runCatching { projectsJson.decodeFromString<List<ProjectSection>>(sectionsJson) }.getOrDefault(emptyList()),
)

private fun ProjectRecord.toEntity(pendingSync: Boolean = true): ProjectEntity = ProjectEntity(
    clientId = clientId,
    serverId = id.takeIf { it != 0 },
    name = name,
    type = type,
    description = description,
    sectionsJson = projectsJson.encodeToString(sections),
    pendingSync = pendingSync,
)

private fun ProjectQuickNoteEntity.toRecord(): ProjectQuickNoteRecord = ProjectQuickNoteRecord(id = serverId ?: 0, clientId = clientId, title = title, text = text)

private fun ProjectQuickNoteRecord.toEntity(pendingSync: Boolean = true): ProjectQuickNoteEntity = ProjectQuickNoteEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, title = title, text = text, pendingSync = pendingSync,
)

private fun ProjectChecklistEntity.toRecord(): ProjectChecklistRecord = ProjectChecklistRecord(
    id = serverId ?: 0, clientId = clientId, title = title,
    items = runCatching { projectsJson.decodeFromString<List<ChecklistItemEntry>>(itemsJson) }.getOrDefault(emptyList()),
)

private fun ProjectChecklistRecord.toEntity(pendingSync: Boolean = true): ProjectChecklistEntity = ProjectChecklistEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, title = title,
    itemsJson = projectsJson.encodeToString(items), pendingSync = pendingSync,
)

class ProjectsRepository(
    private val api: QuailApi,
    private val db: ProjectsDatabase,
    private val context: Context,
) {
    companion object {
        fun newClientId(): String = UUID.randomUUID().toString()
    }

    val projects: Flow<List<ProjectRecord>> = db.projectDao().observeAll().map { list -> list.map { it.toRecord() } }
    val quickNotes: Flow<List<ProjectQuickNoteRecord>> = db.quickNoteDao().observeAll().map { list -> list.map { it.toRecord() } }
    val checklists: Flow<List<ProjectChecklistRecord>> = db.checklistDao().observeAll().map { list -> list.map { it.toRecord() } }

    suspend fun saveProject(project: ProjectRecord) {
        db.projectDao().upsert(project.toEntity())
        ProjectsSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteProject(clientId: String) {
        db.projectDao().markPendingDelete(clientId)
        ProjectsSyncScheduler.scheduleSync(context)
    }

    suspend fun saveQuickNote(note: ProjectQuickNoteRecord) {
        db.quickNoteDao().upsert(note.toEntity())
        ProjectsSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteQuickNote(clientId: String) {
        db.quickNoteDao().markPendingDelete(clientId)
        ProjectsSyncScheduler.scheduleSync(context)
    }

    suspend fun saveChecklist(checklist: ProjectChecklistRecord) {
        db.checklistDao().upsert(checklist.toEntity())
        ProjectsSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteChecklist(clientId: String) {
        db.checklistDao().markPendingDelete(clientId)
        ProjectsSyncScheduler.scheduleSync(context)
    }

    suspend fun pushPending() {
        val projectDao = db.projectDao()
        projectDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = ProjectUpsertRequest(entity.clientId, entity.name, entity.type, entity.description, entity.toRecord().sections)
                val saved = api.upsertProject(req)
                projectDao.markSynced(entity.clientId, saved.id)
            }
        }
        projectDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteProject(entity.serverId)
                projectDao.hardDelete(entity.clientId)
            }
        }

        val noteDao = db.quickNoteDao()
        noteDao.getPendingSync().forEach { entity ->
            runCatching {
                val saved = api.upsertProjectQuickNote(ProjectQuickNoteUpsertRequest(entity.clientId, entity.title, entity.text))
                noteDao.markSynced(entity.clientId, saved.id)
            }
        }
        noteDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteProjectQuickNote(entity.serverId)
                noteDao.hardDelete(entity.clientId)
            }
        }

        val checklistDao = db.checklistDao()
        checklistDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = ProjectChecklistUpsertRequest(entity.clientId, entity.title, entity.toRecord().items)
                val saved = api.upsertProjectChecklist(req)
                checklistDao.markSynced(entity.clientId, saved.id)
            }
        }
        checklistDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteProjectChecklist(entity.serverId)
                checklistDao.hardDelete(entity.clientId)
            }
        }
    }

    suspend fun pullFromServer() {
        runCatching { api.getProjects().forEach { db.projectDao().upsert(it.toEntity(pendingSync = false)) } }
        runCatching { api.getProjectQuickNotes().forEach { db.quickNoteDao().upsert(it.toEntity(pendingSync = false)) } }
        runCatching { api.getProjectChecklists().forEach { db.checklistDao().upsert(it.toEntity(pendingSync = false)) } }
    }
}
