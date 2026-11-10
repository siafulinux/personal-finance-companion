package com.pfc.companion.location

/**
 * Pure rules for Shopping Intelligence.
 *
 * Kept free of Android types so they can be unit-tested on the JVM. The service
 * classes call these; nothing here reads the clock or touches storage.
 */
object ShoppingRules {
    const val MIN_RADIUS_M = 50
    const val MAX_RADIUS_M = 2000

    /** Android rejects geofences outside this radius, and silently drops them. */
    fun clampedRadius(radiusM: Int): Float =
        radiusM.coerceIn(MIN_RADIUS_M, MAX_RADIUS_M).toFloat()

    /** "HH:MM" -> minutes since midnight, or null when unset/malformed. */
    fun minutesOfDay(value: String?): Int? {
        if (value.isNullOrBlank()) return null
        val parts = value.split(":")
        if (parts.size != 2) return null
        val hour = parts[0].toIntOrNull() ?: return null
        val minute = parts[1].toIntOrNull() ?: return null
        if (hour !in 0..23 || minute !in 0..59) return null
        return hour * 60 + minute
    }

    /**
     * Quiet hours may wrap midnight (22:00 - 07:00). An unset or empty window is
     * never quiet, and a zero-length window is treated as "off" rather than
     * "always quiet".
     */
    fun inQuietHours(currentMinutes: Int, start: String?, end: String?): Boolean {
        val from = minutesOfDay(start) ?: return false
        val to = minutesOfDay(end) ?: return false
        if (from == to) return false
        val now = currentMinutes.coerceIn(0, 24 * 60 - 1)
        return if (from < to) now in from until to else now >= from || now < to
    }

    /** True when the cooldown has passed. A first-ever notification is allowed. */
    fun cooldownElapsed(nowMillis: Long, lastNotifiedMillis: Long?, cooldownMinutes: Int): Boolean {
        if (lastNotifiedMillis == null || lastNotifiedMillis <= 0L) return true
        val window = cooldownMinutes.coerceAtLeast(0) * 60_000L
        return nowMillis - lastNotifiedMillis >= window
    }

    /** The single gate every notification passes through. */
    fun shouldNotify(
        featureEnabled: Boolean,
        paused: Boolean,
        quiet: Boolean,
        cooldownElapsed: Boolean,
        hasPrompt: Boolean,
        serverSuppressed: Boolean,
    ): Boolean = featureEnabled && !paused && !quiet && cooldownElapsed && hasPrompt && !serverSuppressed

    /**
     * Confidence for a detected stay. A driving pass has a poor fix and no dwell,
     * so it scores below the threshold instead of producing a visit.
     */
    fun confidenceFor(accuracyM: Double?, dwellMinutes: Int?): Double {
        if (accuracyM == null || accuracyM > 250.0) return 0.0
        val accuracyScore = when {
            accuracyM <= 35.0 -> 1.0
            accuracyM <= 75.0 -> 0.85
            accuracyM <= 150.0 -> 0.6
            else -> 0.35
        }
        val dwell = (dwellMinutes ?: 0).coerceIn(0, 60)
        val dwellScore = when {
            dwell >= 10 -> 1.0
            dwell >= 5 -> 0.8
            dwell >= 3 -> 0.55
            else -> 0.25
        }
        return (accuracyScore * 0.6 + dwellScore * 0.4).coerceIn(0.0, 1.0)
    }

    /** A fix too vague to name a business should not become a suggestion. */
    fun isReliableFix(accuracyM: Double?): Boolean = accuracyM != null && accuracyM <= 150.0
}
