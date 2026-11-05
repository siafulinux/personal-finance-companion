package com.pfc.companion.ui.vm

import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.ACCOUNTS_JSON
import com.pfc.companion.testing.CATEGORIES_JSON
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.TRANSACTION_JSON
import com.pfc.companion.testing.awaitValue
import com.pfc.companion.testing.repositoryFor
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CompletableDeferred
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class TransactionFormViewModelTest {
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

    private fun json(body: String, status: Int = 200) = MockResponse()
        .setResponseCode(status)
        .setHeader("Content-Type", "application/json")
        .setBody(body)

    private fun enqueueFormData() {
        server.enqueue(json(ACCOUNTS_JSON))
        server.enqueue(json(CATEGORIES_JSON))
    }

    @Test
    fun `invalid submissions never reach the server`() {
        enqueueFormData()
        val viewModel = TransactionFormViewModel(repository)
        viewModel.state.awaitValue { !it.loading }
        assertEquals(2, server.requestCount)

        val calls = mutableListOf<String>()
        viewModel.update { it.copy(description = "Coffee") }
        viewModel.submit { calls.add(it) }

        val error = viewModel.state.awaitValue { it.error != null }.error
        assertEquals("Enter an amount above zero.", error)
        assertEquals(2, server.requestCount)
        assertTrue(calls.isEmpty())
    }

    @Test
    fun `creating a matched transaction reports the bill and sends the draft`() {
        enqueueFormData()
        server.enqueue(
            json(
                """{"transaction":$TRANSACTION_JSON,
                    "match_info":{"outcome":"auto","matched":true,"bill_name":"Internet","confidence":"0.950"},
                    "possible_duplicates":[]}"""
            )
        )

        val viewModel = TransactionFormViewModel(repository)
        viewModel.state.awaitValue { !it.loading }
        // Drain the form's account and category lookups so the next request is the POST.
        repeat(2) { server.takeRequest(5, TimeUnit.SECONDS) }
        viewModel.update {
            it.copy(
                amount = "4.50",
                description = "Coffee",
                merchant = "Cafe",
                categoryId = "cat-1",
                tags = "work, coffee",
            )
        }

        val saved = CompletableDeferred<String>()
        viewModel.submit { saved.complete(it) }

        val message = kotlinx.coroutines.runBlocking {
            kotlinx.coroutines.withTimeout(10_000) { saved.await() }
        }
        assertTrue(message.contains("Matched the Internet bill"))

        val createRequest = server.takeRequest(5, TimeUnit.SECONDS)!!
        assertTrue(createRequest.path!!.endsWith("/transactions"))
        val body = createRequest.body.readUtf8()
        assertTrue(body.contains("\"description\":\"Coffee\""))
        assertTrue(body.contains("\"category_id\":\"cat-1\""))
        assertTrue(body.contains("\"tags\":[\"work\",\"coffee\"]"))
        assertFalse(viewModel.state.value.saving)
    }

    @Test
    fun `ambiguous matches ask for review instead of claiming a payment`() {
        enqueueFormData()
        server.enqueue(
            json(
                """{"transaction":$TRANSACTION_JSON,
                    "match_info":{"outcome":"suggest","matched":false,"ambiguous":true,
                                  "reason":"Two bills are equally close"},
                    "possible_duplicates":[]}"""
            )
        )

        val viewModel = TransactionFormViewModel(repository)
        viewModel.state.awaitValue { !it.loading }
        viewModel.update { it.copy(amount = "95.00", description = "Internet", categoryId = "cat-1") }

        val saved = CompletableDeferred<String>()
        viewModel.submit { saved.complete(it) }
        val message = kotlinx.coroutines.runBlocking {
            kotlinx.coroutines.withTimeout(10_000) { saved.await() }
        }
        assertTrue(message.contains("ambiguous bill match"))
    }

    @Test
    fun `backend validation errors are shown on the form`() {
        enqueueFormData()
        server.enqueue(
            json(
                """{"detail":"Please check the highlighted fields.",
                    "errors":[{"loc":["body","amount"],"msg":"Amount must be greater than 0.","type":"value_error"}]}""",
                status = 422,
            )
        )

        val viewModel = TransactionFormViewModel(repository)
        viewModel.state.awaitValue { !it.loading }
        viewModel.update { it.copy(amount = "5.00", description = "Bad", categoryId = "cat-1") }
        viewModel.submit { }

        val error = viewModel.state.awaitValue { it.error != null }.error
        assertNotNull(error)
        assertTrue(error!!.contains("Amount must be greater than 0."))
    }

    @Test
    fun `editing loads the existing transaction and reports an update`() {
        enqueueFormData()
        server.enqueue(json(TRANSACTION_JSON))
        server.enqueue(json(TRANSACTION_JSON))

        val viewModel = TransactionFormViewModel(repository, transactionId = "txn-1")
        val loaded = viewModel.state.awaitValue { !it.loading && it.draft.description.isNotEmpty() }
        assertEquals("Coffee", loaded.draft.description)
        assertEquals("4.50", loaded.draft.amount)

        val saved = CompletableDeferred<String>()
        viewModel.submit { saved.complete(it) }
        val message = kotlinx.coroutines.runBlocking {
            kotlinx.coroutines.withTimeout(10_000) { saved.await() }
        }
        assertEquals("Transaction updated.", message)

        // Skip the three GETs (accounts, categories, transaction), then inspect the PATCH.
        repeat(3) { server.takeRequest(5, TimeUnit.SECONDS) }
        val patch = server.takeRequest(5, TimeUnit.SECONDS)!!
        assertEquals("PATCH", patch.method)
        assertTrue(patch.path!!.endsWith("/transactions/txn-1"))
    }
}
