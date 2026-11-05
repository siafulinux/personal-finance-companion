package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.pfc.companion.data.Account
import com.pfc.companion.data.Category
import com.pfc.companion.data.TransactionDraft
import com.pfc.companion.ui.components.PickerField
import com.pfc.companion.util.formatDate
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset

private val transactionTypes = listOf(
    "purchase" to "Purchase",
    "bill_payment" to "Bill or card payment",
    "income" to "Income",
    "refund" to "Refund",
    "transfer" to "Internal transfer",
)

private val statuses = listOf("posted" to "Posted", "pending" to "Pending")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionFormContent(
    draft: TransactionDraft,
    accounts: List<Account>,
    categories: List<Category>,
    editing: Boolean,
    saving: Boolean,
    error: String?,
    onChange: (TransactionDraft) -> Unit,
    onSubmit: () -> Unit,
    onCancel: () -> Unit,
) {
    var showDatePicker by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            if (editing) "Edit transaction" else "New transaction",
            style = MaterialTheme.typography.headlineSmall,
        )
        Text(
            "Amounts are always positive; the type sets the direction. The server keeps the authoritative balance.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PickerField(
                label = "Type",
                selected = transactionTypes.firstOrNull { it.first == draft.txType }?.second ?: "Purchase",
                options = transactionTypes,
                modifier = Modifier.weight(1f),
                onSelect = { onChange(draft.copy(txType = it, categoryId = if (it == "transfer") "" else draft.categoryId)) },
            )
            PickerField(
                label = "Status",
                selected = statuses.firstOrNull { it.first == draft.status }?.second ?: "Posted",
                options = statuses,
                modifier = Modifier.weight(1f),
                onSelect = { onChange(draft.copy(status = it)) },
            )
        }

        OutlinedTextField(
            value = draft.description,
            onValueChange = { onChange(draft.copy(description = it.take(255))) },
            label = { Text("Description") },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("tx-description"),
        )

        OutlinedTextField(
            value = draft.amount,
            onValueChange = { value ->
                if (value.isEmpty() || value.matches(Regex("^\\d{0,9}(\\.\\d{0,2})?$"))) {
                    onChange(draft.copy(amount = value))
                }
            },
            label = { Text("Amount") },
            prefix = { Text("$") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier
                .fillMaxWidth()
                .testTag("tx-amount"),
        )

        OutlinedTextField(
            value = formatDate(draft.txnDate),
            onValueChange = {},
            readOnly = true,
            label = { Text("Date") },
            trailingIcon = {
                TextButton(onClick = { showDatePicker = true }) { Text("Change") }
            },
            modifier = Modifier.fillMaxWidth(),
        )

        PickerField(
            label = "Account",
            selected = accounts.firstOrNull { it.id == draft.accountId }?.name ?: "Choose an account",
            options = accounts.map { it.id to it.name },
            modifier = Modifier.fillMaxWidth(),
            onSelect = { onChange(draft.copy(accountId = it)) },
        )

        if (draft.isTransfer) {
            PickerField(
                label = "Transfer to",
                selected = accounts.firstOrNull { it.id == draft.transferAccountId }?.name
                    ?: "Choose destination",
                options = accounts.filter { it.id != draft.accountId }.map { it.id to it.name },
                modifier = Modifier.fillMaxWidth(),
                onSelect = { onChange(draft.copy(transferAccountId = it)) },
            )
            Text(
                "Transfers move money between your accounts and never count as income or spending.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            PickerField(
                label = "Category",
                selected = categories.firstOrNull { it.id == draft.categoryId }?.name ?: "Uncategorized",
                options = listOf("" to "Uncategorized") + categories.map { it.id to it.name },
                modifier = Modifier.fillMaxWidth(),
                onSelect = { onChange(draft.copy(categoryId = it)) },
            )
        }

        OutlinedTextField(
            value = draft.merchant,
            onValueChange = { onChange(draft.copy(merchant = it.take(160))) },
            label = { Text("Merchant (optional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = draft.tags,
            onValueChange = { onChange(draft.copy(tags = it)) },
            label = { Text("Tags (comma separated)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = draft.notes,
            onValueChange = { onChange(draft.copy(notes = it.take(2000))) },
            label = { Text("Notes (optional)") },
            minLines = 2,
            modifier = Modifier.fillMaxWidth(),
        )

        if (error != null) {
            Text(
                text = error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OutlinedButton(onClick = onCancel, enabled = !saving, modifier = Modifier.weight(1f)) {
                Text("Cancel")
            }
            Button(onClick = onSubmit, enabled = !saving, modifier = Modifier.weight(1f)) {
                Text(if (saving) "Saving…" else if (editing) "Save changes" else "Record transaction")
            }
        }
    }

    if (showDatePicker) {
        val initial = runCatching { LocalDate.parse(draft.txnDate) }.getOrDefault(LocalDate.now())
        val today = LocalDate.now()
        val pickerState = rememberDatePickerState(
            initialSelectedDateMillis = initial.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli(),
            selectableDates = object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long): Boolean =
                    Instant.ofEpochMilli(utcTimeMillis).atZone(ZoneId.systemDefault()).toLocalDate() <= today
            },
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { millis ->
                        val picked = Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate()
                        onChange(draft.copy(txnDate = picked.toString()))
                    }
                    showDatePicker = false
                }) { Text("Use date") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("Cancel") }
            },
        ) {
            DatePicker(state = pickerState)
        }
    }
}
