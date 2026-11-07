package com.pfc.companion.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TransactionDraftTest {
    private val accounts = setOf("acc-1", "acc-2")

    private val valid = TransactionDraft(
        txType = "purchase",
        amount = "12.34",
        txnDate = "2026-11-02",
        description = "Lunch",
        accountId = "acc-1",
    )

    @Test
    fun `accepts a normal expense`() {
        assertNull(valid.validate(accounts))
    }

    @Test
    fun `accepts income and refund entries with the shared contract`() {
        val income = valid.copy(txType = "income", description = "Paycheck")
        assertNull(income.validate(accounts))
        assertEquals("income", income.toCreateBody().txType)

        val refund = valid.copy(txType = "refund", description = "Returned jacket")
        assertNull(refund.validate(accounts))
        assertEquals("refund", refund.toCreateBody().txType)
    }

    @Test
    fun `rejects missing account, description, amount and bad dates`() {
        assertEquals("Choose an account.", valid.copy(accountId = "").validate(accounts))
        assertEquals("Add a short description.", valid.copy(description = "  ").validate(accounts))
        assertEquals("Enter an amount above zero.", valid.copy(amount = "0").validate(accounts))
        assertEquals("Enter an amount above zero.", valid.copy(amount = "-5.00").validate(accounts))
        assertEquals("Enter an amount above zero.", valid.copy(amount = "abc").validate(accounts))
        assertEquals("Use at most two decimals.", valid.copy(amount = "1.234").validate(accounts))
        assertEquals("Choose a valid date.", valid.copy(txnDate = "11/02/2026").validate(accounts))
    }

    @Test
    fun `transfers need a distinct destination`() {
        val transfer = valid.copy(txType = "transfer", transferAccountId = "")
        assertEquals("Choose the destination account.", transfer.validate(accounts))
        assertEquals("A transfer needs two different accounts.", transfer.copy(transferAccountId = "acc-1").validate(accounts))
        assertNull(transfer.copy(transferAccountId = "acc-2").validate(accounts))
    }

    @Test
    fun `create body trims values, tags and transfer fields`() {
        val body = valid.copy(
            description = "  Lunch  ",
            merchant = " Cafe ",
            tags = "work, reimbursable, work",
            notes = " note ",
        ).toCreateBody()

        assertEquals("Lunch", body.description)
        assertEquals("Cafe", body.merchant)
        assertEquals(listOf("work", "reimbursable"), body.tags)
        assertEquals("note", body.notes)
        assertNull(body.transferAccountId)

        val transfer = valid.copy(
            txType = "transfer",
            categoryId = "cat-1",
            transferAccountId = "acc-2",
        ).toCreateBody()
        assertNull(transfer.categoryId)
        assertEquals("acc-2", transfer.transferAccountId)
    }

    @Test
    fun `patch body clears optional fields explicitly`() {
        val json = valid.copy(merchant = "", categoryId = "", notes = "").toPatchJson().toString()
        assertTrue(json.contains("\"merchant\":null"))
        assertTrue(json.contains("\"category_id\":null"))
        assertTrue(json.contains("\"notes\":null"))
        assertTrue(json.contains("\"transfer_account_id\":null"))
        assertTrue(json.contains("\"amount\":\"12.34\""))
    }

    @Test
    fun `draft restores from an existing transaction`() {
        val transaction = kotlinx.serialization.json.Json {
            ignoreUnknownKeys = true
        }.decodeFromString(Transaction.serializer(), com.pfc.companion.testing.TRANSACTION_JSON)

        val draft = TransactionDraft.from(transaction)
        assertEquals("Coffee", draft.description)
        assertEquals("2026-11-02", draft.txnDate)
        assertEquals("acc-1", draft.accountId)
        assertEquals("cat-1", draft.categoryId)
        assertEquals("4.50", draft.amount)
        assertNull(draft.validate(accounts))
    }
}
