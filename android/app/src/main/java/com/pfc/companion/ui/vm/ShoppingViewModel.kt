package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.Category
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.ShoppingResult
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ShoppingViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _categories = MutableStateFlow<UiState<List<Category>>>(UiState.Loading)
    val categories: StateFlow<UiState<List<Category>>> = _categories.asStateFlow()

    private val _result = MutableStateFlow<ShoppingResult?>(null)
    val result: StateFlow<ShoppingResult?> = _result.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _checking = MutableStateFlow(false)
    val checking: StateFlow<Boolean> = _checking.asStateFlow()

    init {
        loadCategories()
    }

    fun loadCategories() {
        viewModelScope.launch {
            _categories.value = UiState.Loading
            runCatching { repository.categories() }
                .onSuccess { _categories.value = UiState.Ready(it) }
                .onFailure { _categories.value = UiState.Failed(it.message ?: "Could not load categories.") }
        }
    }

    fun check(storeName: String, categoryId: String, amount: String) {
        if (categoryId.isBlank()) {
            _error.value = "Choose a category first."
            return
        }
        viewModelScope.launch {
            _checking.value = true
            _error.value = null
            runCatching {
                repository.shoppingCheck(
                    storeName = storeName,
                    categoryId = categoryId,
                    amount = amount.takeIf { it.isNotBlank() },
                )
            }
                .onSuccess { _result.value = it }
                .onFailure { _error.value = it.message ?: "Could not run the check." }
            _checking.value = false
        }
    }
}
