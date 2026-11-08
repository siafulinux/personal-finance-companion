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
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import java.util.concurrent.CopyOnWriteArrayList
import org.junit.rules.TestWatcher
import org.junit.runner.Description
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.test.resetMain

class InMemorySession(initialBaseUrl: String) : SessionState {
    private val tokenState = MutableStateFlow<String?>("test-token")
    private val baseState = MutableStateFlow(initialBaseUrl)
    private val themeState = MutableStateFlow("system")
    private val serverState = MutableStateFlow(listOf(initialBaseUrl))

    /** Last address handed to [saveBaseUrl], so tests can assert what was selected. */
    var savedBaseUrl: String? = null
        private set

    override val tokenFlow: Flow<String?> = tokenState
    override val baseUrlFlow: Flow<String> = baseState
    override val themeFlow: Flow<String> = themeState
    override val savedServers: Flow<List<String>> = serverState

    override suspend fun token(): String? = tokenState.value
    override suspend fun baseUrl(): String = baseState.value
    override suspend fun theme(): String = themeState.value

    override suspend fun saveToken(value: String) {
        tokenState.value = value
    }

    override suspend fun clearToken() {
        tokenState.value = null
    }

    override suspend fun saveBaseUrl(value: String) {
        savedBaseUrl = value
        baseState.value = value
        rememberServer(value)
    }

    override suspend fun rememberServer(apiBaseUrl: String) {
        serverState.value = (listOf(apiBaseUrl) + serverState.value).distinct()
    }

    override suspend fun saveTheme(value: String) {
        themeState.value = value
    }
}

/**
 * Answers by path suffix instead of queue order.
 *
 * Screens load several endpoints at once, so a queue could hand the categories
 * response to the accounts request and make the test fail for the wrong reason.
 * Routes are checked in the order given, so a longer suffix must come first.
 */
class PathDispatcher(
    private val routes: List<Pair<String, String>>,
) : Dispatcher() {
    val requests: MutableList<RecordedRequest> = CopyOnWriteArrayList()

    override fun dispatch(request: RecordedRequest): MockResponse {
        requests += request
        val path = request.path.orEmpty().substringBefore('?')
        val body = routes.firstOrNull { (suffix, _) -> path.endsWith(suffix) }?.second
            ?: return MockResponse()
                .setResponseCode(404)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"No route for $path"}""")
        return MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody(body)
    }

    fun last(method: String): RecordedRequest? =
        requests.lastOrNull { it.method == method }
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

val BILL_JSON = """
{
  "id": "bill-1",
  "name": "Internet",
  "merchant": "Comcast",
  "expected_amount": "85.00",
  "minimum_amount": "80.00",
  "due_day": null,
  "anchor_date": "2026-11-15",
  "frequency": "monthly",
  "custom_interval_days": null,
  "account_id": null,
  "category_id": "cat-2",
  "notes": "Auto-pay",
  "is_essential": true,
  "reserve_in_safe_to_spend": true,
  "is_active": true,
  "auto_pay": false,
  "created_at": "2026-11-01T10:00:00Z",
  "next_due_date": "2026-11-15",
  "is_overdue": false
}
"""

val INCOME_SOURCE_JSON = """
{
  "id": "inc-1",
  "name": "Paycheck",
  "amount": "2400.00",
  "frequency": "biweekly",
  "next_payday": "2026-11-14",
  "account_id": null,
  "is_active": true,
  "notes": null
}
"""

val INCOME_SOURCES_JSON = """
[$INCOME_SOURCE_JSON]
"""

val BUDGET_JSON = """
{
  "id": "budget-1",
  "year": 2026,
  "month": 11,
  "start_date": "2026-11-01",
  "end_date": "2026-11-30",
  "name": null,
  "notes": null,
  "planned_income": "4800.00",
  "total_allocated": "300.00",
  "total_carryover": "0.00",
  "total_spent": "95.00",
  "total_remaining": "205.00",
  "percent_used": "31.67",
  "income_this_month": "2400.00",
  "unallocated": "4500.00",
  "created_from_wizard": false,
  "rows": [
    {
      "category_id": "cat-1",
      "category_name": "Groceries",
      "category_color": "#2f7a5d",
      "category_kind": "expense",
      "allocated": "300.00",
      "carryover_in": "0.00",
      "carryover_enabled": true,
      "spent": "95.00",
      "remaining": "205.00",
      "percent_used": "31.67",
      "upcoming_commitments": "0.00",
      "previous_month_spent": "0.00",
      "trend_percent": null,
      "transaction_count": 3
    }
  ]
}
"""
