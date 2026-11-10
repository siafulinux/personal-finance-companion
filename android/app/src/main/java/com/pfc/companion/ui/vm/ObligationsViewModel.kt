package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.Obligations
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ObligationsViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<Obligations>>(UiState.Loading)
    val state: StateFlow<UiState<Obligations>> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            if (_state.value !is UiState.Ready) _state.value = UiState.Loading
            runCatching { repository.obligations() }
                .onSuccess { _state.value = UiState.Ready(it) }
                .onFailure { _state.value = UiState.Failed(it.message ?: "Could not load your obligations.") }
        }
    }
}
