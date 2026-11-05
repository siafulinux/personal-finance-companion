package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Bill
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.MatchSuggestionGroup
import com.pfc.companion.data.Occurrence
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class BillsData(
    val bills: List<Bill>,
    val upcoming: List<Occurrence>,
    val suggestions: List<MatchSuggestionGroup> = emptyList(),
)

class BillsViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<BillsData>>(UiState.Loading)
    val state: StateFlow<UiState<BillsData>> = _state.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            if (_state.value !is UiState.Ready) _state.value = UiState.Loading
            runCatching {
                coroutineScope {
                    val bills = async { repository.bills() }
                    val occurrences = async { repository.upcomingOccurrences(days = 60) }
                    val suggestions = async { repository.matchSuggestions() }
                    BillsData(
                        bills = bills.await().items,
                        upcoming = occurrences.await()
                            .filter { it.status != "paid" && it.status != "skipped" }
                            .sortedBy { it.dueDate },
                        suggestions = suggestions.await(),
                    )
                }
            }
                .onSuccess { _state.value = UiState.Ready(it) }
                .onFailure { _state.value = UiState.Failed(it.message ?: "Could not load bills.") }
        }
    }

    fun markPaid(occurrenceId: String) {
        viewModelScope.launch {
            _error.value = null
            runCatching { repository.markBillPaid(occurrenceId) }
                .onSuccess { refresh() }
                .onFailure { _error.value = it.message ?: "Could not mark that bill paid." }
        }
    }

    fun confirmMatch(matchId: String) {
        viewModelScope.launch {
            _error.value = null
            runCatching { repository.confirmMatch(matchId) }
                .onSuccess { refresh() }
                .onFailure { _error.value = it.message ?: "Could not confirm that match." }
        }
    }

    fun rejectMatch(matchId: String) {
        viewModelScope.launch {
            _error.value = null
            runCatching { repository.rejectMatch(matchId) }
                .onSuccess { refresh() }
                .onFailure { _error.value = it.message ?: "Could not reject that match." }
        }
    }
}
