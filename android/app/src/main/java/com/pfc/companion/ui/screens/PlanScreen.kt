package com.pfc.companion.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pfc.companion.ui.components.HorizontalGap
import com.pfc.companion.ui.components.ScreenHeader

/**
 * The permanent way into the planning screens.
 *
 * Loans, savings goals and obligations used to be reachable only from a card low on
 * the dashboard, which meant scrolling past the summary to find them and no way back
 * once that card changed. Each of them is a first-class screen, so they get a tab of
 * their own and this is its index.
 */
@Composable
fun PlanScreen(
    onOpenLoans: () -> Unit,
    onOpenSavings: () -> Unit,
    onOpenObligations: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        ScreenHeader(
            eyebrow = "Everything already committed",
            title = "Plan",
            description = "What you borrowed, what you are setting aside, and what is already owed.",
        )
        HorizontalGap(14)
        PlanEntry(
            title = "Loans & advances",
            description = "Balances, repayment matches and payoff dates for money you borrowed.",
            onOpen = onOpenLoans,
        )
        HorizontalGap(10)
        PlanEntry(
            title = "Savings goals",
            description = "Money set aside for a purpose, virtual or held in its own account.",
            onOpen = onOpenSavings,
        )
        HorizontalGap(10)
        PlanEntry(
            title = "Obligations",
            description = "Bills, loan instalments and card payments in one ordered list.",
            onOpen = onOpenObligations,
        )
    }
}

@Composable
private fun PlanEntry(title: String, description: String, onOpen: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen),
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(18.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.fillMaxWidth(0.9f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                HorizontalGap(4)
                Text(
                    description,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Icon(Icons.Filled.KeyboardArrowRight, contentDescription = null)
        }
    }
}
