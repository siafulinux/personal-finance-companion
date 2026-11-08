package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.BudgetDraft
import com.pfc.companion.data.BudgetRow
import com.pfc.companion.ui.components.EmptyMessage
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.MoneyText
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.theme.NumberStyle
import com.pfc.companion.ui.vm.BudgetEditorState
import com.pfc.companion.ui.vm.BudgetsViewModel
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.formatMonth
import com.pfc.companion.util.formatPercent
import com.pfc.companion.util.parseAmount

@Composable
fun BudgetsScreen(flash: String? = null, onFlashShown: () -> Unit = {}) {
    val viewModel = rememberScreenViewModel("budgets") { BudgetsViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val editor by viewModel.editor.collectAsStateWithLifecycle()
    var localFlash by remember { mutableStateOf<String?>(null) }

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        viewModel.refresh()
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            ScreenHeader(
                eyebrow = "Budgets",
                title = "Give every dollar a job",
                description = "Allocations, carryover and spending are calculated by the same engine that powers Safe-to-Spend.",
            )
        }

        val banner = localFlash ?: flash
        if (banner != null) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 4.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        banner,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = {
                        localFlash = null
                        onFlashShown()
                    }) { Text("Dismiss") }
                }
            }
        }

        when (val current = state) {
            is UiState.Loading -> LoadingPane("Loading this month's budget")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
            is UiState.Ready -> {
                val budget = current.data
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    item {
                        SectionCard(
                            title = formatMonth(budget.year, budget.month),
                            subtitle = "Income this month ${formatMoney(budget.incomeThisMonth)}",
                        ) {
                            Text(
                                formatMoney(budget.totalRemaining),
                                style = MaterialTheme.typography.headlineSmall.merge(NumberStyle),
                            )
                            Text(
                                "remaining of ${formatMoney(budget.totalAllocated)} allocated",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Spacer(Modifier.height(10.dp))
                            LinearProgressIndicator(
                                progress = {
                                    (parseAmount(budget.percentUsed).toFloat() / 100f).coerceIn(0f, 1f)
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(6.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text(
                                    "${formatMoney(budget.totalSpent)} spent · ${formatPercent(budget.percentUsed)}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                Text(
                                    "Unallocated ${formatMoney(budget.unallocated)}",
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                            Spacer(Modifier.height(12.dp))
                            Button(onClick = viewModel::openEditor, modifier = Modifier.fillMaxWidth()) {
                                Text("Edit budget")
                            }
                        }
                    }

                    item {
                        Text(
                            "CATEGORIES",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }

                    if (budget.rows.isEmpty()) {
                        item {
                            EmptyMessage(
                                "No allocations yet",
                                "Give a category a monthly limit with Edit budget.",
                            )
                        }
                    }

                    items(budget.rows, key = { it.categoryId }) { row ->
                        BudgetRowCard(row)
                    }

                    item { Spacer(Modifier.height(12.dp)) }
                }
            }
        }
    }

    BudgetEditorDialog(
        editor = editor,
        onChange = viewModel::updateDraft,
        onSave = { viewModel.save { message -> localFlash = message } },
        onDismiss = viewModel::closeEditor,
    )
}

/**
 * Edits every category limit for the month at once.
 *
 * The API replaces the allocation set rather than patching one row, so the whole
 * list is saved together and a category left at zero loses its allocation.
 */
@Composable
private fun BudgetEditorDialog(
    editor: BudgetEditorState,
    onChange: ((BudgetDraft) -> BudgetDraft) -> Unit,
    onSave: () -> Unit,
    onDismiss: () -> Unit,
) {
    if (!editor.open) return

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit this month's budget") },
        text = {
            Column(
                modifier = Modifier
                    .heightIn(max = 420.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                OutlinedTextField(
                    value = editor.draft.plannedIncome,
                    onValueChange = { value ->
                        if (value.isEmpty() || value.matches(Regex("^\\d{0,9}(\\.\\d{0,2})?$"))) {
                            onChange { it.copy(plannedIncome = value) }
                        }
                    },
                    label = { Text("Planned income for this month") },
                    supportingText = { Text("Used for the unallocated figure and future planning.") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "Amounts are per month. Set a category to zero to remove its allocation.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                editor.draft.allocations.forEach { allocation ->
                    Column {
                        OutlinedTextField(
                            value = allocation.amount,
                            onValueChange = { value ->
                                if (value.isEmpty() || value.matches(Regex("^\\d{0,9}(\\.\\d{0,2})?$"))) {
                                    onChange { it.withAmount(allocation.categoryId, value) }
                                }
                            },
                            label = { Text(allocation.name.ifBlank { "Category" }) },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(
                                checked = allocation.carryover,
                                onCheckedChange = { checked ->
                                    onChange { it.withCarryover(allocation.categoryId, checked) }
                                },
                            )
                            Text(
                                "Carry unused balance forward",
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                    }
                }
                if (editor.error != null) {
                    Text(
                        editor.error!!,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onSave, enabled = !editor.saving) {
                Text(if (editor.saving) "Saving…" else "Save budget")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !editor.saving) { Text("Cancel") }
        },
    )
}

@Composable
private fun BudgetRowCard(row: BudgetRow) {
    SectionCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(row.categoryName, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
                Text(
                    "${formatMoney(row.spent)} of ${formatMoney(row.allocated)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            MoneyText(row.remaining, style = MaterialTheme.typography.bodyLarge)
        }
        Spacer(Modifier.height(8.dp))
        LinearProgressIndicator(
            progress = { (parseAmount(row.percentUsed).toFloat() / 100f).coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth(),
        )
        if (parseAmount(row.upcomingCommitments).signum() > 0) {
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text(
                "${formatMoney(row.upcomingCommitments)} of upcoming bills already reserved",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
