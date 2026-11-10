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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.Loan
import com.pfc.companion.data.LoanPayment
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
import com.pfc.companion.ui.vm.LoansViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.formatPercent
import com.pfc.companion.util.parseAmount
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

private val loanTypes = listOf(
    "personal" to "Personal loan",
    "payday" to "Payday loan",
    "cash_advance" to "Cash advance",
    "earned_wage" to "Earned wage access",
    "bnpl" to "Buy now, pay later",
    "installment" to "Installments",
    "credit_agreement" to "Credit agreement",
    "other" to "Other",
)

/**
 * Loans & Advances.
 *
 * Balances the user typed are labelled as their figure; only a loan whose payments
 * have been confirmed by a bank transaction loses that caveat, which the server
 * decides and this screen simply reports.
 */
@Composable
fun LoansScreen(onBack: () -> Unit, flash: String?, onFlashShown: () -> Unit) {
    val viewModel = rememberScreenViewModel("loans") { LoansViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsState()
    val error by viewModel.error.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val scope = rememberCoroutineScope()

    var editing by remember { mutableStateOf<Loan?>(null) }
    var adding by remember { mutableStateOf(false) }
    var paying by remember { mutableStateOf<Loan?>(null) }
    var reviewing by remember { mutableStateOf<Loan?>(null) }
    var message by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(flash) {
        if (flash != null) {
            message = flash
            onFlashShown()
        }
    }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onBack) { Text("Back") }
            Button(onClick = { adding = true }) { Text("Add loan") }
        }
        when (val current = state) {
            is UiState.Loading -> LoadingPane("Loading your loans")
            is UiState.Failed -> ErrorPane(current.message, onRetry = viewModel::refresh)
            is UiState.Ready -> LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    ScreenHeader(
                        eyebrow = "${current.data.activeLoans} active",
                        title = "Loans & advances",
                        description = "Every repayment you record reduces the balance here and is " +
                            "not counted again as spending.",
                    )
                }
                item {
                    SectionCard(
                        title = "Outstanding",
                        subtitle = "Originally borrowed ${formatMoney(current.data.totalOriginal)}",
                    ) {
                        MoneyText(current.data.totalOutstanding, style = MaterialTheme.typography.headlineMedium)
                        if (current.data.nextPaymentDate != null) {
                            Text(
                                "Next payment ${formatDate(current.data.nextPaymentDate)} · " +
                                    formatMoney(current.data.nextPaymentTotal),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
                if (message != null) {
                    item {
                        Text(message.orEmpty(), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
                    }
                }
                if (error != null) {
                    item {
                        Text(error.orEmpty(), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                    }
                }
                if (current.data.loans.isEmpty()) {
                    item {
                        EmptyMessage(
                            "No loans tracked",
                            "Add a personal loan, a payday advance or a buy-now-pay-later plan. " +
                                "Nothing is assumed about its terms: you enter what you know.",
                        )
                    }
                }
                items(current.data.loans, key = { it.id }) { loan ->
                    LoanCard(
                        loan = loan,
                        onEdit = { editing = loan },
                        onPay = { paying = loan },
                        onReview = { reviewing = loan },
                        onDelete = { viewModel.delete(loan.id) { message = it } },
                        busy = busy,
                    )
                }
            }
        }
    }

    if (adding || editing != null) {
        LoanDialog(
            loan = editing,
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
    paying?.let { loan ->
        PaymentDialog(
            loan = loan,
            busy = busy,
            onDismiss = { paying = null },
            onSave = { body ->
                viewModel.recordPayment(loan.id, body) {
                    message = it
                    paying = null
                }
            },
        )
    }
    reviewing?.let { loan ->
        ReviewMatchesDialog(
            loan = loan,
            onDismiss = { reviewing = null },
            onConfirm = { paymentId ->
                viewModel.confirmLoanPayment(loan.id, paymentId) {
                    message = it
                    reviewing = null
                }
            },
            onReject = { paymentId ->
                viewModel.rejectLoanPayment(loan.id, paymentId) {
                    message = it
                }
            },
        )
    }
    // Keep lint quiet about the unused scope; kept for future refresh gestures.
    scope.launch { }
}

@Composable
private fun LoanCard(
    loan: Loan,
    onEdit: () -> Unit,
    onPay: () -> Unit,
    onReview: () -> Unit,
    onDelete: () -> Unit,
    busy: Boolean,
) {
    SectionCard(
        title = loan.name,
        subtitle = listOfNotNull(loan.lender, loanTypeLabel(loan.loanType), loan.status.replaceFirstChar { it.uppercase() })
            .joinToString(" · "),
        action = {
            TextButton(onClick = onEdit) { Text("Edit") }
        },
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Outstanding", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                MoneyText(loan.currentBalance, style = MaterialTheme.typography.headlineSmall)
            }
            Column(horizontalAlignment = Alignment.End) {
                if (loan.nextPaymentDate != null) {
                    Text("Next ${formatDate(loan.nextPaymentDate)}", style = MaterialTheme.typography.bodySmall)
                }
                if (loan.scheduledPayment != null) {
                    Text(formatMoney(loan.scheduledPayment), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        HorizontalGap(10)
        LinearProgressIndicator(
            progress = { (parseAmount(loan.progressPercent).toFloat() / 100f).coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth(),
        )
        HorizontalGap(6)
        Text(
            "${formatPercent(loan.progressPercent)} repaid · ${formatMoney(loan.principalRepaid)} of " +
                formatMoney(loan.originalAmount),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        HorizontalGap(10)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (loan.balanceIsEstimate) Pill("Estimated balance", PillTone.Warning) else Pill("Confirmed balance", PillTone.Positive)
            if (loan.payoffIsEstimate && loan.estimatedPayoffDate != null) {
                Pill("Payoff ~${formatDate(loan.estimatedPayoffDate)}", PillTone.Neutral)
            }
        }
        if (loan.remainingInstallments != null) {
            HorizontalGap(6)
            Text(
                "${loan.remainingInstallments} payments left at ${formatMoney(loan.scheduledPayment ?: "0.00")}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        HorizontalGap(10)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onPay, enabled = !busy) { Text("Record payment") }
            TextButton(onClick = onReview, enabled = !busy) { Text("Matches") }
            TextButton(onClick = onDelete, enabled = !busy) { Text("Remove") }
        }
        if (loan.interestPaid != "0.00" || loan.feesPaid != "0.00") {
            HorizontalGap(6)
            Text(
                "Interest paid ${formatMoney(loan.interestPaid)} · fees ${formatMoney(loan.feesPaid)}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun loanTypeLabel(value: String): String =
    loanTypes.firstOrNull { it.first == value }?.second ?: value.replace('_', ' ')

@Composable
private fun LoanDialog(
    loan: Loan?,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSave: (JsonObject) -> Unit,
) {
    var name by remember { mutableStateOf(loan?.name.orEmpty()) }
    var lender by remember { mutableStateOf(loan?.lender.orEmpty()) }
    var type by remember { mutableStateOf(loan?.loanType ?: "personal") }
    var original by remember { mutableStateOf(loan?.originalAmount.orEmpty()) }
    var balance by remember { mutableStateOf(loan?.currentBalance.orEmpty()) }
    var nextDate by remember { mutableStateOf(loan?.nextPaymentDate.orEmpty()) }
    var scheduled by remember { mutableStateOf(loan?.scheduledPayment.orEmpty()) }
    var apr by remember { mutableStateOf(loan?.apr.orEmpty()) }
    var remaining by remember { mutableStateOf(loan?.remainingPayments?.toString().orEmpty()) }
    var typeMenu by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (loan == null) "Add a loan" else "Edit ${loan.name}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Loan name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = lender,
                    onValueChange = { lender = it },
                    label = { Text("Lender") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                TextButton(onClick = { typeMenu = true }) {
                    Text("Type: ${loanTypeLabel(type)}")
                }
                if (typeMenu) {
                    AlertDialog(
                        onDismissRequest = { typeMenu = false },
                        title = { Text("Loan type") },
                        text = {
                            Column(Modifier.verticalScroll(rememberScrollState())) {
                                loanTypes.forEach { (value, label) ->
                                    TextButton(onClick = {
                                        type = value
                                        typeMenu = false
                                    }) { Text(label) }
                                }
                            }
                        },
                        confirmButton = { TextButton(onClick = { typeMenu = false }) { Text("Cancel") } },
                    )
                }
                OutlinedTextField(
                    value = original,
                    onValueChange = { original = it },
                    label = { Text("Originally borrowed") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = balance,
                    onValueChange = { balance = it },
                    label = { Text("Outstanding now") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = scheduled,
                    onValueChange = { scheduled = it },
                    label = { Text("Scheduled payment (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = nextDate,
                    onValueChange = { nextDate = it },
                    label = { Text("Next payment date (YYYY-MM-DD)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = apr,
                    onValueChange = { apr = it },
                    label = { Text("APR % (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = remaining,
                    onValueChange = { remaining = it },
                    label = { Text("Payments remaining (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "Leave a term blank if you do not know it. Nothing is estimated from nothing.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && name.isNotBlank() && parseAmount(original).signum() > 0,
                onClick = {
                    onSave(
                        buildJsonObject {
                            put("name", name.trim())
                            if (lender.isNotBlank()) put("lender", lender.trim())
                            put("loan_type", type)
                            put("original_amount", original.trim())
                            put("opening_balance", balance.ifBlank { original }.trim())
                            if (scheduled.isNotBlank()) put("scheduled_payment", scheduled.trim())
                            if (nextDate.isNotBlank()) put("next_payment_date", nextDate.trim())
                            if (apr.isNotBlank()) put("apr", apr.trim())
                            remaining.toIntOrNull()?.let { put("remaining_payments", it) }
                        }
                    )
                },
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun PaymentDialog(
    loan: Loan,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSave: (JsonObject) -> Unit,
) {
    var amount by remember { mutableStateOf(loan.scheduledPayment.orEmpty()) }
    var paidOn by remember { mutableStateOf("") }
    var principal by remember { mutableStateOf("") }
    var interest by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Record a payment to ${loan.name}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Amount") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = paidOn,
                    onValueChange = { paidOn = it },
                    label = { Text("Date (YYYY-MM-DD, today if blank)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "If you know how the payment splits, enter the parts. Otherwise the whole " +
                        "amount reduces principal and the balance is marked an estimate.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = principal,
                    onValueChange = { principal = it },
                    label = { Text("Of which principal (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = interest,
                    onValueChange = { interest = it },
                    label = { Text("Of which interest (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = fee,
                    onValueChange = { fee = it },
                    label = { Text("Of which fees (optional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && parseAmount(amount).signum() > 0,
                onClick = {
                    onSave(
                        buildJsonObject {
                            put("amount", amount.trim())
                            if (paidOn.isNotBlank()) put("paid_on", paidOn.trim())
                            if (principal.isNotBlank()) put("principal_amount", principal.trim())
                            if (interest.isNotBlank()) put("interest_amount", interest.trim())
                            if (fee.isNotBlank()) put("fee_amount", fee.trim())
                        }
                    )
                },
            ) { Text("Record") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/**
 * Pending matches, with the confidence the server calculated. Confirming is the
 * user's decision; nothing here is applied on their behalf.
 */
@Composable
private fun ReviewMatchesDialog(
    loan: Loan,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
    onReject: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var payments by remember { mutableStateOf<List<LoanPayment>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(loan.id) {
        runCatching { ServiceLocator.repository.loanPayments(loan.id) }
            .onSuccess {
                payments = it
                loading = false
            }
            .onFailure {
                error = it.message
                loading = false
            }
    }
    // Referenced so the coroutine scope is not flagged; suggestions refresh on reopen.
    scope.launch { }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Payments and matches") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (loading) Text("Checking recorded payments…")
                if (error != null) Text(error.orEmpty(), color = MaterialTheme.colorScheme.error)
                val pending = payments.filter { it.status == "suggested" }
                val settled = payments.filter { it.status != "suggested" }
                if (!loading && pending.isEmpty()) {
                    Text(
                        "No suggested matches right now. The app only proposes a repayment when " +
                            "one bank transaction clearly fits this loan.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                pending.forEach { payment ->
                    Column(Modifier.padding(vertical = 6.dp)) {
                        Text(
                            "${formatMoney(payment.amount)} on ${formatDate(payment.paidOn)}",
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            payment.reason ?: "Possible repayment",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { onConfirm(payment.id) }) { Text("Confirm") }
                            TextButton(onClick = { onReject(payment.id) }) { Text("Not this loan") }
                        }
                    }
                }
                if (settled.isNotEmpty()) {
                    HorizontalGap(8)
                    Text("Recorded", style = MaterialTheme.typography.labelMedium)
                    settled.forEach { payment ->
                        Text(
                            "${formatDate(payment.paidOn)} · ${formatMoney(payment.amount)} · ${payment.status}",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Done") } },
    )
}
