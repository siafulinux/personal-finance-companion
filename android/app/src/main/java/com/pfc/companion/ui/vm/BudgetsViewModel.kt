package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.BudgetAllocationDraft
import com.pfc.companion.data.BudgetDraft
import com.pfc.companion.data.BudgetSummary
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Progress of the allocation editor for the month currently on screen. */
data class BudgetEditorState(
    val open: Boolean = false,
    val draft: BudgetDraft = BudgetDraft(),
    val saving: Boolean = false,
    val error: String? = null,
)

class BudgetsViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<BudgetSummary>>(UiState.Loading)
    val state: StateFlow<UiState<BudgetSummary>> = _state.asStateFlow()

    private val _editor = MutableStateFlow(BudgetEditorState())
    val editor: StateFlow<BudgetEditorState> = _editor.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            if (_state.value !is UiState.Ready) _state.value = UiState.Loading
            runCatching { repository.currentBudget() }
                .onSuccess { _state.value = UiState.Ready(it) }
                .onFailure { _state.value = UiState.Failed(it.message ?: "Could not load this month's budget.") }
        }
    }

    /**
     * Opens the editor seeded from the budget on screen, then fills in categories
     * that have no allocation yet so a new limit can be set in the same pass.
     */
    fun openEditor() {
        val budget = (_state.value as? UiState.Ready)?.data ?: return
        val seeded = BudgetDraft(
            plannedIncome = budget.plannedIncome.orEmpty(),
            allocations = budget.rows.map {
                BudgetAllocationDraft(
                    categoryId = it.categoryId,
                    amount = it.allocated,
                    carryover = it.carryoverEnabled,
                    name = it.categoryName,
                )
            },
        )
        _editor.value = BudgetEditorState(open = true, draft = seeded)
        viewModelScope.launch {
            runCatching { repository.categories() }
                .onSuccess { categories ->
                    val draft = _editor.value.draft
                    val missing = categories
                        .filter { category -> draft.allocations.none { it.categoryId == category.id } }
                        .map {
                            BudgetAllocationDraft(
                                categoryId = it.id,
                                amount = "0.00",
                                carryover = false,
                                name = it.name,
                            )
                        }
                    if (missing.isNotEmpty() && _editor.value.open) {
                        _editor.value = _editor.value.copy(
                            draft = _editor.value.draft.copy(
                                allocations = _editor.value.draft.allocations + missing,
                            ),
                        )
                    }
                }
        }
    }

    fun closeEditor() {
        _editor.value = BudgetEditorState()
    }

    fun updateDraft(transform: (BudgetDraft) -> BudgetDraft) {
        _editor.value = _editor.value.copy(draft = transform(_editor.value.draft), error = null)
    }

    fun save(onSaved: (String) -> Unit) {
        val current = _editor.value
        val budget = (_state.value as? UiState.Ready)?.data ?: return
        if (current.saving) return
        val invalid = current.draft.validate()
        if (invalid != null) {
            _editor.value = current.copy(error = invalid)
            return
        }
        _editor.value = current.copy(saving = true, error = null)
        viewModelScope.launch {
            runCatching { repository.updateBudget(budget.id, current.draft) }
                .onSuccess {
                    _state.value = UiState.Ready(it)
                    _editor.value = BudgetEditorState()
                    onSaved("Budget saved.")
                }
                .onFailure {
                    _editor.value = _editor.value.copy(
                        saving = false,
                        error = it.message ?: "Could not save the budget.",
                    )
                }
        }
    }
}
