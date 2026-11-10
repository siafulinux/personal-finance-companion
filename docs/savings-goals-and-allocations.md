# Savings goals and protected allocations

Savings goals let a user commit money on purpose. The hard part is not the goal list; it is
making sure a dollar of savings is never subtracted from Safe-to-Spend twice. That invariant
is what `backend/app/services/savings.py` exists to keep.

## Two kinds of savings

| Mode | Where the money is | What the engine does |
| --- | --- | --- |
| `virtual` | Still in the everyday account. | Subtracts the goal's `saved_amount` from Safe-to-Spend. The money is protected, not moved. |
| `account` | Physically in a linked savings account. | Subtracts nothing when that account is excluded from spending (it was never part of the eligible balance). If the owner deliberately keeps the account spendable, the goal protects its `saved_amount` there. |

Nothing in this phase moves money between accounts. A goal is a reservation, and the API
says so in every response note.

The double-deduction rules, in order:

1. A linked account that is **excluded** from Safe-to-Spend contributes nothing to
   `eligible_balance`, so its goal protects nothing extra — regardless of mode.
2. A `virtual` goal whose account is **included** protects its amount once.
3. Planned contributions (future instalments before the next payday) are reserved like a
   bill and marked `is_planned_contribution: true`, never as money already saved.
4. A goal can never protect more than its own `saved_amount`.

## What a goal records

- `name` (unique per user), `target_amount`, optional `target_date`;
- `mode` (`virtual` / `account`) and optional `account_id`;
- `saved_amount` — protected amount for virtual goals, attributed share for account goals;
- optional `contribution_amount` + `contribution_frequency` (`weekly`, `biweekly`,
  `monthly`, …), which produce the reserve schedule;
- optional `category_id`, `color`, `notes`;
- `status` (`active`, `completed`, `archived`) and `completed_at`;
- a contribution ledger (`savings_contributions`) with date, amount, source and note.

`contribution_frequency` schedules are projected forward only up to the Safe-to-Spend
horizon, and stop after `MAX_SCHEDULE_ITERATIONS` (600) periods.

## API surface

```
GET    /api/v1/savings                              summary + goals
POST   /api/v1/savings                              create a goal
GET    /api/v1/savings/{id}                         one goal with numbers
PATCH  /api/v1/savings/{id}                         edit (including mode and linked account)
DELETE /api/v1/savings/{id}
GET    /api/v1/savings/{id}/contributions           contribution history
POST   /api/v1/savings/{id}/contributions           record a contribution
DELETE /api/v1/savings/{id}/contributions/{cid}
```

Each goal also returns derived, read-only numbers the UI must not recompute:
`protected_amount`, `protects_money` (whether this goal actually reduces Safe-to-Spend),
`progress_percent`, `remaining_to_target`, `next_contribution_date`,
`required_per_period` and `projected_completion`.

The summary returns `total_target`, `total_saved`, `total_protected` (what actually leaves
Safe-to-Spend), `active_goals`, `completed_goals` and `monthly_commitment`.

Every goal is owned by one user; another user's goal answers 404, and a linked account or
category must belong to the same user (validated on write).

## Completing a goal

A goal whose `saved_amount` reaches `target_amount` is completed either by
`PATCH /api/v1/savings/{id}` with `{"status": "completed"}`, or at creation time with
`mark_complete: true`. Archiving (`status: "archived"`) removes it from the active list
without claiming success. Completed goals release their protection — the money is ordinary
balance again — and `protects_money` becomes false.

## Web and Android

- **Web:** sidebar → Savings. Cards per goal with progress, target date, mode badge
  ("protected in place" / "in its own account"), contribution schedule, a contribution
  form and an archive action. `web/src/pages/SavingsPage.tsx`.
- **Android:** Dashboard → Savings, via `SavingsViewModel` and
  `ui/screens/SavingsScreen.kt`: same list, create/edit, record contribution, complete or
  archive, plus the linked-account picker.

## What is deliberately not implemented

- Automatic transfers. Moving money requires explicit authorisation, provider capability
  and extra security controls, and none of that is in this phase.
- Interest on savings goals. The engine reports balances, not projected yield.

## Related

- [Safe-to-Spend calculation](safe-to-spend-calculation.md)
- [Unified financial obligations](unified-financial-obligations.md)
