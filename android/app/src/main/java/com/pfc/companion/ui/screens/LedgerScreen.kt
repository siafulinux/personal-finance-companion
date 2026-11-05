package com.pfc.companion.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.Transaction
import com.pfc.companion.ui.components.EmptyMessage
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.MoneyText
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.LedgerViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.parseAmount
import com.pfc.companion.util.txTypeLabel

private val filters = listOf(
    null to "All",
    "purchase" to "Purchases",
    "income" to "Income",
    "bill_payment" to "Bills",
    "refund" to "Refunds",
)

@Composable
fun LedgerScreen(
    onAddTransaction: () -> Unit,
    onImportCsv: () -> Unit,
    onOpenTransaction: (String) -> Unit,
    flash: String?,
    onFlashShown: () -> Unit,
) {
    val viewModel = rememberScreenViewModel("ledger") { LedgerViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val filter by viewModel.filter.collectAsState()

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        viewModel.refresh()
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            ScreenHeader(
                eyebrow = "Ledger",
                title = "Every balance change",
                description = "Transfers are excluded from income and spending. Refunds reduce the category they came from.",
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Button(onClick = onAddTransaction, modifier = Modifier.weight(1f)) {
                    Text("Add transaction")
                }
                OutlinedButton(onClick = onImportCsv, modifier = Modifier.weight(1f)) {
                    Text("Import CSV")
                }
            }
        }

        if (flash != null) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp),
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
                        flash,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = onFlashShown) { Text("Dismiss") }
                }
            }
        }

        LazyRow(
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 20.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(filters) { (value, label) ->
                FilterChip(
                    selected = filter == value,
                    onClick = { viewModel.setFilter(value) },
                    label = { Text(label) },
                )
            }
        }

        when (val current = state) {
            is UiState.Loading -> LoadingPane("Loading transactions")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
            is UiState.Ready -> LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(18.dp),
                    ) {
                        Summary("Income", current.data.totals.income)
                        Summary("Spending", current.data.totals.spending)
                        Summary("Refunds", current.data.totals.refunds)
                    }
                }
                item {
                    Text(
                        "${current.data.total} matching transaction(s)",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (current.data.items.isEmpty()) {
                    item {
                        EmptyMessage("Nothing here yet", "Add a transaction or import a CSV to get started.")
                    }
                }
                items(current.data.items, key = { it.id }) { transaction ->
                    TransactionRow(transaction, onClick = { onOpenTransaction(transaction.id) })
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                }
            }
        }
    }
}

@Composable
private fun Summary(label: String, amount: String) {
    Column {
        Text(
            label.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        MoneyText(amount, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun TransactionRow(transaction: Transaction, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(transaction.description, style = MaterialTheme.typography.bodyLarge)
            Text(
                listOfNotNull(
                    formatDate(transaction.txnDate),
                    transaction.accountName,
                    transaction.categoryName ?: txTypeLabel(transaction.txType),
                    if (transaction.status == "pending") "pending" else null,
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        // Amounts are stored positive; only money coming in earns an explicit "+",
        // matching how the web ledger presents the same rows.
        val incoming = transaction.txType == "income" || transaction.txType == "refund"
        MoneyText(
            transaction.amount,
            signed = incoming,
            style = MaterialTheme.typography.bodyLarge,
            color = if (incoming) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.onSurface
            },
        )
    }
}
