package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.BuildConfig
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.ServerInfo
import com.pfc.companion.data.ServerUrl
import com.pfc.companion.data.ApiException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Outcome of asking an address what server it is. */
sealed interface ServerTestState {
    data object Idle : ServerTestState
    data object Testing : ServerTestState
    data class Invalid(val reason: String) : ServerTestState
    data class Reachable(val info: ServerInfo) : ServerTestState
    data class Unreachable(val message: String) : ServerTestState
}

/**
 * Drives the "which server does this app talk to" screen.
 *
 * Saving is deliberately gated on a successful test: an address that cannot answer
 * `/server/info` would leave the user signed out of a server that does not exist,
 * with the real one one tap away. Testing never authenticates, so a typo cannot
 * leak the current session to whatever answers at that address.
 */
class ServerConnectionViewModel(private val repository: FinanceRepository) : ViewModel() {
    private val _draft = MutableStateFlow("")
    val draft: StateFlow<String> = _draft.asStateFlow()

    private val _test = MutableStateFlow<ServerTestState>(ServerTestState.Idle)
    val test: StateFlow<ServerTestState> = _test.asStateFlow()

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving.asStateFlow()

    val currentBaseUrl: StateFlow<String> = repository.baseUrlFlow.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = "",
    )

    val savedServers: StateFlow<List<String>> = repository.savedServers.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = emptyList(),
    )

    private val _validation = MutableStateFlow<String?>(null)

    /** Non-null while the typed address is not acceptable, shown under the field. */
    val validationError: StateFlow<String?> = _validation.asStateFlow()

    init {
        viewModelScope.launch {
            val current = repository.baseUrlFlow.first()
            if (_draft.value.isBlank()) _draft.value = ServerUrl.displayAddress(current)
        }
    }

    fun onDraftChange(value: String) {
        _draft.value = value
        _test.value = ServerTestState.Idle
        _validation.value = null
        _message.value = null
    }

    fun useSaved(apiBaseUrl: String) {
        _draft.value = ServerUrl.displayAddress(apiBaseUrl)
        _test.value = ServerTestState.Idle
        _validation.value = null
        _message.value = null
    }

    fun testConnection() {
        val parsed = when (val result = ServerUrl.parse(_draft.value)) {
            is ServerUrl.Result.Invalid -> {
                _validation.value = result.reason
                _test.value = ServerTestState.Invalid(result.reason)
                return
            }
            is ServerUrl.Result.Valid -> result.parsed
        }
        _validation.value = null
        _test.value = ServerTestState.Testing
        _message.value = null

        viewModelScope.launch {
            _test.value = try {
                val info = repository.serverInfo(parsed.apiBaseUrl)
                if (info.status != "ok") {
                    ServerTestState.Unreachable("The server answered but reported status \"${info.status}\".")
                } else if (info.apiVersion < BuildConfig.CLIENT_API_VERSION) {
                    ServerTestState.Unreachable(
                        "This server speaks API v${info.apiVersion}; this app needs v${BuildConfig.CLIENT_API_VERSION}. " +
                            "Update the server before connecting."
                    )
                } else {
                    ServerTestState.Reachable(info)
                }
            } catch (err: ApiException) {
                ServerTestState.Unreachable(err.message ?: "Could not reach that server.")
            } catch (err: Exception) {
                ServerTestState.Unreachable(err.message ?: "Could not reach that server.")
            }
        }
    }

    /** Saves the tested address as this device's server. */
    fun save() {
        val reachable = _test.value as? ServerTestState.Reachable ?: run {
            _message.value = "Test the connection first."
            return
        }
        val parsed = (ServerUrl.parse(_draft.value) as? ServerUrl.Result.Valid)?.parsed ?: return
        val testedBase = ServerUrl.apiBaseUrlOrNull(reachable.info.apiBaseUrl)
        if (testedBase != null && testedBase != parsed.apiBaseUrl) {
            // The address was edited after the successful test.
            _message.value = "Test the connection again for this address."
            return
        }

        _saving.value = true
        viewModelScope.launch {
            try {
                repository.saveBaseUrl(parsed.apiBaseUrl)
                _message.value = buildString {
                    append("Connected to ")
                    append(reachable.info.serverName.ifBlank { reachable.info.appName })
                    append(" (v").append(reachable.info.version).append("). ")
                    if (reachable.info.needsSetup) {
                        append("Finish the first-run setup in its web app before signing in.")
                    } else {
                        append("Sign in with your account on that server.")
                    }
                }
            } finally {
                _saving.value = false
            }
        }
    }

    fun clearMessage() {
        _message.value = null
    }
}
