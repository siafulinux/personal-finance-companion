package com.pfc.companion.data

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.LocalDate

/**
 * Form state and validation for creating or editing a recurring bill.
 *
 * Validation mirrors the backend contract; the server stays the final authority.
 * [anchorDate] is the first due date the schedule counts from. The web app treats
 * it as write-once — changing it would rewrite occurrence history — so a PATCH
 * omits it and only a create sends it.
 */
data class BillDraft(
    val name: String = "",
    val merchant: String = "",
    val expectedAmount: String = "",
    val minimumAmount: String = "",
    val anchorDate: String = LocalDate.now().toString(),
    val frequency: String = "monthly",
    val customIntervalDays: String = "",
    val accountId: String = "",
    val categoryId: String = "",
    val notes: String = "",
    val isEssential: Boolean = true,
    val reserveInSafeToSpend: Boolean = true,
    val isActive: Boolean = true,
) {
    val isCustom: Boolean get() = frequency == "custom"

    fun validate(): String? {
        if (name.isBlank()) return "Give this bill a name."
        val amount = expectedAmount.trim().toBigDecimalOrNull()
            ?: return "Enter the expected amount."
        if (amount.signum() <= 0) return "Enter an amount above zero."
        if (amount.scale() > 2) return "Use at most two decimals."
        if (minimumAmount.isNotBlank()) {
            val minimum = minimumAmount.trim().toBigDecimalOrNull()
                ?: return "The minimum amount is not a number."
            if (minimum.scale() > 2) return "Use at most two decimals."
            if (minimum.signum() < 0) return "The minimum cannot be negative."
            if (minimum > amount) return "The minimum cannot exceed the expected amount."
        }
        if (runCatching { LocalDate.parse(anchorDate) }.isFailure) {
            return "Choose the first due date."
        }
        if (isCustom) {
            val days = customIntervalDays.trim().toIntOrNull()
                ?: return "A custom schedule needs an interval in days."
            if (days < 1) return "The interval must be at least one day."
        }
        return null
    }

    /**
     * Create includes the anchor date; edit leaves it alone. Blank optional text
     * is sent as an explicit null so clearing a merchant or note actually clears it.
     */
    fun toJson(editing: Boolean): JsonObject = buildJsonObject {
        put("name", name.trim())
        putNullable("merchant", merchant.trim())
        put("expected_amount", expectedAmount.trim())
        putNullable("minimum_amount", minimumAmount.trim())
        put("frequency", frequency)
        put(
            "custom_interval_days",
            if (isCustom) JsonPrimitive(customIntervalDays.trim().toInt()) else JsonNull,
        )
        putNullable("account_id", accountId)
        putNullable("category_id", categoryId)
        putNullable("notes", notes.trim())
        put("is_essential", isEssential)
        put("reserve_in_safe_to_spend", reserveInSafeToSpend)
        put("is_active", isActive)
        if (!editing) put("anchor_date", anchorDate)
    }

    private fun JsonObjectBuilder.putNullable(key: String, value: String?) {
        put(key, if (value.isNullOrBlank()) JsonNull else JsonPrimitive(value))
    }

    companion object {
        fun from(bill: Bill): BillDraft = BillDraft(
            name = bill.name,
            merchant = bill.merchant.orEmpty(),
            expectedAmount = bill.expectedAmount,
            minimumAmount = bill.minimumAmount.orEmpty(),
            anchorDate = bill.anchorDate?.take(10) ?: LocalDate.now().toString(),
            frequency = bill.frequency,
            customIntervalDays = bill.customIntervalDays?.toString().orEmpty(),
            accountId = bill.accountId.orEmpty(),
            categoryId = bill.categoryId.orEmpty(),
            notes = bill.notes.orEmpty(),
            isEssential = bill.isEssential,
            reserveInSafeToSpend = bill.reserveInSafeToSpend,
            isActive = bill.isActive,
        )
    }
}
