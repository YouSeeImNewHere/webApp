package com.quailcash.android.data.repository

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking

private val Context.authDataStore by preferencesDataStore(name = "quail_auth")

data class AuthSession(val token: String, val email: String?, val tenantId: Int?)

/** Mirrors AuthStore.swift: stores the mobile bearer token minted by the
 * backend's Google OAuth callback (see AppConfig.oauthStartUrl). */
class AuthStore(private val context: Context) {
    private object Keys {
        val TOKEN = stringPreferencesKey("quail.mobile.api.token")
        val EMAIL = stringPreferencesKey("quail.mobile.api.email")
        val TENANT_ID = intPreferencesKey("quail.mobile.api.tenant_id")
    }

    val session: Flow<AuthSession?> = context.authDataStore.data.map { prefs ->
        val token = prefs[Keys.TOKEN] ?: return@map null
        AuthSession(token = token, email = prefs[Keys.EMAIL], tenantId = prefs[Keys.TENANT_ID])
    }

    suspend fun save(token: String, email: String?, tenantId: Int?) {
        context.authDataStore.edit { prefs ->
            prefs[Keys.TOKEN] = token
            if (email != null) prefs[Keys.EMAIL] = email
            if (tenantId != null) prefs[Keys.TENANT_ID] = tenantId
        }
    }

    suspend fun clear() {
        context.authDataStore.edit { it.clear() }
    }

    /** Blocking read for use inside the OkHttp auth interceptor, which runs
     * synchronously on a background dispatcher thread, not a coroutine. */
    fun currentTokenBlocking(): String? = runBlocking { session.first()?.token }

    companion object {
        @Volatile private var instance: AuthStore? = null

        fun getInstance(context: Context): AuthStore =
            instance ?: synchronized(this) {
                instance ?: AuthStore(context.applicationContext).also { instance = it }
            }
    }
}
