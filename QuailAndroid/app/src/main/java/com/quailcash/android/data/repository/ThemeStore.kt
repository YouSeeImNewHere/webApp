package com.quailcash.android.data.repository

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.themeDataStore by preferencesDataStore(name = "quail_theme")

/** Mirrors SettingsHomePageView.swift's `quail.settings.theme` AppStorage key
 * and its 7-option list. Only "system"/"light"/"dark" actually change
 * anything visually today — the Android app has one branded dark palette
 * plus a stock Material3 light fallback; the other 4 iOS-only palettes
 * (oled/solarized/forest/midnight) aren't built here yet. */
class ThemeStore(private val context: Context) {
    private object Keys {
        val THEME = stringPreferencesKey("quail.settings.theme")
    }

    val theme: Flow<String> = context.themeDataStore.data.map { prefs -> prefs[Keys.THEME] ?: "system" }

    suspend fun setTheme(value: String) {
        context.themeDataStore.edit { prefs -> prefs[Keys.THEME] = value }
    }

    companion object {
        @Volatile private var instance: ThemeStore? = null

        fun getInstance(context: Context): ThemeStore =
            instance ?: synchronized(this) {
                instance ?: ThemeStore(context.applicationContext).also { instance = it }
            }
    }
}
