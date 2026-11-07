package com.pfc.companion.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The address rules decide where a bearer token and financial data may travel, so
 * they are tested as policy rather than as string formatting.
 */
class ServerUrlTest {

    private fun valid(raw: String): ServerUrl.Parsed {
        val result = ServerUrl.parse(raw)
        assertTrue("expected $raw to be accepted, got $result", result is ServerUrl.Result.Valid)
        return (result as ServerUrl.Result.Valid).parsed
    }

    private fun reason(raw: String): String {
        val result = ServerUrl.parse(raw)
        assertTrue("expected $raw to be rejected, got $result", result is ServerUrl.Result.Invalid)
        return (result as ServerUrl.Result.Invalid).reason
    }

    @Test
    fun `a bare LAN host gets https and the api path`() {
        val parsed = valid("192.168.1.100:8088")
        assertEquals("https://192.168.1.100:8088/api/v1/", parsed.apiBaseUrl)
        assertFalse(parsed.insecure)
    }

    @Test
    fun `plain http is accepted on a private address`() {
        val parsed = valid("http://192.168.1.100:8088")
        assertEquals("http://192.168.1.100:8088/api/v1/", parsed.apiBaseUrl)
        assertTrue(parsed.insecure)
    }

    @Test
    fun `a pasted api url does not double the path`() {
        assertEquals(
            "http://192.168.1.100:8088/api/v1/",
            valid("http://192.168.1.100:8088/api/v1/").apiBaseUrl,
        )
        assertEquals(
            "https://finance.example.com/api/v1/",
            valid("https://finance.example.com/api/v1").apiBaseUrl,
        )
    }

    @Test
    fun `a public name must use https`() {
        val message = reason("http://finance.example.com")
        assertTrue(message.contains("https://"))
        assertTrue(message.contains("Plain http://"))
    }

    @Test
    fun `plain http is refused for public IPs`() {
        reason("http://8.8.8.8:8088")
        reason("http://172.32.0.5")
        valid("http://172.31.0.5")
        valid("http://10.0.2.2:8443")
        valid("http://localhost:5183")
        valid("http://127.0.0.1:8080")
        valid("http://[fd00::1]:8080")
        valid("http://finance.local:8088")
        valid("http://nas:8088")
    }

    @Test
    fun `credentials in the address are refused`() {
        assertTrue(reason("http://alice:secret@192.168.1.5:8088").contains("username"))
    }

    @Test
    fun `other schemes and paths are refused`() {
        reason("ftp://192.168.1.5")
        reason("https://finance.example.com/v2")
        assertNull(ServerUrl.apiBaseUrlOrNull("https://finance.example.com/v2"))
    }

    @Test
    fun `an empty address is refused`() {
        reason("   ")
    }

    @Test
    fun `displayed address is the origin`() {
        assertEquals(
            "https://finance.example.com",
            ServerUrl.displayAddress("https://finance.example.com/api/v1/"),
        )
        assertEquals("http://192.168.1.100:8088", ServerUrl.displayAddress("http://192.168.1.100:8088/api/v1"))
    }

    /**
     * A stored address can lack the API path: an older build saved the display
     * form, and app data survives reinstallation. Requests are appended to the
     * stored base, so `https://host:8443/` used to ask `/auth/me` and get a 404
     * from a server that was otherwise perfectly reachable.
     */
    @Test
    fun `a stored origin is repaired to the api base`() {
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443"),
        )
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/"),
        )
        assertEquals(
            "http://192.168.1.100:8088/api/v1/",
            ServerUrl.apiBaseFromStored("http://192.168.1.100:8088"),
        )
    }

    @Test
    fun `a stored address that already has the api path is left alone`() {
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/api/v1/"),
        )
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/api/v1"),
        )
        // Whitespace from a pasted value must not defeat the repair.
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("  https://192.168.1.5:8443/  "),
        )
    }

    /**
     * A stored address can carry only part of the API path — a truncated paste, or
     * a value written by a build that assumed `/api`. Appending the full prefix to
     * that asked `/api/api/v1/auth/me`, which the server answers with 404 at a port
     * that is working, so the failure looks like an outage instead of a bad address.
     */
    @Test
    fun `a stored partial api path is not doubled`() {
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/api"),
        )
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/api/"),
        )
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/v1/"),
        )
        // The same mistake made twice must still land on one prefix.
        assertEquals(
            "https://192.168.1.5:8443/api/v1/",
            ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/api/api/v1/"),
        )
    }

    /**
     * The editable field must never show a value the same form rejects. A stored
     * `.../api` used to display as `.../api`, fail validation on submit, and leave
     * the user stuck on the sign-in screen with a path error they had not typed.
     */
    @Test
    fun `a stored partial api path displays as the origin`() {
        assertEquals("https://192.168.1.5:8443", ServerUrl.displayAddress("https://192.168.1.5:8443/api"))
        assertEquals("https://192.168.1.5:8443", ServerUrl.displayAddress("https://192.168.1.5:8443/api/"))
        assertEquals("https://192.168.1.5:8443", ServerUrl.displayAddress("https://192.168.1.5:8443/v1"))
        assertEquals("", ServerUrl.displayAddress(""))
    }

    @Test
    fun `a displayed stored address parses back to the same api base`() {
        for (stored in listOf(
            "https://192.168.1.5:8443",
            "https://192.168.1.5:8443/",
            "https://192.168.1.5:8443/api",
            "https://192.168.1.5:8443/api/v1/",
        )) {
            val shown = ServerUrl.displayAddress(stored)
            val parsed = (ServerUrl.parse(shown) as? ServerUrl.Result.Valid)?.parsed
            assertEquals(
                "stored $stored shown as $shown should parse",
                ServerUrl.apiBaseFromStored(stored),
                parsed?.apiBaseUrl,
            )
        }
    }

    @Test
    fun `repairing a stored address is idempotent`() {
        val once = ServerUrl.apiBaseFromStored("https://192.168.1.5:8443/api")
        assertEquals(once, ServerUrl.apiBaseFromStored(once))
        assertEquals(once, ServerUrl.apiBaseFromStored(ServerUrl.apiBaseFromStored(once)))
    }

    @Test
    fun `an empty stored address stays empty instead of becoming a path-only base`() {
        assertEquals("", ServerUrl.apiBaseFromStored(""))
        assertEquals("", ServerUrl.apiBaseFromStored("   \n "))
    }

    @Test
    fun `a stored api base lines up with a parsed one`() {
        val parsed = valid("https://192.168.1.5:8443").apiBaseUrl
        assertEquals(parsed, ServerUrl.apiBaseFromStored("https://192.168.1.5:8443"))
    }
}
