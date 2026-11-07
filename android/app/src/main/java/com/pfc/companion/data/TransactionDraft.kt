package com.pfc.companion.data

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.math.BigDecimal
import java.time.LocalDate

/**
 * Form state and validation for creating or editing a transaction. Validation mirrors
 * the backend contract, but the server remains the final authority.
 */
data class TransactionDraft(
    val txType: String = "purchase",
    val amount: String = "",
    val txnDate: String = LocalDate.now().toString(),
    val description: String = "",
    val merchant: String = "",
    val accountId: String = "",
    val transferAccountId: String = "",
    val categoryId: String = "",
    val status: String = "posted",
    val notes: String = "",
    val tags: String = "",
) {
    val isTransfer: Boolean get() = txType == "transfer"

    fun parsedAmount(): BigDecimal? =
        amount.trim().toBigDecimalOrNull()?.takeIf { it.signum() > 0 && it.scale() <= 2 }

    fun tagsList(): List<String> =
        tags.split(",")
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
            .take(10)

    fun validate(activeAccountIds: Set<String>): String? {
        if (accountId.isBlank()) return "Choose an account."
        if (accountId !in activeAccountIds) return "That account is no longer available."
        if (description.isBlank()) return "Add a short description."
        val parsed = amount.trim().toBigDecimalOrNull()
            ?: return "Enter an amount above zero."
        if (parsed.signum() <= 0) return "Enter an amount above zero."
        if (parsed.scale() > 2) return "Use at most two decimals."
        if (runCatching { LocalDate.parse(txnDate) }.isFailure) return "Choose a valid date."
        if (isTransfer) {
            if (transferAccountId.isBlank()) return "Choose the destination account."
            if (transferAccountId == accountId) return "A transfer needs two different accounts."
            if (transferAccountId !in activeAccountIds) return "That destination account is no longer available."
        }
        return null
    }

    fun toCreateBody(): TransactionWrite = TransactionWrite(
        accountId = accountId,
        description = description.trim(),
        merchant = merchant.trim().ifBlank { null },
        amount = amount.trim(),
        txType = txType,
        status = status,
        txnDate = txnDate,
        categoryId = categoryId.takeIf { it.isNotBlank() }.takeUnless { isTransfer },
        notes = notes.trim().ifBlank { null },
        tags = tagsList(),
        transferAccountId = transferAccountId.ifBlank { null }.takeIf { isTransfer },
    )

    /**
     * PATCH bodies include explicit nulls so clearing a category, merchant, note or
     * transfer destination actually clears it on the server.
     */
    fun toPatchJson(): JsonObject = buildJsonObject {
        put("account_id", accountId)
        put("description", description.trim())
        putNullable("merchant", merchant.trim())
        put("amount", amount.trim())
        put("tx_type", txType)
        put("status", status)
        put("txn_date", txnDate)
        putNullable("category_id", categoryId.takeUnless { isTransfer })
        putNullable("notes", notes.trim())
        put("tags", JsonArray(tagsList().map(::JsonPrimitive)))
        putNullable("transfer_account_id", transferAccountId.takeIf { isTransfer })
    }

    private fun JsonObjectBuilder.putNullable(key: String, value: String?) {
        put(key, if (value.isNullOrBlank()) JsonNull else JsonPrimitive(value))
    }

    companion object {
        fun from(transaction: Transaction): TransactionDraft = TransactionDraft(
            txType = transaction.txType,
            amount = transaction.amount,
            txnDate = transaction.txnDate.take(10),
            description = transaction.description,
            merchant = transaction.merchant.orEmpty(),
            accountId = transaction.accountId,
            transferAccountId = transaction.transferAccountId.orEmpty(),
            categoryId = transaction.categoryId.orEmpty(),
            status = transaction.status,
            notes = transaction.notes.orEmpty(),
            tags = transaction.tags.joinToString(", "),
        )
    }
}
