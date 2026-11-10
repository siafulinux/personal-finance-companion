package com.pfc.companion.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import com.pfc.companion.ServiceLocator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * A saved place was entered and the user stayed long enough for the loitering
 * delay to elapse.
 *
 * Only the geofence's request id leaves the device: the server already knows where
 * that place is. The notification is posted here, after the server has decided
 * whether the user should be told at all.
 */
class GeofenceReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ServiceLocator.isReady) return
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.hasError()) return
        val transition = event.geofenceTransition
        if (transition != Geofence.GEOFENCE_TRANSITION_ENTER &&
            transition != Geofence.GEOFENCE_TRANSITION_DWELL
        ) {
            return
        }
        val ids = event.triggeringGeofences?.map { it.requestId }.orEmpty()
        if (ids.isEmpty()) return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                for (id in ids) {
                    val result = runCatching { ServiceLocator.repository.recordArrival(id) }
                        .getOrNull() ?: continue
                    val prompt = result.prompt ?: continue
                    if (result.notify) {
                        ShoppingNotifications.arrival(context, prompt)
                        ShoppingMonitoring.recordNotified(context)
                    }
                }
            } finally {
                pendingResult.finish()
            }
        }
    }
}
