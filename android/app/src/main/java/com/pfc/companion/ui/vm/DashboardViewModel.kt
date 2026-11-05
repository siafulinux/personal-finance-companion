package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Dashboard
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class DashboardViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<Dashboard>>(UiState.Loading)
    val state: StateFlow<UiState<Dashboard>> = _state.asStateFlow()

    private val _actionError = MutableStateFlow<String?>(null)
    val actionError: StateFlow<String?> = _actionError.asStateFlow()

    private val _busyOccurrence = MutableStateFlow<String?>(null)
    val busyOccurrence: StateFlow<String?> = _busyOccurrence.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val current = _state.value
            if (current !is UiState.Ready) _state.value = UiState.Loading
            runCatching { repository.dashboard() }
                .onSuccess { _state.value = UiState.Ready(it) }
                .onFailure { _state.value = UiState.Failed(it.message ?: "Could not load your dashboard.") }
        }
    }

    fun markPaid(occurrenceId: String) {
        viewModelScope.launch {
            _busyOccurrence.value = occurrenceId
            _actionError.value = null
            runCatching { repository.markBillPaid(occurrenceId) }
                .onSuccess {
                    _busyOccurrence.value = null
                    refresh()
                }
                .onFailure {
                    _busyOccurrence.value = null
                    _actionError.value = it.message ?: "Could not mark that bill paid."
                }
        }
    }
}
