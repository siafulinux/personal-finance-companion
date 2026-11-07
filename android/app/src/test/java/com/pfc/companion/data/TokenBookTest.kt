package com.pfc.companion.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Two servers must never share an entry, and a trailing slash must not split one. */
class TokenBookTest {

    @Test
    fun `round trips one token per server`() {
        val book = mapOf(
            "https://a.example.com/api/v1/" to "token-a",
            "http://192.168.1.100:8088/api/v1" to "token-b",
        )
        val decoded = TokenBook.decode(TokenBook.encode(book))
        assertEquals("token-a", decoded[TokenBook.key("https://a.example.com/api/v1")])
        assertEquals("token-b", decoded[TokenBook.key("http://192.168.1.100:8088/api/v1/")])
        assertEquals(2, decoded.size)
    }

    @Test
    fun `keys ignore a trailing slash and case`() {
        assertEquals(TokenBook.key("https://A.example.com/api/v1/"), TokenBook.key("https://a.example.com/api/v1"))
    }

    @Test
    fun `garbage decodes to an empty book instead of throwing`() {
        assertTrue(TokenBook.decode("not json").isEmpty())
        assertTrue(TokenBook.decode("{\"https://a/api/v1\":\"\"}").isEmpty())
        assertTrue(TokenBook.decode("[]").isEmpty())
    }
}
