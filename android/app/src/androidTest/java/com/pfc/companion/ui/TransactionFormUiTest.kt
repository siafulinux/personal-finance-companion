package com.pfc.companion.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.pfc.companion.data.Account
import com.pfc.companion.data.Category
import com.pfc.companion.data.TransactionDraft
import com.pfc.companion.ui.screens.TransactionFormContent
import com.pfc.companion.ui.theme.CompanionTheme
import org.junit.Rule
import org.junit.Test

class TransactionFormUiTest {
    @get:Rule
    val composeRule = createComposeRule()

    private val accounts = listOf(
        Account(id = "acc-1", name = "Checking", accountType = "checking", balance = "500.00"),
        Account(id = "acc-2", name = "Savings", accountType = "savings", balance = "900.00"),
    )
    private val categories = listOf(Category(id = "cat-1", name = "Groceries"))

    @Test
    fun showsFieldsAndBlocksAnEmptySubmit() {
        composeRule.setContent {
            CompanionTheme {
                var draft by remember { mutableStateOf(TransactionDraft(accountId = "acc-1")) }
                var error by remember { mutableStateOf<String?>(null) }
                TransactionFormContent(
                    draft = draft,
                    accounts = accounts,
                    categories = categories,
                    editing = false,
                    saving = false,
                    error = error,
                    onChange = { draft = it },
                    onSubmit = {
                        error = draft.validate(accounts.map { it.id }.toSet())
                    },
                    onCancel = {},
                )
            }
        }

        composeRule.onNodeWithText("New transaction").assertIsDisplayed()
        composeRule.onNodeWithText("Record transaction").performScrollTo().performClick()
        composeRule.onNodeWithText("Add a short description.").assertExists()
    }

    @Test
    fun acceptsAValidEntry() {
        composeRule.setContent {
            CompanionTheme {
                var draft by remember { mutableStateOf(TransactionDraft(accountId = "acc-1")) }
                var error by remember { mutableStateOf<String?>(null) }
                var saved by remember { mutableStateOf(false) }
                TransactionFormContent(
                    draft = draft,
                    accounts = accounts,
                    categories = categories,
                    editing = false,
                    saving = false,
                    error = error,
                    onChange = { draft = it },
                    onSubmit = {
                        error = draft.validate(accounts.map { it.id }.toSet())
                        if (error == null) saved = true
                    },
                    onCancel = {},
                )
                if (saved) {
                    androidx.compose.material3.Text("Saved ${draft.amount}", modifier = androidx.compose.ui.Modifier)
                }
            }
        }

        composeRule.onNodeWithTag("tx-description").performTextInput("Coffee")
        composeRule.onNodeWithTag("tx-amount").performTextInput("12.50")
        composeRule.onNodeWithText("Record transaction").performScrollTo().performClick()
        composeRule.onNodeWithText("Saved 12.50").assertExists()
    }
}
