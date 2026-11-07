package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.ApiException
import com.pfc.companion.data.ServerUrl
import kotlinx.coroutines.launch
import java.util.TimeZone

@Composable
fun LoginScreen() {
    val repository = ServiceLocator.repository
    val scope = rememberCoroutineScope()
    val storedBaseUrl by repository.baseUrlFlow.collectAsState(initial = "")

    var mode by remember { mutableStateOf(0) } // 0 sign in, 1 create account
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("") }
    var serverUrl by remember(storedBaseUrl) { mutableStateOf(ServerUrl.displayAddress(storedBaseUrl)) }
    var showServer by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    // Filled in only after /server/info answers, so the address can be verified
    // before the user spends a sign-in attempt on it.
    var testing by remember { mutableStateOf(false) }
    var testResult by remember { mutableStateOf<String?>(null) }
    var testOk by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = 24.dp, vertical = 48.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            "PERSONAL FINANCE",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        Text("Companion", style = MaterialTheme.typography.displaySmall)
        Text(
            "Your ledger, bills and safe-to-spend in one place. Same numbers as the web app, computed on your own server.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(Modifier.height(8.dp))

        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            shape = MaterialTheme.shapes.extraLarge,
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                TabRow(selectedTabIndex = mode) {
                    Tab(selected = mode == 0, onClick = { mode = 0; error = null }, text = { Text("Sign in") })
                    Tab(selected = mode == 1, onClick = { mode = 1; error = null }, text = { Text("Create account") })
                }
                Spacer(Modifier.height(16.dp))

                if (mode == 1) {
                    OutlinedTextField(
                        value = displayName,
                        onValueChange = { displayName = it },
                        label = { Text("Your name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(10.dp))
                }

                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Password") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        imeAction = ImeAction.Done,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )

                if (showServer) {
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = serverUrl,
                        onValueChange = {
                            serverUrl = it
                            // A result belongs to the address that was tested.
                            testResult = null
                            testOk = false
                        },
                        label = { Text("Server address") },
                        supportingText = {
                            Text("The address you open the web app at, e.g. http://192.168.1.100:8088 or https://finance.example.com")
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(8.dp))
                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                        horizontalAlignment = Alignment.Start,
                    ) {
                        OutlinedButton(
                            enabled = serverUrl.isNotBlank() && !testing,
                            onClick = {
                                testResult = null
                                testOk = false
                                when (val parsed = ServerUrl.parse(serverUrl)) {
                                    is ServerUrl.Result.Invalid -> testResult = parsed.reason
                                    is ServerUrl.Result.Valid -> {
                                        testing = true
                                        scope.launch {
                                            try {
                                                val info = repository.serverInfo(parsed.parsed.apiBaseUrl)
                                                testOk = true
                                                testResult = "Reachable · " +
                                                    info.serverName.ifBlank { info.appName } +
                                                    " v" + info.version
                                            } catch (err: Exception) {
                                                testResult = (err as? ApiException)?.message
                                                    ?: "Could not reach that server. Check the address and that you are on the same network."
                                            } finally {
                                                testing = false
                                            }
                                        }
                                    }
                                }
                            },
                        ) {
                            Text(if (testing) "Checking…" else "Test connection")
                        }
                        if (testResult != null) {
                            Text(
                                testResult!!,
                                style = MaterialTheme.typography.bodySmall,
                                color = if (testOk) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }

                if (error != null) {
                    Spacer(Modifier.height(10.dp))
                    Text(error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }

                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = {
                        error = null
                        busy = true
                        scope.launch {
                            try {
                                // Validate before touching the saved session: an
                                // unusable address must not sign the user out of a
                                // working server.
                                when (val parsed = ServerUrl.parse(serverUrl)) {
                                    is ServerUrl.Result.Invalid -> {
                                        error = parsed.reason
                                        return@launch
                                    }
                                    is ServerUrl.Result.Valid -> {
                                        if (parsed.parsed.apiBaseUrl != storedBaseUrl) {
                                            repository.saveBaseUrl(parsed.parsed.apiBaseUrl)
                                        }
                                    }
                                }
                                if (mode == 1) {
                                    repository.register(
                                        email = email,
                                        password = password,
                                        displayName = displayName,
                                        timezone = TimeZone.getDefault().id,
                                    )
                                } else {
                                    repository.login(email, password)
                                }
                            } catch (err: Exception) {
                                error = (err as? ApiException)?.message ?: "Could not sign you in."
                            } finally {
                                busy = false
                            }
                        }
                    },
                    enabled = !busy && email.isNotBlank() && password.isNotBlank() &&
                        (mode == 0 || displayName.isNotBlank()),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        when {
                            busy -> "Working…"
                            mode == 1 -> "Create my account"
                            else -> "Sign in"
                        }
                    )
                }

                TextButton(
                    onClick = { showServer = !showServer },
                    modifier = Modifier.align(Alignment.End),
                ) {
                    Text(if (showServer) "Hide server settings" else "Server settings")
                }
            }
        }

        Text(
            "No bank connection required. Add accounts and transactions yourself, or import a CSV from the web app.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
