package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.ObligationItem
import com.pfc.companion.ui.components.EmptyMessage
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.MoneyText
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.ObligationsViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney

/**
 * One list of everything that will be taken out of the account: bills, loan
 * repayments, installments and card payments.
 *
 * The server resolves overlaps (a card purchase is spending, the card payment is a
 * transfer) and reports which guards it applied; those are shown rather than hidden.
 */
@Composable
fun ObligationsScreen(onBack: () -> Unit) {
    val viewModel = rememberScreenViewModel("obligations") { ObligationsViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsState()

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("Back") }
        when (val current = state) {
            is UiState.Loading -> LoadingPane("Loading your obligations")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
            is UiState.Ready -> LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    ScreenHeader(
                        eyebrow = "Through ${formatDate(current.data.horizonEnd)}",
                        title = "Obligations",
                        description = "What is already committed, and when it leaves your account.",
                    )
                }
                item {
                    SectionCard(
                        title = "Due in this period",
                        subtitle = current.data.nextPayday?.let { "Payday ${formatDate(it)}" }
                            ?: "No payday marked",
                    ) {
                        MoneyText(current.data.totals.dueInHorizon, style = MaterialTheme.typography.headlineMedium)
                        Text(
                            "Next 7 days ${formatMoney(current.data.totals.dueWithin7Days)} · " +
                                "before payday ${formatMoney(current.data.totals.dueBeforePayday)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (current.data.totals.overdue != "0.00") {
                            Text(
                                "Overdue ${formatMoney(current.data.totals.overdue)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                    }
                }
                if (current.data.items.isEmpty()) {
                    item {
                        EmptyMessage(
                            "Nothing due",
                            "Bills, loan repayments and installments appear here as soon as they " +
                                "have a date inside the planning horizon.",
                        )
                    }
                }
                items(current.data.items, key = { it.id }) { item ->
                    ObligationRow(item)
                }
                if (current.data.guards.isNotEmpty()) {
                    item {
                        SectionCard(title = "How overlaps are avoided") {
                            current.data.guards.forEach { guard ->
                                Text("· $guard", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ObligationRow(item: ObligationItem) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.padding(end = 12.dp)) {
            Text(item.name, style = MaterialTheme.typography.bodyMedium)
            Text(
                listOfNotNull(
                    kindLabel(item.kind),
                    item.dueDate?.let { formatDate(it) },
                    item.detail,
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (item.isOverdue) Pill("Overdue", PillTone.Danger)
                if (item.isEstimate) Pill("Estimate", PillTone.Warning)
                if (!item.reservedInSafeToSpend) Pill("Not reserved", PillTone.Neutral)
            }
        }
        MoneyText(item.amount, style = MaterialTheme.typography.bodyMedium)
    }
}

private fun kindLabel(kind: String): String = when (kind) {
    "bill" -> "Bill"
    "loan" -> "Loan repayment"
    "card" -> "Card payment"
    "savings" -> "Savings contribution"
    else -> kind.replace('_', ' ').replaceFirstChar { it.uppercase() }
}
