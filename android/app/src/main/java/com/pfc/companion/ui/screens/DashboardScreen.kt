package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.Dashboard
import com.pfc.companion.data.Occurrence
import com.pfc.companion.data.Transaction
import com.pfc.companion.ui.components.EmptyMessage
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.MoneyText
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.SafeToSpendCard
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.theme.NumberStyle
import com.pfc.companion.ui.vm.DashboardViewModel
import com.pfc.companion.util.accountTypeLabel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.formatPercent
import com.pfc.companion.util.parseAmount
import com.pfc.companion.util.relativeDueLabel

@Composable
fun DashboardScreen(
    onOpenShopping: () -> Unit,
    onOpenLedger: () -> Unit,
) {
    val viewModel = rememberScreenViewModel("dashboard") {
        DashboardViewModel(ServiceLocator.repository)
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val actionError by viewModel.actionError.collectAsState()
    val busyOccurrence by viewModel.busyOccurrence.collectAsState()

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        viewModel.refresh()
    }

    when (val current = state) {
        is UiState.Loading -> LoadingPane()
        is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
        is UiState.Ready -> DashboardContent(
            data = current.data,
            actionError = actionError,
            busyOccurrence = busyOccurrence,
            onMarkPaid = viewModel::markPaid,
            onOpenShopping = onOpenShopping,
            onOpenLedger = onOpenLedger,
            onRefresh = viewModel::refresh,
        )
    }
}

@Composable
private fun DashboardContent(
    data: Dashboard,
    actionError: String?,
    busyOccurrence: String?,
    onMarkPaid: (String) -> Unit,
    onOpenShopping: () -> Unit,
    onOpenLedger: () -> Unit,
    onRefresh: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            ScreenHeader(
                eyebrow = formatDate(data.today),
                title = if (data.isDemo) "Demo, here is what is actually yours." else "Here is what is actually yours.",
                description = "Figures come from your ledger on the server. No estimates in the spend number.",
            )
        }

        item { SafeToSpendCard(data.safeToSpend) }

        if (data.warnings.isNotEmpty()) {
            item {
                SectionCard(title = "Worth your attention") {
                    data.warnings.forEach { warning ->
                        Text(
                            "!  $warning",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.padding(vertical = 3.dp),
                        )
                    }
                }
            }
        }

        if (actionError != null) {
            item {
                Text(
                    actionError,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        item {
            SectionCard(
                title = "Next up",
                subtitle = "Upcoming bills · ${formatMoney(data.upcomingBillsTotal)}",
                action = {
                    TextButton(onClick = onRefresh) { Text("Refresh") }
                },
            ) {
                if (data.upcomingBills.isEmpty()) {
                    EmptyMessage(
                        "No bills inside the planning horizon",
                        "Add recurring bills on the web app or mark paydays to widen the horizon.",
                    )
                } else {
                    data.upcomingBills.take(6).forEachIndexed { index, occurrence ->
                        if (index > 0) HorizontalDivider(Modifier.padding(vertical = 8.dp))
                        BillLine(
                            occurrence = occurrence,
                            busy = busyOccurrence == occurrence.id,
                            onMarkPaid = { onMarkPaid(occurrence.id) },
                        )
                    }
                }
            }
        }

        item {
            SectionCard(
                title = "Accounts",
                subtitle = "Cash ${formatMoney(data.accountTotals.totalCash)} · Net worth ${formatMoney(data.accountTotals.netWorth)}",
            ) {
                data.accounts.filterNot { it.isArchived }.forEach { account ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 5.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column {
                            Text(account.name, style = MaterialTheme.typography.bodyMedium)
                            Text(
                                accountTypeLabel(account.accountType),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        MoneyText(
                            account.balance,
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (parseAmount(account.balance).signum() < 0) {
                                MaterialTheme.colorScheme.error
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            },
                        )
                    }
                }
            }
        }

        item {
            SectionCard(
                title = "This month",
                subtitle = "Income ${formatMoney(data.monthTotals.income)} · Net ${formatMoney(data.monthTotals.net)}",
            ) {
                Text(
                    "Spent so far",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    formatMoney(data.monthTotals.spending),
                    style = MaterialTheme.typography.headlineSmall.merge(NumberStyle),
                )
                if (data.budget != null) {
                    Spacer(Modifier.height(10.dp))
                    LinearProgressIndicator(
                        progress = { (parseAmount(data.budget.percentUsed).toFloat() / 100f).coerceIn(0f, 1f) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(6.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            "${formatPercent(data.budget.percentUsed)} of budget used",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            "${formatMoney(data.budget.totalRemaining)} left",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }

        item {
            SectionCard(
                title = "Recent activity",
                action = { TextButton(onClick = onOpenLedger) { Text("View ledger") } },
            ) {
                if (data.recentTransactions.isEmpty()) {
                    EmptyMessage("Nothing recorded yet", "Add a transaction in the web app and it appears here.")
                } else {
                    data.recentTransactions.take(6).forEach { transaction ->
                        TransactionLine(transaction)
                    }
                }
            }
        }

        item {
            SectionCard(
                title = "Before you buy",
                subtitle = "Check cash and category budget before spending.",
            ) {
                Button(onClick = onOpenShopping, modifier = Modifier.fillMaxWidth()) {
                    Text("Start a Shopping Check")
                }
            }
        }

        item { Spacer(Modifier.height(12.dp)) }
    }
}

@Composable
private fun BillLine(occurrence: Occurrence, busy: Boolean, onMarkPaid: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    occurrence.billName ?: "Bill",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                )
                if (occurrence.isOverdue) {
                    Spacer(Modifier.height(0.dp))
                    androidx.compose.foundation.layout.Box(Modifier.padding(start = 6.dp)) {
                        Pill("Overdue", PillTone.Danger)
                    }
                }
            }
            Text(
                "${relativeDueLabel(occurrence.dueDate)} · ${formatDate(occurrence.dueDate)}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            MoneyText(occurrence.remainingAmount, style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = onMarkPaid, enabled = !busy) {
                Text(if (busy) "Saving…" else "Mark paid")
            }
        }
    }
}

@Composable
private fun TransactionLine(transaction: Transaction) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(transaction.description, style = MaterialTheme.typography.bodyMedium)
            Text(
                listOfNotNull(
                    formatDate(transaction.txnDate),
                    transaction.accountName,
                    transaction.categoryName,
                    if (transaction.status == "pending") "pending" else null,
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        // Amounts are stored positive; only money coming in earns an explicit "+".
        val incoming = transaction.txType == "income" || transaction.txType == "refund"
        MoneyText(
            transaction.amount,
            signed = incoming,
            style = MaterialTheme.typography.bodyMedium,
            color = if (incoming) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.onSurface
            },
        )
    }
}
