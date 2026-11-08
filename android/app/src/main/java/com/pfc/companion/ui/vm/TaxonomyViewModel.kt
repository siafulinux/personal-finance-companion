package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Category
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.MerchantAlias
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Categories and merchant aliases.
 *
 * Both are matching inputs: a category decides where spending lands, an alias says
 * a statement descriptor belongs to a known merchant. Neither changes a past
 * classification by itself.
 */
class TaxonomyViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _categories = MutableStateFlow<List<Category>>(emptyList())
    val categories: StateFlow<List<Category>> = _categories.asStateFlow()

    private val _aliases = MutableStateFlow<List<MerchantAlias>>(emptyList())
    val aliases: StateFlow<List<MerchantAlias>> = _aliases.asStateFlow()

    private val _loading = MutableStateFlow(true)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            runCatching {
                coroutineScope {
                    val categories = async { repository.allCategories() }
                    val aliases = async { repository.merchantAliases() }
                    categories.await() to aliases.await()
                }
            }
                .onSuccess { (categories, aliases) ->
                    _categories.value = categories
                    _aliases.value = aliases
                    _error.value = null
                }
                .onFailure { _error.value = it.message ?: "Could not load categories." }
            _loading.value = false
        }
    }

    private fun run(action: suspend () -> Unit, failure: String) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            runCatching { action() }
                .onSuccess { refresh() }
                .onFailure { _error.value = it.message ?: failure }
            _busy.value = false
        }
    }

    fun createCategory(name: String, color: String) {
        if (name.isBlank()) {
            _error.value = "Give the category a name."
            return
        }
        run({ repository.createCategory(name, color) }, "Could not add that category.")
    }

    fun archiveCategory(id: String) =
        run({ repository.archiveCategory(id) }, "Could not archive that category.")

    fun deleteCategory(id: String) =
        run({ repository.deleteCategory(id) }, "Could not delete that category.")

    fun createAlias(alias: String, canonicalMerchant: String) {
        if (alias.isBlank() || canonicalMerchant.isBlank()) {
            _error.value = "Both the statement text and the merchant are needed."
            return
        }
        run({ repository.createAlias(alias, canonicalMerchant) }, "Could not add that alias.")
    }

    fun deleteAlias(id: String) =
        run({ repository.deleteAlias(id) }, "Could not remove that alias.")
}
