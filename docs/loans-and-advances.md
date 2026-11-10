# Loans & Advances

Loans and advances are first-class liabilities in the Personal Finance Companion, not
disguised bills. Each one has its own balance, repayment history and link to the bank
transaction that settled it, and its instalments are reserved inside Safe-to-Spend exactly
once.

## What a loan records

| Field | Notes |
| --- | --- |
| Lender / provider | Free text (`lender`), used for matching descriptions. |
| Name | Unique per user. |
| Type | `personal`, `payday`, `cash_advance`, `earned_wage_access`, `buy_now_pay_later`, `installment`, `credit_agreement`, `other`. |
| Original amount | What was borrowed. Checked `> 0`. |
| Opening balance + `balance_as_of` | The outstanding figure **and the date you last knew it**. Never silently recomputed. |
| Balance source | `user`, `provider` or `derived` — tells the UI whether the balance was typed in or imported. |
| APR | Nullable. Many payday/BNPL products publish none, and a blank is better than a guess. |
| Interest / fees charged | Nullable running totals the user maintains. |
| Next payment date, scheduled payment, frequency | Drive the obligation and the payoff projection. |
| Remaining payments | Optional; enables a payoff date. |
| Linked account / category | Where the repayment leaves from and how it is categorised. |
| Status | `active`, `paid_off`, `defaulted`. |
| Notes | Free text. |

## Balances: derived, and honest about it

`GET /api/v1/loans` returns, per loan:

- `opening_balance` and `balance_as_of` exactly as stored;
- `principal_repaid` — the sum of **confirmed** repayment allocations marked as principal;
- `current_balance` = opening balance − confirmed principal repaid;
- `balance_is_estimate` — true when the terms are incomplete;
- `payoff_is_estimate`, `remaining_installments`, `progress_percent`;
- `interest_paid`, `fees_paid`, `total_repaid`, `payment_count`, `last_payment_date`.

A repayment does not automatically reduce principal by its full amount. A payment records
`amount` (what left the bank) plus an optional split of `principal_amount`,
`interest_amount` and `fee_amount`, because on an interest-bearing loan most of an early
instalment is interest. Only the principal part reduces the balance; when the split is
absent the whole amount is treated as principal **and** the balance is flagged as an
estimate.

`balance_is_estimate` is true whenever the engine cannot verify the arithmetic, for example
when `remaining_payments` is unknown or a payment was recorded without a split. The UI
labels those loans "estimate" rather than presenting the figure as authoritative.

### Payoff projection

`estimated_payoff_date` is produced only from figures the user gave: remaining count,
scheduled payment and frequency. The projection stops at 600 periods
(`MAX_PROJECTION_PERIODS`) and returns `null` instead of inventing a date when the inputs
are missing. Nothing is inferred from the lender's marketing terms.

## Repayments and bank transactions

Every repayment goes through `/api/v1/loans/{id}/payments` and is a `LoanPayment` row with
its own status:

- `suggested` — the matcher proposed a link; nothing has been applied to the balance.
- `confirmed` — the user accepted it, or it was auto-matched with strong evidence.
- `rejected` — the user said no; the candidate is remembered so it is not re-suggested.

### Matching

`backend/app/services/loan_matching.py` scores candidates as a transparent weighted sum:

| Signal | Weight |
| --- | --- |
| Amount closeness to the scheduled payment | 0.50 |
| Lender or loan name appearing in the description | 0.25 |
| Date proximity to the next due date (14 days before, 7 after) | 0.25 |

Automatic linking happens only when **all** of these hold:

1. the best score clears the user's `auto_match_threshold` (default 0.85);
2. there is no close runner-up — two plausible loans means the user decides
   (`AMBIGUITY_MARGIN` = 0.08);
3. the transaction is not already confirmed against a bill;
4. the transaction is not already a loan payment;
5. automatic bill matching is enabled for the account owner.

Everything else stays a suggestion in **Loans → Match a bank transaction**.

### Double-counting protection

A confirmed loan payment is a *transfer* to a liability. It removes the transaction from
expense totals and it removes that loan instalment from the reserve list, so a repayment
cannot appear both as a bill-like commitment and as spending. If the linked bank
transaction is itself matched to a bill, the link is refused — one outflow cannot settle
two obligations.

### Partial, extra and corrected payments

- Partial payments: record the actual amount; principal reduces by the principal portion.
- Extra payments: same path, any amount, with its own `reason`.
- Fees and interest: set `interest_amount` / `fee_amount` on the payment, or keep
  `interest_charged` / `fees_charged` at the loan level.
- Corrections: `PATCH /api/v1/loans/{id}/payments/{payment_id}` edits the recorded payment;
  `POST .../confirm` and `.../reject` change its status; `DELETE` removes it and reopens the
  transaction for matching.

## API surface

```
GET    /api/v1/loans                        summary + loans
POST   /api/v1/loans                        create (manual or imported)
GET    /api/v1/loans/{id}                   one loan with numbers
PATCH  /api/v1/loans/{id}                   edit
DELETE /api/v1/loans/{id}                   remove
GET    /api/v1/loans/{id}/payments          repayment history
POST   /api/v1/loans/{id}/payments          record a repayment
PATCH  /api/v1/loans/{id}/payments/{pid}    correct a repayment
POST   /api/v1/loans/{id}/payments/{pid}/confirm
POST   /api/v1/loans/{id}/payments/{pid}/reject
DELETE /api/v1/loans/{id}/payments/{pid}
GET    /api/v1/loans/{id}/suggestions       candidate bank transactions
POST   /api/v1/loans/{id}/suggestions/{transaction_id}
```

Every query is filtered by `user_id`; a loan belonging to another account answers 404, not
403, so the existence of another user's records is not disclosed.

## Web and Android

- **Web:** sidebar → Loans. Summary cards (total outstanding, next payment), one card per
  loan with balance, APR, next due date and estimate badge, repayment history, "Record a
  repayment", "Match a bank transaction", and an explainer of how a balance becomes an
  estimate. `web/src/pages/LoansPage.tsx`.
- **Android:** Dashboard → Loans. Same reads and writes through
  `FinanceRepository`/`LoansViewModel`; add, edit, delete, record repayment and confirm a
  suggested match all work offline-tolerantly (errors are shown, not swallowed).
  `android/app/src/main/java/com/pfc/companion/ui/screens/LoansScreen.kt`.

## Related

- [Unified financial obligations](unified-financial-obligations.md)
- [Safe-to-Spend calculation](safe-to-spend-calculation.md)
- [API reference](api.md)
