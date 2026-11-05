export type Money = string;

export type AccountType =
  | "checking"
  | "savings"
  | "cash"
  | "digital_wallet"
  | "payment_app"
  | "credit_card"
  | "other";

export type TransactionType =
  | "income"
  | "purchase"
  | "bill_payment"
  | "refund"
  | "transfer"
  | "adjustment";

export interface Account {
  id: string;
  name: string;
  account_type: AccountType;
  currency: string;
  opening_balance: Money;
  opening_balance_date: string;
  include_in_safe_to_spend: boolean;
  credit_limit: Money | null;
  description: string | null;
  institution: string | null;
  is_archived: boolean;
  created_at: string;
  balance: Money;
  pending_balance: Money;
  available_balance: Money;
  total_inflows: Money;
  total_outflows: Money;
  transaction_count: number;
}

export interface AccountSummary {
  total_cash: Money;
  total_debt: Money;
  net_worth: Money;
  accounts: Account[];
}

export interface Category {
  id: string;
  name: string;
  kind: "expense" | "income" | "savings" | "debt";
  color: string;
  icon: string | null;
  is_archived: boolean;
  is_system: boolean;
  sort_order: number;
}

export interface Transaction {
  id: string;
  account_id: string;
  transfer_account_id: string | null;
  description: string;
  merchant: string | null;
  amount: Money;
  tx_type: TransactionType;
  status: "pending" | "posted";
  txn_date: string;
  posting_date: string | null;
  category_id: string | null;
  notes: string | null;
  tags: string[];
  source: "manual" | "csv" | "provider";
  external_id: string | null;
  import_id: string | null;
  created_at: string;
  account_name: string | null;
  transfer_account_name: string | null;
  category_name: string | null;
  category_color: string | null;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
  totals: {
    income: Money;
    spending: Money;
    transfers: Money;
    refunds: Money;
  };
}

export interface DuplicateCandidate {
  transaction_id: string;
  description: string;
  amount: Money;
  txn_date: string;
  account_id: string;
  reason: string;
}

export interface SafeToSpendAccount {
  id: string;
  name: string;
  account_type: AccountType;
  balance: Money;
  contributes: boolean;
}

export interface SafeToSpendBill {
  occurrence_id: string;
  bill_id: string;
  name: string;
  due_date: string;
  amount: Money;
  is_overdue: boolean;
  is_essential: boolean;
  category_id: string | null;
}

export interface ExplanationLine {
  key: string;
  label: string;
  amount: Money;
  kind: "credit" | "debit" | "result";
  detail: string | null;
}

export interface SafeToSpend {
  currency: string;
  as_of: string;
  today: string;
  horizon_end: string;
  payday: string | null;
  eligible_balance: Money;
  pending_debits: Money;
  bill_reserves: Money;
  minimum_buffer: Money;
  explicit_reserves: Money;
  raw_amount: Money;
  safe_to_spend: Money;
  projected_shortfall: Money;
  is_negative: boolean;
  accounts: SafeToSpendAccount[];
  bills: SafeToSpendBill[];
  reserves: { id: string; name: string; amount: Money; is_savings: boolean }[];
  pending_items: { id: string; account_id: string; amount: Money; tx_type: string }[];
  warnings: string[];
  explanation: ExplanationLine[];
  stale_information: boolean;
}

export interface CategoryAvailability {
  category_id: string;
  category_name: string;
  budgeted: Money;
  spent: Money;
  carryover_in: Money;
  remaining: Money;
  percent_used: Money;
  upcoming_commitments: Money;
  max_safe_purchase: Money;
  overall_safe_to_spend: Money;
  limited_by: "category" | "cash" | "none";
}

export interface BudgetRow {
  category_id: string;
  category_name: string;
  category_color: string;
  category_kind: string;
  allocated: Money;
  carryover_in: Money;
  carryover_enabled: boolean;
  spent: Money;
  remaining: Money;
  percent_used: Money;
  upcoming_commitments: Money;
  previous_month_spent: Money;
  trend_percent: Money | null;
  transaction_count: number;
}

export interface BudgetSummary {
  id: string;
  year: number;
  month: number;
  name: string | null;
  notes: string | null;
  planned_income: Money | null;
  total_allocated: Money;
  total_carryover: Money;
  total_spent: Money;
  total_remaining: Money;
  percent_used: Money;
  income_this_month: Money;
  unallocated: Money;
  rows: BudgetRow[];
  created_from_wizard: boolean;
}

export interface Bill {
  id: string;
  name: string;
  merchant: string | null;
  expected_amount: Money;
  minimum_amount: Money | null;
  due_day: number | null;
  anchor_date: string;
  frequency: string;
  custom_interval_days: number | null;
  account_id: string | null;
  category_id: string | null;
  notes: string | null;
  is_essential: boolean;
  reserve_in_safe_to_spend: boolean;
  is_active: boolean;
  auto_pay: boolean;
  created_at: string;
  next_due_date?: string | null;
  next_remaining?: Money;
  is_overdue?: boolean;
}

export interface Occurrence {
  id: string;
  bill_id: string;
  bill_name: string | null;
  merchant: string | null;
  category_id: string | null;
  account_id: string | null;
  due_date: string;
  expected_amount: Money;
  paid_amount: Money;
  remaining_amount: Money;
  status: "upcoming" | "partial" | "paid" | "skipped";
  is_overdue: boolean;
  is_essential: boolean;
  is_partial: boolean;
  confirmed_at: string | null;
  notes: string | null;
}

export interface MatchSuggestionGroup {
  transaction_id: string;
  transaction_description: string;
  transaction_merchant: string | null;
  transaction_amount: Money;
  transaction_date: string;
  account_id: string;
  candidates: {
    match_id: string;
    occurrence_id: string;
    bill_name: string | null;
    due_date: string;
    remaining: Money;
    amount: Money;
    confidence: string;
    is_ambiguous: boolean;
    reason: string | null;
  }[];
}

export interface IncomeSource {
  id: string;
  name: string;
  amount: Money;
  frequency: string;
  next_payday: string | null;
  account_id: string | null;
  is_active: boolean;
  notes: string | null;
}

export interface Preferences {
  minimum_balance_buffer: Money;
  safe_to_spend_horizon_days: number;
  include_pending_debits: boolean;
  auto_bill_matching: boolean;
  match_window_before_days: number;
  match_window_after_days: number;
  match_tolerance_amount: Money;
  match_tolerance_percent: Money;
  auto_match_threshold: Money;
  suggestion_threshold: Money;
  week_starts_on: number;
  theme: "system" | "light" | "dark";
}

export interface NotificationPreferences {
  shopping_assistant_enabled: boolean;
  bill_reminders_enabled: boolean;
  low_money_warnings_enabled: boolean;
  favorite_store_reminders_enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  quiet_hours_timezone: string | null;
  location_features_opted_in: boolean;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  timezone: string;
  currency: string;
  is_demo: boolean;
  onboarding_completed_at: string | null;
  created_at: string;
}

export interface Profile {
  user: User;
  preferences: Preferences;
  notification_preferences: NotificationPreferences;
}

export interface Dashboard {
  as_of: string;
  today: string;
  safe_to_spend: SafeToSpend;
  accounts: {
    id: string;
    name: string;
    account_type: AccountType;
    balance: Money;
    pending_balance: Money;
    include_in_safe_to_spend: boolean;
    is_archived: boolean;
  }[];
  account_totals: { total_cash: Money; total_debt: Money; net_worth: Money };
  budget: BudgetSummary | null;
  spending_by_category: { category_id: string | null; name: string; color: string; amount: Money }[];
  upcoming_bills: Occurrence[];
  upcoming_bills_total: Money;
  next_payday: string | null;
  recent_transactions: Transaction[];
  pending_match_suggestions: number;
  month_totals: { income: Money; spending: Money; net: Money };
  reserved_total: Money;
  warnings: string[];
  shopping_categories: CategoryAvailability[];
  currency: string;
  is_demo: boolean;
}

export interface ShoppingResult {
  store_name: string;
  category: CategoryAvailability;
  safe_to_spend: SafeToSpend;
  expected_amount: Money | null;
  purchase: {
    amount: Money;
    allowed: boolean;
    category_remaining: Money;
    category_remaining_after: Money;
    safe_to_spend: Money;
    safe_to_spend_after: Money;
    category_over_budget: boolean;
    cash_shortfall: Money;
    message: string;
  } | null;
  message: string;
  upcoming_bills: Occurrence[];
  next_payday: string | null;
  bills_covered: boolean;
  projected_shortfall: Money;
  warnings: string[];
  note: string | null;
  notification_context: Record<string, unknown>;
  as_of: string;
}

export interface ImportPreviewRow {
  row_number: number;
  date: string | null;
  description: string;
  merchant: string | null;
  amount: string | null;
  signed_amount: string | null;
  suggested_type: string;
  external_id: string | null;
  status: "ok" | "duplicate" | "error";
  reason: string | null;
  duplicate_of: string | null;
  raw: Record<string, string>;
}

export interface ImportPreview {
  import_id: string;
  filename: string;
  account_id: string;
  headers: string[];
  mapping: Record<string, string | null>;
  suggested_mapping: Record<string, string | null>;
  has_header: boolean;
  delimiter: string;
  rows: ImportPreviewRow[];
  truncated: boolean;
  summary: {
    total_rows: number;
    ready: number;
    duplicates: number;
    rejected: number;
    ready_total: string;
  };
}

export interface UploadResponse {
  import: {
    id: string;
    account_id: string;
    filename: string;
    status: string;
    row_count: number;
    created_at: string;
  };
  headers: string[];
  suggested_mapping: Record<string, string | null>;
  preview: ImportPreview | null;
  preview_error: string | null;
}

export interface ImportJob {
  id: string;
  account_id: string;
  filename: string;
  file_size: number;
  status: "uploaded" | "previewed" | "committed" | "failed";
  row_count: number;
  imported_count: number;
  duplicate_count: number;
  rejected_count: number;
  created_at: string;
  committed_at: string | null;
}

export interface Forecast {
  start_date: string;
  end_date: string;
  starting_available_cash: Money;
  expected_income_total: Money;
  bills_total: Money;
  projected_end_balance: Money;
  lowest_projected_balance: Money;
  next_payday: string | null;
  safe_to_spend_now: Money;
  warnings: string[];
  points: {
    date: string;
    expected_income: Money;
    bills_due: Money;
    projected_balance: Money;
  }[];
  assumption: string;
}
