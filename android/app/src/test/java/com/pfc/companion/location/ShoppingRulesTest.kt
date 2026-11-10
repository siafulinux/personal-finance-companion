package com.pfc.companion.location

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The rules that decide whether a detected place becomes a notification.
 *
 * These are plain JVM tests: the geofence and activity receivers only gather facts,
 * and every judgement call lives here where it can be checked without a device.
 */
class ShoppingRulesTest {
    @Test
    fun `radius is clamped to what Android accepts`() {
        assertEquals(50f, ShoppingRules.clampedRadius(10))
        assertEquals(150f, ShoppingRules.clampedRadius(150))
        assertEquals(2000f, ShoppingRules.clampedRadius(9000))
    }

    @Test
    fun `quiet hours wrap midnight`() {
        // 23:30 is inside 22:00-07:00.
        assertTrue(ShoppingRules.inQuietHours(23 * 60 + 30, "22:00", "07:00"))
        // 03:00 too.
        assertTrue(ShoppingRules.inQuietHours(3 * 60, "22:00", "07:00"))
        // Noon is not.
        assertFalse(ShoppingRules.inQuietHours(12 * 60, "22:00", "07:00"))
    }

    @Test
    fun `a daytime window does not wrap`() {
        assertTrue(ShoppingRules.inQuietHours(13 * 60, "12:00", "14:00"))
        assertFalse(ShoppingRules.inQuietHours(15 * 60, "12:00", "14:00"))
    }

    @Test
    fun `unset or malformed quiet hours are never quiet`() {
        assertFalse(ShoppingRules.inQuietHours(23 * 60, null, null))
        assertFalse(ShoppingRules.inQuietHours(23 * 60, "", ""))
        assertFalse(ShoppingRules.inQuietHours(23 * 60, "25:00", "07:00"))
        // A zero-length window means "off", not "always quiet".
        assertFalse(ShoppingRules.inQuietHours(23 * 60, "22:00", "22:00"))
    }

    @Test
    fun `cooldown blocks a second notification inside the window`() {
        val now = 1_700_000_000_000L
        assertTrue(ShoppingRules.cooldownElapsed(now, null, 60))
        assertFalse(ShoppingRules.cooldownElapsed(now, now - 30 * 60_000L, 60))
        assertTrue(ShoppingRules.cooldownElapsed(now, now - 61 * 60_000L, 60))
    }

    @Test
    fun `should notify needs every gate open`() {
        assertTrue(
            ShoppingRules.shouldNotify(
                featureEnabled = true,
                paused = false,
                quiet = false,
                cooldownElapsed = true,
                hasPrompt = true,
                serverSuppressed = false,
            )
        )
        val blocked = listOf(
            ShoppingRules.shouldNotify(true, true, false, true, true, false),
            ShoppingRules.shouldNotify(true, false, true, true, true, false),
            ShoppingRules.shouldNotify(true, false, false, false, true, false),
            ShoppingRules.shouldNotify(true, false, false, true, false, false),
            ShoppingRules.shouldNotify(true, false, false, true, true, true),
            ShoppingRules.shouldNotify(false, false, false, true, true, false),
        )
        assertTrue(blocked.none { it })
    }

    @Test
    fun `a driving pass scores below a real stop`() {
        // Poor fix, no dwell: not a place worth naming.
        assertTrue(ShoppingRules.confidenceFor(400.0, 0) < 0.35)
        // A precise stop.
        assertTrue(ShoppingRules.confidenceFor(20.0, 12) > 0.9)
        // Stopped in traffic with a mediocre fix.
        val traffic = ShoppingRules.confidenceFor(120.0, 2)
        assertTrue(traffic < ShoppingRules.confidenceFor(20.0, 10))
        assertTrue(traffic < 0.65)
    }

    @Test
    fun `vague fixes are rejected outright`() {
        assertFalse(ShoppingRules.isReliableFix(null))
        assertFalse(ShoppingRules.isReliableFix(300.0))
        assertTrue(ShoppingRules.isReliableFix(80.0))
    }
}
