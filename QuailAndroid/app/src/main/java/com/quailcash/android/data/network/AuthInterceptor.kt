package com.quailcash.android.data.network

import com.quailcash.android.data.repository.AuthStore
import okhttp3.Interceptor
import okhttp3.Response

/** Mirrors QuailCashAPI.swift's header setup: attaches the mobile bearer
 * token to every request when present. */
class AuthInterceptor(private val authStore: AuthStore) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = authStore.currentTokenBlocking()
        val request = chain.request().newBuilder()
            .addHeader("Accept", "application/json")
            .addHeader("User-Agent", "QuailAndroid/1.0")
            .apply {
                if (token != null) addHeader("Authorization", "Bearer $token")
            }
            .build()
        return chain.proceed(request)
    }
}
