package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.SettingsViewModel

private val themes = listOf("system" to "System", "light" to "Light", "dark" to "Dark")

@Composable
fun SettingsScreen(onSignOut: () -> Unit) {
    val viewModel = rememberScreenViewModel("settings") { SettingsViewModel(ServiceLocator.repository) }
    val profileState by viewModel.profile.collectAsStateWithLifecycle()
    val baseUrl by viewModel.baseUrl.collectAsState()
    val theme by viewModel.theme.collectAsState()
    val message by viewModel.message.collectAsState()

    var serverDraft by remember(baseUrl) { mutableStateOf(baseUrl) }

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
                androidx.compose.foundation.layout.Spacer(Modifier.padding(top = 8.dp))
                Text(
                    "${current.data.user.timezone} · ${current.data.user.currency}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        SectionCard(
            title = "Server address",
            subtitle = "The API the app talks to. Emulators reach the host at 10.0.2.2.",
        ) {
            OutlinedTextField(
                value = serverDraft,
                onValueChange = { serverDraft = it },
                label = { Text("API base URL") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            androidx.compose.foundation.layout.Spacer(Modifier.padding(top = 10.dp))
            Button(
                onClick = { viewModel.saveServer(serverDraft) },
                enabled = serverDraft.isNotBlank() && serverDraft != baseUrl,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Save server address")
            }
        }

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

        SectionCard(title = "Session") {
            Text(
                "Signing out removes the access token from this device. Your ledger stays on the server.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            androidx.compose.foundation.layout.Spacer(Modifier.padding(top = 10.dp))
            OutlinedButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) {
                Text("Sign out")
            }
        }

        SectionCard(title = "About this phase") {
            Text(
                "Phase 1 covers accounts, transactions, budgets, bills, CSV import on the web, Safe-to-Spend and Shopping Check. " +
                    "AI assistance and location features are prepared for but intentionally off.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
