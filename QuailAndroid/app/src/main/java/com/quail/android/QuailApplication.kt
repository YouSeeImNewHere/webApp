package com.quail.android

import android.app.Activity
import android.app.Application
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import com.quail.android.bugreport.BugOverlayManager
import com.quail.android.bugreport.CurrentActivityHolder
import java.lang.ref.WeakReference

class QuailApplication : Application() {
    private var startedActivityCount = 0
    private val handler = Handler(Looper.getMainLooper())
    private var pendingHide: Runnable? = null

    override fun onCreate() {
        super.onCreate()

        registerActivityLifecycleCallbacks(object : Application.ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                CurrentActivityHolder.current = WeakReference(activity)
            }

            override fun onActivityPaused(activity: Activity) {
                if (CurrentActivityHolder.current?.get() === activity) {
                    CurrentActivityHolder.current = null
                }
            }

            override fun onActivityStarted(activity: Activity) {
                startedActivityCount++
                if (startedActivityCount == 1) {
                    // App just came to the foreground (or just launched).
                    pendingHide?.let { handler.removeCallbacks(it) }
                    pendingHide = null
                    BugOverlayManager.ensureShown(this@QuailApplication)
                }
            }

            override fun onActivityStopped(activity: Activity) {
                startedActivityCount--
                if (startedActivityCount == 0) {
                    // Debounce so a screen rotation (stop -> start of the new
                    // instance) doesn't flash the button off and back on.
                    val runnable = Runnable { BugOverlayManager.hide() }
                    pendingHide = runnable
                    handler.postDelayed(runnable, 500)
                }
            }

            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {}
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
            override fun onActivityDestroyed(activity: Activity) {}
        })
    }
}
