package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.Profile
import com.pfc.companion.ui.components.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class SettingsViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _profile = MutableStateFlow<UiState<Profile>>(UiState.Loading)
    val profile: StateFlow<UiState<Profile>> = _profile.asStateFlow()

    val baseUrl: StateFlow<String> = repository.baseUrlFlow.stateIn(
        scope = viewModelScope,
        started = kotlinx.coroutines.flow.SharingStarted.WhileSubscribed(5_000),
        initialValue = "",
    )

    val theme: StateFlow<String> = repository.themeFlow.stateIn(
        scope = viewModelScope,
        started = kotlinx.coroutines.flow.SharingStarted.WhileSubscribed(5_000),
        initialValue = "system",
    )

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _profile.value = UiState.Loading
            runCatching { repository.profile() }
                .onSuccess { _profile.value = UiState.Ready(it) }
                .onFailure { _profile.value = UiState.Failed(it.message ?: "Could not load your profile.") }
        }
    }

    fun setTheme(value: String) {
        viewModelScope.launch {
            repository.saveTheme(value)
            _message.value = "Theme updated."
        }
    }

    fun clearMessage() {
        _message.value = null
    }
}
