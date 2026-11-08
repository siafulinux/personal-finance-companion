package com.pfc.companion.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.ServerUrl
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.ServerConnectionViewModel
import com.pfc.companion.ui.vm.ServerTestState
import com.pfc.companion.ui.vm.SettingsViewModel
import com.pfc.companion.ui.vm.PasswordFormState

private val themes = listOf("system" to "System", "light" to "Light", "dark" to "Dark")

@Composable
fun SettingsScreen(onSignOut: () -> Unit) {
    val viewModel = rememberScreenViewModel("settings") { SettingsViewModel(ServiceLocator.repository) }
    val profileState by viewModel.profile.collectAsStateWithLifecycle()
    val theme by viewModel.theme.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        ScreenHeader(
            eyebrow = "Settings",
            title = "Your account and server",
            description = "The Android app reads and writes the same ledger as the web app. Nothing financial is stored on this device.",
        )

        if (message != null) {
            Text(
                message!!,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        when (val current = profileState) {
            is UiState.Loading -> LoadingPane("Loading your profile")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
            is UiState.Ready -> SectionCard {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column {
                        Text(
                            current.data.user.displayName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            current.data.user.email,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (current.data.user.isDemo) {
                        Pill("Demo data", PillTone.Warning)
                    }
                }
                Spacer(Modifier.padding(top = 8.dp))
                Text(
                    "${current.data.user.timezone} · ${current.data.user.currency}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        ServerConnectionSection()

        SectionCard(title = "Appearance") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                themes.forEach { (value, label) ->
                    FilterChip(
                        selected = theme == value,
                        onClick = { viewModel.setTheme(value) },
                        label = { Text(label) },
                    )
                }
            }
        }

        PasswordSection(viewModel)

        SectionCard(title = "Session") {
            Text(
                "Signing out removes this server's access token from the device. Your ledger stays on the server.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(10.dp))
            OutlinedButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) {
                Text("Sign out")
            }
        }

        SectionCard(title = "About this phase") {
            Text(
                "Phase 2 connects the app to any self-hosted server. Bank synchronization, insights and the assistant " +
                    "live in the web app; this app reads the same authoritative numbers.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Changes this account's password.
 *
 * The server ends every other session; this device is handed a fresh token, so it is
 * not signed out by its own security action. The fields are cleared once the server
 * confirms, so a secret does not sit on screen afterwards.
 */
@Composable
private fun PasswordSection(viewModel: SettingsViewModel) {
    val state by viewModel.password.collectAsStateWithLifecycle()
    var current by remember { mutableStateOf("") }
    var next by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }

    LaunchedEffect(state.saved) {
        if (state.saved) {
            current = ""
            next = ""
            confirm = ""
        }
    }

    SectionCard(title = "Password") {
        Text(
            "Changing your password signs out every other device that is signed in. " +
                "This phone stays signed in.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = current,
            onValueChange = {
                current = it
                viewModel.clearPasswordMessage()
            },
            label = { Text("Current password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = next,
            onValueChange = {
                next = it
                viewModel.clearPasswordMessage()
            },
            label = { Text("New password") },
            supportingText = { Text("At least 8 characters, with a letter and a number.") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = confirm,
            onValueChange = {
                confirm = it
                viewModel.clearPasswordMessage()
            },
            label = { Text("Confirm new password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )

        if (state.error != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                state.error!!,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
        if (state.saved) {
            Spacer(Modifier.height(8.dp))
            Text(
                "Password changed. Other devices were signed out.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        Spacer(Modifier.height(10.dp))
        Button(
            onClick = { viewModel.changePassword(current, next, confirm) },
            enabled = !state.busy && current.isNotBlank() && next.isNotBlank() && confirm.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (state.busy) "Changing…" else "Change password")
        }
    }
}

/**
 * Points the app at a server. Saving requires a successful test first, so a typo
 * cannot strand the user on an address nothing answers at.
 */
@Composable
private fun ServerConnectionSection() {
    val viewModel = rememberScreenViewModel("settings-server") {
        ServerConnectionViewModel(ServiceLocator.repository)
    }
    val draft by viewModel.draft.collectAsStateWithLifecycle()
    val test by viewModel.test.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()
    val validationError by viewModel.validationError.collectAsStateWithLifecycle()
    val currentBaseUrl by viewModel.currentBaseUrl.collectAsStateWithLifecycle()
    val savedServers by viewModel.savedServers.collectAsStateWithLifecycle()
    val saving by viewModel.saving.collectAsStateWithLifecycle()

    val parsed = (ServerUrl.parse(draft) as? ServerUrl.Result.Valid)?.parsed

    SectionCard(
        title = "Server",
        subtitle = "The installation this phone reads and writes.",
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    "IN USE",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    ServerUrl.displayAddress(currentBaseUrl).ifBlank { "—" },
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            if (parsed != null && parsed.apiBaseUrl == currentBaseUrl) {
                Pill("Current", PillTone.Positive)
            }
        }

        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = draft,
            onValueChange = viewModel::onDraftChange,
            label = { Text("Server address") },
            placeholder = { Text("192.168.1.100:8088") },
            singleLine = true,
            isError = validationError != null || test is ServerTestState.Unreachable,
            supportingText = {
                Text(
                    validationError
                        ?: "The address you open the web app at. https:// for a public name, http:// only on your own network."
                )
            },
            modifier = Modifier.fillMaxWidth(),
        )

        if (parsed?.insecure == true) {
            Spacer(Modifier.height(6.dp))
            Text(
                "Plain HTTP on your local network: traffic is not encrypted. Fine on a trusted LAN, not over the internet.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.error,
            )
        }

        Spacer(Modifier.height(12.dp))
        when (val state = test) {
            ServerTestState.Idle, is ServerTestState.Invalid -> Unit
            ServerTestState.Testing -> Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                Text("Contacting the server…", style = MaterialTheme.typography.bodySmall)
            }
            is ServerTestState.Unreachable -> Text(
                state.message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
            is ServerTestState.Reachable -> Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Pill("Reachable", PillTone.Positive)
                    Text(
                        state.info.serverName.ifBlank { state.info.appName },
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Text(
                    "Version ${state.info.version} · API v${state.info.apiVersion}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (state.info.webUrl.isNotBlank()) {
                    Text(
                        "Web app: ${state.info.webUrl}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state.info.needsSetup) {
                    Text(
                        "This server still needs its first-run setup. Open ${state.info.webUrl} to create the owner account.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = viewModel::testConnection,
                enabled = draft.isNotBlank() && test !is ServerTestState.Testing,
                modifier = Modifier.weight(1f),
            ) {
                Text("Test connection")
            }
            Button(
                onClick = viewModel::save,
                enabled = test is ServerTestState.Reachable && !saving,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (saving) "Saving…" else "Save server")
            }
        }

        if (message != null) {
            Spacer(Modifier.height(10.dp))
            Text(
                message!!,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        if (savedServers.size > 1) {
            Spacer(Modifier.height(12.dp))
            Text(
                "RECENT SERVERS",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontWeight = FontWeight.SemiBold,
            )
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                savedServers.forEach { saved ->
                    AssistChip(
                        onClick = { viewModel.useSaved(saved) },
                        label = { Text(ServerUrl.displayAddress(saved), maxLines = 1) },
                    )
                }
            }
        }
    }
}
