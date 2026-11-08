package com.pfc.companion.ui.vm

import com.pfc.companion.data.ApiClient
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.InMemorySession
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.awaitValue
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.TimeUnit

class SettingsViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var session: InMemorySession
    private lateinit var viewModel: SettingsViewModel

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        session = InMemorySession(server.url("/api/v1/").toString())
        val repository = FinanceRepository(ApiClient(session), session)

        // SettingsViewModel loads the profile on creation; absorb that request so the
        // assertions below only see what the password form does.
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"expired"}"""))
        viewModel = SettingsViewModel(repository)
        server.takeRequest(5, TimeUnit.SECONDS)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `a mismatched confirmation never reaches the server`() {
        val before = server.requestCount

        viewModel.changePassword("OldPassword123", "NewPassword456", "DifferentPassword789")

        val state = viewModel.password.value
        assertTrue(state.error!!.contains("do not match"))
        assertFalse(state.saved)
        assertEquals(before, server.requestCount)
    }

    @Test
    fun `a blank field is rejected before any request`() {
        val before = server.requestCount

        viewModel.changePassword("", "NewPassword456", "NewPassword456")

        assertTrue(viewModel.password.value.error!!.contains("Enter your current"))
        assertEquals(before, server.requestCount)
    }

    @Test
    fun `a successful change stores the replacement token`() {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"access_token":"replacement-token","token_type":"bearer"}"""),
        )

        viewModel.changePassword("OldPassword123", "NewPassword456", "NewPassword456")
        viewModel.password.awaitValue { it.saved }

        val request = server.takeRequest(5, TimeUnit.SECONDS)!!
        assertEquals("/api/v1/auth/password", request.path)
        assertEquals("POST", request.method)
        val body = request.body.readUtf8()
        assertTrue(body.contains("\"current_password\":\"OldPassword123\""))
        assertTrue(body.contains("\"new_password\":\"NewPassword456\""))

        // Keeping the session means storing the new token, not the old one.
        assertEquals("replacement-token", kotlinx.coroutines.runBlocking { session.token() })
        assertNull(viewModel.password.value.error)
    }

    @Test
    fun `a wrong current password is reported as such, not as an expired session`() {
        server.enqueue(
            MockResponse()
                .setResponseCode(401)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"Current password is incorrect."}"""),
        )

        viewModel.changePassword("WrongPassword123", "NewPassword456", "NewPassword456")
        val state = viewModel.password.awaitValue { it.error != null }

        assertEquals("Current password is incorrect.", state.error)
        assertFalse(state.saved)
        // A rejected attempt must leave the existing session alone.
        assertEquals("test-token", kotlinx.coroutines.runBlocking { session.token() })
    }

    @Test
    fun `editing a field clears the previous message`() {
        server.enqueue(
            MockResponse()
                .setResponseCode(422)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"Password must contain at least one number."}"""),
        )
        viewModel.changePassword("OldPassword123", "onlyletters", "onlyletters")
        viewModel.password.awaitValue { it.error != null }

        viewModel.clearPasswordMessage()

        assertNull(viewModel.password.value.error)
        assertFalse(viewModel.password.value.busy)
    }
}
