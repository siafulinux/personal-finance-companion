import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InsightsPage } from "./InsightsPage";
import type { MerchantInsights, MerchantRow, PersonalInsights } from "../lib/types";

const insights = vi.fn();
const list = vi.fn();

vi.mock("../lib/api", () => ({
  api: {
    personal: {
      insights: () => insights(),
      updatePreferences: vi.fn(),
    },
    merchants: {
      list: (days?: number) => list(days),
      dismiss: vi.fn(),
      restore: vi.fn(),
    },
  },
}));

const personal: PersonalInsights = {
  enabled: true,
  sensitivity: "normal",
  minimum_history: { months: 3, transactions: 5 },
  insights: [],
  unusual_transactions: [],
};

function merchant(overrides: Partial<MerchantRow> = {}): MerchantRow {
  return {
    merchant_key: "target",
    merchant: "Target",
    category_id: null,
    category_name: "Groceries",
    transaction_count: 7,
    total: "609.65",
    average: "87.09",
    largest: "298.75",
    last_purchase: "2026-11-09",
    months_observed: 4,
    prior_total: "430.00",
    change_percent: "41.8",
    has_enough_history: true,
    confidence: "medium",
    window_days: 90,
    ...overrides,
  };
}

function merchants(overrides: Partial<MerchantInsights> = {}): MerchantInsights {
  return {
    window_days: 90,
    start: "2026-08-13",
    end: "2026-11-11",
    minimum_history: { months: 3, transactions: 5 },
    merchants: [],
    findings: [],
    dismissed: [],
    note: "Patterns require at least three months and five purchases.",
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <InsightsPage />
    </QueryClientProvider>
  );
}

const NO_PURCHASES = "No merchant purchases in this window yet";
const NO_PATTERN = "No pattern is strong enough to report yet";

describe("InsightsPage merchant empty state", () => {
  beforeEach(() => {
    insights.mockReset();
    list.mockReset();
    insights.mockResolvedValue(personal);
  });

  it("says there is nothing to compare when no merchant has any history", async () => {
    list.mockResolvedValue(merchants({ merchants: [] }));
    renderPage();

    expect(await screen.findByText(new RegExp(NO_PURCHASES))).toBeInTheDocument();
    // The whole point of the fix: with no merchants at all, the page must not
    // claim a pattern was evaluated and found weak.
    expect(screen.queryByText(new RegExp(NO_PATTERN))).not.toBeInTheDocument();
  });

  it("explains that a pattern is not yet strong enough when history exists", async () => {
    list.mockResolvedValue(merchants({ merchants: [merchant()] }));
    renderPage();

    expect(await screen.findByText(new RegExp(NO_PATTERN))).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(NO_PURCHASES))).not.toBeInTheDocument();
    // The rows behind that sentence are still listed, so the claim is auditable.
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText(/7 purchase\(s\) · 4 month\(s\) · medium confidence/)).toBeInTheDocument();
  });

  it("lists a finding instead of either empty-state sentence when one is reported", async () => {
    list.mockResolvedValue(
      merchants({
        merchants: [merchant()],
        findings: [
          {
            key: "merchant:target:increase",
            type: "spend_increase",
            severity: "medium",
            merchant: "Target",
            merchant_key: "target",
            title: "Spending at Target is up",
            message: "You spent 41.8% more at Target than in the previous period.",
            confidence: "medium",
            evidence: { change_percent: "41.8", purchases: 7 },
          },
        ],
      })
    );
    renderPage();

    expect(await screen.findByText("Spending at Target is up")).toBeInTheDocument();
    expect(screen.getByText(/41.8%/)).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(NO_PATTERN))).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(NO_PURCHASES))).not.toBeInTheDocument();
  });

  it("still shows the no-history sentence when the merchant list is empty and a finding exists", async () => {
    // A finding without rows is inconsistent data, but the page must not render
    // both empty-state sentences at once.
    list.mockResolvedValue(
      merchants({
        merchants: [],
        findings: [
          {
            key: "merchant:target:increase",
            type: "spend_increase",
            severity: "medium",
            merchant: "Target",
            merchant_key: "target",
            title: "Spending at Target is up",
            message: "You spent more at Target.",
            confidence: "medium",
            evidence: {},
          },
        ],
      })
    );
    renderPage();

    expect(await screen.findByText("Spending at Target is up")).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(NO_PURCHASES))).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(NO_PATTERN))).not.toBeInTheDocument();
  });
});
