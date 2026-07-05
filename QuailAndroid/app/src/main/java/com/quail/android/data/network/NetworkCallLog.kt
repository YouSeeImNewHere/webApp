package com.quail.android.data.network

import okhttp3.Interceptor
import okhttp3.Response
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object NetworkCallLog {
    data class Entry(
        val method: String,
        val path: String,
        val status: Int,
        val durationMs: Long,
        val timestampMillis: Long,
    )

    private const val MAX_ENTRIES = 40
    private val entries = ArrayDeque<Entry>()
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.US)

    @Synchronized
    fun record(entry: Entry) {
        entries.addLast(entry)
        while (entries.size > MAX_ENTRIES) entries.removeFirst()
    }

    @Synchronized
    fun snapshotText(): String {
        if (entries.isEmpty()) return "No recent network calls."
        return entries.reversed().joinToString("\n") { e ->
            val time = timeFormat.format(Date(e.timestampMillis))
            "$time  ${e.status}  ${e.method} ${e.path}  (${e.durationMs}ms)"
        }
    }
}

class NetworkCallLogInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val start = System.currentTimeMillis()
        var statusCode = -1
        try {
            val response = chain.proceed(request)
            statusCode = response.code
            return response
        } finally {
            NetworkCallLog.record(
                NetworkCallLog.Entry(
                    method = request.method,
                    path = request.url.encodedPath,
                    status = statusCode,
                    durationMs = System.currentTimeMillis() - start,
                    timestampMillis = start,
                )
            )
        }
    }
}
