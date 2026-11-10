package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.SavingsSummary
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

class SavingsViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<SavingsSummary>>(UiState.Loading)
    val state: StateFlow<UiState<SavingsSummary>> = _state.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            if (_state.value !is UiState.Ready) _state.value = UiState.Loading
            runCatching { repository.savings() }
                .onSuccess { _state.value = UiState.Ready(it) }
                .onFailure { _state.value = UiState.Failed(it.message ?: "Could not load your savings goals.") }
        }
    }

    fun save(goalId: String?, body: JsonObject, onSaved: (String) -> Unit) {
        submit(onSaved) {
            if (goalId == null) repository.createSavingsGoal(body) else repository.updateSavingsGoal(goalId, body)
            if (goalId == null) "Goal added." else "Goal updated."
        }
    }

    fun contribute(goalId: String, amount: String, on: String?, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.contributeToGoal(goalId, amount, on)
            "Contribution recorded."
        }
    }

    fun delete(goalId: String, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.deleteSavingsGoal(goalId)
            "Goal removed."
        }
    }

    private fun submit(onSaved: (String) -> Unit, block: suspend () -> String) {
        viewModelScope.launch {
            _busy.value = true
            _error.value = null
            runCatching { block() }
                .onSuccess {
                    _busy.value = false
                    refresh()
                    onSaved(it)
                }
                .onFailure {
                    _busy.value = false
                    _error.value = it.message ?: "That did not save."
                }
        }
    }
}
