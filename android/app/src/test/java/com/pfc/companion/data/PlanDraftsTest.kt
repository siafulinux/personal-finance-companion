package com.pfc.companion.data

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The drafts are what stand between a form and the API, so these cover the two
 * things that can go wrong silently: a body that omits or invents a field, and a
 * validation rule that lets an impossible value through.
 */
class PlanDraftsTest {

    // --- BillDraft ---------------------------------------------------------

    @Test
    fun `bill needs a name and a positive amount`() {
        assertEquals("Give this bill a name.", BillDraft().validate())
        assertEquals(
            "Enter the expected amount.",
            BillDraft(name = "Internet").validate(),
        )
        assertEquals(
            "Enter an amount above zero.",
            BillDraft(name = "Internet", expectedAmount = "0").validate(),
        )
        assertNull(BillDraft(name = "Internet", expectedAmount = "85.00").validate())
    }

    @Test
    fun `a minimum above the expected amount is rejected`() {
        val draft = BillDraft(
            name = "Internet",
            expectedAmount = "85.00",
            minimumAmount = "90.00",
        )
        assertEquals("The minimum cannot exceed the expected amount.", draft.validate())
    }

    @Test
    fun `custom schedules need an interval`() {
        val missing = BillDraft(
            name = "Water",
            expectedAmount = "40.00",
            frequency = "custom",
        )
        assertEquals("A custom schedule needs an interval in days.", missing.validate())

        val zero = missing.copy(customIntervalDays = "0")
        assertEquals("The interval must be at least one day.", zero.validate())

        assertNull(missing.copy(customIntervalDays = "45").validate())
    }

    @Test
    fun `creating sends the anchor date and editing leaves it alone`() {
        val draft = BillDraft(
            name = "Internet",
            merchant = "Comcast",
            expectedAmount = "85.00",
            anchorDate = "2026-12-01",
            frequency = "monthly",
        )
        val create = draft.toJson(editing = false)
        assertEquals("2026-12-01", create["anchor_date"]!!.jsonPrimitive.content)

        // The server treats the anchor as the schedule's origin; a PATCH that
        // repeated it could rewrite occurrences already generated.
        val update = draft.toJson(editing = true)
        assertFalse(update.containsKey("anchor_date"))
        assertEquals("Internet", update["name"]!!.jsonPrimitive.content)
    }

    @Test
    fun `blank optional text is cleared rather than dropped`() {
        val body = BillDraft(name = "Rent", expectedAmount = "1500.00", merchant = "").toJson(false)
        assertTrue(body.containsKey("merchant"))
        assertEquals("null", body["merchant"].toString())
        assertEquals("null", body["minimum_amount"].toString())
    }

    @Test
    fun `a non-custom bill always sends a null interval`() {
        val body = BillDraft(name = "Rent", expectedAmount = "1500.00").toJson(false)
        assertEquals("null", body["custom_interval_days"].toString())
    }

    @Test
    fun `draft round-trips from a stored bill`() {
        val bill = Bill(
            id = "bill-1",
            name = "Internet",
            merchant = "Comcast",
            expectedAmount = "85.00",
            minimumAmount = "80.00",
            anchorDate = "2026-11-15",
            frequency = "monthly",
            categoryId = "cat-2",
            notes = "Auto-pay",
            isActive = false,
        )
        val draft = BillDraft.from(bill)
        assertEquals("Internet", draft.name)
        assertEquals("2026-11-15", draft.anchorDate)
        assertEquals("cat-2", draft.categoryId)
        assertFalse(draft.isActive)
    }

    // --- IncomeDraft -------------------------------------------------------

    @Test
    fun `income validates amount and payday`() {
        assertEquals("Give this income a name.", IncomeDraft().validate())
        assertEquals(
            "Enter the amount.",
            IncomeDraft(name = "Paycheck").validate(),
        )
        assertEquals(
            "The next payday must be a real date.",
            IncomeDraft(name = "Paycheck", amount = "2400", nextPayday = "2026-13-01").validate(),
        )
        assertNull(
            IncomeDraft(name = "Paycheck", amount = "2400", nextPayday = "2026-11-14").validate(),
        )
    }

    @Test
    fun `income sends the payday, and clearing it sends null`() {
        val withPayday = IncomeDraft(
            name = "Paycheck",
            amount = "2400",
            frequency = "biweekly",
            nextPayday = "2026-11-14",
        ).toJson(editing = false)
        assertEquals("2026-11-14", withPayday["next_payday"]!!.jsonPrimitive.content)

        val cleared = withPayday.let {
            IncomeDraft(name = "Paycheck", amount = "2400", frequency = "biweekly")
                .toJson(editing = true)
        }
        assertEquals("null", cleared["next_payday"].toString())
        assertEquals("true", cleared["is_active"].toString())
    }

    // --- BudgetDraft -------------------------------------------------------

    @Test
    fun `budget keeps only funded categories and drops the rest`() {
        val draft = BudgetDraft(
            plannedIncome = "4800",
            allocations = listOf(
                BudgetAllocationDraft("cat-1", "120.00", carryover = true, name = "Groceries"),
                BudgetAllocationDraft("cat-2", "0.00", name = "Hobbies"),
                BudgetAllocationDraft("cat-3", "40.00", name = "Transport"),
            ),
        )
        val body = draft.toJson()
        val allocations = body["allocations"]!!.jsonArray
        assertEquals(2, allocations.size)
        assertEquals("cat-1", allocations[0].jsonObject["category_id"]!!.jsonPrimitive.content)
        assertEquals("true", allocations[0].jsonObject["carryover_enabled"].toString())
        assertEquals("4800", body["planned_income"]!!.jsonPrimitive.content)
    }

    @Test
    fun `blank planned income is sent as null`() {
        val body = BudgetDraft(plannedIncome = "").toJson()
        assertEquals("null", body["planned_income"].toString())
        assertEquals(0, body["allocations"]!!.jsonArray.size)
    }

    @Test
    fun `budget rejects non-numeric and negative limits`() {
        assertNotNull(BudgetDraft(plannedIncome = "lots").validate())
        assertNotNull(BudgetDraft(allocations = listOf(BudgetAllocationDraft("c", "abc"))).validate())
        assertNotNull(BudgetDraft(allocations = listOf(BudgetAllocationDraft("c", "-5"))).validate())
        assertNull(BudgetDraft(plannedIncome = "4800", allocations = listOf(BudgetAllocationDraft("c", "10"))).validate())
    }

    @Test
    fun `budget seeds from the summary and includes unfunded categories`() {
        val summary = BudgetSummary(
            id = "budget-1",
            year = 2026,
            month = 11,
            plannedIncome = "4800",
            rows = listOf(
                BudgetRow(
                    categoryId = "cat-1",
                    categoryName = "Groceries",
                    allocated = "300.00",
                    carryoverEnabled = true,
                ),
            ),
        )
        val categories = listOf(
            Category(id = "cat-1", name = "Groceries"),
            Category(id = "cat-2", name = "Transport"),
        )
        val draft = BudgetDraft.from(summary, categories)
        assertEquals("4800", draft.plannedIncome)
        assertEquals(2, draft.allocations.size)
        assertEquals("300.00", draft.allocations.first { it.categoryId == "cat-1" }.amount)
        assertTrue(draft.allocations.first { it.categoryId == "cat-1" }.carryover)
        assertEquals("0.00", draft.allocations.first { it.categoryId == "cat-2" }.amount)
        assertEquals("Transport", draft.allocations.first { it.categoryId == "cat-2" }.name)
    }

    // --- Settings drafts ---------------------------------------------------

    @Test
    fun `rules enforce the server's bounds`() {
        assertNotNull(RulesDraft(horizon = "0").validate())
        assertNotNull(RulesDraft(horizon = "90").validate())
        assertNotNull(RulesDraft(autoMatchThreshold = "1.4").validate())
        assertNotNull(RulesDraft(suggestionThreshold = "0.99").validate())
        assertNull(RulesDraft().validate())
    }

    @Test
    fun `rules send every calculation input`() {
        val body: JsonObject = RulesDraft(
            buffer = "200.00",
            horizon = "21",
            includePending = false,
            autoMatch = false,
        ).toJson()
        assertEquals("21", body["safe_to_spend_horizon_days"]!!.jsonPrimitive.content)
        assertEquals("false", body["include_pending_debits"].toString())
        assertEquals("false", body["auto_bill_matching"].toString())
        assertEquals("0.850", body["auto_match_threshold"]!!.jsonPrimitive.content)
    }

    @Test
    fun `quiet hours must be a time or blank`() {
        assertNotNull(NotificationDraft(quietStart = "22").validate())
        assertNull(NotificationDraft(quietStart = "22:00", quietEnd = "07:00").validate())
        assertNull(NotificationDraft().validate())
    }

    @Test
    fun `notification times clear to null and carry the timezone`() {
        val body = NotificationDraft(quietStart = "", quietEnd = "").toJson("America/New_York")
        assertEquals("null", body["quiet_hours_start"].toString())
        assertEquals("null", body["quiet_hours_end"].toString())
        assertEquals("America/New_York", body["quiet_hours_timezone"]!!.jsonPrimitive.content)
    }
}
