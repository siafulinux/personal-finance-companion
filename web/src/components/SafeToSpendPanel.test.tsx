import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SafeToSpendPanel } from "./SafeToSpendPanel";
import type { SafeToSpend } from "../lib/types";

const base: SafeToSpend = {
  currency: "USD",
  as_of: "2026-11-02T12:00:00Z",
  today: "2026-11-02",
  horizon_end: "2026-11-16",
  payday: "2026-11-16",
  eligible_balance: "900.00",
  pending_debits: "40.00",
  bill_reserves: "300.00",
  minimum_buffer: "200.00",
  explicit_reserves: "50.00",
  raw_amount: "310.00",
  safe_to_spend: "310.00",
  projected_shortfall: "0.00",
  is_negative: false,
  accounts: [],
  bills: [],
  reserves: [],
  pending_items: [],
  warnings: [],
  explanation: [
    { key: "eligible_balance", label: "Available in spending accounts", amount: "900.00", kind: "credit", detail: null },
    { key: "safe_to_spend", label: "Safe to spend now", amount: "310.00", kind: "result", detail: null },
  ],
  stale_information: false,
};

describe("SafeToSpendPanel", () => {
  it("shows the calculated amount and breakdown", () => {
    render(<SafeToSpendPanel data={base} />);
    expect(screen.getByText("$310.00")).toBeInTheDocument();
    expect(screen.getByText("$900.00")).toBeInTheDocument();
    expect(screen.getByText(/Bills reserved/)).toBeInTheDocument();
  });

  it("breaks out loan, card and savings reservations when present", () => {
    render(
      <SafeToSpendPanel
        data={{
          ...base,
          loan_reserves: "100.00",
          credit_card_reserves: "35.00",
          savings_reserves: "200.00",
          obligations_total: "435.00",
          loans: [
            {
              loan_id: "l1",
              name: "Payday",
              due_date: "2026-11-10",
              amount: "100.00",
              is_overdue: false,
              is_estimate: true,
              remaining_balance: "300.00",
            },
          ],
          savings: [
            {
              goal_id: "g1",
              name: "Emergency fund",
              amount: "200.00",
              mode: "virtual",
              is_planned_contribution: false,
              due_date: null,
            },
          ],
          credit_cards: [
            { account_id: "c1", name: "Visa", minimum_payment: "35.00", due_date: null },
          ],
        }}
      />
    );
    // The breakdown lists each reservation separately so the total is auditable.
    expect(screen.getByText(/Loan repayments/)).toBeInTheDocument();
    expect(screen.getByText(/Card minimums/)).toBeInTheDocument();
    expect(screen.getByText(/Savings goals/)).toBeInTheDocument();
    expect(screen.getByText("-$100.00")).toBeInTheDocument();
    expect(screen.getByText("-$35.00")).toBeInTheDocument();
  });

  it("warns when the plan is short", () => {
    render(
      <SafeToSpendPanel
        data={{ ...base, safe_to_spend: "0.00", projected_shortfall: "390.00", is_negative: true }}
      />
    );
    expect(screen.getByText(/Projected shortfall \$390.00/)).toBeInTheDocument();
    expect(
      screen.getByText(/Every available dollar is already committed/)
    ).toBeInTheDocument();
  });
});
