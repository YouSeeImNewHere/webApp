package com.quail.android.data.bugs

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

private const val SYNC_WORK_NAME = "bugs_sync"

class BugsSyncWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        return try {
            val authStore = AuthStore.getInstance(applicationContext)
            val api = NetworkModule.create(authStore)
            val db = BugsDatabase.getInstance(applicationContext)
            val repository = BugsRepository(api, db, applicationContext)
            repository.pushPending()
            repository.pullFromServer()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}

object BugsSyncScheduler {
    fun scheduleSync(context: Context) {
        val request = OneTimeWorkRequestBuilder<BugsSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(SYNC_WORK_NAME, ExistingWorkPolicy.KEEP, request)
    }
}
