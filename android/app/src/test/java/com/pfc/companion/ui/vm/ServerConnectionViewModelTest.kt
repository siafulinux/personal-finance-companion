package com.pfc.companion.ui.vm

import com.pfc.companion.data.ApiClient
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.InMemorySession
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.awaitValue
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.TimeUnit

class ServerConnectionViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun infoJson(
        name: String = "Home Finance",
        version: String = "2.0.0",
        apiVersion: Int = 1,
        status: String = "ok",
        setupRequired: Boolean = false,
    ) = """
        {
          "app_name": "Personal Finance Companion",
          "server_name": "$name",
          "version": "$version",
          "api_version": $apiVersion,
          "min_client_api_version": 1,
          "api_base_url": "${server.url("/api/v1/")}",
          "web_url": "${server.url("/")}",
          "status": "$status",
          "registration_enabled": false,
          "setup_required": $setupRequired
        }
    """.trimIndent()

    private fun newSession() = InMemorySession(server.url("/api/v1/").toString())

    private fun newViewModel(session: InMemorySession = newSession()): Pair<ServerConnectionViewModel, InMemorySession> =
        ServerConnectionViewModel(FinanceRepository(ApiClient(session), session)) to session

    private fun address() = server.url("/").toString().trimEnd('/')

    @Test
    fun `an unusable address is rejected before any request`() {
        val (vm, _) = newViewModel()
        vm.onDraftChange("http://finance.example.com")
        vm.testConnection()

        val state = vm.test.value
        assertTrue(state is ServerTestState.Invalid)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `a server that answers is described by name and version`() {
        server.enqueue(MockResponse().setBody(infoJson()))
        val (vm, _) = newViewModel()

        vm.onDraftChange(address())
        vm.testConnection()

        val state = vm.test.awaitValue { it is ServerTestState.Reachable } as ServerTestState.Reachable
        assertEquals("Home Finance", state.info.serverName)
        assertEquals("2.0.0", state.info.version)
        assertEquals("/api/v1/server/info", server.takeRequest().path)
    }

    @Test
    fun `the probe never carries the current server's token`() {
        server.enqueue(MockResponse().setBody(infoJson()))
        val (vm, session) = newViewModel()

        // The session holds a token for whatever server it was configured with.
        assertNotNull(runBlocking { session.token() })
        vm.onDraftChange(address())
        vm.testConnection()
        vm.test.awaitValue { it is ServerTestState.Reachable }

        assertNull(server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun `a server that errors is reported without leaking internals`() {
        server.enqueue(MockResponse().setResponseCode(500).setBody("Traceback: secret path /srv/app"))
        val (vm, _) = newViewModel()

        vm.onDraftChange(address())
        vm.testConnection()

        val state = vm.test.awaitValue { it is ServerTestState.Unreachable } as ServerTestState.Unreachable
        assertTrue(state.message.contains("500"))
        assertTrue(!state.message.contains("Traceback") && !state.message.contains("/srv/app"))
    }

    @Test
    fun `a server speaking an older API is refused`() {
        server.enqueue(MockResponse().setBody(infoJson(apiVersion = 0)))
        val (vm, _) = newViewModel()

        vm.onDraftChange(address())
        vm.testConnection()

        val state = vm.test.awaitValue { it is ServerTestState.Unreachable } as ServerTestState.Unreachable
        assertTrue(state.message.contains("API v0"))
    }

    @Test
    fun `saving requires a successful test`() {
        val (vm, session) = newViewModel()
        vm.onDraftChange(address())
        vm.save()

        assertEquals("Test the connection first.", vm.message.value)
        assertNull(session.savedBaseUrl)
    }

    @Test
    fun `saving after a test selects the tested server`() {
        server.enqueue(MockResponse().setBody(infoJson()))
        val (vm, session) = newViewModel()

        vm.onDraftChange(address())
        vm.testConnection()
        vm.test.awaitValue { it is ServerTestState.Reachable }
        vm.save()

        vm.message.awaitValue { it != null }
        assertEquals("${address()}/api/v1/", session.savedBaseUrl)
        assertTrue(vm.message.value!!.contains("Home Finance"))
        assertTrue(vm.message.value!!.contains("2.0.0"))
    }

    @Test
    fun `editing the address after a test requires a new test`() {
        server.enqueue(MockResponse().setBody(infoJson()))
        val (vm, session) = newViewModel()

        vm.onDraftChange(address())
        vm.testConnection()
        vm.test.awaitValue { it is ServerTestState.Reachable }

        // onDraftChange resets the result, so a stale success cannot be saved.
        vm.onDraftChange("${address()}/")
        assertEquals(ServerTestState.Idle, vm.test.value)
        vm.save()

        assertEquals("Test the connection first.", vm.message.value)
        assertNull(session.savedBaseUrl)
    }

    @Test
    fun `a server awaiting first-run setup says so`() {
        server.enqueue(MockResponse().setBody(infoJson(setupRequired = true)))
        val (vm, _) = newViewModel()

        vm.onDraftChange(address())
        vm.testConnection()
        vm.test.awaitValue { it is ServerTestState.Reachable }
        vm.save()

        vm.message.awaitValue { it != null }
        assertTrue(vm.message.value!!.contains("first-run setup"))
    }

    @Test
    fun `the current address is shown as an origin`() {
        val (vm, _) = newViewModel()
        val draft = vm.draft.awaitValue(timeoutMillis = TimeUnit.SECONDS.toMillis(5)) { it.isNotBlank() }
        assertTrue(draft, !draft.contains("/api/v1"))
        assertTrue(draft, draft.startsWith("http"))
    }
}
