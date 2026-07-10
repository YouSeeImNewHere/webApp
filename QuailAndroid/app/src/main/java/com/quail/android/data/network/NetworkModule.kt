package com.quail.android.data.network

import com.quail.android.AppConfig
import com.quail.android.BuildConfig
import com.quail.android.data.repository.AuthStore
import kotlinx.serialization.json.Json
import okhttp3.Dispatcher
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

object NetworkModule {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }

    fun create(authStore: AuthStore): QuailApi {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }

        // OkHttp's default Dispatcher caps concurrent requests to the SAME
        // host at 5 — fine for a public API, but every map tile request
        // goes to this one homelab host, so a single viewport's worth of
        // tiles (commonly 20-30) queued in waves of 5 at a time, not
        // actually in parallel. That's the real cause of tiles "loading
        // really slowly" while panning — not a server render-speed issue.
        // Bumped since this is one trusted host over Tailscale, not a rate-
        // limited third party.
        val dispatcher = Dispatcher().apply { maxRequestsPerHost = 24 }

        val client = OkHttpClient.Builder()
            .dispatcher(dispatcher)
            .addInterceptor(AuthInterceptor(authStore))
            .addInterceptor(NetworkCallLogInterceptor())
            .addInterceptor(logging)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .build()

        val contentType = "application/json".toMediaType()
        val retrofit = Retrofit.Builder()
            .baseUrl("${AppConfig.BASE_URL}/")
            .client(client)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()

        return retrofit.create(QuailApi::class.java)
    }
}
