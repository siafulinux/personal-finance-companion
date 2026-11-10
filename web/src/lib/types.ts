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
  minimum_payment: Money | null;
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

export interface LoanReserveLine {
  loan_id: string;
  name: string;
  due_date: string;
  amount: Money;
  is_overdue: boolean;
  is_estimate: boolean;
  remaining_balance: Money;
}

export interface SavingsReserveLine {
  goal_id: string;
  name: string;
  amount: Money;
  mode: SavingsMode;
  is_planned_contribution: boolean;
  due_date: string | null;
}

export interface CreditCardReserveLine {
  account_id: string;
  name: string;
  minimum_payment: Money;
  due_date: string | null;
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
  loan_reserves?: Money;
  savings_reserves?: Money;
  credit_card_reserves?: Money;
  obligations_total?: Money;
  loans?: LoanReserveLine[];
  savings?: SavingsReserveLine[];
  credit_cards?: CreditCardReserveLine[];
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

// ---------------------------------------------------------------- Phase 2
export interface ProviderInfo {
  name: string;
  display_name: string;
  configured: boolean;
  usable: boolean;
  requires_credentials: boolean;
  simulated: boolean;
  note: string;
}

/** One institution, already resolved to whichever provider can serve it. */
export interface InstitutionEntry {
  key: string;
  name: string;
  available: boolean;
  reason: string | null;
  simulated: boolean;
  account_types: string[];
}

export interface InstitutionCatalog {
  institutions: InstitutionEntry[];
  warnings: string[];
  configured: boolean;
}

/**
 * What `/connectivity/connect/start` hands back. `flow` is provider-specific
 * (a Teller Connect configuration or a Plaid link token) and the client only
 * forwards it to the provider's own script.
 */
export interface ConnectFlow {
  connection: InstitutionEntry;
  provider: string;
  mode: "teller_connect" | "plaid_link" | "direct" | string;
  flow: Record<string, unknown>;
}

export interface ConnectResult {
  link: ProviderLink;
  accounts: LinkedAccountRef[];
  sync: SyncRunSummary;
}

export interface ProviderCredentialField {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  multiline: boolean;
  placeholder: string | null;
  help: string;
  present: boolean;
  value: string | null;
  hint: string | null;
}

export interface ProviderTestResult {
  at: string | null;
  ok: boolean | null;
  message: string | null;
  detail: Record<string, unknown>;
}

export interface ProviderAdmin {
  name: string;
  label: string;
  enabled: boolean;
  priority: number;
  environment: string;
  environments: string[];
  configured: boolean;
  usable: boolean;
  source: "database" | "environment" | "none";
  missing: string[];
  problem: string | null;
  fields: ProviderCredentialField[];
  last_test: ProviderTestResult | null;
}

export interface ProviderOverview {
  providers: ProviderAdmin[];
  auto_select: boolean;
  primary: string | null;
  any_usable: boolean;
  sandbox_available: boolean;
}

export interface CoverageMatch {
  institution_id: string;
  name: string;
  products: string[];
  transactions: boolean;
  balances: boolean;
  account_types: string[];
  note: string | null;
}

export interface CoverageProvider {
  provider: string;
  label: string;
  available: boolean;
  reason: string | null;
  match: CoverageMatch | null;
}

export interface CoverageReport {
  auto_select: boolean;
  institutions: { query: string; providers: CoverageProvider[] }[];
}

export interface LinkedAccountRef {
  id: string;
  name: string;
  account_type: string;
  external_account_id: string | null;
}

export interface SyncRunSummary {
  id: string;
  status: "running" | "success" | "partial" | "failed";
  started_at: string;
  finished_at: string | null;
  added: number;
  modified: number;
  removed: number;
  skipped_duplicates: number;
  suggestions_created?: number;
  unmatched_pending?: number;
  error_code?: string | null;
  error_message?: string | null;
  detail?: Record<string, unknown> | null;
}

export interface ProviderLink {
  id: string;
  provider: string;
  institution_name: string;
  status: "active" | "error" | "reauth_required" | "disconnected";
  last_synced_at: string | null;
  last_success_at: string | null;
  next_retry_at: string | null;
  error_code: string | null;
  error_message: string | null;
  failure_count: number;
  consented_at: string | null;
  disconnected_at: string | null;
  history_start: string | null;
  account_count: number;
  accounts: LinkedAccountRef[];
  last_run: (SyncRunSummary & { started_at: string }) | null;
  has_stored_credential: boolean;
}

export interface CategorySuggestionItem {
  id: string;
  transaction_id: string;
  category_id: string;
  category_name: string | null;
  category_color: string | null;
  confidence: string;
  source: "rule" | "history" | "provider";
  status: "suggested" | "accepted" | "rejected";
  reason: string | null;
  transaction: {
    description: string;
    merchant: string | null;
    amount: string;
    txn_date: string;
  } | null;
}

export interface RecurringItem {
  id: string;
  display_name: string;
  merchant: string | null;
  category_id: string | null;
  average_amount: string;
  last_amount: string;
  frequency: string;
  interval_days: number;
  occurrences: number;
  first_seen: string;
  last_seen: string;
  next_expected_date: string | null;
  confidence: string;
  is_subscription: boolean;
  status: "detected" | "confirmed" | "dismissed";
  detail: Record<string, unknown> | null;
}

export interface PersonalInsight {
  type: string;
  severity: "high" | "medium" | "low";
  category_id?: string;
  merchant?: string;
  title: string;
  message: string;
  evidence: Record<string, string | number>;
}

export interface PersonalInsights {
  enabled: boolean;
  sensitivity: string;
  minimum_history: { months: number; transactions: number };
  insights: PersonalInsight[];
  unusual_transactions: {
    transaction_id: string;
    description: string;
    merchant: string | null;
    amount: string;
    txn_date: string;
    typical_amount: string;
    times_typical: number;
    reason: string;
  }[];
  as_of?: string;
  note?: string;
}

export interface AssistantStatus {
  mode: string;
  model_configured: boolean;
  model: string | null;
  consent_required: boolean;
  ai_consent: boolean;
  capabilities: string[];
  can_modify_data: boolean;
  note: string;
}

export interface ServerInfo {
  app_name: string;
  server_name: string;
  version: string;
  api_version: number;
  min_client_api_version: number;
  api_base_url: string;
  web_url: string;
  status: string;
  registration_enabled: boolean;
  setup_required: boolean;
}

export interface ServerSettingsView {
  server_name: string;
  registration_enabled: boolean;
  public_base_url: string | null;
  is_admin: boolean;
  setup_required?: boolean;
}

export interface PairingCode {
  token: string;
  expires_at: string;
  ttl_minutes: number;
  pairing_url: string;
  connection: ServerInfo;
}

export interface AssistantAnswer {
  question: string;
  answer: string;
  mode: string;
  used_tools: string[];
  data: Record<string, unknown>;
  can_modify_data: boolean;
  disclaimer: string;
  note?: string;
}

// ---------------------------------------------------------------- Phase 4: loans
export type LoanType =
  | "personal"
  | "payday"
  | "cash_advance"
  | "earned_wage_access"
  | "buy_now_pay_later"
  | "installment"
  | "credit_agreement"
  | "other";

export interface Loan {
  id: string;
  name: string;
  lender: string | null;
  loan_type: LoanType;
  original_amount: Money;
  opening_balance: Money;
  balance_as_of: string;
  balance_source: string;
  apr: string | null;
  interest_charged: Money | null;
  fees_charged: Money | null;
  next_payment_date: string | null;
  scheduled_payment: Money | null;
  payment_frequency: string | null;
  remaining_payments: number | null;
  account_id: string | null;
  category_id: string | null;
  status: "active" | "paid_off" | "defaulted";
  notes: string | null;
  created_at: string;
  current_balance: Money;
  principal_repaid: Money;
  interest_paid: Money;
  fees_paid: Money;
  total_repaid: Money;
  balance_is_estimate: boolean;
  progress_percent: Money;
  payment_count: number;
  last_payment_date: string | null;
  estimated_payoff_date: string | null;
  payoff_is_estimate: boolean;
  remaining_installments: number | null;
}

export interface LoanSummary {
  total_outstanding: Money;
  total_original: Money;
  active_loans: number;
  next_payment_date: string | null;
  next_payment_total: Money;
  loans: Loan[];
}

export interface LoanPayment {
  id: string;
  loan_id: string;
  transaction_id: string | null;
  amount: Money;
  principal_amount: Money | null;
  interest_amount: Money | null;
  fee_amount: Money | null;
  paid_on: string;
  status: "suggested" | "confirmed" | "rejected";
  confidence: string;
  is_automatic: boolean;
  is_ambiguous: boolean;
  reason: string | null;
  notes: string | null;
  created_at: string;
  transaction_description: string | null;
  transaction_merchant: string | null;
}

export interface LoanPaymentSuggestion {
  transaction_id: string;
  description: string;
  merchant: string | null;
  amount: Money;
  txn_date: string;
  account_id: string;
  confidence: string;
  reason: string;
  is_ambiguous: boolean;
}

// -------------------------------------------------------------- Phase 4: savings
export type SavingsMode = "virtual" | "account";

export interface SavingsGoal {
  id: string;
  name: string;
  target_amount: Money;
  target_date: string | null;
  mode: SavingsMode;
  saved_amount: Money;
  account_id: string | null;
  account_name: string | null;
  account_balance: Money | null;
  account_is_spendable: boolean | null;
  category_id: string | null;
  contribution_amount: Money | null;
  contribution_frequency: string | null;
  status: "active" | "completed" | "archived";
  color: string | null;
  notes: string | null;
  created_at: string;
  progress_percent: Money;
  remaining_to_target: Money;
  protected_amount: Money;
  protects_money: boolean;
  next_contribution_date: string | null;
  required_per_period: Money | null;
  projected_completion: string | null;
}

export interface SavingsSummary {
  total_target: Money;
  total_saved: Money;
  total_protected: Money;
  active_goals: number;
  completed_goals: number;
  monthly_commitment: Money;
  goals: SavingsGoal[];
}

// ----------------------------------------------------------- Phase 4: obligations
export interface ObligationItem {
  kind: "bill" | "loan" | "credit_card";
  id: string;
  source_id: string;
  name: string;
  detail: string | null;
  due_date: string | null;
  amount: Money;
  status: string;
  is_overdue: boolean;
  is_estimate: boolean;
  is_essential: boolean;
  category_id: string | null;
  account_id: string | null;
  reserved_in_safe_to_spend: boolean;
  remaining_balance?: Money;
}

export interface Obligations {
  today: string;
  horizon_end: string;
  next_payday: string | null;
  items: ObligationItem[];
  counts: { total: number; overdue: number; estimated: number };
  totals: {
    due_in_horizon: Money;
    overdue: Money;
    due_within_7_days: Money;
    due_before_payday: Money;
  };
  income: {
    next_payday: string | null;
    sources: { name: string; amount: Money; frequency: string; next_payday: string | null }[];
    note: string;
  };
  data_freshness: { last_transaction_date: string | null; stale: boolean; warning: string | null };
  double_counting_guards: string[];
}

// ------------------------------------------------- Phase 4: merchants & shopping
export interface MerchantRow {
  merchant_key: string;
  merchant: string;
  category_id: string | null;
  category_name: string | null;
  transaction_count: number;
  total: Money;
  average: Money;
  largest: Money;
  last_purchase: string;
  months_observed: number;
  prior_total: Money;
  change_percent: string | null;
  has_enough_history: boolean;
  confidence: "low" | "medium" | "high";
  window_days: number;
}

export interface MerchantFinding {
  key: string;
  type: string;
  severity: "high" | "medium" | "low";
  merchant: string;
  merchant_key: string;
  category_id?: string;
  title: string;
  message: string;
  confidence: string;
  evidence: Record<string, string | number>;
}

export interface MerchantInsights {
  window_days: number;
  start: string;
  end: string;
  minimum_history: { months: number; transactions: number };
  merchants: MerchantRow[];
  findings: MerchantFinding[];
  dismissed: string[];
  note: string;
}

export interface TrackedLocation {
  id: string;
  name: string;
  merchant: string | null;
  merchant_key: string | null;
  address: string | null;
  latitude: string | null;
  longitude: string | null;
  radius_m: number;
  category_id: string | null;
  monthly_budget: Money | null;
  notify_enabled: boolean;
  is_active: boolean;
  source: string;
  notes: string | null;
  created_at: string;
  visit_count: number;
  last_visit_at: string | null;
  month_spend: Money | null;
  budget_remaining: Money | null;
}

export interface ShoppingVisit {
  id: string;
  tracked_location_id: string | null;
  business_name: string;
  merchant_key: string;
  category_id: string | null;
  visited_at: string;
  visit_day: string;
  status: "detected" | "suggested" | "confirmed" | "ignored";
  confidence: string;
  distance_m: number | null;
  source: string;
  note: string | null;
  is_new_place: boolean;
  visit_count: number;
  transaction_count: number;
  spend_total: Money;
}

export interface ShoppingVisits {
  items: ShoppingVisit[];
  count: number;
  suggested: number;
  tracked_locations: number;
  retention_days: number;
  note: string;
}

export interface LocationSettings {
  location_features_opted_in: boolean;
  shopping_intelligence_enabled: boolean;
  discovery_enabled: boolean;
  paused: boolean;
  location_paused_until: string | null;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  quiet_hours_timezone: string | null;
  notification_cooldown_minutes: number;
  visit_history_retention_days: number;
  tracked_location_count: number;
  supported: { business_lookup: string; lookup_attribution: string };
}

export interface RecommendationItem {
  key: string;
  kind: string;
  severity: "high" | "medium" | "low";
  title: string;
  message: string;
  confidence: string;
  facts: Record<string, string | number | null>;
  period?: Record<string, string>;
  merchant?: string;
  category_id?: string | null;
  suggested_limit?: Money;
}

export interface Recommendations {
  generated_at: string;
  today: string;
  data_freshness: { last_transaction_date: string | null; stale: boolean; checked_at: string };
  safe_to_spend: Money;
  obligations_due: Money;
  savings_protected: Money;
  items: RecommendationItem[];
  note: string;
}
