package com.quail.android

import android.app.Activity
import android.app.Application
import android.os.Bundle
import com.quail.android.bugreport.CurrentActivityHolder
import java.lang.ref.WeakReference

class QuailApplication : Application() {
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

            override fun onActivityStarted(activity: Activity) {}
            override fun onActivityStopped(activity: Activity) {}
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {}
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
            override fun onActivityDestroyed(activity: Activity) {}
        })
    }
}
