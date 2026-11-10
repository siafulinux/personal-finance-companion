package com.pfc.companion.location

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.pfc.companion.MainActivity
import com.pfc.companion.data.ShoppingVisit
import com.pfc.companion.data.VisitPrompt
import com.pfc.companion.util.formatMoney

/**
 * Notifications for Shopping Intelligence.
 *
 * Deliberately plain: one channel, a short body built from the server's own text,
 * and at most two actions. Nothing repeats on its own, and every notification is
 * cancelled as soon as the visit is dealt with.
 */
object ShoppingNotifications {
    const val CHANNEL_ID = "shopping_intelligence"
    const val ACTION_NOT_NOW = "com.pfc.companion.SHOPPING_NOT_NOW"
    const val ACTION_IGNORE = "com.pfc.companion.SHOPPING_IGNORE"
    const val EXTRA_VISIT_ID = "visit_id"
    const val EXTRA_NOTIFICATION_ID = "notification_id"

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Shopping Check",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Guidance when you arrive somewhere you chose to monitor."
            }
        )
    }

    fun canPost(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        return NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    private fun openApp(context: Context): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("shopping_intelligence", true)
        }
        return PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun action(context: Context, action: String, visitId: String, code: Int): PendingIntent {
        val intent = Intent(context, ShoppingActionReceiver::class.java).apply {
            this.action = action
            putExtra(EXTRA_VISIT_ID, visitId)
            putExtra(EXTRA_NOTIFICATION_ID, visitId.hashCode())
        }
        return PendingIntent.getBroadcast(
            context,
            code,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    /** Arrival at a place the user already tracks. */
    fun arrival(context: Context, prompt: VisitPrompt) {
        if (!canPost(context)) return
        ensureChannel(context)
        val limit = prompt.suggestedLimit
        val body = buildString {
            append(prompt.message)
            if (!limit.isNullOrBlank()) {
                append(" Suggested limit for this visit: ")
                append(formatMoney(limit))
            }
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_map)
            .setContentTitle("You're at ${prompt.businessName}")
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(openApp(context))
            .addAction(0, "Not now", action(context, ACTION_NOT_NOW, prompt.visitId, 1))
            .build()
        NotificationManagerCompat.from(context).notify(prompt.visitId.hashCode(), notification)
    }

    /** A place the app noticed but the user has not added. Never silent addition. */
    fun newPlace(context: Context, visit: ShoppingVisit) {
        if (!canPost(context)) return
        ensureChannel(context)
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_map)
            .setContentTitle("New place: ${visit.businessName}")
            .setContentText("Add it to Shopping Check to see budgets and guidance when you arrive.")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    "Add it to Shopping Check to see budgets and guidance when you arrive. " +
                        "Nothing is added unless you say so."
                )
            )
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(openApp(context))
            .addAction(0, "Not now", action(context, ACTION_NOT_NOW, visit.id, 2))
            .addAction(0, "Don't suggest", action(context, ACTION_IGNORE, visit.id, 3))
            .build()
        NotificationManagerCompat.from(context).notify(visit.id.hashCode(), notification)
    }

    fun cancel(context: Context, visitId: String) {
        NotificationManagerCompat.from(context).cancel(visitId.hashCode())
    }
}
