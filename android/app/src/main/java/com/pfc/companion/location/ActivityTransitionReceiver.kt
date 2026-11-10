package com.pfc.companion.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.ActivityTransition
import com.google.android.gms.location.ActivityTransitionEvent
import com.google.android.gms.location.ActivityTransitionResult
import com.google.android.gms.location.DetectedActivity
import com.pfc.companion.ServiceLocator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Low-power discovery of places the user has not saved.
 *
 * The activity service reports when movement stops (or a walk begins), which is the
 * cheapest reliable signal that a person has arrived somewhere. Only then is a
 * single balanced-accuracy fix requested. A driving pass produces neither event, so
 * it cannot turn into a visit.
 */
class ActivityTransitionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val result = ActivityTransitionResult.extractResult(intent) ?: return
        if (!ServiceLocator.isReady) return
        if (!ShoppingMonitoring.isLocallyEnabled(context)) return
        if (!ShoppingMonitoring.isDiscoveryEnabled(context)) return

        val transition = pickTransition(result.transitionEvents) ?: return
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val location = ShoppingMonitoring.currentFix(context) ?: return@launch
                val accuracy = location.accuracy.toDouble()
                if (!ShoppingRules.isReliableFix(accuracy)) return@launch
                // A stop means the user is probably settling in; a walk means they
                // are moving through, so demand a better fix before asking.
                val dwell = if (transition == DetectedActivity.STILL) 5 else 2
                val confidence = ShoppingRules.confidenceFor(accuracy, dwell)
                val body = buildJsonObject {
                    put("latitude", location.latitude)
                    put("longitude", location.longitude)
                    put("accuracy_m", accuracy)
                    put("source", "discovery")
                    put("confidence", confidence)
                    put("dwell_minutes", dwell)
                }
                val detected = runCatching { ServiceLocator.repository.detectVisit(body) }
                    .getOrNull() ?: return@launch
                val visit = detected.visit ?: return@launch
                val prompt = detected.prompt
                if (prompt != null && detected.notify) {
                    ShoppingNotifications.newPlace(context, visit)
                    ShoppingMonitoring.recordNotified(context)
                }
            } finally {
                pendingResult.finish()
            }
        }
    }

    private fun pickTransition(events: List<ActivityTransitionEvent>): Int? {
        if (events.isEmpty()) return null
        val entered = events.lastOrNull {
            it.transitionType == ActivityTransition.ACTIVITY_TRANSITION_ENTER
        } ?: return null
        return when (entered.activityType) {
            DetectedActivity.STILL -> DetectedActivity.STILL
            DetectedActivity.WALKING -> DetectedActivity.WALKING
            else -> null
        }
    }
}
