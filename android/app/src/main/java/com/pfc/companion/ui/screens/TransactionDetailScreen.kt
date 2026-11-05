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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.MoneyText
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.UiState
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.theme.NumberStyle
import com.pfc.companion.ui.vm.TransactionDetailViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.txTypeLabel

@Composable
fun TransactionDetailScreen(
    transactionId: String,
    onEdit: () -> Unit,
    onBack: () -> Unit,
) {
    val viewModel = rememberScreenViewModel("transaction-detail-$transactionId") {
        TransactionDetailViewModel(ServiceLocator.repository, transactionId)
    }
    val state by viewModel.state.collectAsStateWithLifecycle()

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        viewModel.load()
    }

    Column(modifier = Modifier.fillMaxSize()) {
        TextButton(onClick = onBack) { Text("← Ledger") }

        when (val current = state) {
            is UiState.Loading -> LoadingPane("Loading transaction")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::load)
            is UiState.Ready -> {
                val transaction = current.data
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Text(
                        transaction.description,
                        style = MaterialTheme.typography.headlineSmall,
                    )
                    MoneyText(
                        transaction.amount,
                        style = MaterialTheme.typography.displaySmall.merge(NumberStyle),
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Pill(txTypeLabel(transaction.txType))
                        Pill(
                            if (transaction.status == "pending") "Pending" else "Posted",
                            if (transaction.status == "pending") com.pfc.companion.ui.components.PillTone.Warning
                            else com.pfc.companion.ui.components.PillTone.Positive,
                        )
                    }

                    SectionCard(title = "Details") {
                        DetailRow("Date", formatDate(transaction.txnDate))
                        DetailRow("Account", transaction.accountName ?: "—")
                        transaction.transferAccountName?.let { DetailRow("Transfer to", it) }
                        DetailRow("Category", transaction.categoryName ?: "Uncategorized")
                        DetailRow("Merchant", transaction.merchant ?: "—")
                        DetailRow("Notes", transaction.notes ?: "—")
                        DetailRow(
                            "Tags",
                            if (transaction.tags.isEmpty()) "—" else transaction.tags.joinToString(", "),
                        )
                    }

                    Text(
                        "Amounts are stored as exact decimals on the server; this screen never recalculates balances.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    Button(onClick = onEdit, modifier = Modifier.fillMaxWidth()) {
                        Text("Edit transaction")
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
        )
    }
}
