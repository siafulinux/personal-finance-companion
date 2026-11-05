const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return currencyFormatter.format(numeric);
}

/** Negative amounts are shown with an explicit minus rather than parentheses. */
export function formatSignedMoney(value: string | number): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${numeric < 0 ? "-" : ""}${formatMoney(Math.abs(numeric))}`;
}

export function formatPercent(value: string | number | null, digits = 0): string {
  if (value === null) return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${numeric.toFixed(digits)}%`;
}

export function todayISO(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  return new Date(now.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

export function formatDate(value: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return value;
  const date = new Date(year, month - 1, day);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(opts ?? { year: "numeric" }),
  }).format(date);
}

export function formatMonth(year: number, month: number): string {
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(
    new Date(year, month - 1, 1)
  );
}

export function monthInputValue(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function parseMonth(value: string): { year: number; month: number } {
  const [year, month] = value.split("-").map(Number);
  return { year, month };
}

export function daysBetween(from: string, to: string): number {
  const start = new Date(`${from}T00:00:00`).getTime();
  const end = new Date(`${to}T00:00:00`).getTime();
  return Math.round((end - start) / 86_400_000);
}

export function relativeDueLabel(dueDate: string, today: string): string {
  const days = daysBetween(today, dueDate);
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days === -1) return "Overdue by 1 day";
  if (days < 0) return `Overdue by ${Math.abs(days)} days`;
  if (days <= 14) return `Due in ${days} days`;
  return `In ${days} days`;
}

export function addDaysISO(dateISO: string, days: number): string {
  const [year, month, day] = dateISO.slice(0, 10).split("-").map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + days);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

export function accountTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    checking: "Checking",
    savings: "Savings",
    cash: "Cash",
    digital_wallet: "Digital wallet",
    payment_app: "Payment app",
    credit_card: "Credit card",
    other: "Other",
  };
  return labels[type] ?? type;
}

export function txTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    income: "Income",
    purchase: "Purchase",
    bill_payment: "Bill payment",
    refund: "Refund",
    transfer: "Transfer",
    adjustment: "Adjustment",
  };
  return labels[type] ?? type;
}

export function frequencyLabel(frequency: string): string {
  const labels: Record<string, string> = {
    weekly: "Weekly",
    biweekly: "Every 2 weeks",
    monthly: "Monthly",
    every_two_months: "Every 2 months",
    quarterly: "Quarterly",
    semiannual: "Every 6 months",
    annual: "Yearly",
    custom: "Custom",
  };
  return labels[frequency] ?? frequency;
}

export function amountInput(value: string): string | null {
  const cleaned = value.replace(/[^0-9.\-]/g, "");
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? cleaned : null;
}
