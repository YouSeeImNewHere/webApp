package com.quail.android.bugreport

import android.app.Activity
import java.lang.ref.WeakReference

/** Tracks the foreground Activity so the floating overlay button (which lives
 * outside any Activity's view tree) can grab a screenshot of whatever is
 * currently on screen when tapped. */
object CurrentActivityHolder {
    @Volatile
    var current: WeakReference<Activity>? = null
        internal set
}

/** Breadcrumb of the Compose navigation back stack, updated from AppNav, so a
 * bug report can record how the user got to the screen they're reporting on. */
object NavPathHolder {
    @Volatile
    var current: String = ""
}
