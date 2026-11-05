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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
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
import com.pfc.companion.ui.vm.BudgetsViewModel
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.formatMonth
import com.pfc.companion.util.formatPercent
import com.pfc.companion.util.parseAmount

@Composable
fun BudgetsScreen() {
    val viewModel = rememberScreenViewModel("budgets") { BudgetsViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsStateWithLifecycle()

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
                                "Set up a budget in the web app; the same categories appear here.",
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
