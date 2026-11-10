package com.pfc.companion.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.pfc.companion.ServiceLocator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Re-arms activity transitions after a reboot or an app update.
 *
 * Geofences survive a reboot in the system, but activity-recognition requests do
 * not, and a user who restarts their phone should not silently lose discovery.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ServiceLocator.isReady) return
        if (!ShoppingMonitoring.isLocallyEnabled(context)) return
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val settings = runCatching { ServiceLocator.repository.locationSettings() }
                    .getOrNull() ?: return@launch
                ShoppingMonitoring.applySettings(context, settings)
                if (!settings.enabled || !settings.optedIn) return@launch
                val locations = runCatching { ServiceLocator.repository.trackedLocations() }
                    .getOrDefault(emptyList())
                runCatching { ShoppingMonitoring.registerGeofences(context, locations) }
                if (settings.discoveryEnabled) {
                    runCatching { ShoppingMonitoring.registerActivityTransitions(context) }
                }
            } finally {
                pendingResult.finish()
            }
        }
    }
}
