package com.quailcash.android

import android.os.Build

object AppConfig {
    // Mirrors QuailCash/QuailCash/AppConfig.swift's own
    // `#if targetEnvironment(simulator)` split: production Render URL on a
    // real device, local dev backend when running on an emulator. No manual
    // toggle to remember — building straight to a physical phone always
    // hits the real server.
    const val BASE_URL_PROD = "https://webapp-pe3q.onrender.com"
    const val BASE_URL_EMULATOR_LOCAL = "http://10.0.2.2:8000"

    // Host machine's LAN IP — only reachable (and only used) if you force
    // BASE_URL to this while testing a physical device against the local
    // `finance_local` Postgres DB. Re-run `ipconfig getifaddr en0` if this
    // changes networks.
    const val BASE_URL_LOCAL_LAN = "http://192.168.0.31:8000"

    val BASE_URL: String = if (isRunningOnEmulator()) BASE_URL_EMULATOR_LOCAL else BASE_URL_PROD

    private fun isRunningOnEmulator(): Boolean {
        return Build.FINGERPRINT.startsWith("generic")
            || Build.FINGERPRINT.startsWith("unknown")
            || Build.MODEL.contains("google_sdk")
            || Build.MODEL.contains("Emulator")
            || Build.MODEL.contains("Android SDK built for")
            || Build.MODEL.startsWith("sdk_gphone")
            || Build.MANUFACTURER.contains("Genymotion")
            || Build.HARDWARE.contains("goldfish")
            || Build.HARDWARE.contains("ranchu")
            || Build.PRODUCT.contains("sdk")
            || (Build.BRAND.startsWith("generic") && Build.DEVICE.startsWith("generic"))
    }

    const val AUTH_CALLBACK_SCHEME = "quailcash"
    const val AUTH_CALLBACK_HOST = "auth"
    const val AUTH_CALLBACK_URL = "$AUTH_CALLBACK_SCHEME://$AUTH_CALLBACK_HOST"

    fun oauthStartUrl(next: String = "/page/home"): String {
        return "$BASE_URL/gmail/oauth/start?callback=$AUTH_CALLBACK_URL&next=$next"
    }
}
