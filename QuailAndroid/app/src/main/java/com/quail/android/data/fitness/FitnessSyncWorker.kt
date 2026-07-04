package com.quail.android.data.fitness

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.repository.AuthStore

private const val SYNC_WORK_NAME = "fitness_sync"

/** Runs whenever the device has network connectivity (see the NetworkType.CONNECTED
 * constraint in FitnessSyncScheduler) and pushes any locally-queued fitness writes
 * to the backend, then pulls the server's copy back into the local cache. WorkManager
 * persists the request across process death/reboot, so a session logged mid-flight
 * with no signal still reaches the server the next time Wi-Fi/data comes back. */
class FitnessSyncWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        return try {
            val authStore = AuthStore.getInstance(applicationContext)
            val api = NetworkModule.create(authStore)
            val db = FitnessDatabase.getInstance(applicationContext)
            val repository = FitnessRepository(api, db, applicationContext)
            repository.pushPending()
            repository.pullFromServer()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}

object FitnessSyncScheduler {
    /** Enqueues a sync run that WorkManager holds until a network is available.
     * ExistingWorkPolicy.KEEP means a burst of local writes (e.g. logging a whole
     * workout set-by-set while offline) collapses onto whatever sync is already
     * queued — the DAOs query "pending" rows fresh at run time, so the one
     * already-queued worker still picks up every write made before it executes. */
    fun scheduleSync(context: Context) {
        val request = OneTimeWorkRequestBuilder<FitnessSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(SYNC_WORK_NAME, ExistingWorkPolicy.KEEP, request)
    }
}
