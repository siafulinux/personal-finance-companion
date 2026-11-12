package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.Account
import com.pfc.companion.data.SavingsGoal
import com.pfc.companion.ui.components.EmptyMessage
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.HorizontalGap
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.MoneyText
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.SavingsViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.formatPercent
import com.pfc.companion.util.parseAmount
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import androidx.compose.runtime.rememberCoroutineScope

/**
 * Savings goals and money set aside.
 *
 * Two kinds of saving are shown differently on purpose: a virtual goal protects
 * money that is still in a spending account, while an account-backed goal points at
 * a separate balance. The server refuses to subtract both, and the labels here say
 * which one the user is looking at.
 */
@Composable
fun SavingsScreen(onBack: () -> Unit) {
    val viewModel = rememberScreenViewModel("savings") { SavingsViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsState()
    val error by viewModel.error.collectAsState()
    val busy by viewModel.busy.collectAsState()

    var adding by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<SavingsGoal?>(null) }
    var contributing by remember { mutableStateOf<SavingsGoal?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    val accounts = remember { mutableStateOf<List<Account>>(emptyList()) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        runCatching { ServiceLocator.repository.accounts() }.onSuccess { accounts.value = it.accounts }
    }
    scope.launch { }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onBack) { Text("Back") }
            Button(onClick = { adding = true }) { Text("New goal") }
        }
        when (val current = state) {
            is UiState.Loading -> LoadingPane("Loading your goals")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
            is UiState.Ready -> LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    ScreenHeader(
                        eyebrow = "${current.data.activeGoals} active",
                        title = "Savings goals",
                        description = "Money set aside is unavailable to Safe-to-Spend. " +
                            "Nothing is transferred automatically.",
                    )
                }
                item {
                    SectionCard(
                        title = "Set aside",
                        subtitle = "Target ${formatMoney(current.data.totalTarget)} · " +
                            "${formatMoney(current.data.monthlyCommitment)} planned this month",
                    ) {
                        MoneyText(current.data.totalProtected, style = MaterialTheme.typography.headlineMedium)
                        Text(
                            "Protected from spending. Saved so far ${formatMoney(current.data.totalSaved)}.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                message?.let {
                    item { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
                }
                error?.let {
                    item { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                }
                if (current.data.goals.isEmpty()) {
                    item {
                        EmptyMessage(
                            "No goals yet",
                            "Start with an emergency fund: a target, a date, and the amount you " +
                                "can put aside each payday.",
                        )
                    }
                }
                items(current.data.goals, key = { it.id }) { goal ->
                    GoalCard(
                        goal = goal,
                        busy = busy,
                        onEdit = { editing = goal },
                        onContribute = { contributing = goal },
                        onDelete = { viewModel.delete(goal.id) { message = it } },
                    )
                }
            }
        }
    }

    if (adding || editing != null) {
        GoalDialog(
            goal = editing,
            accounts = accounts.value,
            busy = busy,
            onDismiss = {
                adding = false
                editing = null
            },
            onSave = { body ->
                viewModel.save(editing?.id, body) {
                    message = it
                    adding = false
                    editing = null
                }
            },
        )
    }
    contributing?.let { goal ->
        ContributeDialog(
            goal = goal,
            busy = busy,
            onDismiss = { contributing = null },
            onSave = { amount, on ->
                viewModel.contribute(goal.id, amount, on) {
                    message = it
                    contributing = null
                }
            },
        )
    }
}

@Composable
private fun GoalCard(
    goal: SavingsGoal,
    busy: Boolean,
    onEdit: () -> Unit,
    onContribute: () -> Unit,
    onDelete: () -> Unit,
) {
    SectionCard(
        title = goal.name,
        subtitle = if (goal.mode == "account") {
            "In ${goal.accountName ?: "a savings account"}"
        } else {
            "Virtual allocation"
        },
        action = { TextButton(onClick = onEdit) { Text("Edit") } },
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Set aside", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                MoneyText(goal.savedAmount, style = MaterialTheme.typography.headlineSmall)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("of ${formatMoney(goal.targetAmount)}", style = MaterialTheme.typography.bodySmall)
                if (goal.targetDate != null) {
                    Text(formatDate(goal.targetDate), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        HorizontalGap(10)
        LinearProgressIndicator(
            progress = { (parseAmount(goal.progressPercent).toFloat() / 100f).coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth(),
        )
        HorizontalGap(6)
        Text(
            "${formatPercent(goal.progressPercent)} · ${formatMoney(goal.remainingToTarget)} to go",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        HorizontalGap(8)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                goal.status == "completed" -> Pill("Complete", PillTone.Positive)
                goal.protectsMoney -> Pill("Protected ${formatMoney(goal.protectedAmount)}", PillTone.Warning)
                else -> Pill("Account balance", PillTone.Neutral)
            }
            if (goal.contributionAmount != null) {
                Pill(
                    "${formatMoney(goal.contributionAmount)} ${goal.contributionFrequency ?: ""}".trim(),
                    PillTone.Neutral,
                )
            }
        }
        if (goal.projectedCompletion != null) {
            HorizontalGap(6)
            Text(
                "At this pace, done around ${formatDate(goal.projectedCompletion)}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        HorizontalGap(10)
        // FlowRow, not Row: two actions squeeze each other on a narrow card, and a
        // squeezed label breaks mid-word ("Remov" / "e"). Flowing moves a button to
        // the next line whole instead.
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Button(onClick = onContribute, enabled = !busy) { Text("Add money", maxLines = 1) }
            TextButton(onClick = onDelete, enabled = !busy) { Text("Remove", maxLines = 1) }
        }
    }
}

@Composable
private fun GoalDialog(
    goal: SavingsGoal?,
    accounts: List<Account>,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSave: (JsonObject) -> Unit,
) {
    var name by remember { mutableStateOf(goal?.name.orEmpty()) }
    var target by remember { mutableStateOf(goal?.targetAmount.orEmpty()) }
    var saved by remember { mutableStateOf(goal?.savedAmount.orEmpty()) }
    var targetDate by remember { mutableStateOf(goal?.targetDate.orEmpty()) }
    var mode by remember { mutableStateOf(goal?.mode ?: "virtual") }
    var accountId by remember { mutableStateOf(goal?.accountId.orEmpty()) }
    var contribution by remember { mutableStateOf(goal?.contributionAmount.orEmpty()) }
    var frequency by remember { mutableStateOf(goal?.contributionFrequency ?: "monthly") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (goal == null) "New savings goal" else "Edit ${goal.name}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Goal name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = target,
                    onValueChange = { target = it },
                    label = { Text("Target amount") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = saved,
                    onValueChange = { saved = it },
                    label = { Text("Already set aside") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = targetDate,
                    onValueChange = { targetDate = it },
                    label = { Text("Target date (YYYY-MM-DD)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                HorizontalGap(8)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { mode = "virtual" }) {
                        Text(if (mode == "virtual") "• Set aside" else "Set aside")
                    }
                    TextButton(onClick = { mode = "account" }) {
                        Text(if (mode == "account") "• Savings account" else "Savings account")
                    }
                }
                Text(
                    if (mode == "virtual") {
                        "The money stays where it is; Safe-to-Spend treats it as committed."
                    } else {
                        "The money lives in an account. Choose which one, and it will not be " +
                            "subtracted a second time."
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (mode == "account") {
                    accounts.filterNot { it.isArchived }.forEach { account ->
                        TextButton(onClick = { accountId = account.id }) {
                            Text((if (accountId == account.id) "• " else "") + account.name)
                        }
                    }
                }
                OutlinedTextField(
                    value = contribution,
                    onValueChange = { contribution = it },
                    label = { Text("Planned contribution (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("weekly", "biweekly", "monthly", "payday").forEach { option ->
                        TextButton(onClick = { frequency = option }) {
                            Text((if (frequency == option) "• " else "") + option)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && name.isNotBlank() && parseAmount(target).signum() > 0 &&
                    (mode != "account" || accountId.isNotBlank()),
                onClick = {
                    onSave(
                        buildJsonObject {
                            put("name", name.trim())
                            put("target_amount", target.trim())
                            if (saved.isNotBlank()) put("saved_amount", saved.trim())
                            if (targetDate.isNotBlank()) put("target_date", targetDate.trim())
                            put("mode", mode)
                            if (mode == "account") put("account_id", accountId)
                            if (contribution.isNotBlank()) {
                                put("contribution_amount", contribution.trim())
                                put("contribution_frequency", frequency)
                            }
                        }
                    )
                },
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun ContributeDialog(
    goal: SavingsGoal,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSave: (String, String?) -> Unit,
) {
    var amount by remember { mutableStateOf(goal.contributionAmount.orEmpty()) }
    var on by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add to ${goal.name}") },
        text = {
            Column {
                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Amount") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = on,
                    onValueChange = { on = it },
                    label = { Text("Date (YYYY-MM-DD, today if blank)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "This records that you set the money aside. It does not move money between accounts.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && parseAmount(amount).signum() > 0,
                onClick = { onSave(amount.trim(), on.ifBlank { null }) },
            ) { Text("Add") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
