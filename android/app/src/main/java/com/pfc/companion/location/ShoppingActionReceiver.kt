package com.pfc.companion.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.pfc.companion.ServiceLocator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** "Not now" and "Don't suggest" from a notification. */
class ShoppingActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val visitId = intent.getStringExtra(ShoppingNotifications.EXTRA_VISIT_ID) ?: return
        ShoppingNotifications.cancel(context, visitId)
        if (intent.action != ShoppingNotifications.ACTION_IGNORE) return
        if (!ServiceLocator.isReady) return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                runCatching { ServiceLocator.repository.ignoreVisit(visitId) }
            } finally {
                pendingResult.finish()
            }
        }
    }
}
