package com.pfc.companion.ui.vm

import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.testing.BUDGET_JSON
import com.pfc.companion.testing.CATEGORIES_JSON
import com.pfc.companion.testing.MainDispatcherRule
import com.pfc.companion.testing.PathDispatcher
import com.pfc.companion.testing.awaitValue
import com.pfc.companion.testing.repositoryFor
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class BudgetsViewModelTest {
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
                "budgets/current" to BUDGET_JSON,
                "budgets/budget-1" to BUDGET_JSON,
                "categories" to CATEGORIES_JSON,
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

    private fun ready(viewModel: BudgetsViewModel) =
        viewModel.state.awaitValue { it is UiState.Ready } as UiState.Ready

    @Test
    fun `the month budget carries its id so it can be edited`() {
        val viewModel = BudgetsViewModel(repository)
        val budget = ready(viewModel).data
        assertEquals("budget-1", budget.id)
        assertEquals("4800.00", budget.plannedIncome)
        assertTrue(budget.rows.first().carryoverEnabled)
    }

    @Test
    fun `the editor seeds every funded category and adds unfunded ones`() {
        val viewModel = BudgetsViewModel(repository)
        ready(viewModel)

        viewModel.openEditor()
        val state = viewModel.editor.awaitValue { it.open && it.draft.allocations.size == 2 }

        assertEquals("4800.00", state.draft.plannedIncome)
        val groceries = state.draft.allocations.first { it.categoryId == "cat-1" }
        assertEquals("300.00", groceries.amount)
        assertTrue(groceries.carryover)
        assertEquals("Groceries", groceries.name)
        // cat-2 exists but was never funded: it must still be editable.
        assertEquals("0.00", state.draft.allocations.first { it.categoryId == "cat-2" }.amount)
    }

    @Test
    fun `saving sends the whole allocation list and drops zeroed categories`() {
        val viewModel = BudgetsViewModel(repository)
        ready(viewModel)
        viewModel.openEditor()
        viewModel.editor.awaitValue { it.open && it.draft.allocations.size == 2 }

        viewModel.updateDraft { it.withAmount("cat-1", "350.00") }
        viewModel.updateDraft { it.withAmount("cat-2", "60.00") }
        viewModel.updateDraft { it.copy(plannedIncome = "5000") }

        val message = awaitMessage { viewModel.save { text -> it.complete(text) } }
        assertEquals("Budget saved.", message)

        val patch = dispatcher.last("PATCH")!!
        assertTrue(patch.path!!.endsWith("/budgets/budget-1"))
        val body = patch.body.readUtf8()
        assertTrue(body.contains("\"category_id\":\"cat-1\""))
        assertTrue(body.contains("\"amount\":\"350.00\""))
        assertTrue(body.contains("\"category_id\":\"cat-2\""))
        assertTrue(body.contains("\"planned_income\":\"5000\""))
        assertFalse(viewModel.editor.value.open)
    }

    @Test
    fun `a zeroed category is removed from the request`() {
        val viewModel = BudgetsViewModel(repository)
        ready(viewModel)
        viewModel.openEditor()
        viewModel.editor.awaitValue { it.open && it.draft.allocations.size == 2 }

        viewModel.updateDraft { it.withAmount("cat-1", "0.00") }
        awaitMessage { viewModel.save { text -> it.complete(text) } }

        val body = dispatcher.last("PATCH")!!.body.readUtf8()
        assertFalse(body.contains("\"category_id\":\"cat-1\""))
    }

    @Test
    fun `a non-numeric limit never reaches the server`() {
        val viewModel = BudgetsViewModel(repository)
        ready(viewModel)
        viewModel.openEditor()
        // Wait for the category fill-in too, or its request shows up as an extra call.
        viewModel.editor.awaitValue { it.open && it.draft.allocations.size == 2 }
        val before = dispatcher.requests.size

        viewModel.updateDraft { it.withAmount("cat-1", "abc") }
        viewModel.save { }

        assertTrue(viewModel.editor.value.error != null)
        assertEquals(before, dispatcher.requests.size)
    }
}
