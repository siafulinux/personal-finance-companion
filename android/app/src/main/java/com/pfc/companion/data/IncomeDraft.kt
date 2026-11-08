package com.pfc.companion.data

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.LocalDate

/**
 * Form state and validation for an income source.
 *
 * The next payday is what first-run setup collects, and what Safe-to-Spend uses
 * as the end of its horizon, so editing it here changes the deterministic
 * calculation rather than a display value.
 */
data class IncomeDraft(
    val name: String = "",
    val amount: String = "",
    val frequency: String = "biweekly",
    val nextPayday: String = "",
    val isActive: Boolean = true,
) {
    fun validate(): String? {
        if (name.isBlank()) return "Give this income a name."
        val parsed = amount.trim().toBigDecimalOrNull() ?: return "Enter the amount."
        if (parsed.signum() <= 0) return "Enter an amount above zero."
        if (parsed.scale() > 2) return "Use at most two decimals."
        if (nextPayday.isNotBlank() && runCatching { LocalDate.parse(nextPayday) }.isFailure) {
            return "The next payday must be a real date."
        }
        return null
    }

    fun toJson(editing: Boolean): JsonObject = buildJsonObject {
        put("name", name.trim())
        put("amount", amount.trim())
        put("frequency", frequency)
        put("next_payday", if (nextPayday.isBlank()) JsonNull else JsonPrimitive(nextPayday))
        if (editing) put("is_active", isActive)
    }

    companion object {
        fun from(source: IncomeSource): IncomeDraft = IncomeDraft(
            name = source.name,
            amount = source.amount,
            frequency = source.frequency,
            nextPayday = source.nextPayday?.take(10).orEmpty(),
            isActive = source.isActive,
        )
    }
}
