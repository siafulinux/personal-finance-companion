package com.pfc.companion.data

import com.pfc.companion.testing.ACCOUNTS_JSON
import com.pfc.companion.testing.COMMIT_RESULT_JSON
import com.pfc.companion.testing.TRANSACTION_JSON
import com.pfc.companion.testing.UPLOAD_RESPONSE_JSON
import com.pfc.companion.testing.repositoryFor
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class FinanceRepositoryTest {
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

    @Test
    fun `creating an expense posts the contract fields and parses the match`() = runBlocking {
        server.enqueue(
            json(
                """{"transaction":$TRANSACTION_JSON,
                    "match_info":{"outcome":"auto","matched":true,"bill_name":"Internet","confidence":"0.950"},
                    "possible_duplicates":[]}"""
            )
        )

        val result = repository.createTransaction(
            TransactionDraft(
                txType = "purchase",
                amount = "4.50",
                txnDate = "2026-11-02",
                description = "Coffee",
                merchant = "Cafe",
                accountId = "acc-1",
                categoryId = "cat-1",
                tags = "work, reimbursable",
            )
        )

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/v1/transactions", request.path)
        val body = request.body.readUtf8()
        assertTrue(body.contains("\"account_id\":\"acc-1\""))
        assertTrue(body.contains("\"amount\":\"4.50\""))
        assertTrue(body.contains("\"tx_type\":\"purchase\""))
        assertTrue(body.contains("\"tags\":[\"work\",\"reimbursable\"]"))

        assertEquals("Internet", result.matchInfo?.billName)
        assertEquals("auto", result.matchInfo?.outcome)
        assertEquals("4.50", result.transaction.amount)
    }

    @Test
    fun `creating a transfer includes both accounts`() = runBlocking {
        server.enqueue(json("""{"transaction":$TRANSACTION_JSON,"match_info":null,"possible_duplicates":[]}"""))

        repository.createTransaction(
            TransactionDraft(
                txType = "transfer",
                amount = "100.00",
                txnDate = "2026-11-02",
                description = "Move to savings",
                accountId = "acc-1",
                transferAccountId = "acc-2",
            )
        )

        val body = server.takeRequest().body.readUtf8()
        assertTrue(body.contains("\"transfer_account_id\":\"acc-2\""))
        assertTrue(body.contains("\"tx_type\":\"transfer\""))
    }

    @Test
    fun `editing sends explicit nulls so fields can be cleared`() = runBlocking {
        server.enqueue(json(TRANSACTION_JSON))

        repository.updateTransaction(
            "txn-1",
            TransactionDraft(
                txType = "purchase",
                amount = "4.50",
                txnDate = "2026-11-02",
                description = "Coffee",
                accountId = "acc-1",
                merchant = "",
                categoryId = "",
                transferAccountId = "",
            ),
        )

        val request = server.takeRequest()
        assertEquals("PATCH", request.method)
        assertEquals("/api/v1/transactions/txn-1", request.path)
        val body = request.body.readUtf8()
        assertTrue(body.contains("\"category_id\":null"))
        assertTrue(body.contains("\"transfer_account_id\":null"))
        assertTrue(body.contains("\"merchant\":null"))
    }

    @Test
    fun `csv upload is multipart, streamed and reports progress`() = runBlocking {
        server.enqueue(json(UPLOAD_RESPONSE_JSON))
        val csv = "Date,Description,Amount\n2026-11-01,Coffee,-4.50\n"
        val progress = mutableListOf<Float>()

        val response = repository.uploadCsv(
            CsvUpload.fromBytes("sample.csv", csv.toByteArray()),
            accountId = "acc-1",
        ) { progress.add(it) }

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/v1/imports", request.path)
        assertEquals("Bearer test-token", request.getHeader("Authorization"))
        val body = request.body.readUtf8()
        assertTrue(body.contains("name=\"account_id\""))
        assertTrue(body.contains("acc-1"))
        assertTrue(body.contains("name=\"file\"; filename=\"sample.csv\""))
        assertTrue(body.contains("Coffee"))
        assertTrue(progress.isNotEmpty())
        assertEquals(1f, progress.last(), 0.001f)

        assertEquals("sample.csv", response.import.filename)
        assertEquals(1, response.preview?.summary?.ready)
        assertEquals(1, response.preview?.summary?.duplicates)
        assertEquals("Date", response.preview?.mapping?.get("date"))
    }

    @Test
    fun `commit result carries bill match counts`() = runBlocking {
        server.enqueue(json(COMMIT_RESULT_JSON))

        val result = repository.commitImport("imp-1", mapOf("date" to "Date", "description" to "Description", "amount" to "Amount"))

        assertEquals(1, result.imported)
        assertEquals(1, result.duplicates)
        assertEquals(1, result.autoMatched)
        assertEquals(0, result.suggestedMatches)
        assertEquals(1, result.matchedBills)
    }

    @Test
    fun `backend validation messages are surfaced`() = runBlocking {
        server.enqueue(
            json(
                """{"detail":"Please check the highlighted fields.",
                    "errors":[{"loc":["body","amount"],"msg":"Amount must be greater than 0.","type":"value_error"}]}""",
                status = 422,
            )
        )

        val error = runCatching {
            repository.createTransaction(
                TransactionDraft(amount = "0", description = "Zero", accountId = "acc-1")
            )
        }.exceptionOrNull()

        assertTrue(error is ApiException)
        assertTrue(error!!.message!!.contains("Amount must be greater than 0."))
        assertEquals(422, (error as ApiException).status)
    }

    @Test
    fun `profile and accounts parse from the shared api`() = runBlocking {
        server.enqueue(
            json(
                """{"user":{"id":"u1","email":"demo@example.com","display_name":"Demo","timezone":"UTC","currency":"USD","is_demo":true},
                    "preferences":{"minimum_balance_buffer":"0.00","safe_to_spend_horizon_days":14,"include_pending_debits":true,"theme":"system"}}"""
            )
        )
        server.enqueue(json(ACCOUNTS_JSON))

        val profile = repository.profile()
        val accounts = repository.accounts()

        assertTrue(profile.user.isDemo)
        assertEquals(2, accounts.accounts.size)
        assertEquals("Checking", accounts.accounts.first().name)
    }
}
