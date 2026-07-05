package com.quail.android.data.projects

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

private const val SYNC_WORK_NAME = "projects_sync"

class ProjectsSyncWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        return try {
            val authStore = AuthStore.getInstance(applicationContext)
            val api = NetworkModule.create(authStore)
            val db = ProjectsDatabase.getInstance(applicationContext)
            val repository = ProjectsRepository(api, db, applicationContext)
            repository.pushPending()
            repository.pullFromServer()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}

object ProjectsSyncScheduler {
    fun scheduleSync(context: Context) {
        val request = OneTimeWorkRequestBuilder<ProjectsSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(SYNC_WORK_NAME, ExistingWorkPolicy.KEEP, request)
    }
}
