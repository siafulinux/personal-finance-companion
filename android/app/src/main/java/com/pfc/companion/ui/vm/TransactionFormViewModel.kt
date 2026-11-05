package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Account
import com.pfc.companion.data.Category
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.TransactionDraft
import com.pfc.companion.data.TransactionCreateResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TransactionFormState(
    val draft: TransactionDraft = TransactionDraft(),
    val accounts: List<Account> = emptyList(),
    val categories: List<Category> = emptyList(),
    val editing: Boolean = false,
    val loading: Boolean = true,
    val saving: Boolean = false,
    val error: String? = null,
)

class TransactionFormViewModel(
    private val repository: FinanceRepository,
    private val transactionId: String? = null,
) : ViewModel() {
    private val _state = MutableStateFlow(TransactionFormState(editing = transactionId != null))
    val state: StateFlow<TransactionFormState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            runCatching {
                // Sequential on purpose: a deterministic request order keeps tests reliable
                // and the three small calls cost little.
                val accounts = repository.accounts().accounts
                val categories = repository.categories()
                val transaction = transactionId?.let { id -> repository.transaction(id) }
                Triple(accounts, categories, transaction)
            }.onSuccess { (accounts, categories, transaction) ->
                val active = accounts.filterNot { it.isArchived }
                val draft = transaction?.let(TransactionDraft::from)
                    ?: TransactionDraft(accountId = active.firstOrNull()?.id.orEmpty())
                _state.update {
                    it.copy(
                        accounts = active,
                        categories = categories,
                        draft = draft,
                        editing = transaction != null,
                        loading = false,
                        error = null,
                    )
                }
            }.onFailure { err ->
                _state.update {
                    it.copy(loading = false, error = err.message ?: "Could not load the form.")
                }
            }
        }
    }

    fun update(transform: (TransactionDraft) -> TransactionDraft) {
        _state.update { current ->
            val next = transform(current.draft)
            // Clearing the destination when the source changes avoids an invalid pair.
            val adjusted = if (next.transferAccountId == next.accountId) {
                next.copy(transferAccountId = "")
            } else {
                next
            }
            current.copy(draft = adjusted, error = null)
        }
    }

    fun submit(onSaved: (String) -> Unit) {
        val current = _state.value
        if (current.saving) return
        val activeIds = current.accounts.map { it.id }.toSet()
        val validation = current.draft.validate(activeIds)
        if (validation != null) {
            _state.update { it.copy(error = validation) }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(saving = true, error = null) }
            runCatching {
                if (current.editing && transactionId != null) {
                    repository.updateTransaction(transactionId, current.draft)
                    null
                } else {
                    repository.createTransaction(current.draft)
                }
            }.onSuccess { response ->
                _state.update { it.copy(saving = false) }
                onSaved(messageFor(response, current.editing))
            }.onFailure { err ->
                _state.update {
                    it.copy(saving = false, error = err.message ?: "Could not save the transaction.")
                }
            }
        }
    }

    private fun messageFor(response: TransactionCreateResponse?, editing: Boolean): String {
        if (editing || response == null) return "Transaction updated."
        val match = response.matchInfo
        val duplicate = response.possibleDuplicates.firstOrNull()
        return when {
            match?.outcome == "auto" && match.billName != null ->
                "Saved. Matched the ${match.billName} bill."
            match?.outcome == "auto" -> "Saved. A bill payment was matched."
            match?.outcome == "suggest" && match.ambiguous ->
                "Saved. An ambiguous bill match is waiting for review under Bills."
            match?.outcome == "suggest" ->
                "Saved. A possible bill match is waiting for review under Bills."
            duplicate != null ->
                "Saved. There is a similar transaction (${duplicate.description}) on ${duplicate.txnDate}."
            else -> "Transaction saved."
        }
    }
}
