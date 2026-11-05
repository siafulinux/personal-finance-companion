package com.pfc.companion.testing

import com.pfc.companion.data.ApiClient
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.SessionState
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockWebServer
import org.junit.rules.TestWatcher
import org.junit.runner.Description
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.test.resetMain

class InMemorySession(initialBaseUrl: String) : SessionState {
    private val tokenState = MutableStateFlow<String?>("test-token")
    override val tokenFlow: Flow<String?> = tokenState
    override val baseUrlFlow: Flow<String> = MutableStateFlow(initialBaseUrl)
    override val themeFlow: Flow<String> = MutableStateFlow("system")

    override suspend fun token(): String? = tokenState.value
    override suspend fun baseUrl(): String = baseUrlFlow.first()
    override suspend fun theme(): String = "system"
    override suspend fun saveToken(value: String) {
        tokenState.value = value
    }

    override suspend fun clearToken() {
        tokenState.value = null
    }

    override suspend fun saveBaseUrl(value: String) = Unit
    override suspend fun saveTheme(value: String) = Unit
}

fun repositoryFor(server: MockWebServer): FinanceRepository {
    val session = InMemorySession(server.url("/api/v1/").toString())
    return FinanceRepository(ApiClient(session), session)
}

class MainDispatcherRule : TestWatcher() {
    override fun starting(description: Description) {
        Dispatchers.setMain(Dispatchers.Unconfined)
    }

    override fun finished(description: Description) {
        Dispatchers.resetMain()
    }
}

/** Waits for a StateFlow to satisfy a predicate using real time (network calls are real). */
fun <T> StateFlow<T>.awaitValue(
    timeoutMillis: Long = 5_000,
    predicate: (T) -> Boolean,
): T = runBlocking {
    withTimeout(timeoutMillis) { first(predicate) }
}

const val TRANSACTION_JSON = """
{
  "id": "txn-1",
  "account_id": "acc-1",
  "transfer_account_id": null,
  "description": "Coffee",
  "merchant": "Cafe",
  "amount": "4.50",
  "tx_type": "purchase",
  "status": "posted",
  "txn_date": "2026-11-02",
  "category_id": "cat-1",
  "notes": null,
  "tags": [],
  "source": "manual",
  "external_id": null,
  "import_id": null,
  "created_at": "2026-11-02T10:00:00Z",
  "account_name": "Checking",
  "transfer_account_name": null,
  "category_name": "Fast food",
  "category_color": "#b4552f"
}
"""

val ACCOUNTS_JSON = """
{
  "accounts": [
    {"id":"acc-1","name":"Checking","account_type":"checking","balance":"500.00","include_in_safe_to_spend":true,"is_archived":false},
    {"id":"acc-2","name":"Savings","account_type":"savings","balance":"900.00","include_in_safe_to_spend":false,"is_archived":false}
  ],
  "total_cash": "500.00",
  "total_debt": "0.00",
  "net_worth": "1400.00"
}
"""

val CATEGORIES_JSON = """
[
  {"id":"cat-1","name":"Fast food","kind":"expense","color":"#b4552f"},
  {"id":"cat-2","name":"Groceries","kind":"expense","color":"#2f7a5d"}
]
"""

val TRANSACTION_PAGE_JSON = """
{
  "items": [$TRANSACTION_JSON],
  "total": 1,
  "limit": 100,
  "offset": 0,
  "totals": {"income":"0.00","spending":"4.50","transfers":"0.00","refunds":"0.00"}
}
"""

val UPLOAD_RESPONSE_JSON = """
{
  "import": {"id":"imp-1","account_id":"acc-1","filename":"sample.csv","file_size":42,"status":"previewed","row_count":2,"created_at":"2026-11-02T10:00:00Z"},
  "headers": ["Date","Description","Amount"],
  "suggested_mapping": {"date":"Date","description":"Description","amount":"Amount"},
  "preview": {
    "import_id":"imp-1",
    "filename":"sample.csv",
    "account_id":"acc-1",
    "headers":["Date","Description","Amount"],
    "mapping":{"date":"Date","description":"Description","amount":"Amount"},
    "suggested_mapping":{"date":"Date","description":"Description","amount":"Amount"},
    "has_header":true,
    "delimiter":",",
    "rows":[
      {"row_number":1,"date":"2026-11-01","description":"Coffee","merchant":null,"amount":"4.50","signed_amount":"-4.50","suggested_type":"purchase","status":"ok","reason":null,"duplicate_of":null},
      {"row_number":2,"date":"2026-11-02","description":"Paycheck","merchant":null,"amount":"900.00","signed_amount":"900.00","suggested_type":"income","status":"duplicate","reason":"Already imported","duplicate_of":"txn-9"}
    ],
    "truncated": false,
    "summary": {"total_rows":2,"ready":1,"duplicates":1,"rejected":0,"ready_total":"4.50"}
  },
  "preview_error": null
}
"""

val COMMIT_RESULT_JSON = """
{
  "import_id":"imp-1",
  "already_committed":false,
  "imported":1,
  "duplicates":1,
  "rejected":0,
  "matched_bills":1,
  "auto_matched":1,
  "suggested_matches":0,
  "committed_at":"2026-11-02T10:05:00Z"
}
"""

val IMPORT_RECORDS_JSON = """
[
  {"id":"rec-1","row_number":3,"status":"rejected","reason":"Invalid date","transaction_id":null}
]
"""
