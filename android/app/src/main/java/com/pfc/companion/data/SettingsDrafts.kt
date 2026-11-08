package com.pfc.companion.data

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The Safe-to-Spend rules as the settings form holds them.
 *
 * Every value here feeds the deterministic calculation, so the form validates the
 * same bounds the API enforces and leaves the maths itself to the server.
 */
data class RulesDraft(
    val buffer: String = "0.00",
    val horizon: String = "14",
    val autoMatchThreshold: String = "0.850",
    val suggestionThreshold: String = "0.550",
    val toleranceAmount: String = "2.00",
    val tolerancePercent: String = "1.00",
    val includePending: Boolean = true,
    val autoMatch: Boolean = true,
) {
    fun validate(): String? {
        val bufferValue = buffer.trim().toBigDecimalOrNull() ?: return "The buffer is not an amount."
        if (bufferValue.signum() < 0) return "The buffer cannot be negative."
        val days = horizon.trim().toIntOrNull() ?: return "The horizon must be a whole number of days."
        if (days !in 1..60) return "The horizon must be between 1 and 60 days."
        val auto = autoMatchThreshold.trim().toBigDecimalOrNull()
            ?: return "The auto-match threshold is not a number."
        if (auto < "0.5".toBigDecimal() || auto > "1".toBigDecimal()) {
            return "The auto-match threshold must be between 0.5 and 1."
        }
        val suggestion = suggestionThreshold.trim().toBigDecimalOrNull()
            ?: return "The suggestion threshold is not a number."
        if (suggestion.signum() < 0 || suggestion > "0.95".toBigDecimal()) {
            return "The suggestion threshold must be between 0 and 0.95."
        }
        val amount = toleranceAmount.trim().toBigDecimalOrNull()
            ?: return "The amount tolerance is not a number."
        if (amount.signum() < 0) return "The amount tolerance cannot be negative."
        val percent = tolerancePercent.trim().toBigDecimalOrNull()
            ?: return "The percent tolerance is not a number."
        if (percent.signum() < 0 || percent > "50".toBigDecimal()) {
            return "The percent tolerance must be between 0 and 50."
        }
        return null
    }

    fun toJson(): JsonObject = buildJsonObject {
        put("minimum_balance_buffer", buffer.trim())
        put("safe_to_spend_horizon_days", horizon.trim().toInt())
        put("include_pending_debits", includePending)
        put("auto_bill_matching", autoMatch)
        put("match_tolerance_amount", toleranceAmount.trim())
        put("match_tolerance_percent", tolerancePercent.trim())
        put("auto_match_threshold", autoMatchThreshold.trim())
        put("suggestion_threshold", suggestionThreshold.trim())
    }

    companion object {
        fun from(preferences: Preferences): RulesDraft = RulesDraft(
            buffer = preferences.minimumBalanceBuffer,
            horizon = preferences.horizonDays.toString(),
            autoMatchThreshold = preferences.autoMatchThreshold,
            suggestionThreshold = preferences.suggestionThreshold,
            toleranceAmount = preferences.matchToleranceAmount,
            tolerancePercent = preferences.matchTolerancePercent,
            includePending = preferences.includePendingDebits,
            autoMatch = preferences.autoBillMatching,
        )
    }
}

/** Notification toggles and quiet hours. Times are "HH:MM" or blank for unset. */
data class NotificationDraft(
    val shoppingAssistant: Boolean = true,
    val billReminders: Boolean = true,
    val lowMoney: Boolean = true,
    val favoriteStores: Boolean = false,
    val quietStart: String = "",
    val quietEnd: String = "",
) {
    private val timePattern = Regex("^\\d{2}:\\d{2}$")

    fun validate(): String? {
        if (quietStart.isNotBlank() && !timePattern.matches(quietStart)) {
            return "Use HH:MM for the quiet hours."
        }
        if (quietEnd.isNotBlank() && !timePattern.matches(quietEnd)) {
            return "Use HH:MM for the quiet hours."
        }
        return null
    }

    fun toJson(timezone: String): JsonObject = buildJsonObject {
        put("shopping_assistant_enabled", shoppingAssistant)
        put("bill_reminders_enabled", billReminders)
        put("low_money_warnings_enabled", lowMoney)
        put("favorite_store_reminders_enabled", favoriteStores)
        put("quiet_hours_start", quietStart.ifBlank { null }?.let(::JsonPrimitive) ?: JsonNull)
        put("quiet_hours_end", quietEnd.ifBlank { null }?.let(::JsonPrimitive) ?: JsonNull)
        put("quiet_hours_timezone", timezone)
    }

    companion object {
        fun from(preferences: NotificationPreferences): NotificationDraft = NotificationDraft(
            shoppingAssistant = preferences.shoppingAssistantEnabled,
            billReminders = preferences.billRemindersEnabled,
            lowMoney = preferences.lowMoneyWarningsEnabled,
            favoriteStores = preferences.favoriteStoreRemindersEnabled,
            quietStart = preferences.quietHoursStart.orEmpty(),
            quietEnd = preferences.quietHoursEnd.orEmpty(),
        )
    }
}
