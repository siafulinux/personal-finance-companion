package com.pfc.companion.util

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val shortDate = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)
private val monthTitle = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.US)

fun parseAmount(value: String?): BigDecimal =
    value?.takeIf { it.isNotBlank() }?.toBigDecimalOrNull() ?: BigDecimal.ZERO

/** Formats an exact decimal string as "$1,234.56", keeping the sign explicit. */
fun formatMoney(value: String?): String {
    val amount = value?.toBigDecimalOrNull() ?: return "—"
    val rounded = amount.setScale(2, RoundingMode.HALF_UP)
    val sign = if (rounded.signum() < 0) "-" else ""
    return "$sign$${rounded.abs().toPlainString().formatThousands()}"
}

private fun String.formatThousands(): String {
    val parts = split(".")
    val whole = parts[0]
    val grouped = whole.reversed().chunked(3).joinToString(",").reversed()
    return if (parts.size > 1) "$grouped.${parts[1]}" else grouped
}

fun formatSignedMoney(value: String?): String {
    val amount = value?.toBigDecimalOrNull() ?: return "—"
    val sign = if (amount.signum() > 0) "+" else ""
    return sign + formatMoney(value)
}

fun formatPercent(value: String?): String {
    val amount = value?.toBigDecimalOrNull() ?: return "—"
    return "${amount.setScale(0, RoundingMode.HALF_UP)}%"
}

fun formatDate(value: String?): String {
    if (value.isNullOrBlank()) return "—"
    return runCatching { LocalDate.parse(value.take(10)).format(shortDate) }.getOrDefault(value)
}

fun formatMonth(year: Int, month: Int): String =
    LocalDate.of(year, month, 1).format(monthTitle)

fun relativeDueLabel(dueDate: String, today: LocalDate = LocalDate.now()): String {
    val due = runCatching { LocalDate.parse(dueDate.take(10)) }.getOrNull() ?: return formatDate(dueDate)
    val days = java.time.temporal.ChronoUnit.DAYS.between(today, due).toInt()
    return when {
        days == 0 -> "Due today"
        days == 1 -> "Due tomorrow"
        days == -1 -> "Overdue by 1 day"
        days < 0 -> "Overdue by ${-days} days"
        days <= 14 -> "Due in $days days"
        else -> "In $days days"
    }
}

fun accountTypeLabel(type: String): String = when (type) {
    "checking" -> "Checking"
    "savings" -> "Savings"
    "cash" -> "Cash"
    "digital_wallet" -> "Digital wallet"
    "payment_app" -> "Payment app"
    "credit_card" -> "Credit card"
    else -> "Account"
}

fun txTypeLabel(type: String): String = when (type) {
    "income" -> "Income"
    "purchase" -> "Purchase"
    "bill_payment" -> "Bill payment"
    "refund" -> "Refund"
    "transfer" -> "Transfer"
    "adjustment" -> "Adjustment"
    else -> type
}
