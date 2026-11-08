import type {
  Account,
  AccountSummary,
  Bill,
  BudgetSummary,
  Category,
  CategoryAvailability,
  Dashboard,
  Forecast,
  ImportJob,
  ImportPreview,
  IncomeSource,
  MatchSuggestionGroup,
  NotificationPreferences,
  Occurrence,
  PairingCode,
  Preferences,
  ServerInfo,
  ServerSettingsView,
  Profile,
  SafeToSpend,
  ShoppingResult,
  AssistantAnswer,
  AssistantStatus,
  CategorySuggestionItem,
  LinkedAccountRef,
  PersonalInsights,
  ProviderInfo,
  ProviderLink,
  RecurringItem,
  SyncRunSummary,
  Transaction,
  TransactionPage,
  UploadResponse,
  User,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function request<T>(
  path: string,
  options: RequestInit & { query?: Record<string, string | number | boolean | undefined | null> } = {}
): Promise<T> {
  const { query, ...init } = options;
  let url = `${API_BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    });
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD") {
    const csrf = readCookie("pfc_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      method,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the finance server. Is it running?");
  }

  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : "Something went wrong. Please try again.";
    throw new ApiError(response.status, detail, payload);
  }
  return payload as T;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  server: {
    // Public: this is how a browser or phone that knows only a URL learns what
    // it is talking to, and whether the server still needs its first-run setup.
    info: () => request<ServerInfo>("/server/info"),
    setup: (body: {
      server_name: string;
      admin_email: string;
      admin_name: string;
      admin_password: string;
      registration_enabled: boolean;
      public_base_url?: string | null;
    }) => request<{ server: ServerInfo }>("/server/setup", { method: "POST", body: json(body) }),
    settings: () =>
      request<{ server: ServerInfo; settings: ServerSettingsView }>("/server/settings"),
    updateSettings: (body: {
      server_name?: string;
      registration_enabled?: boolean;
      public_base_url?: string | null;
    }) =>
      request<{ server: ServerInfo; settings: ServerSettingsView }>("/server/settings", {
        method: "PATCH",
        body: json(body),
      }),
    createPairing: (label?: string) =>
      request<PairingCode>("/server/pairing", {
        method: "POST",
        body: json({ label: label || null }),
      }),
  },
  auth: {
    register: (body: {
      email: string;
      password: string;
      display_name: string;
      timezone: string;
    }) => request<{ access_token: string }>("/auth/register", { method: "POST", body: json(body) }),
    login: (body: { email: string; password: string }) =>
      request<{ access_token: string }>("/auth/login", { method: "POST", body: json(body) }),
    logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),
    // Changing the password ends every other session; this browser is signed back
    // in by the new cookie the response sets.
    changePassword: (body: { current_password: string; new_password: string }) =>
      request<{ access_token: string }>("/auth/password", { method: "POST", body: json(body) }),
    me: () => request<Profile>("/auth/me"),
    onboarding: (body: unknown) =>
      request<Profile>("/auth/onboarding", { method: "POST", body: json(body) }),
    updateProfile: (body: { display_name?: string; timezone?: string }) =>
      request<Profile>("/auth/profile", { method: "PATCH", body: json(body) }),
    updatePreferences: (body: Partial<Preferences>) =>
      request<Preferences>("/auth/preferences", { method: "PATCH", body: json(body) }),
    updateNotifications: (body: Partial<NotificationPreferences>) =>
      request<NotificationPreferences>("/auth/notification-preferences", {
        method: "PATCH",
        body: json(body),
      }),
    exportData: () => request<Record<string, unknown>>("/account/export"),
    deleteAccount: (body: { password: string; confirm: string }) =>
      request<{ message: string }>("/account/delete", { method: "POST", body: json(body) }),
  },

  meta: () => request<Record<string, unknown>>("/meta"),

  accounts: {
    list: (includeArchived = false) =>
      request<AccountSummary>("/accounts", { query: { include_archived: includeArchived } }),
    get: (id: string) => request<Account>(`/accounts/${id}`),
    create: (body: unknown) => request<Account>("/accounts", { method: "POST", body: json(body) }),
    update: (id: string, body: unknown) =>
      request<Account>(`/accounts/${id}`, { method: "PATCH", body: json(body) }),
    archive: (id: string) => request<Account>(`/accounts/${id}/archive`, { method: "POST" }),
    remove: (id: string) => request<void>(`/accounts/${id}`, { method: "DELETE" }),
    adjustments: (id: string) =>
      request<
        {
          id: string;
          amount: string;
          previous_balance: string;
          new_balance: string;
          reason: string;
          created_at: string;
        }[]
      >(`/accounts/${id}/adjustments`),
    adjust: (id: string, body: { target_balance: string; reason: string }) =>
      request<{ id: string }>(`/accounts/${id}/adjustments`, { method: "POST", body: json(body) }),
  },

  categories: {
    list: (includeArchived = false) =>
      request<Category[]>("/categories", { query: { include_archived: includeArchived } }),
    create: (body: unknown) => request<Category>("/categories", { method: "POST", body: json(body) }),
    update: (id: string, body: unknown) =>
      request<Category>(`/categories/${id}`, { method: "PATCH", body: json(body) }),
    archive: (id: string) => request<Category>(`/categories/${id}/archive`, { method: "POST" }),
    remove: (id: string) => request<void>(`/categories/${id}`, { method: "DELETE" }),
  },

  transactions: {
    list: (query: Record<string, string | number | boolean | undefined | null>) =>
      request<TransactionPage>("/transactions", { query }),
    create: (body: unknown) =>
      request<{
        transaction: Transaction;
        match_info: { outcome: string; reason?: string; bill_name?: string } | null;
        possible_duplicates: { transaction_id: string; description: string; amount: string; txn_date: string }[];
      }>("/transactions", { method: "POST", body: json(body) }),
    update: (id: string, body: unknown) =>
      request<Transaction>(`/transactions/${id}`, { method: "PATCH", body: json(body) }),
    remove: (id: string) => request<void>(`/transactions/${id}`, { method: "DELETE" }),
  },

  imports: {
    list: () => request<ImportJob[]>("/imports"),
    upload: (file: File, accountId: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("account_id", accountId);
      return request<UploadResponse>("/imports", { method: "POST", body: form });
    },
    preview: (id: string, mapping: Record<string, string | null>) =>
      request<ImportPreview>(`/imports/${id}/preview`, {
        method: "POST",
        body: json({ mapping }),
      }),
    commit: (id: string, mapping: Record<string, string | null>) =>
      request<{
        imported: number;
        duplicates: number;
        rejected: number;
        already_committed?: boolean;
        matched_bills?: number;
      }>(`/imports/${id}/commit`, { method: "POST", body: json({ mapping }) }),
    records: (id: string) =>
      request<
        {
          id: string;
          row_number: number;
          status: string;
          reason: string | null;
          transaction_id: string | null;
        }[]
      >(`/imports/${id}/records`),
  },

  budgets: {
    current: () => request<BudgetSummary>("/budgets/current"),
    month: (year: number, month: number) => request<BudgetSummary>(`/budgets/${year}/${month}`),
    create: (body: unknown) =>
      request<BudgetSummary>("/budgets", { method: "POST", body: json(body) }),
    update: (id: string, body: unknown) =>
      request<BudgetSummary>(`/budgets/${id}`, { method: "PATCH", body: json(body) }),
    copy: (body: unknown) =>
      request<BudgetSummary>("/budgets/copy", { method: "POST", body: json(body) }),
    wizard: (body: unknown) =>
      request<BudgetSummary>("/budgets/wizard", { method: "POST", body: json(body) }),
    category: (categoryId: string) =>
      request<CategoryAvailability>(`/safe-to-spend/category/${categoryId}`),
  },

  bills: {
    list: (includeInactive = false) =>
      request<{ items: Bill[] }>("/bills", { query: { include_inactive: includeInactive } }),
    create: (body: unknown) => request<Bill>("/bills", { method: "POST", body: json(body) }),
    update: (id: string, body: unknown) =>
      request<Bill>(`/bills/${id}`, { method: "PATCH", body: json(body) }),
    remove: (id: string) => request<void>(`/bills/${id}`, { method: "DELETE" }),
    occurrences: (query: Record<string, string | number | boolean | undefined>) =>
      request<Occurrence[]>("/bill-occurrences", { query }),
    calendar: (year: number, month: number) =>
      request<{
        year: number;
        month: number;
        start_date: string;
        end_date: string;
        occurrences: Occurrence[];
        totals: Record<string, string>;
      }>("/bills/calendar", { query: { year, month } }),
    markPaid: (id: string) =>
      request<Occurrence>(`/bill-occurrences/${id}/mark-paid`, {
        method: "POST",
        body: json({}),
      }),
    markUnpaid: (id: string) =>
      request<Occurrence>(`/bill-occurrences/${id}/unpaid`, { method: "POST" }),
    skip: (id: string) =>
      request<Occurrence>(`/bill-occurrences/${id}/skip`, { method: "POST" }),
    recordPayment: (
      id: string,
      body: { account_id: string; amount?: string; paid_on?: string; notes?: string }
    ) => request<Occurrence>(`/bill-occurrences/${id}/record-payment`, {
      method: "POST",
      body: json(body),
    }),
    suggestions: () =>
      request<{ items: MatchSuggestionGroup[] }>("/match-suggestions"),
    confirmMatch: (matchId: string, amount?: string) =>
      request<unknown>(`/matches/${matchId}/confirm`, {
        method: "POST",
        body: json(amount ? { amount } : {}),
      }),
    rejectMatch: (matchId: string) =>
      request<unknown>(`/matches/${matchId}/reject`, { method: "POST" }),
    link: (occurrenceId: string, transactionId: string) =>
      request<unknown>("/matches/link", {
        method: "POST",
        body: json({ occurrence_id: occurrenceId, transaction_id: transactionId }),
      }),
    aliases: () =>
      request<{ id: string; alias: string; canonical_merchant: string; notes: string | null }[]>(
        "/merchant-aliases"
      ),
    createAlias: (body: { alias: string; canonical_merchant: string; notes?: string }) =>
      request<{ id: string; alias: string; canonical_merchant: string }>("/merchant-aliases", {
        method: "POST",
        body: json(body),
      }),
    removeAlias: (id: string) =>
      request<void>(`/merchant-aliases/${id}`, { method: "DELETE" }),
  },

  insights: {
    dashboard: () => request<Dashboard>("/dashboard"),
    safeToSpend: () => request<SafeToSpend>("/safe-to-spend"),
    forecast: (days = 60) => request<Forecast>("/forecast", { query: { days } }),
    shopping: (body: { store_name: string; category_id: string; expected_amount?: string | null; note?: string }) =>
      request<ShoppingResult>("/shopping/check", { method: "POST", body: json(body) }),
    aiStatus: () => request<{ enabled: boolean; provider: string; phase: string }>("/ai/status"),
  },

  connectivity: {
    providers: () => request<{ providers: ProviderInfo[] }>("/connectivity/providers"),
    linkToken: (provider: string) =>
      request<{ provider: string; link_token: string; mode: string; note?: string }>(
        "/connectivity/link-token",
        { method: "POST", body: json({ provider }) }
      ),
    exchange: (body: { provider: string; public_token: string; consent: boolean }) =>
      request<{
        link: ProviderLink;
        accounts: LinkedAccountRef[];
        sync: SyncRunSummary;
      }>("/connectivity/exchange", { method: "POST", body: json(body) }),
    links: () => request<{ links: ProviderLink[] }>("/connectivity/links"),
    sync: (linkId: string, fullRefresh = false) =>
      request<{ sync: SyncRunSummary; link: ProviderLink; error?: string }>(
        `/connectivity/links/${linkId}/sync`,
        { method: "POST", query: { full_refresh: fullRefresh } }
      ),
    unlink: (linkId: string, deleteData: boolean) =>
      request<{
        revoked_at_provider: boolean;
        deleted_transactions: number;
        deleted_accounts: number;
        kept_accounts: number;
      }>(`/connectivity/links/${linkId}`, { method: "DELETE", query: { delete_data: deleteData } }),
    syncRuns: (limit = 20) =>
      request<{ runs: SyncRunSummary[] }>("/connectivity/sync-runs", { query: { limit } }),
  },

  review: {
    suggestions: (status = "suggested") =>
      request<{ items: CategorySuggestionItem[]; count: number }>("/suggestions", {
        query: { status },
      }),
    accept: (id: string) =>
      request<CategorySuggestionItem>(`/suggestions/${id}/accept`, { method: "POST" }),
    reject: (id: string) =>
      request<CategorySuggestionItem>(`/suggestions/${id}/reject`, { method: "POST" }),
    recurring: () =>
      request<{
        items: RecurringItem[];
        subscriptions: RecurringItem[];
        subscription_monthly_total: string;
        note: string;
      }>("/recurring"),
    detectRecurring: () =>
      request<{ detected: number; items: RecurringItem[] }>("/recurring/detect", {
        method: "POST",
      }),
    confirmRecurring: (id: string) =>
      request<RecurringItem>(`/recurring/${id}/confirm`, { method: "POST" }),
    dismissRecurring: (id: string) =>
      request<RecurringItem>(`/recurring/${id}/dismiss`, { method: "POST" }),
  },

  personal: {
    insights: () => request<PersonalInsights>("/insights/personal"),
    merchant: (merchant: string) =>
      request<Record<string, unknown>>("/insights/merchant", { query: { merchant } }),
    updatePreferences: (body: {
      ai_consent?: boolean;
      personalized_insights_enabled?: boolean;
      insight_sensitivity?: string;
      recurring_detection_enabled?: boolean;
    }) =>
      request<{
        ai_consent: boolean;
        personalized_insights_enabled: boolean;
        insight_sensitivity: string;
        recurring_detection_enabled: boolean;
      }>("/insights/preferences", { method: "PATCH", body: json(body) }),
  },

  assistant: {
    status: () => request<AssistantStatus>("/assistant/status"),
    ask: (question: string) =>
      request<AssistantAnswer>("/assistant/ask", {
        method: "POST",
        body: json({ question }),
      }),
    consent: (consent: boolean) =>
      request<{ ai_consent: boolean }>("/assistant/consent", {
        method: "POST",
        body: json({ consent }),
      }),
  },

  income: {
    list: () => request<IncomeSource[]>("/income-sources"),
    create: (body: unknown) =>
      request<IncomeSource>("/income-sources", { method: "POST", body: json(body) }),
    update: (id: string, body: unknown) =>
      request<IncomeSource>(`/income-sources/${id}`, { method: "PATCH", body: json(body) }),
    remove: (id: string) => request<void>(`/income-sources/${id}`, { method: "DELETE" }),
  },
};

export type { User };
