package com.pfc.companion.ui.vm

import com.pfc.companion.data.CsvUpload
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.ACCOUNTS_JSON
import com.pfc.companion.testing.COMMIT_RESULT_JSON
import com.pfc.companion.testing.IMPORT_RECORDS_JSON
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.UPLOAD_RESPONSE_JSON
import com.pfc.companion.testing.awaitValue
import com.pfc.companion.testing.repositoryFor
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class ImportViewModelTest {
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

    private fun upload(viewModel: ImportViewModel) {
        viewModel.state.awaitValue { !it.accountsLoading && it.accounts.isNotEmpty() }
        server.enqueue(json(UPLOAD_RESPONSE_JSON))
        viewModel.upload(CsvUpload.fromBytes("sample.csv", "Date,Description,Amount\n2026-11-01,Coffee,-4.50\n".toByteArray()))
        viewModel.state.awaitValue { it.preview != null || it.error != null }
    }

    @Test
    fun `mapping readiness requires date, description and an amount source`() {
        assertFalse(mappingReady(emptyMap()))
        assertFalse(mappingReady(mapOf("date" to "Date", "description" to "Description")))
        assertTrue(
            mappingReady(mapOf("date" to "Date", "description" to "Description", "amount" to "Amount"))
        )
        assertTrue(
            mappingReady(mapOf("date" to "Date", "description" to "Description", "debit" to "Out"))
        )
    }

    @Test
    fun `upload shows preview then commit returns counts and rejected rows`() {
        server.enqueue(json(ACCOUNTS_JSON))
        val viewModel = ImportViewModel(repository)
        upload(viewModel)

        val previewState = viewModel.state.value
        assertEquals("Date", previewState.mapping["date"])
        assertEquals(3, previewState.headers.size)
        assertEquals("acc-1", previewState.preview?.accountId)
        assertEquals(1, previewState.preview?.summary?.ready)
        assertEquals(1, previewState.preview?.summary?.duplicates)

        server.enqueue(json(COMMIT_RESULT_JSON))
        server.enqueue(json(IMPORT_RECORDS_JSON))
        viewModel.commit()

        val resultState = viewModel.state.awaitValue { it.result != null }
        val result = resultState.result!!
        assertEquals(1, result.imported)
        assertEquals(1, result.duplicates)
        assertEquals(1, result.autoMatched)

        val withFailures = viewModel.state.awaitValue { it.failedRecords.isNotEmpty() }
        assertEquals("Invalid date", withFailures.failedRecords.first().reason)
    }

    @Test
    fun `a failed commit keeps the preview and can be retried safely`() {
        server.enqueue(json(ACCOUNTS_JSON))
        val viewModel = ImportViewModel(repository)
        upload(viewModel)

        server.enqueue(json("""{"detail":"Temporary import failure"}""", status = 500))
        viewModel.commit()

        val failed = viewModel.state.awaitValue { it.error != null }
        assertNull(failed.result)
        assertNotNull(failed.preview)

        server.enqueue(json(COMMIT_RESULT_JSON))
        server.enqueue(json(IMPORT_RECORDS_JSON))
        viewModel.commit()

        val retried = viewModel.state.awaitValue { it.result != null }
        assertEquals(1, retried.result?.imported)
        assertNull(retried.error)
    }

    @Test
    fun `a rejected csv upload shows the server error and keeps no file`() {
        server.enqueue(json(ACCOUNTS_JSON))
        val viewModel = ImportViewModel(repository)
        viewModel.state.awaitValue { !it.accountsLoading && it.accounts.isNotEmpty() }

        server.enqueue(
            json("""{"detail":"Could not parse the date on row 2."}""", status = 422)
        )
        viewModel.upload(
            CsvUpload.fromBytes(
                "broken.csv",
                "Date,Description,Amount\nnot-a-date,Coffee,-4.50\n".toByteArray(),
            )
        )

        val state = viewModel.state.awaitValue { it.error != null }
        assertNull(state.upload)
        assertNull(state.preview)
        assertTrue(state.error!!.contains("Could not parse the date"))
        assertFalse(state.uploading)
    }

    @Test
    fun `reset clears the file but keeps accounts`() {
        server.enqueue(json(ACCOUNTS_JSON))
        val viewModel = ImportViewModel(repository)
        upload(viewModel)

        viewModel.reset()

        val state = viewModel.state.value
        assertNull(state.upload)
        assertNull(state.preview)
        assertEquals(2, state.accounts.size)
        assertTrue(state.selectedAccountId.isNotEmpty())
    }
}
