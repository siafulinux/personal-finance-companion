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

/**
 * The password form's progress. [saved] means the server accepted the change and
 * every other device was signed out; [error] is a message shown as it came back.
 */
data class PasswordFormState(
    val busy: Boolean = false,
    val error: String? = null,
    val saved: Boolean = false,
)

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

    private val _password = MutableStateFlow(PasswordFormState())
    val password: StateFlow<PasswordFormState> = _password.asStateFlow()

    /**
     * Checks only what a form can know — that both new entries are present and
     * equal. Whether the current password is right, and whether the new one meets
     * policy, is the server's answer and is shown unchanged.
     */
    fun changePassword(current: String, newPassword: String, confirm: String) {
        if (_password.value.busy) return
        if (current.isBlank() || newPassword.isBlank()) {
            _password.value = PasswordFormState(error = "Enter your current and new password.")
            return
        }
        if (newPassword != confirm) {
            _password.value = PasswordFormState(error = "The new passwords do not match.")
            return
        }
        _password.value = PasswordFormState(busy = true)
        viewModelScope.launch {
            runCatching { repository.changePassword(current, newPassword) }
                .onSuccess { _password.value = PasswordFormState(saved = true) }
                .onFailure {
                    _password.value = PasswordFormState(
                        error = it.message ?: "Unable to change your password.",
                    )
                }
        }
    }

    /** A message belongs to the attempt that produced it, not to the next edit. */
    fun clearPasswordMessage() {
        if (!_password.value.busy) _password.value = PasswordFormState()
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
