package com.pfc.companion.util

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class FormatTest {
    @Test
    fun `formats exact money strings with grouping`() {
        assertEquals("$1,234.50", formatMoney("1234.5"))
        assertEquals("-$18.75", formatMoney("-18.75"))
        assertEquals("$0.00", formatMoney("0"))
        assertEquals("—", formatMoney(null))
    }

    @Test
    fun `signs positive amounts only when asked`() {
        assertEquals("+$2,400.00", formatSignedMoney("2400.00"))
        assertEquals("-$9.50", formatSignedMoney("-9.50"))
    }

    @Test
    fun `formats percents without decimals`() {
        assertEquals("54%", formatPercent("53.6"))
    }

    @Test
    fun `formats dates independently of locale`() {
        assertEquals("Nov 2, 2026", formatDate("2026-11-02"))
        assertEquals("November 2026", formatMonth(2026, 11))
    }

    @Test
    fun `describes due dates relative to a fixed today`() {
        val today = LocalDate.of(2026, 11, 2)
        assertEquals("Due today", relativeDueLabel("2026-11-02", today))
        assertEquals("Due tomorrow", relativeDueLabel("2026-11-03", today))
        assertEquals("Overdue by 2 days", relativeDueLabel("2026-10-31", today))
        assertEquals("Due in 6 days", relativeDueLabel("2026-11-08", today))
        assertEquals("In 30 days", relativeDueLabel("2026-12-02", today))
    }
}
