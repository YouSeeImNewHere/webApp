package com.quail.android.bugreport

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.PixelCopy
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import com.quail.android.data.network.NetworkCallLog
import java.io.File
import java.io.FileOutputStream
import kotlin.math.abs

/** Floating "report a bug" button rendered as a true system overlay window so
 * it stays visible and tappable above any other on-screen popup/dialog,
 * including ones from this app (which render in their own Android windows). */
object BugOverlayManager {
    private const val PREFS_NAME = "bug_overlay_prefs"
    private const val KEY_X = "x"
    private const val KEY_Y = "y"

    private var buttonView: View? = null
    private var windowManager: WindowManager? = null

    private fun savePosition(context: Context, x: Int, y: Int) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putInt(KEY_X, x).putInt(KEY_Y, y).apply()
    }

    private fun loadPosition(context: Context): Pair<Int, Int>? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (!prefs.contains(KEY_X) || !prefs.contains(KEY_Y)) return null
        return prefs.getInt(KEY_X, 0) to prefs.getInt(KEY_Y, 0)
    }

    fun hasPermission(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)

    fun requestPermission(context: Context) {
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:${context.packageName}"),
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }

    fun ensureShown(appContext: Context) {
        if (buttonView != null) return
        if (!hasPermission(appContext)) return

        val wm = appContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val sizePx = (46 * appContext.resources.displayMetrics.density).toInt()

        val button = ImageView(appContext).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#E53935"))
            }
            setImageResource(android.R.drawable.ic_dialog_email)
            setColorFilter(Color.WHITE)
            val pad = (10 * appContext.resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
            alpha = 0.92f
        }

        val overlayType =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE

        val savedPosition = loadPosition(appContext)
        val margin = (16 * appContext.resources.displayMetrics.density).toInt()

        val params = WindowManager.LayoutParams(
            sizePx, sizePx, overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            if (savedPosition != null) {
                x = savedPosition.first
                y = savedPosition.second
            } else {
                // Default to the bottom-right corner, out of the way of app content.
                x = appContext.resources.displayMetrics.widthPixels - sizePx - margin
                y = appContext.resources.displayMetrics.heightPixels - sizePx - margin * 6
            }
        }

        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var dragged = false

        button.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    startX = params.x
                    startY = params.y
                    dragged = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - downX).toInt()
                    val dy = (event.rawY - downY).toInt()
                    if (abs(dx) > 8 || abs(dy) > 8) dragged = true
                    params.x = startX + dx
                    params.y = startY + dy
                    runCatching { wm.updateViewLayout(button, params) }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (dragged) savePosition(appContext, params.x, params.y) else onTap()
                    true
                }
                else -> false
            }
        }

        runCatching {
            wm.addView(button, params)
            buttonView = button
            windowManager = wm
        }
    }

    fun hide() {
        val wm = windowManager ?: return
        val view = buttonView ?: return
        runCatching { wm.removeView(view) }
        buttonView = null
        windowManager = null
    }

    private fun onTap() {
        val activity = CurrentActivityHolder.current?.get() ?: return
        captureAndOpenReport(activity)
    }

    private fun captureAndOpenReport(activity: Activity) {
        val decorView = activity.window.decorView
        val width = decorView.width
        val height = decorView.height
        if (width <= 0 || height <= 0) return

        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val handler = Handler(Looper.getMainLooper())
        val listener = PixelCopy.OnPixelCopyFinishedListener { result ->
            if (result == PixelCopy.SUCCESS) {
                runCatching {
                    val file = File(activity.cacheDir, "bug_screenshot_${System.currentTimeMillis()}.png")
                    FileOutputStream(file).use { out -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, out) }

                    val intent = Intent(activity, BugReportActivity::class.java).apply {
                        putExtra(BugReportActivity.EXTRA_SCREENSHOT_PATH, file.absolutePath)
                        putExtra(BugReportActivity.EXTRA_ROUTE, NavPathHolder.current)
                        putExtra(BugReportActivity.EXTRA_NETWORK_LOG, NetworkCallLog.snapshotText())
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    activity.startActivity(intent)
                }
            }
        }
        PixelCopy.request(activity.window, bitmap, listener, handler)
    }
}
