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

// ---------------------------------------------------------------- Phase 4: loans
@Serializable
data class Loan(
    val id: String,
    val name: String,
    val lender: String? = null,
    @SerialName("loan_type") val loanType: String = "personal",
    @SerialName("original_amount") val originalAmount: String = "0.00",
    @SerialName("opening_balance") val openingBalance: String = "0.00",
    @SerialName("balance_as_of") val balanceAsOf: String = "",
    @SerialName("balance_source") val balanceSource: String = "user",
    val apr: String? = null,
    @SerialName("interest_charged") val interestCharged: String? = null,
    @SerialName("fees_charged") val feesCharged: String? = null,
    @SerialName("next_payment_date") val nextPaymentDate: String? = null,
    @SerialName("scheduled_payment") val scheduledPayment: String? = null,
    @SerialName("payment_frequency") val paymentFrequency: String? = null,
    @SerialName("remaining_payments") val remainingPayments: Int? = null,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    val status: String = "active",
    val notes: String? = null,
    val createdAt: String = "",
    @SerialName("current_balance") val currentBalance: String = "0.00",
    @SerialName("principal_repaid") val principalRepaid: String = "0.00",
    @SerialName("interest_paid") val interestPaid: String = "0.00",
    @SerialName("fees_paid") val feesPaid: String = "0.00",
    @SerialName("total_repaid") val totalRepaid: String = "0.00",
    @SerialName("balance_is_estimate") val balanceIsEstimate: Boolean = false,
    @SerialName("progress_percent") val progressPercent: String = "0.00",
    @SerialName("payment_count") val paymentCount: Int = 0,
    @SerialName("last_payment_date") val lastPaymentDate: String? = null,
    @SerialName("estimated_payoff_date") val estimatedPayoffDate: String? = null,
    @SerialName("payoff_is_estimate") val payoffIsEstimate: Boolean = false,
    @SerialName("remaining_installments") val remainingInstallments: Int? = null,
) {
    val balance: Double get() = currentBalance.toDoubleOrNull() ?: 0.0
}

@Serializable
data class LoanSummary(
    @SerialName("total_outstanding") val totalOutstanding: String = "0.00",
    @SerialName("total_original") val totalOriginal: String = "0.00",
    @SerialName("active_loans") val activeLoans: Int = 0,
    @SerialName("next_payment_date") val nextPaymentDate: String? = null,
    @SerialName("next_payment_total") val nextPaymentTotal: String = "0.00",
    val loans: List<Loan> = emptyList(),
)

@Serializable
data class LoanPayment(
    val id: String,
    @SerialName("loan_id") val loanId: String,
    @SerialName("transaction_id") val transactionId: String? = null,
    val amount: String = "0.00",
    @SerialName("paid_on") val paidOn: String = "",
    val status: String = "confirmed",
    val confidence: String = "1.000",
    @SerialName("is_automatic") val isAutomatic: Boolean = false,
    val reason: String? = null,
    @SerialName("transaction_description") val transactionDescription: String? = null,
)

@Serializable
data class LoanPaymentSuggestion(
    @SerialName("transaction_id") val transactionId: String,
    val description: String = "",
    val merchant: String? = null,
    val amount: String = "0.00",
    @SerialName("txn_date") val txnDate: String = "",
    val confidence: String = "0.000",
    val reason: String = "",
    @SerialName("is_ambiguous") val isAmbiguous: Boolean = false,
)

@Serializable
data class LoanPaymentSuggestions(
    @SerialName("loan_id") val loanId: String,
    @SerialName("loan_name") val loanName: String = "",
    val items: List<LoanPaymentSuggestion> = emptyList(),
)

// -------------------------------------------------------------- Phase 4: savings
@Serializable
data class SavingsGoal(
    val id: String,
    val name: String,
    @SerialName("target_amount") val targetAmount: String = "0.00",
    @SerialName("target_date") val targetDate: String? = null,
    val mode: String = "virtual",
    @SerialName("saved_amount") val savedAmount: String = "0.00",
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("account_balance") val accountBalance: String? = null,
    @SerialName("account_is_spendable") val accountIsSpendable: Boolean? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("contribution_amount") val contributionAmount: String? = null,
    @SerialName("contribution_frequency") val contributionFrequency: String? = null,
    val status: String = "active",
    val notes: String? = null,
    @SerialName("progress_percent") val progressPercent: String = "0.00",
    @SerialName("remaining_to_target") val remainingToTarget: String = "0.00",
    @SerialName("protected_amount") val protectedAmount: String = "0.00",
    @SerialName("protects_money") val protectsMoney: Boolean = false,
    @SerialName("next_contribution_date") val nextContributionDate: String? = null,
    @SerialName("required_per_period") val requiredPerPeriod: String? = null,
    @SerialName("projected_completion") val projectedCompletion: String? = null,
)

@Serializable
data class SavingsSummary(
    @SerialName("total_target") val totalTarget: String = "0.00",
    @SerialName("total_saved") val totalSaved: String = "0.00",
    @SerialName("total_protected") val totalProtected: String = "0.00",
    @SerialName("active_goals") val activeGoals: Int = 0,
    @SerialName("completed_goals") val completedGoals: Int = 0,
    @SerialName("monthly_commitment") val monthlyCommitment: String = "0.00",
    val goals: List<SavingsGoal> = emptyList(),
)

// ----------------------------------------------------------- Phase 4: obligations
@Serializable
data class ObligationItem(
    val kind: String = "bill",
    val id: String,
    @SerialName("source_id") val sourceId: String = "",
    val name: String = "",
    val detail: String? = null,
    @SerialName("due_date") val dueDate: String? = null,
    val amount: String = "0.00",
    val status: String = "upcoming",
    @SerialName("is_overdue") val isOverdue: Boolean = false,
    @SerialName("is_estimate") val isEstimate: Boolean = false,
    @SerialName("is_essential") val isEssential: Boolean = true,
    @SerialName("reserved_in_safe_to_spend") val reservedInSafeToSpend: Boolean = true,
)

@Serializable
data class ObligationTotals(
    @SerialName("due_in_horizon") val dueInHorizon: String = "0.00",
    val overdue: String = "0.00",
    @SerialName("due_within_7_days") val dueWithin7Days: String = "0.00",
    @SerialName("due_before_payday") val dueBeforePayday: String = "0.00",
)

@Serializable
data class Obligations(
    val today: String = "",
    @SerialName("horizon_end") val horizonEnd: String = "",
    @SerialName("next_payday") val nextPayday: String? = null,
    val items: List<ObligationItem> = emptyList(),
    val totals: ObligationTotals = ObligationTotals(),
    @SerialName("double_counting_guards") val guards: List<String> = emptyList(),
)

// ------------------------------------------------- Phase 4: merchant and location
@Serializable
data class TrackedLocation(
    val id: String,
    val name: String,
    val merchant: String? = null,
    val address: String? = null,
    val latitude: String? = null,
    val longitude: String? = null,
    @SerialName("radius_m") val radiusM: Int = 150,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("monthly_budget") val monthlyBudget: String? = null,
    @SerialName("notify_enabled") val notifyEnabled: Boolean = true,
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("visit_count") val visitCount: Int = 0,
    @SerialName("last_visit_at") val lastVisitAt: String? = null,
    @SerialName("month_spend") val monthSpend: String? = null,
    @SerialName("budget_remaining") val budgetRemaining: String? = null,
) {
    val hasCoordinates: Boolean get() = !latitude.isNullOrBlank() && !longitude.isNullOrBlank()
}

@Serializable
data class ShoppingVisit(
    val id: String,
    @SerialName("tracked_location_id") val trackedLocationId: String? = null,
    @SerialName("business_name") val businessName: String = "",
    @SerialName("visit_day") val visitDay: String = "",
    @SerialName("visited_at") val visitedAt: String = "",
    val status: String = "detected",
    val confidence: String = "0.000",
    @SerialName("is_new_place") val isNewPlace: Boolean = false,
    @SerialName("visit_count") val visitCount: Int = 0,
    @SerialName("transaction_count") val transactionCount: Int = 0,
    @SerialName("spend_total") val spendTotal: String = "0.00",
)

@Serializable
data class ShoppingVisits(
    val items: List<ShoppingVisit> = emptyList(),
    val count: Int = 0,
    val suggested: Int = 0,
    val note: String = "",
)

@Serializable
data class LocationSettings(
    @SerialName("location_features_opted_in") val optedIn: Boolean = false,
    @SerialName("shopping_intelligence_enabled") val enabled: Boolean = false,
    @SerialName("discovery_enabled") val discoveryEnabled: Boolean = false,
    val paused: Boolean = false,
    @SerialName("location_paused_until") val pausedUntil: String? = null,
    @SerialName("quiet_hours_start") val quietStart: String? = null,
    @SerialName("quiet_hours_end") val quietEnd: String? = null,
    @SerialName("quiet_hours_timezone") val quietTimezone: String? = null,
    @SerialName("notification_cooldown_minutes") val cooldownMinutes: Int = 120,
    @SerialName("visit_history_retention_days") val retentionDays: Int = 90,
    @SerialName("tracked_location_count") val trackedLocationCount: Int = 0,
)

@Serializable
data class VisitPrompt(
    @SerialName("visit_id") val visitId: String = "",
    @SerialName("business_name") val businessName: String = "",
    val tracked: Boolean = false,
    val message: String = "",
    @SerialName("safe_to_spend") val safeToSpend: String = "0.00",
    @SerialName("store_budget") val storeBudget: String? = null,
    @SerialName("store_remaining") val storeRemaining: String? = null,
    @SerialName("typical_spend") val typicalSpend: String? = null,
    @SerialName("suggested_limit") val suggestedLimit: String? = null,
    @SerialName("upcoming_obligations_total") val upcomingObligations: String = "0.00",
    @SerialName("data_is_stale") val dataIsStale: Boolean = false,
    @SerialName("suppress_reason") val suppressReason: String? = null,
)

@Serializable
data class VisitRecordResult(
    val recorded: Boolean = false,
    val reason: String? = null,
    val visit: ShoppingVisit? = null,
    val prompt: VisitPrompt? = null,
    val notify: Boolean = false,
)
