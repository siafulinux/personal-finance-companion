package com.pfc.companion.ui.vm

import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.TRANSACTION_PAGE_JSON
import com.pfc.companion.testing.awaitValue
import com.pfc.companion.testing.repositoryFor
import com.pfc.companion.ui.components.UiState
import java.util.concurrent.TimeUnit
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class LedgerViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var repository: FinanceRepository

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        repository = repositoryFor(server)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun page() = MockResponse()
        .setHeader("Content-Type", "application/json")
        .setBody(TRANSACTION_PAGE_JSON)

    @Test
    fun `loads the ledger and refilters through the api`() {
        server.enqueue(page())
        server.enqueue(page())

        val viewModel = LedgerViewModel(repository)
        val initial = viewModel.state.awaitValue { it is UiState.Ready } as UiState.Ready
        assertEquals(1, initial.data.items.size)
        assertEquals("4.50", initial.data.totals.spending)

        // The first response belongs to the initial, unfiltered load.
        server.takeRequest(5, TimeUnit.SECONDS)
        viewModel.setFilter("income")

        val filteredRequest = server.takeRequest(5, TimeUnit.SECONDS)
        assertTrue(filteredRequest!!.path!!.contains("tx_type=income"))
        val filtered = viewModel.state.awaitValue { it is UiState.Ready } as UiState.Ready
        assertEquals(1, filtered.data.total)
    }

    @Test
    fun `surfaces api failures with a readable message`() {
        server.enqueue(
            MockResponse()
                .setResponseCode(500)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"The ledger is unavailable."}""")
        )

        val viewModel = LedgerViewModel(repository)
        val failed = viewModel.state.awaitValue { it is UiState.Failed } as UiState.Failed
        assertTrue(failed.message.contains("ledger is unavailable"))
    }
}
