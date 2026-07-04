package com.quail.android.push

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.quail.android.AppConfig
import com.quail.android.MainActivity
import com.quail.android.R
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.repository.AuthStore
import com.quail.android.data.repository.HomeRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import kotlin.random.Random

/** Handles FCM token refresh (registers with the backend) and incoming
 * pushes. A custom onMessageReceived is required even though the backend
 * sends a "notification" payload, because Android only auto-displays
 * notification-payload pushes when the app is backgrounded — when it's in
 * the foreground, FCM delivers silently and the app must show it itself. */
class QuailMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(Dispatchers.IO)

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        val authStore = AuthStore.getInstance(applicationContext)
        scope.launch {
            val current = authStore.session.firstOrNull()
            if (current == null) return@launch
            try {
                val repository = HomeRepository(NetworkModule.create(authStore))
                repository.registerAndroidPushDevice(token = token, deviceName = Build.MODEL)
            } catch (_: Exception) {
                // Best-effort; will retry next time onNewToken fires or the user re-logs in.
            }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        val title = message.notification?.title ?: message.data["title"] ?: "Quail"
        val body = message.notification?.body ?: message.data["body"] ?: ""

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notification = NotificationCompat.Builder(this, AppConfig.DEFAULT_NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        NotificationManagerCompat.from(this).notify(Random.nextInt(), notification)
    }
}
