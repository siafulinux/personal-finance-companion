package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Account
import com.pfc.companion.data.BillDraft
import com.pfc.companion.data.Category
import com.pfc.companion.data.FinanceRepository
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class BillFormState(
    val loading: Boolean = true,
    val draft: BillDraft = BillDraft(),
    val accounts: List<Account> = emptyList(),
    val categories: List<Category> = emptyList(),
    val editing: Boolean = false,
    val saving: Boolean = false,
    val error: String? = null,
    /** The form could not be prepared at all, so it must not be shown half-filled. */
    val loadFailed: Boolean = false,
)

/**
 * Adds a bill or edits an existing one.
 *
 * Editing loads the bill from the server rather than relying on the list row, so
 * fields the list does not show (notes, minimum amount, account) start from what
 * is actually stored instead of being silently reset to defaults.
 */
class BillFormViewModel(
    private val repository: FinanceRepository,
    private val billId: String?,
) : ViewModel() {
    private val _state = MutableStateFlow(BillFormState())
    val state: StateFlow<BillFormState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null, loadFailed = false)
            runCatching {
                coroutineScope {
                    val accounts = async { repository.accounts() }
                    val categories = async { repository.categories() }
                    val bill = billId?.let { async { repository.bill(it) } }
                    val existing = bill?.await()
                    BillFormState(
                        loading = false,
                        draft = existing?.let(BillDraft::from) ?: BillDraft(),
                        accounts = accounts.await().accounts,
                        categories = categories.await(),
                        editing = existing != null,
                    )
                }
            }
                .onSuccess { _state.value = it }
                .onFailure {
                    _state.value = BillFormState(
                        loading = false,
                        editing = billId != null,
                        error = it.message ?: "Could not load this bill.",
                        loadFailed = true,
                    )
                }
        }
    }

    fun update(transform: (BillDraft) -> BillDraft) {
        _state.value = _state.value.copy(draft = transform(_state.value.draft), error = null)
    }

    fun submit(onSaved: (String) -> Unit) {
        val current = _state.value
        if (current.saving) return
        val invalid = current.draft.validate()
        if (invalid != null) {
            _state.value = current.copy(error = invalid)
            return
        }
        _state.value = current.copy(saving = true, error = null)
        viewModelScope.launch {
            runCatching {
                if (billId == null) {
                    repository.createBill(current.draft)
                } else {
                    repository.updateBill(billId, current.draft)
                }
            }
                .onSuccess { saved ->
                    _state.value = _state.value.copy(saving = false)
                    onSaved(
                        if (billId == null) "Added ${saved.name}." else "Saved ${saved.name}."
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        saving = false,
                        error = it.message ?: "Could not save this bill.",
                    )
                }
        }
    }

    /** Deleting is offered from the form so a mistaken bill can be removed where it is found. */
    fun delete(onDeleted: (String) -> Unit) {
        val id = billId ?: return
        if (_state.value.saving) return
        _state.value = _state.value.copy(saving = true, error = null)
        viewModelScope.launch {
            runCatching { repository.deleteBill(id) }
                .onSuccess {
                    _state.value = _state.value.copy(saving = false)
                    onDeleted("Bill deleted.")
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        saving = false,
                        error = it.message ?: "Could not delete this bill.",
                    )
                }
        }
    }
}
