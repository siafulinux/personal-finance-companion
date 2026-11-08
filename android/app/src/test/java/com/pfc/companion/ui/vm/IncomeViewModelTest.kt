package com.pfc.companion.ui.vm

import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.INCOME_SOURCES_JSON
import com.pfc.companion.testing.INCOME_SOURCE_JSON
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.PathDispatcher
import com.pfc.companion.testing.awaitValue
import com.pfc.companion.testing.repositoryFor
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class IncomeViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var dispatcher: PathDispatcher
    private lateinit var repository: FinanceRepository

    @Before
    fun setUp() {
        server = MockWebServer()
        dispatcher = PathDispatcher(
            listOf(
                "income-sources/inc-1" to INCOME_SOURCE_JSON,
                "income-sources" to INCOME_SOURCES_JSON,
            )
        )
        server.dispatcher = dispatcher
        server.start()
        repository = repositoryFor(server)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun awaitMessage(block: (CompletableDeferred<String>) -> Unit): String {
        val deferred = CompletableDeferred<String>()
        block(deferred)
        return runBlocking { withTimeout(10_000) { deferred.await() } }
    }

    @Test
    fun `sources load with their payday`() {
        val viewModel = IncomeViewModel(repository)
        val sources = viewModel.sources.awaitValue { it.isNotEmpty() }
        assertEquals(1, sources.size)
        assertEquals("Paycheck", sources.first().name)
        assertEquals("2026-11-14", sources.first().nextPayday)
        assertFalse(viewModel.loading.value)
    }

    @Test
    fun `editing prefills the stored payday and frequency`() {
        val viewModel = IncomeViewModel(repository)
        val source = viewModel.sources.awaitValue { it.isNotEmpty() }.first()

        viewModel.startEdit(source)

        val editor = viewModel.editor.value
        assertTrue(editor.open)
        assertEquals("inc-1", editor.editingId)
        assertEquals("2026-11-14", editor.draft.nextPayday)
        assertEquals("biweekly", editor.draft.frequency)
        assertEquals("2400.00", editor.draft.amount)
    }

    @Test
    fun `changing the payday patches it to the server`() {
        val viewModel = IncomeViewModel(repository)
        val source = viewModel.sources.awaitValue { it.isNotEmpty() }.first()
        viewModel.startEdit(source)
        viewModel.updateDraft { it.copy(nextPayday = "2026-11-28") }

        val message = awaitMessage { viewModel.save { text -> it.complete(text) } }
        assertEquals("Income updated.", message)

        val patch = dispatcher.last("PATCH")!!
        assertTrue(patch.path!!.endsWith("/income-sources/inc-1"))
        val body = patch.body.readUtf8()
        assertTrue(body.contains("\"next_payday\":\"2026-11-28\""))
        assertTrue(body.contains("\"is_active\":true"))
    }

    @Test
    fun `clearing the payday sends an explicit null`() {
        val viewModel = IncomeViewModel(repository)
        val source = viewModel.sources.awaitValue { it.isNotEmpty() }.first()
        viewModel.startEdit(source)
        viewModel.updateDraft { it.copy(nextPayday = "") }

        awaitMessage { viewModel.save { text -> it.complete(text) } }

        val body = dispatcher.last("PATCH")!!.body.readUtf8()
        assertTrue(body.contains("\"next_payday\":null"))
    }

    @Test
    fun `an invalid amount is caught before the request`() {
        val viewModel = IncomeViewModel(repository)
        viewModel.sources.awaitValue { it.isNotEmpty() }
        viewModel.startAdd()
        viewModel.updateDraft { it.copy(name = "Bonus", amount = "0") }
        val before = dispatcher.requests.size

        viewModel.save { }

        assertEquals("Enter an amount above zero.", viewModel.editor.value.error)
        assertEquals(before, dispatcher.requests.size)
    }

    @Test
    fun `removing an income source deletes it and reloads`() {
        val viewModel = IncomeViewModel(repository)
        val source = viewModel.sources.awaitValue { it.isNotEmpty() }.first()

        val message = awaitMessage { viewModel.remove(source.id) { text -> it.complete(text) } }

        assertEquals("Income removed.", message)
        assertEquals("DELETE", dispatcher.last("DELETE")!!.method)
        assertNull(viewModel.error.value)
    }
}
