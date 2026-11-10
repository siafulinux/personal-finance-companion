package com.pfc.companion.location

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.location.Location
import android.os.Build
import androidx.core.content.ContextCompat
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.ActivityTransition
import com.google.android.gms.location.ActivityTransitionRequest
import com.google.android.gms.location.DetectedActivity
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingClient
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices
import com.pfc.companion.data.LocationSettings
import com.pfc.companion.data.TrackedLocation
import kotlinx.coroutines.tasks.await

/**
 * Registers and tears down the two location mechanisms.
 *
 * Saved places use the Geofencing API, which the system evaluates in hardware and
 * wakes the app only on entry. Unfamiliar places use Activity Recognition: when the
 * activity service reports that the user stopped or started walking, one balanced
 * fix is requested and resolved. There is no polling loop and no high-accuracy
 * request anywhere in this class, and everything is removed the moment the user
 * turns the feature off.
 */
object ShoppingMonitoring {
    private const val PREFS = "shopping_intelligence"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_DISCOVERY = "discovery"
    private const val KEY_LAST_NOTIFIED = "last_notified"
    private const val GEOFENCE_REQUEST = "pfc-shopping-places"

    fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun isLocallyEnabled(context: Context): Boolean = prefs(context).getBoolean(KEY_ENABLED, false)

    fun isDiscoveryEnabled(context: Context): Boolean =
        prefs(context).getBoolean(KEY_DISCOVERY, false)

    fun lastNotified(context: Context): Long = prefs(context).getLong(KEY_LAST_NOTIFIED, 0L)

    fun recordNotified(context: Context, at: Long = System.currentTimeMillis()) {
        prefs(context).edit().putLong(KEY_LAST_NOTIFIED, at).apply()
    }

    fun applySettings(context: Context, settings: LocationSettings) {
        prefs(context).edit()
            .putBoolean(KEY_ENABLED, settings.enabled && settings.optedIn)
            .putBoolean(KEY_DISCOVERY, settings.discoveryEnabled && settings.enabled && settings.optedIn)
            .apply()
    }

    fun hasForegroundLocation(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    fun hasBackgroundLocation(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    fun hasActivityRecognition(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACTIVITY_RECOGNITION) ==
            PackageManager.PERMISSION_GRANTED

    private fun geofencePendingIntent(context: Context): PendingIntent =
        PendingIntent.getBroadcast(
            context,
            0,
            Intent(context, GeofenceReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )

    private fun activityPendingIntent(context: Context): PendingIntent =
        PendingIntent.getBroadcast(
            context,
            1,
            Intent(context, ActivityTransitionReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )

    /** Registers every saved place that has coordinates. Places without them are skipped. */
    suspend fun registerGeofences(context: Context, locations: List<TrackedLocation>) {
        val client: GeofencingClient = LocationServices.getGeofencingClient(context)
        val pending = geofencePendingIntent(context)
        client.removeGeofences(pending).await()
        if (!isLocallyEnabled(context) || !hasForegroundLocation(context) || !hasBackgroundLocation(context)) {
            return
        }
        val fences = locations
            .filter { it.isActive && it.hasCoordinates }
            .mapNotNull { location ->
                val lat = location.latitude?.toDoubleOrNull() ?: return@mapNotNull null
                val lon = location.longitude?.toDoubleOrNull() ?: return@mapNotNull null
                Geofence.Builder()
                    .setRequestId(location.id)
                    .setCircularRegion(lat, lon, ShoppingRules.clampedRadius(location.radiusM))
                    // Dwell is what separates a visit from driving past the shop.
                    .setLoiteringDelay(5 * 60 * 1000)
                    .setExpirationDuration(Geofence.NEVER_EXPIRE)
                    .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER or Geofence.GEOFENCE_TRANSITION_DWELL)
                    .build()
            }
        if (fences.isEmpty()) return
        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofences(fences)
            .build()
        client.addGeofences(request, pending).await()
    }

    suspend fun removeGeofences(context: Context) {
        LocationServices.getGeofencingClient(context)
            .removeGeofences(geofencePendingIntent(context))
            .await()
    }

    /** Low-power discovery: the activity service tells us when moving stops. */
    suspend fun registerActivityTransitions(context: Context) {
        if (!isDiscoveryEnabled(context) || !hasActivityRecognition(context)) return
        val transitions = listOf(
            ActivityTransition.Builder()
                .setActivityType(DetectedActivity.STILL)
                .setActivityTransition(ActivityTransition.ACTIVITY_TRANSITION_ENTER)
                .build(),
            ActivityTransition.Builder()
                .setActivityType(DetectedActivity.WALKING)
                .setActivityTransition(ActivityTransition.ACTIVITY_TRANSITION_ENTER)
                .build(),
        )
        ActivityRecognition.getClient(context)
            .requestActivityTransitionUpdates(
                ActivityTransitionRequest(transitions),
                activityPendingIntent(context),
            )
            .await()
    }

    suspend fun removeActivityTransitions(context: Context) {
        ActivityRecognition.getClient(context)
            .removeActivityTransitionUpdates(activityPendingIntent(context))
            .await()
    }

    /** Full teardown used when the user disables the feature or revokes consent. */
    suspend fun stop(context: Context) {
        runCatching { removeGeofences(context) }
        runCatching { removeActivityTransitions(context) }
    }

    /** One balanced-power fix. Never a stream, never high accuracy. */
    suspend fun currentFix(context: Context): Location? {
        if (!hasForegroundLocation(context)) return null
        return LocationServices.getFusedLocationProviderClient(context)
            .getCurrentLocation(
                com.google.android.gms.location.Priority.PRIORITY_BALANCED_POWER_ACCURACY,
                null,
            )
            .await()
    }
}
