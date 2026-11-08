package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.NotificationDraft
import com.pfc.companion.data.Profile
import com.pfc.companion.data.RulesDraft
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

/** Delete-account progress. [done] means the server has wiped the records. */
data class DeleteAccountState(
    val busy: Boolean = false,
    val error: String? = null,
    val done: Boolean = false,
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

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving.asStateFlow()

    private val _formError = MutableStateFlow<String?>(null)
    val formError: StateFlow<String?> = _formError.asStateFlow()

    private val _password = MutableStateFlow(PasswordFormState())
    val password: StateFlow<PasswordFormState> = _password.asStateFlow()

    private val _deletion = MutableStateFlow(DeleteAccountState())
    val deletion: StateFlow<DeleteAccountState> = _deletion.asStateFlow()

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

    private fun replaceProfile(transform: (Profile) -> Profile) {
        val current = _profile.value
        if (current is UiState.Ready) _profile.value = UiState.Ready(transform(current.data))
    }

    /** Display name and timezone — both were set during first-run setup and stay editable. */
    fun saveProfile(displayName: String, timezone: String) {
        if (_saving.value) return
        if (displayName.isBlank()) {
            _formError.value = "Your display name cannot be empty."
            return
        }
        _saving.value = true
        _formError.value = null
        _message.value = null
        viewModelScope.launch {
            runCatching { repository.updateProfile(displayName, timezone) }
                .onSuccess {
                    _profile.value = UiState.Ready(it)
                    _message.value = "Profile saved."
                }
                .onFailure { _formError.value = it.message ?: "Unable to save your profile." }
            _saving.value = false
        }
    }

    fun saveRules(draft: RulesDraft) {
        if (_saving.value) return
        val invalid = draft.validate()
        if (invalid != null) {
            _formError.value = invalid
            return
        }
        _saving.value = true
        _formError.value = null
        viewModelScope.launch {
            runCatching { repository.updatePreferences(draft.toJson()) }
                .onSuccess { preferences ->
                    replaceProfile { it.copy(preferences = preferences) }
                    _message.value = "Safe-to-Spend rules saved."
                }
                .onFailure { _formError.value = it.message ?: "Unable to save the rules." }
            _saving.value = false
        }
    }

    fun saveNotifications(draft: NotificationDraft, timezone: String) {
        if (_saving.value) return
        val invalid = draft.validate()
        if (invalid != null) {
            _formError.value = invalid
            return
        }
        _saving.value = true
        _formError.value = null
        viewModelScope.launch {
            runCatching { repository.updateNotifications(draft.toJson(timezone)) }
                .onSuccess { updated ->
                    replaceProfile { it.copy(notificationPreferences = updated) }
                    _message.value = "Notification settings saved."
                }
                .onFailure { _formError.value = it.message ?: "Unable to save notifications." }
            _saving.value = false
        }
    }

    /**
     * Handles the export to the caller, which owns writing and sharing the file.
     * Nothing is written to storage the app does not already own.
     */
    fun export(onReady: (String) -> Unit) {
        _saving.value = true
        _formError.value = null
        viewModelScope.launch {
            runCatching { repository.exportJson() }
                .onSuccess { onReady(it) }
                .onFailure { _formError.value = it.message ?: "Unable to export your data." }
            _saving.value = false
        }
    }

    fun deleteAccount(password: String, confirm: String) {
        if (_deletion.value.busy) return
        if (password.isBlank() || confirm != "DELETE") {
            _deletion.value = DeleteAccountState(
                error = "Enter your password and type DELETE to confirm.",
            )
            return
        }
        _deletion.value = DeleteAccountState(busy = true)
        viewModelScope.launch {
            runCatching { repository.deleteAccount(password, confirm) }
                .onSuccess { _deletion.value = DeleteAccountState(done = true) }
                .onFailure {
                    _deletion.value = DeleteAccountState(
                        error = it.message ?: "Unable to delete the account.",
                    )
                }
        }
    }

    fun clearDeletionMessage() {
        if (!_deletion.value.busy) _deletion.value = DeleteAccountState()
    }

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

    /** Lets a section report a server-confirmed outcome through the same banner. */
    fun showMessage(value: String) {
        _message.value = value
        _formError.value = null
    }

    fun clearMessage() {
        _message.value = null
        _formError.value = null
    }
}
