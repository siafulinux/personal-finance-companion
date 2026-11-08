package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.IncomeDraft
import com.pfc.companion.data.IncomeSource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** The add/edit sheet for one income source, including its next payday. */
data class IncomeEditorState(
    val open: Boolean = false,
    val editingId: String? = null,
    val draft: IncomeDraft = IncomeDraft(),
    val saving: Boolean = false,
    val error: String? = null,
)

/**
 * Income sources, which hold the payday first-run setup asks for.
 *
 * Editing here changes when Safe-to-Spend's horizon ends, so the list is reloaded
 * from the server after every change rather than patched locally.
 */
class IncomeViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _sources = MutableStateFlow<List<IncomeSource>>(emptyList())
    val sources: StateFlow<List<IncomeSource>> = _sources.asStateFlow()

    private val _loading = MutableStateFlow(true)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _editor = MutableStateFlow(IncomeEditorState())
    val editor: StateFlow<IncomeEditorState> = _editor.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            runCatching { repository.incomeSources() }
                .onSuccess {
                    _sources.value = it
                    _error.value = null
                }
                .onFailure { _error.value = it.message ?: "Could not load your income." }
            _loading.value = false
        }
    }

    fun startAdd() {
        _editor.value = IncomeEditorState(open = true)
    }

    fun startEdit(source: IncomeSource) {
        _editor.value = IncomeEditorState(
            open = true,
            editingId = source.id,
            draft = IncomeDraft.from(source),
        )
    }

    fun updateDraft(transform: (IncomeDraft) -> IncomeDraft) {
        _editor.value = _editor.value.copy(draft = transform(_editor.value.draft), error = null)
    }

    fun closeEditor() {
        _editor.value = IncomeEditorState()
    }

    fun save(onSaved: (String) -> Unit) {
        val current = _editor.value
        if (current.saving) return
        val invalid = current.draft.validate()
        if (invalid != null) {
            _editor.value = current.copy(error = invalid)
            return
        }
        _editor.value = current.copy(saving = true, error = null)
        viewModelScope.launch {
            runCatching {
                if (current.editingId == null) {
                    repository.createIncome(current.draft)
                } else {
                    repository.updateIncome(current.editingId, current.draft)
                }
            }
                .onSuccess {
                    _editor.value = IncomeEditorState()
                    refresh()
                    onSaved(if (current.editingId == null) "Income added." else "Income updated.")
                }
                .onFailure {
                    _editor.value = _editor.value.copy(
                        saving = false,
                        error = it.message ?: "Could not save that income source.",
                    )
                }
        }
    }

    fun remove(id: String, onDone: (String) -> Unit) {
        viewModelScope.launch {
            runCatching { repository.deleteIncome(id) }
                .onSuccess {
                    refresh()
                    onDone("Income removed.")
                }
                .onFailure { _error.value = it.message ?: "Could not remove that income source." }
        }
    }
}
