package com.pfc.companion.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for the shared finance API. Amounts are decimal strings on the wire,
 * so they stay exact until the UI formats them for display.
 */

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

@Serializable
data class ChangePasswordRequest(
    @SerialName("current_password") val currentPassword: String,
    @SerialName("new_password") val newPassword: String,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
)

/** The public facts a server reports about itself (`GET /api/v1/server/info`). */
@Serializable
data class ServerInfo(
    @SerialName("app_name") val appName: String = "",
    @SerialName("server_name") val serverName: String = "",
    val version: String = "",
    @SerialName("api_version") val apiVersion: Int = 0,
    @SerialName("min_client_api_version") val minClientApiVersion: Int = 0,
    @SerialName("api_base_url") val apiBaseUrl: String = "",
    @SerialName("web_url") val webUrl: String = "",
    val status: String = "",
    @SerialName("registration_enabled") val registrationEnabled: Boolean = false,
    @SerialName("setup_required") val setupRequired: Boolean = false,
) {
    /** The web app still needs its owner to finish the first-run wizard. */
    val needsSetup: Boolean get() = setupRequired
}

@Serializable
data class User(
    val id: String,
    val email: String,
    @SerialName("display_name") val displayName: String,
    val timezone: String = "UTC",
    val currency: String = "USD",
    @SerialName("is_demo") val isDemo: Boolean = false,
    @SerialName("onboarding_completed_at") val onboardingCompletedAt: String? = null,
)

@Serializable
data class OnboardingAccount(
    val name: String,
    @SerialName("account_type") val accountType: String = "checking",
    @SerialName("opening_balance") val openingBalance: String = "0.00",
    @SerialName("include_in_safe_to_spend") val includeInSafeToSpend: Boolean = true,
)

@Serializable
data class OnboardingRequest(
    @SerialName("display_name") val displayName: String,
    val timezone: String,
    val currency: String = "USD",
    @SerialName("income_amount") val incomeAmount: String? = null,
    @SerialName("income_frequency") val incomeFrequency: String? = null,
    @SerialName("next_payday") val nextPayday: String? = null,
    @SerialName("starting_balance") val startingBalance: String = "0.00",
    @SerialName("minimum_balance_buffer") val minimumBalanceBuffer: String = "0.00",
    val accounts: List<OnboardingAccount> = emptyList(),
    @SerialName("use_default_categories") val useDefaultCategories: Boolean = true,
    @SerialName("seed_budget") val seedBudget: Boolean = false,
)

@Serializable
data class Preferences(
    @SerialName("minimum_balance_buffer") val minimumBalanceBuffer: String = "0.00",
    @SerialName("safe_to_spend_horizon_days") val horizonDays: Int = 14,
    @SerialName("include_pending_debits") val includePendingDebits: Boolean = true,
    @SerialName("auto_bill_matching") val autoBillMatching: Boolean = true,
    @SerialName("match_tolerance_amount") val matchToleranceAmount: String = "2.00",
    @SerialName("match_tolerance_percent") val matchTolerancePercent: String = "1.00",
    @SerialName("auto_match_threshold") val autoMatchThreshold: String = "0.850",
    @SerialName("suggestion_threshold") val suggestionThreshold: String = "0.550",
    val theme: String = "system",
)

@Serializable
data class NotificationPreferences(
    @SerialName("shopping_assistant_enabled") val shoppingAssistantEnabled: Boolean = true,
    @SerialName("bill_reminders_enabled") val billRemindersEnabled: Boolean = true,
    @SerialName("low_money_warnings_enabled") val lowMoneyWarningsEnabled: Boolean = true,
    @SerialName("favorite_store_reminders_enabled") val favoriteStoreRemindersEnabled: Boolean = false,
    @SerialName("quiet_hours_start") val quietHoursStart: String? = null,
    @SerialName("quiet_hours_end") val quietHoursEnd: String? = null,
    @SerialName("quiet_hours_timezone") val quietHoursTimezone: String? = null,
)

/** A paycheck or other regular income. [nextPayday] is the baseline setup asks for. */
@Serializable
data class IncomeSource(
    val id: String,
    val name: String,
    val amount: String = "0.00",
    val frequency: String = "biweekly",
    @SerialName("next_payday") val nextPayday: String? = null,
    @SerialName("is_active") val isActive: Boolean = true,
    val notes: String? = null,
)

/** Teaches bill matching that a statement descriptor belongs to a known merchant. */
@Serializable
data class MerchantAlias(
    val id: String,
    val alias: String,
    @SerialName("canonical_merchant") val canonicalMerchant: String,
)

@Serializable
data class Profile(
    val user: User,
    val preferences: Preferences = Preferences(),
    @SerialName("notification_preferences") val notificationPreferences: NotificationPreferences =
        NotificationPreferences(),
)

@Serializable
data class Account(
    val id: String,
    val name: String,
    @SerialName("account_type") val accountType: String,
    val balance: String,
    @SerialName("include_in_safe_to_spend") val includeInSafeToSpend: Boolean = false,
    @SerialName("is_archived") val isArchived: Boolean = false,
)

@Serializable
data class AccountsResponse(
    val accounts: List<Account> = emptyList(),
    @SerialName("total_cash") val totalCash: String = "0.00",
    @SerialName("total_debt") val totalDebt: String = "0.00",
    @SerialName("net_worth") val netWorth: String = "0.00",
)

@Serializable
data class Category(
    val id: String,
    val name: String,
    val kind: String = "expense",
    val color: String = "#64748b",
    @SerialName("is_archived") val isArchived: Boolean = false,
)

@Serializable
data class Transaction(
    val id: String,
    @SerialName("account_id") val accountId: String = "",
    @SerialName("transfer_account_id") val transferAccountId: String? = null,
    val description: String,
    val merchant: String? = null,
    val amount: String,
    @SerialName("tx_type") val txType: String,
    val status: String = "posted",
    @SerialName("txn_date") val txnDate: String,
    @SerialName("category_id") val categoryId: String? = null,
    val notes: String? = null,
    val tags: List<String> = emptyList(),
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("transfer_account_name") val transferAccountName: String? = null,
    @SerialName("category_name") val categoryName: String? = null,
    @SerialName("category_color") val categoryColor: String? = null,
)

@Serializable
data class TransactionTotals(
    val income: String = "0.00",
    val spending: String = "0.00",
    val transfers: String = "0.00",
    val refunds: String = "0.00",
)

@Serializable
data class TransactionPage(
    val items: List<Transaction> = emptyList(),
    val total: Int = 0,
    val totals: TransactionTotals = TransactionTotals(),
)

@Serializable
data class ExplanationLine(
    val key: String,
    val label: String,
    val amount: String,
    val kind: String,
    val detail: String? = null,
)

@Serializable
data class SafeToSpendBill(
    @SerialName("occurrence_id") val occurrenceId: String,
    @SerialName("bill_id") val billId: String,
    val name: String,
    @SerialName("due_date") val dueDate: String,
    val amount: String,
    @SerialName("is_overdue") val isOverdue: Boolean = false,
    @SerialName("is_essential") val isEssential: Boolean = false,
)

@Serializable
data class SafeToSpendAccount(
    val id: String,
    val name: String,
    @SerialName("account_type") val accountType: String,
    val balance: String,
    val contributes: Boolean,
)

@Serializable
data class Reserve(
    val id: String,
    val name: String,
    val amount: String,
    @SerialName("is_savings") val isSavings: Boolean = false,
)

@Serializable
data class SafeToSpend(
    val currency: String = "USD",
    @SerialName("as_of") val asOf: String = "",
    val today: String = "",
    @SerialName("horizon_end") val horizonEnd: String = "",
    val payday: String? = null,
    @SerialName("eligible_balance") val eligibleBalance: String = "0.00",
    @SerialName("pending_debits") val pendingDebits: String = "0.00",
    @SerialName("bill_reserves") val billReserves: String = "0.00",
    @SerialName("minimum_buffer") val minimumBuffer: String = "0.00",
    @SerialName("explicit_reserves") val explicitReserves: String = "0.00",
    @SerialName("safe_to_spend") val amount: String = "0.00",
    @SerialName("projected_shortfall") val projectedShortfall: String = "0.00",
    @SerialName("is_negative") val isNegative: Boolean = false,
    val accounts: List<SafeToSpendAccount> = emptyList(),
    val bills: List<SafeToSpendBill> = emptyList(),
    val reserves: List<Reserve> = emptyList(),
    val warnings: List<String> = emptyList(),
    val explanation: List<ExplanationLine> = emptyList(),
)

@Serializable
data class DashboardAccount(
    val id: String,
    val name: String,
    @SerialName("account_type") val accountType: String,
    val balance: String,
    @SerialName("include_in_safe_to_spend") val includeInSafeToSpend: Boolean = false,
    @SerialName("is_archived") val isArchived: Boolean = false,
)

@Serializable
data class AccountTotals(
    @SerialName("total_cash") val totalCash: String = "0.00",
    @SerialName("total_debt") val totalDebt: String = "0.00",
    @SerialName("net_worth") val netWorth: String = "0.00",
)

@Serializable
data class SpendingSlice(
    @SerialName("category_id") val categoryId: String? = null,
    val name: String,
    val color: String = "#64748b",
    val amount: String,
)

@Serializable
data class MonthTotals(
    val income: String = "0.00",
    val spending: String = "0.00",
    val net: String = "0.00",
)

@Serializable
data class Dashboard(
    @SerialName("as_of") val asOf: String,
    val today: String,
    @SerialName("safe_to_spend") val safeToSpend: SafeToSpend,
    val accounts: List<DashboardAccount> = emptyList(),
    @SerialName("account_totals") val accountTotals: AccountTotals = AccountTotals(),
    val budget: BudgetSummary? = null,
    @SerialName("spending_by_category") val spendingByCategory: List<SpendingSlice> = emptyList(),
    @SerialName("upcoming_bills") val upcomingBills: List<Occurrence> = emptyList(),
    @SerialName("upcoming_bills_total") val upcomingBillsTotal: String = "0.00",
    @SerialName("next_payday") val nextPayday: String? = null,
    @SerialName("recent_transactions") val recentTransactions: List<Transaction> = emptyList(),
    @SerialName("pending_match_suggestions") val pendingMatchSuggestions: Int = 0,
    @SerialName("month_totals") val monthTotals: MonthTotals = MonthTotals(),
    @SerialName("reserved_total") val reservedTotal: String = "0.00",
    val warnings: List<String> = emptyList(),
    val currency: String = "USD",
    @SerialName("is_demo") val isDemo: Boolean = false,
)

@Serializable
data class BudgetRow(
    @SerialName("category_id") val categoryId: String,
    @SerialName("category_name") val categoryName: String,
    @SerialName("category_color") val categoryColor: String = "#64748b",
    val allocated: String = "0.00",
    val spent: String = "0.00",
    val remaining: String = "0.00",
    @SerialName("percent_used") val percentUsed: String = "0.00",
    @SerialName("upcoming_commitments") val upcomingCommitments: String = "0.00",
    @SerialName("carryover_enabled") val carryoverEnabled: Boolean = false,
)

@Serializable
data class BudgetSummary(
    val id: String = "",
    val year: Int,
    val month: Int,
    val name: String? = null,
    val notes: String? = null,
    @SerialName("planned_income") val plannedIncome: String? = null,
    @SerialName("total_allocated") val totalAllocated: String = "0.00",
    @SerialName("total_spent") val totalSpent: String = "0.00",
    @SerialName("total_remaining") val totalRemaining: String = "0.00",
    @SerialName("percent_used") val percentUsed: String = "0.00",
    @SerialName("income_this_month") val incomeThisMonth: String = "0.00",
    val unallocated: String = "0.00",
    val rows: List<BudgetRow> = emptyList(),
)

@Serializable
data class Bill(
    val id: String,
    val name: String,
    val merchant: String? = null,
    @SerialName("expected_amount") val expectedAmount: String,
    @SerialName("minimum_amount") val minimumAmount: String? = null,
    @SerialName("due_day") val dueDay: Int? = null,
    @SerialName("anchor_date") val anchorDate: String? = null,
    val frequency: String = "monthly",
    @SerialName("custom_interval_days") val customIntervalDays: Int? = null,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    val notes: String? = null,
    @SerialName("reserve_in_safe_to_spend") val reserveInSafeToSpend: Boolean = true,
    @SerialName("auto_pay") val autoPay: Boolean = false,
    @SerialName("next_due_date") val nextDueDate: String? = null,
    @SerialName("is_overdue") val isOverdue: Boolean = false,
    @SerialName("is_essential") val isEssential: Boolean = true,
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class BillsResponse(
    val items: List<Bill> = emptyList(),
)

@Serializable
data class Occurrence(
    val id: String,
    @SerialName("bill_id") val billId: String,
    @SerialName("bill_name") val billName: String? = null,
    val merchant: String? = null,
    @SerialName("due_date") val dueDate: String,
    @SerialName("expected_amount") val expectedAmount: String,
    @SerialName("paid_amount") val paidAmount: String = "0.00",
    @SerialName("remaining_amount") val remainingAmount: String = "0.00",
    val status: String = "upcoming",
    @SerialName("is_overdue") val isOverdue: Boolean = false,
    @SerialName("is_essential") val isEssential: Boolean = false,
)

@Serializable
data class CategoryAvailability(
    @SerialName("category_name") val categoryName: String,
    val budgeted: String = "0.00",
    val spent: String = "0.00",
    val remaining: String = "0.00",
    @SerialName("percent_used") val percentUsed: String = "0.00",
    @SerialName("max_safe_purchase") val maxSafePurchase: String = "0.00",
    @SerialName("limited_by") val limitedBy: String = "none",
)

@Serializable
data class PurchaseResult(
    val amount: String,
    val allowed: Boolean,
    @SerialName("category_remaining_after") val categoryRemainingAfter: String,
    @SerialName("safe_to_spend_after") val safeToSpendAfter: String,
    @SerialName("category_over_budget") val categoryOverBudget: Boolean = false,
    @SerialName("cash_shortfall") val cashShortfall: String = "0.00",
    val message: String,
)

@Serializable
data class ShoppingRequest(
    @SerialName("store_name") val storeName: String,
    @SerialName("category_id") val categoryId: String,
    @SerialName("expected_amount") val expectedAmount: String? = null,
)

@Serializable
data class ShoppingResult(
    @SerialName("store_name") val storeName: String,
    val category: CategoryAvailability,
    @SerialName("safe_to_spend") val safeToSpend: SafeToSpend,
    @SerialName("purchase") val purchase: PurchaseResult? = null,
    val message: String,
    @SerialName("upcoming_bills") val upcomingBills: List<Occurrence> = emptyList(),
    @SerialName("next_payday") val nextPayday: String? = null,
    @SerialName("bills_covered") val billsCovered: Boolean = true,
    @SerialName("projected_shortfall") val projectedShortfall: String = "0.00",
    val warnings: List<String> = emptyList(),
    val note: String? = null,
    @SerialName("as_of") val asOf: String = "",
)

@Serializable
data class TransactionWrite(
    @SerialName("account_id") val accountId: String,
    val description: String,
    val merchant: String? = null,
    val amount: String,
    @SerialName("tx_type") val txType: String,
    val status: String = "posted",
    @SerialName("txn_date") val txnDate: String,
    @SerialName("category_id") val categoryId: String? = null,
    val notes: String? = null,
    val tags: List<String> = emptyList(),
    @SerialName("transfer_account_id") val transferAccountId: String? = null,
)

@Serializable
data class MatchInfo(
    val outcome: String = "none",
    val matched: Boolean = false,
    @SerialName("bill_name") val billName: String? = null,
    val confidence: String? = null,
    val reason: String? = null,
    val ambiguous: Boolean = false,
)

@Serializable
data class DuplicateCandidate(
    @SerialName("transaction_id") val transactionId: String,
    val description: String,
    val amount: String,
    @SerialName("txn_date") val txnDate: String,
    @SerialName("account_id") val accountId: String = "",
    val reason: String = "",
)

@Serializable
data class TransactionCreateResponse(
    val transaction: Transaction,
    @SerialName("match_info") val matchInfo: MatchInfo? = null,
    @SerialName("possible_duplicates") val possibleDuplicates: List<DuplicateCandidate> = emptyList(),
)

@Serializable
data class MatchCandidate(
    @SerialName("match_id") val matchId: String,
    @SerialName("occurrence_id") val occurrenceId: String,
    @SerialName("bill_name") val billName: String? = null,
    @SerialName("due_date") val dueDate: String = "",
    val remaining: String = "0.00",
    val amount: String = "0.00",
    val confidence: String = "0.0",
    @SerialName("is_ambiguous") val isAmbiguous: Boolean = false,
    val reason: String? = null,
)

@Serializable
data class MatchSuggestionGroup(
    @SerialName("transaction_id") val transactionId: String,
    @SerialName("transaction_description") val transactionDescription: String = "Transaction",
    @SerialName("transaction_merchant") val transactionMerchant: String? = null,
    @SerialName("transaction_amount") val transactionAmount: String = "0.00",
    @SerialName("transaction_date") val transactionDate: String = "",
    val candidates: List<MatchCandidate> = emptyList(),
)

@Serializable
data class MatchSuggestionsResponse(
    val items: List<MatchSuggestionGroup> = emptyList(),
)

@Serializable
data class ImportJob(
    val id: String,
    @SerialName("account_id") val accountId: String = "",
    val filename: String = "import.csv",
    @SerialName("file_size") val fileSize: Long = 0,
    val status: String = "uploaded",
    @SerialName("row_count") val rowCount: Int = 0,
    @SerialName("imported_count") val importedCount: Int = 0,
    @SerialName("duplicate_count") val duplicateCount: Int = 0,
    @SerialName("rejected_count") val rejectedCount: Int = 0,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("committed_at") val committedAt: String? = null,
)

@Serializable
data class ImportPreviewRow(
    @SerialName("row_number") val rowNumber: Int,
    val date: String? = null,
    val description: String = "",
    val merchant: String? = null,
    val amount: String? = null,
    @SerialName("signed_amount") val signedAmount: String? = null,
    @SerialName("suggested_type") val suggestedType: String = "purchase",
    val status: String = "ok",
    val reason: String? = null,
    @SerialName("duplicate_of") val duplicateOf: String? = null,
)

@Serializable
data class ImportSummary(
    @SerialName("total_rows") val totalRows: Int = 0,
    val ready: Int = 0,
    val duplicates: Int = 0,
    val rejected: Int = 0,
    @SerialName("ready_total") val readyTotal: String = "0.00",
)

@Serializable
data class ImportPreview(
    @SerialName("import_id") val importId: String,
    val filename: String = "",
    @SerialName("account_id") val accountId: String = "",
    val headers: List<String> = emptyList(),
    val mapping: Map<String, String?> = emptyMap(),
    @SerialName("suggested_mapping") val suggestedMapping: Map<String, String?> = emptyMap(),
    val rows: List<ImportPreviewRow> = emptyList(),
    val truncated: Boolean = false,
    val summary: ImportSummary = ImportSummary(),
)

@Serializable
data class CsvUploadResponse(
    val import: ImportJob,
    val headers: List<String> = emptyList(),
    @SerialName("suggested_mapping") val suggestedMapping: Map<String, String?> = emptyMap(),
    val preview: ImportPreview? = null,
    @SerialName("preview_error") val previewError: String? = null,
)

@Serializable
data class ImportMappingBody(
    val mapping: Map<String, String?>,
)

@Serializable
data class ImportCommitResult(
    @SerialName("import_id") val importId: String = "",
    @SerialName("already_committed") val alreadyCommitted: Boolean = false,
    val imported: Int = 0,
    val duplicates: Int = 0,
    val rejected: Int = 0,
    @SerialName("matched_bills") val matchedBills: Int = 0,
    @SerialName("auto_matched") val autoMatched: Int = 0,
    @SerialName("suggested_matches") val suggestedMatches: Int = 0,
    @SerialName("committed_at") val committedAt: String? = null,
)

@Serializable
data class ImportRecord(
    val id: String,
    @SerialName("row_number") val rowNumber: Int = 0,
    val status: String = "",
    val reason: String? = null,
    @SerialName("transaction_id") val transactionId: String? = null,
)
