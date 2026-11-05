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
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.ApiException
import com.pfc.companion.data.Profile
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import kotlinx.coroutines.launch

private val frequencies = listOf(
    "weekly" to "Weekly",
    "biweekly" to "Every 2 weeks",
    "semimonthly" to "Twice a month",
    "monthly" to "Monthly",
    "irregular" to "Irregular",
)

/**
 * Minimal first-run setup. The full planning tools remain on the web, but a new
 * Android account must at least have a cash account and a planning baseline.
 */
@Composable
fun OnboardingScreen(profile: Profile, onDone: (Profile) -> Unit) {
    val repository = ServiceLocator.repository
    val scope = rememberCoroutineScope()

    var displayName by remember(profile) { mutableStateOf(profile.user.displayName) }
    var accountName by remember { mutableStateOf("Everyday Checking") }
    var startingBalance by remember { mutableStateOf("") }
    var buffer by remember { mutableStateOf("0.00") }
    var incomeAmount by remember { mutableStateOf("") }
    var frequency by remember { mutableStateOf("biweekly") }
    var nextPayday by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        ScreenHeader(
            eyebrow = "First-run setup",
            title = "Give your ledger a starting point",
            description = "Safe-to-Spend needs one real cash balance and, if you have one, your next payday. You can change all of this later.",
        )

        SectionCard(title = "Your details") {
            OutlinedTextField(
                value = displayName,
                onValueChange = { displayName = it },
                label = { Text("Display name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            Text(
                "Timezone: ${profile.user.timezone}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        SectionCard(title = "Cash account") {
            OutlinedTextField(
                value = accountName,
                onValueChange = { accountName = it },
                label = { Text("Account name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = startingBalance,
                onValueChange = { startingBalance = it },
                label = { Text("Current checking balance") },
                supportingText = { Text("Use the balance you can verify in your bank app.") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = buffer,
                onValueChange = { buffer = it },
                label = { Text("Minimum cash buffer") },
                supportingText = { Text("Money you never want to spend, such as an emergency floor.") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
        }

        SectionCard(title = "Income (optional)") {
            OutlinedTextField(
                value = incomeAmount,
                onValueChange = { incomeAmount = it },
                label = { Text("Take-home pay per paycheck") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                frequencies.take(3).forEach { (value, label) ->
                    FilterChip(
                        selected = frequency == value,
                        onClick = { frequency = value },
                        label = { Text(label) },
                    )
                }
            }
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                frequencies.drop(3).forEach { (value, label) ->
                    FilterChip(
                        selected = frequency == value,
                        onClick = { frequency = value },
                        label = { Text(label) },
                    )
                }
            }
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = nextPayday,
                onValueChange = { nextPayday = it },
                label = { Text("Next payday (YYYY-MM-DD)") },
                supportingText = { Text("Bills due before this date are reserved from Safe-to-Spend.") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, imeAction = ImeAction.Done),
                modifier = Modifier.fillMaxWidth(),
            )
        }

        if (error != null) {
            Text(error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        Button(
            onClick = {
                error = null
                busy = true
                scope.launch {
                    try {
                        val next = repository.completeOnboarding(
                            displayName = displayName,
                            timezone = profile.user.timezone,
                            accountName = accountName,
                            startingBalance = startingBalance,
                            buffer = buffer,
                            incomeAmount = incomeAmount,
                            incomeFrequency = frequency,
                            nextPayday = nextPayday.ifBlank { null },
                        )
                        onDone(next)
                    } catch (err: Exception) {
                        error = (err as? ApiException)?.message ?: "Could not finish setup."
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy && displayName.isNotBlank() && accountName.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "Saving…" else "Open my dashboard")
        }

        Text(
            "You can add other accounts, budgets and recurring bills on the web app. The same server is the source of truth for both apps.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(12.dp))
    }
}
