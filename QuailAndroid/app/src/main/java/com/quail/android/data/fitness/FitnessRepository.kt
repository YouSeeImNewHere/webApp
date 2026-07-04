package com.quail.android.data.fitness

import android.content.Context
import com.quail.android.data.model.BodyweightRecord
import com.quail.android.data.model.BodyweightUpsertRequest
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.GoalUpsertRequest
import com.quail.android.data.model.MilestoneRecord
import com.quail.android.data.model.MilestoneUpsertRequest
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.RoutineUpsertRequest
import com.quail.android.data.model.WorkoutExerciseEntry
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.WorkoutSessionUpsertRequest
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.UUID

private val fitnessJson = Json { ignoreUnknownKeys = true }

private fun WorkoutSessionEntity.toRecord(): WorkoutSessionRecord = WorkoutSessionRecord(
    id = serverId ?: 0,
    clientId = clientId,
    date = date,
    durationMinutes = durationMinutes,
    bodyweightKg = bodyweightKg,
    notes = notes,
    exercises = runCatching { fitnessJson.decodeFromString<List<WorkoutExerciseEntry>>(exercisesJson) }.getOrDefault(emptyList()),
)

private fun WorkoutSessionRecord.toEntity(pendingSync: Boolean = true): WorkoutSessionEntity = WorkoutSessionEntity(
    clientId = clientId,
    serverId = id.takeIf { it != 0 },
    date = date,
    durationMinutes = durationMinutes,
    bodyweightKg = bodyweightKg,
    notes = notes,
    exercisesJson = fitnessJson.encodeToString(exercises),
    pendingSync = pendingSync,
)

private fun RoutineEntity.toRecord(): RoutineRecord = RoutineRecord(
    id = serverId ?: 0,
    clientId = clientId,
    name = name,
    exercises = runCatching { fitnessJson.decodeFromString<List<WorkoutExerciseEntry>>(exercisesJson) }.getOrDefault(emptyList()),
)

private fun RoutineRecord.toEntity(pendingSync: Boolean = true): RoutineEntity = RoutineEntity(
    clientId = clientId,
    serverId = id.takeIf { it != 0 },
    name = name,
    exercisesJson = fitnessJson.encodeToString(exercises),
    pendingSync = pendingSync,
)

private fun GoalEntity.toRecord(): GoalRecord = GoalRecord(
    id = serverId ?: 0, clientId = clientId, title = title, goalType = goalType,
    targetExerciseId = targetExerciseId, targetReps = targetReps,
    targetDurationSeconds = targetDurationSeconds, targetDate = targetDate, notes = notes,
)

private fun GoalRecord.toEntity(pendingSync: Boolean = true): GoalEntity = GoalEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, title = title, goalType = goalType,
    targetExerciseId = targetExerciseId, targetReps = targetReps,
    targetDurationSeconds = targetDurationSeconds, targetDate = targetDate, notes = notes,
    pendingSync = pendingSync,
)

private fun MilestoneEntity.toRecord(): MilestoneRecord = MilestoneRecord(
    id = serverId ?: 0, clientId = clientId, title = title, date = date, exerciseId = exerciseId, notes = notes,
)

private fun MilestoneRecord.toEntity(pendingSync: Boolean = true): MilestoneEntity = MilestoneEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, title = title, date = date,
    exerciseId = exerciseId, notes = notes, pendingSync = pendingSync,
)

private fun BodyweightEntity.toRecord(): BodyweightRecord = BodyweightRecord(
    id = serverId ?: 0, clientId = clientId, date = date, weightKg = weightKg,
)

private fun BodyweightRecord.toEntity(pendingSync: Boolean = true): BodyweightEntity = BodyweightEntity(
    clientId = clientId, serverId = id.takeIf { it != 0 }, date = date, weightKg = weightKg, pendingSync = pendingSync,
)

class FitnessRepository(
    private val api: QuailApi,
    private val db: FitnessDatabase,
    private val context: Context,
) {
    companion object {
        fun newClientId(): String = UUID.randomUUID().toString()
    }

    // ---- Local-first reads ----

    val sessions: Flow<List<WorkoutSessionRecord>> = db.workoutSessionDao().observeAll().map { list -> list.map { it.toRecord() } }
    val routines: Flow<List<RoutineRecord>> = db.routineDao().observeAll().map { list -> list.map { it.toRecord() } }
    val goals: Flow<List<GoalRecord>> = db.goalDao().observeAll().map { list -> list.map { it.toRecord() } }
    val milestones: Flow<List<MilestoneRecord>> = db.milestoneDao().observeAll().map { list -> list.map { it.toRecord() } }
    val bodyweightLogs: Flow<List<BodyweightRecord>> = db.bodyweightDao().observeAll().map { list -> list.map { it.toRecord() } }

    // ---- Local-first writes: land in Room immediately, then let the sync
    // worker push whenever there's a connection (see FitnessSyncScheduler). ----

    suspend fun saveSession(session: WorkoutSessionRecord) {
        db.workoutSessionDao().upsert(session.toEntity())
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteSession(clientId: String) {
        db.workoutSessionDao().markPendingDelete(clientId)
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun saveRoutine(routine: RoutineRecord) {
        db.routineDao().upsert(routine.toEntity())
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteRoutine(clientId: String) {
        db.routineDao().markPendingDelete(clientId)
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun saveGoal(goal: GoalRecord) {
        db.goalDao().upsert(goal.toEntity())
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteGoal(clientId: String) {
        db.goalDao().markPendingDelete(clientId)
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun saveMilestone(milestone: MilestoneRecord) {
        db.milestoneDao().upsert(milestone.toEntity())
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteMilestone(clientId: String) {
        db.milestoneDao().markPendingDelete(clientId)
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun saveBodyweight(record: BodyweightRecord) {
        db.bodyweightDao().upsert(record.toEntity())
        FitnessSyncScheduler.scheduleSync(context)
    }

    suspend fun deleteBodyweight(clientId: String) {
        db.bodyweightDao().markPendingDelete(clientId)
        FitnessSyncScheduler.scheduleSync(context)
    }

    // ---- Sync worker entry point: push everything pending, best-effort ----

    suspend fun pushPending() {
        val sessionDao = db.workoutSessionDao()
        sessionDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = WorkoutSessionUpsertRequest(entity.clientId, entity.date, entity.durationMinutes, entity.bodyweightKg, entity.notes, entity.toRecord().exercises)
                val saved = api.upsertWorkoutSession(req)
                sessionDao.markSynced(entity.clientId, saved.id)
            }
        }
        sessionDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteWorkoutSession(entity.serverId)
                sessionDao.hardDelete(entity.clientId)
            }
        }

        val routineDao = db.routineDao()
        routineDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = RoutineUpsertRequest(entity.clientId, entity.name, entity.toRecord().exercises)
                val saved = api.upsertRoutine(req)
                routineDao.markSynced(entity.clientId, saved.id)
            }
        }
        routineDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteRoutine(entity.serverId)
                routineDao.hardDelete(entity.clientId)
            }
        }

        val goalDao = db.goalDao()
        goalDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = GoalUpsertRequest(entity.clientId, entity.title, entity.goalType, entity.targetExerciseId, entity.targetReps, entity.targetDurationSeconds, entity.targetDate, entity.notes)
                val saved = api.upsertGoal(req)
                goalDao.markSynced(entity.clientId, saved.id)
            }
        }
        goalDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteGoal(entity.serverId)
                goalDao.hardDelete(entity.clientId)
            }
        }

        val milestoneDao = db.milestoneDao()
        milestoneDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = MilestoneUpsertRequest(entity.clientId, entity.title, entity.date, entity.exerciseId, entity.notes)
                val saved = api.upsertMilestone(req)
                milestoneDao.markSynced(entity.clientId, saved.id)
            }
        }
        milestoneDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteMilestone(entity.serverId)
                milestoneDao.hardDelete(entity.clientId)
            }
        }

        val bodyweightDao = db.bodyweightDao()
        bodyweightDao.getPendingSync().forEach { entity ->
            runCatching {
                val req = BodyweightUpsertRequest(entity.clientId, entity.date, entity.weightKg)
                val saved = api.upsertBodyweight(req)
                bodyweightDao.markSynced(entity.clientId, saved.id)
            }
        }
        bodyweightDao.getPendingDelete().forEach { entity ->
            runCatching {
                if (entity.serverId != null) api.deleteBodyweight(entity.serverId)
                bodyweightDao.hardDelete(entity.clientId)
            }
        }
    }

    /** Pulls the server's copy into the local cache — run after pushPending()
     * so in-flight local edits aren't clobbered. Safe to call opportunistically
     * (e.g. right after a successful push) to pick up data from other devices. */
    suspend fun pullFromServer() {
        runCatching {
            api.getWorkoutSessions().records.forEach { db.workoutSessionDao().upsert(it.toEntity(pendingSync = false)) }
        }
        runCatching {
            api.getRoutines().forEach { db.routineDao().upsert(it.toEntity(pendingSync = false)) }
        }
        runCatching {
            api.getGoals().forEach { db.goalDao().upsert(it.toEntity(pendingSync = false)) }
        }
        runCatching {
            api.getMilestones().forEach { db.milestoneDao().upsert(it.toEntity(pendingSync = false)) }
        }
        runCatching {
            api.getBodyweightLogs().forEach { db.bodyweightDao().upsert(it.toEntity(pendingSync = false)) }
        }
    }
}
