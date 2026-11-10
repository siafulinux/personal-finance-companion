# Unified financial obligations

One forward-looking list of everything the user owes: recurring bills, loan and advance
instalments, credit-card minimums, and the transfer-style payments that settle a liability.
It exists so nobody has to add up four screens, and so the same outflow is never counted
twice.

Source: `backend/app/services/obligations.py`, exposed as `GET /api/v1/obligations`.

## What is merged

| Kind | Source | Notes |
| --- | --- | --- |
| `bill` | Bill occurrences inside the horizon | Uses the occurrence's **remaining** amount, so a part-paid bill shows what is still owed. |
| `loan` | `upcoming_payments()` for active and defaulted loans | Carries `remaining_balance`; `is_estimate` when the loan's terms are incomplete. |
| `credit_card` | A card's typed-in `minimum_payment` | The only card figure that is an obligation. Purchases are already spending; the repayment is a transfer. |

Items are ordered by due date (undated last), then by name, and each carries
`status` (`upcoming` / `overdue`), `is_overdue`, `is_estimate`, `is_essential`,
`category_id`, `account_id` and `reserved_in_safe_to_spend` so the client can be honest
about what is already accounted for.

## Totals and cash flow

```json
{
  "today": "2026-11-10",
  "horizon_end": "2026-12-25",
  "next_payday": "2026-11-15",
  "items": [],
  "counts": { "total": 0, "overdue": 0, "estimated": 0 },
  "totals": {
    "due_in_horizon": "0.00",
    "overdue": "0.00",
    "due_within_7_days": "0.00",
    "due_before_payday": "0.00"
  },
  "income": { "next_payday": "2026-11-15", "sources": [], "note": "…" },
  "data_freshness": { "last_transaction_date": null, "stale": true, "warning": "…" },
  "double_counting_guards": ["…"]
}
```

- The horizon defaults to 45 days and is clamped to 1–180 days (`?days=`).
- **Income is reported separately and never netted against obligations**, so a payday cannot
  make the amount owed look smaller. `due_before_payday` is the useful comparison instead.
- `data_freshness.stale` is true when there are no transactions in the last 45 days, and the
  response says the list may be out of date rather than implying it is complete.

## The double-counting rules

1. **A bill and its loan instalment cannot both appear.** Loan instalments already settled by
   a recorded repayment are dropped from `upcoming_payments()`, and a confirmed loan payment
   removes the matching bill-like commitment.
2. **Credit-card repayments are transfers, not purchases.** They never appear as spending;
   only a minimum payment the owner typed in appears as an obligation.
3. **Transfers between the user's own accounts are never income or spending.** The
   `double_counting_guards` array states this in every response so a client cannot quietly
   forget it.
4. **A part-paid bill shows the remainder**, not its original amount.

## Where it is used

- `GET /api/v1/obligations` — the merged list.
- `GET /api/v1/safe-to-spend` — bills, loan instalments, credit-card minimums and savings
  contributions are reserved from the same figures, so the two screens cannot disagree.
- The recommendation engine (`app/services/recommendations.py`) emits `obligation` and `loan`
  items from this data.
- The assistant's `obligations` tool reads the same service; the LLM never computes totals.

## Web and Android

- **Web:** sidebar → Obligations. Totals strip (due in horizon, overdue, due in 7 days, due
  before payday), the merged list with kind badges and estimate markers, income shown apart
  from what is owed, and the staleness warning. `web/src/pages/ObligationsPage.tsx`.
- **Android:** Dashboard → Obligations, via `ObligationsViewModel` and
  `ui/screens/ObligationsScreen.kt`, with the same ordering and the same separate income
  block.

## Related

- [Loans & advances](loans-and-advances.md)
- [Safe-to-Spend calculation](safe-to-spend-calculation.md)
- [Savings goals and protected allocations](savings-goals-and-allocations.md)
