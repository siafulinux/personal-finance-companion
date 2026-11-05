package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Account
import com.pfc.companion.data.CsvUpload
import com.pfc.companion.data.CsvUploadResponse
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.ImportCommitResult
import com.pfc.companion.data.ImportPreview
import com.pfc.companion.data.ImportRecord
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MappingField(val key: String, val label: String, val hint: String? = null)

val importMappingFields = listOf(
    MappingField("date", "Date", "Required"),
    MappingField("description", "Description", "Required"),
    MappingField("amount", "Amount", "Signed amount"),
    MappingField("debit", "Debit (money out)"),
    MappingField("credit", "Credit (money in)"),
    MappingField("merchant", "Merchant"),
    MappingField("type", "Transaction type"),
    MappingField("category", "Category name"),
    MappingField("external_id", "External ID"),
)

/** A preview needs at least a date, a description and one amount source. */
fun mappingReady(mapping: Map<String, String?>): Boolean =
    !mapping["date"].isNullOrBlank() &&
        !mapping["description"].isNullOrBlank() &&
        listOf("amount", "debit", "credit").any { !mapping[it].isNullOrBlank() }

data class ImportState(
    val accounts: List<Account> = emptyList(),
    val selectedAccountId: String = "",
    val accountsLoading: Boolean = true,
    val upload: CsvUploadResponse? = null,
    val headers: List<String> = emptyList(),
    val mapping: Map<String, String?> = emptyMap(),
    val preview: ImportPreview? = null,
    val uploading: Boolean = false,
    val uploadProgress: Float? = null,
    val busy: Boolean = false,
    val error: String? = null,
    val result: ImportCommitResult? = null,
    val failedRecords: List<ImportRecord> = emptyList(),
)

class ImportViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _state = MutableStateFlow(ImportState())
    val state: StateFlow<ImportState> = _state.asStateFlow()

    init {
        loadAccounts()
    }

    fun loadAccounts() {
        viewModelScope.launch {
            _state.update { it.copy(accountsLoading = true, error = null) }
            runCatching { repository.accounts().accounts.filterNot { account -> account.isArchived } }
                .onSuccess { accounts ->
                    _state.update { current ->
                        current.copy(
                            accounts = accounts,
                            selectedAccountId = current.selectedAccountId.ifBlank {
                                accounts.firstOrNull()?.id.orEmpty()
                            },
                            accountsLoading = false,
                        )
                    }
                }
                .onFailure {
                    _state.update { current ->
                        current.copy(
                            accountsLoading = false,
                            error = it.message ?: "Could not load accounts.",
                        )
                    }
                }
        }
    }

    fun selectAccount(accountId: String) {
        _state.update { it.copy(selectedAccountId = accountId, error = null) }
    }

    fun upload(file: CsvUpload) {
        val current = _state.value
        if (current.selectedAccountId.isBlank()) {
            _state.update { it.copy(error = "Choose the account this CSV belongs to first.") }
            return
        }
        viewModelScope.launch {
            _state.update {
                it.copy(uploading = true, uploadProgress = null, error = null, result = null)
            }
            runCatching {
                repository.uploadCsv(file, current.selectedAccountId) { fraction ->
                    _state.update { it.copy(uploadProgress = fraction) }
                }
            }.onSuccess { response ->
                _state.update {
                    it.copy(
                        uploading = false,
                        uploadProgress = null,
                        upload = response,
                        headers = response.preview?.headers ?: response.headers,
                        mapping = response.preview?.mapping ?: response.suggestedMapping,
                        preview = response.preview,
                        error = response.previewError,
                    )
                }
            }.onFailure { err ->
                _state.update {
                    it.copy(
                        uploading = false,
                        uploadProgress = null,
                        error = err.message ?: "Could not upload that file.",
                    )
                }
            }
        }
    }

    fun updateMapping(field: String, header: String?) {
        _state.update { it.copy(mapping = it.mapping + (field to header), error = null) }
    }

    fun refreshPreview() {
        val current = _state.value
        val upload = current.upload ?: return
        if (!mappingReady(current.mapping)) {
            _state.update { it.copy(error = "Map a date, a description and an amount to continue.") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            runCatching { repository.previewImport(upload.import.id, current.mapping) }
                .onSuccess { preview ->
                    _state.update {
                        it.copy(
                            busy = false,
                            preview = preview,
                            headers = preview.headers.ifEmpty { it.headers },
                            mapping = preview.mapping,
                        )
                    }
                }
                .onFailure { err ->
                    _state.update {
                        it.copy(busy = false, preview = null, error = err.message ?: "Could not preview this mapping.")
                    }
                }
        }
    }

    fun commit() {
        val current = _state.value
        val upload = current.upload ?: return
        val preview = current.preview
        if (preview == null || preview.summary.ready <= 0) {
            _state.update { it.copy(error = "There is nothing ready to import yet.") }
            return
        }
        if (current.busy) return
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            runCatching { repository.commitImport(upload.import.id, current.mapping) }
                .onSuccess { result ->
                    _state.update { it.copy(busy = false, result = result) }
                    val failed = runCatching { repository.importRecords(upload.import.id) }
                        .getOrDefault(emptyList())
                        .filter { it.status == "rejected" }
                    _state.update { it.copy(failedRecords = failed) }
                }
                .onFailure { err ->
                    _state.update {
                        it.copy(busy = false, error = err.message ?: "Import failed. Nothing was committed.")
                    }
                }
        }
    }

    fun reset() {
        _state.update {
            ImportState(
                accounts = it.accounts,
                selectedAccountId = it.selectedAccountId,
                accountsLoading = false,
            )
        }
    }
}
