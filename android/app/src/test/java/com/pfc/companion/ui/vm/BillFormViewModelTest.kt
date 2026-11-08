package com.pfc.companion.ui.vm

import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.ACCOUNTS_JSON
import com.pfc.companion.testing.BILL_JSON
import com.pfc.companion.testing.CATEGORIES_JSON
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

class BillFormViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var dispatcher: PathDispatcher
    private lateinit var repository: FinanceRepository

    private val routes = listOf(
        "bills/bill-1" to BILL_JSON,
        "bills" to BILL_JSON,
        "accounts" to ACCOUNTS_JSON,
        "categories" to CATEGORIES_JSON,
    )

    @Before
    fun setUp() {
        server = MockWebServer()
        dispatcher = PathDispatcher(routes)
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
    fun `editing loads the stored bill instead of a blank form`() {
        val viewModel = BillFormViewModel(repository, billId = "bill-1")
        val state = viewModel.state.awaitValue { !it.loading && it.draft.name.isNotEmpty() }

        assertTrue(state.editing)
        assertEquals("Internet", state.draft.name)
        assertEquals("Comcast", state.draft.merchant)
        assertEquals("85.00", state.draft.expectedAmount)
        assertEquals("80.00", state.draft.minimumAmount)
        assertEquals("2026-11-15", state.draft.anchorDate)
        assertEquals("cat-2", state.draft.categoryId)
        assertEquals("Auto-pay", state.draft.notes)
        assertEquals(2, state.accounts.size)
        assertEquals(2, state.categories.size)
    }

    @Test
    fun `creating sends the anchor date and the chosen schedule`() {
        val viewModel = BillFormViewModel(repository, billId = null)
        viewModel.state.awaitValue { !it.loading }
        viewModel.update {
            it.copy(
                name = "Water",
                expectedAmount = "40.00",
                anchorDate = "2026-12-01",
                frequency = "quarterly",
                categoryId = "cat-1",
            )
        }

        val message = awaitMessage { viewModel.submit { text -> it.complete(text) } }
        // The server's response is the created bill, so the name it reports wins.
        assertEquals("Added Internet.", message)

        val create = dispatcher.last("POST")!!
        assertTrue(create.path!!.endsWith("/bills"))
        val body = create.body.readUtf8()
        assertTrue(body.contains("\"anchor_date\":\"2026-12-01\""))
        assertTrue(body.contains("\"frequency\":\"quarterly\""))
        assertTrue(body.contains("\"category_id\":\"cat-1\""))
        assertFalse(viewModel.state.value.saving)
    }

    @Test
    fun `editing patches without repeating the anchor date`() {
        val viewModel = BillFormViewModel(repository, billId = "bill-1")
        viewModel.state.awaitValue { !it.loading && it.draft.name.isNotEmpty() }
        viewModel.update { it.copy(expectedAmount = "95.00") }

        val message = awaitMessage { viewModel.submit { text -> it.complete(text) } }
        assertEquals("Saved Internet.", message)

        val patch = dispatcher.last("PATCH")!!
        assertEquals("PATCH", patch.method)
        assertTrue(patch.path!!.endsWith("/bills/bill-1"))
        val body = patch.body.readUtf8()
        assertTrue(body.contains("\"expected_amount\":\"95.00\""))
        // Moving the anchor would rewrite occurrences that already exist.
        assertFalse(body.contains("anchor_date"))
    }

    @Test
    fun `an invalid draft never reaches the server`() {
        val viewModel = BillFormViewModel(repository, billId = null)
        viewModel.state.awaitValue { !it.loading }
        val before = dispatcher.requests.size

        val called = mutableListOf<String>()
        viewModel.submit { called.add(it) }

        val error = viewModel.state.awaitValue { it.error != null }.error
        assertEquals("Give this bill a name.", error)
        assertEquals(before, dispatcher.requests.size)
        assertTrue(called.isEmpty())
    }

    @Test
    fun `deleting a bill calls the delete endpoint`() {
        val viewModel = BillFormViewModel(repository, billId = "bill-1")
        viewModel.state.awaitValue { !it.loading && it.draft.name.isNotEmpty() }

        val message = awaitMessage { viewModel.delete { text -> it.complete(text) } }
        assertEquals("Bill deleted.", message)
        assertEquals("DELETE", dispatcher.last("DELETE")!!.method)
        assertNull(viewModel.state.value.error)
    }
}
