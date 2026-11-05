package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.Category
import com.pfc.companion.data.ShoppingResult
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
import com.pfc.companion.ui.vm.ShoppingViewModel
import com.pfc.companion.util.formatMoney

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShoppingScreen(onBack: () -> Unit) {
    val viewModel = rememberScreenViewModel("shopping") { ShoppingViewModel(ServiceLocator.repository) }
    val categoriesState by viewModel.categories.collectAsStateWithLifecycle()
    val result by viewModel.result.collectAsState()
    val error by viewModel.error.collectAsState()
    val checking by viewModel.checking.collectAsState()

    var store by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var categoryId by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }

    val categories: List<Category> = (categoriesState as? UiState.Ready)?.data ?: emptyList()
    val selected = categories.firstOrNull { it.id == categoryId }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        TextButton(onClick = onBack) { Text("← Back") }

        ScreenHeader(
            eyebrow = "Shopping check",
            title = "Should you buy it?",
            description = "Cash first, category second. The answer is computed from your ledger, not guessed.",
        )

        when (categoriesState) {
            is UiState.Loading -> LoadingPane("Loading categories")
            is UiState.Failed -> ErrorPane(
                (categoriesState as UiState.Failed).message,
                onRetry = viewModel::loadCategories,
            )
            else -> SectionCard(title = "Plan a purchase") {
                OutlinedTextField(
                    value = store,
                    onValueChange = { store = it },
                    label = { Text("Store") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                androidx.compose.foundation.layout.Spacer(Modifier.height(10.dp))

                ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                    OutlinedTextField(
                        value = selected?.name ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Category") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(androidx.compose.material3.MenuAnchorType.PrimaryNotEditable),
                    )
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        categories.forEach { category ->
                            DropdownMenuItem(
                                text = { Text(category.name) },
                                onClick = {
                                    categoryId = category.id
                                    expanded = false
                                },
                            )
                        }
                    }
                }

                androidx.compose.foundation.layout.Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Expected amount (optional)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )

                if (error != null) {
                    androidx.compose.foundation.layout.Spacer(Modifier.height(8.dp))
                    Text(error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }

                androidx.compose.foundation.layout.Spacer(Modifier.height(14.dp))
                Button(
                    onClick = { viewModel.check(store, categoryId, amount) },
                    enabled = !checking && categoryId.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (checking) "Checking…" else "Check this purchase")
                }
            }
        }

        result?.let { ResultCard(it) }

        SectionCard(title = "How answers are made") {
            Text(
                "A healthy clothing budget cannot spend money already reserved for rent. " +
                    "The recommended maximum is always the smaller of Safe-to-Spend and the category's remaining budget.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            androidx.compose.foundation.layout.Spacer(Modifier.height(6.dp))
            Text(
                "Location-based reminders arrive with a later Android phase. This version never requests or stores GPS data.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ResultCard(result: ShoppingResult) {
    SectionCard(title = result.storeName, subtitle = result.category.categoryName) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    result.message,
                    style = MaterialTheme.typography.bodyMedium,
                )
                androidx.compose.foundation.layout.Spacer(Modifier.height(8.dp))
                if (result.purchase != null) {
                    Pill(
                        if (result.purchase.allowed) "Recommended" else "Not recommended",
                        if (result.purchase.allowed) PillTone.Positive else PillTone.Danger,
                    )
                }
            }
        }

        androidx.compose.foundation.layout.Spacer(Modifier.height(14.dp))
        Text(
            "MAX RECOMMENDED",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            formatMoney(result.category.maxSafePurchase),
            style = MaterialTheme.typography.headlineSmall.merge(NumberStyle),
        )
        Text(
            "Category remaining ${formatMoney(result.category.remaining)} · Safe-to-Spend ${formatMoney(result.safeToSpend.amount)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (result.purchase != null) {
            androidx.compose.foundation.layout.Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("After this purchase", style = MaterialTheme.typography.bodySmall)
                MoneyText(result.purchase.categoryRemainingAfter, style = MaterialTheme.typography.bodySmall)
            }
            Text(
                if (result.billsCovered) "Your upcoming bills stay covered." else "This plan leaves bills short.",
                style = MaterialTheme.typography.bodySmall,
                color = if (result.billsCovered) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            )
        }
    }
}
