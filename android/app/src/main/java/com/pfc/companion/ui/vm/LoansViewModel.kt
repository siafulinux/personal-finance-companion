package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.LoanSummary
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

class LoansViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<LoanSummary>>(UiState.Loading)
    val state: StateFlow<UiState<LoanSummary>> = _state.asStateFlow()

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
            runCatching { repository.loans() }
                .onSuccess { _state.value = UiState.Ready(it) }
                .onFailure { _state.value = UiState.Failed(it.message ?: "Could not load your loans.") }
        }
    }

    fun save(loanId: String?, body: JsonObject, onSaved: (String) -> Unit) {
        submit(onSaved) {
            if (loanId == null) repository.createLoan(body) else repository.updateLoan(loanId, body)
            if (loanId == null) "Loan added." else "Loan updated."
        }
    }

    fun recordPayment(loanId: String, body: JsonObject, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.addLoanPayment(loanId, body)
            "Payment recorded."
        }
    }

    fun delete(loanId: String, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.deleteLoan(loanId)
            "Loan removed."
        }
    }

    /** A suggested repayment becomes a real one only when the user says so. */
    fun confirmLoanPayment(loanId: String, paymentId: String, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.confirmLoanPayment(loanId, paymentId)
            "Payment confirmed."
        }
    }

    fun rejectLoanPayment(loanId: String, paymentId: String, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.rejectLoanPayment(loanId, paymentId)
            "Suggestion dismissed. The balance is unchanged."
        }
    }

    /** A suggested bank transaction becomes a payment only when the user says so. */
    fun acceptSuggestion(loanId: String, transactionId: String, onSaved: (String) -> Unit) {
        submit(onSaved) {
            repository.acceptLoanSuggestion(loanId, transactionId)
            "Payment matched to the transaction."
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
