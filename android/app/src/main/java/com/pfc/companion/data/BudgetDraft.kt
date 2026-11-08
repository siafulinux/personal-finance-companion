package com.pfc.companion.data

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** One category's monthly limit inside the budget editor. */
data class BudgetAllocationDraft(
    val categoryId: String,
    val amount: String = "0.00",
    val carryover: Boolean = false,
    val name: String = "",
)

/**
 * The whole allocation list for a month.
 *
 * The API replaces the set on PATCH rather than patching single rows, so the
 * editor always sends the complete list — a category set to zero is dropped,
 * which is how the web app removes an allocation.
 */
data class BudgetDraft(
    val plannedIncome: String = "",
    val allocations: List<BudgetAllocationDraft> = emptyList(),
) {
    fun withAmount(categoryId: String, amount: String): BudgetDraft = copy(
        allocations = allocations.map { if (it.categoryId == categoryId) it.copy(amount = amount) else it },
    )

    fun withCarryover(categoryId: String, carryover: Boolean): BudgetDraft = copy(
        allocations = allocations.map {
            if (it.categoryId == categoryId) it.copy(carryover = carryover) else it
        },
    )

    /** Categories with a positive limit, which is what the server keeps. */
    fun funded(): List<BudgetAllocationDraft> = allocations.filter { it.parsedAmount()?.signum() == 1 }

    fun validate(): String? {
        if (plannedIncome.isNotBlank()) {
            val planned = plannedIncome.trim().toBigDecimalOrNull()
                ?: return "Planned income is not a number."
            if (planned.scale() > 2) return "Use at most two decimals."
            if (planned.signum() < 0) return "Planned income cannot be negative."
        }
        allocations.forEach { allocation ->
            val parsed = allocation.amount.trim().toBigDecimalOrNull()
                ?: return "${allocation.amount} is not a valid amount."
            if (parsed.scale() > 2) return "Use at most two decimals."
            if (parsed.signum() < 0) return "A limit cannot be negative."
        }
        return null
    }

    fun toJson(): JsonObject = buildJsonObject {
        put(
            "planned_income",
            if (plannedIncome.isBlank()) JsonNull else JsonPrimitive(plannedIncome.trim()),
        )
        put(
            "allocations",
            buildJsonArray {
                funded().forEach { allocation ->
                    addJsonObject {
                        put("category_id", allocation.categoryId)
                        put("amount", allocation.amount.trim())
                        put("carryover_enabled", allocation.carryover)
                    }
                }
            },
        )
    }

    companion object {
        /** Every active category is listed, funded or not, so zeroing one is a visible choice. */
        fun from(budget: BudgetSummary, categories: List<Category>): BudgetDraft {
            val rows = budget.rows.associateBy { it.categoryId }
            return BudgetDraft(
                plannedIncome = budget.plannedIncome.orEmpty(),
                allocations = categories
                    .filter { it.kind != "income" }
                    .map { category ->
                        BudgetAllocationDraft(
                            categoryId = category.id,
                            amount = rows[category.id]?.allocated ?: "0.00",
                            carryover = rows[category.id]?.carryoverEnabled ?: false,
                            name = category.name,
                        )
                    },
            )
        }
    }
}

private fun BudgetAllocationDraft.parsedAmount() = amount.trim().toBigDecimalOrNull()
