# Architecture

## Shape of the system

```
Android (Kotlin/Compose) ─┐
                          ├── HTTPS/JSON ── FastAPI ── services ── PostgreSQL
Web (React/TypeScript)  ──┘                     │
                                                └── pure calculation + matching modules
```

There is one source of financial truth: the API. Both clients render server-computed values; neither recalculates balances locally. The calculation and matching modules are pure functions so they can be tested without a database and reused by a future AI layer.

## Backend layout

```
backend/app/
  api/            versioned routers (auth, accounts, categories, transactions,
                  budgets, bills, imports, insights)
  calculations/   pure Safe-to-Spend + purchase evaluation logic
  matching/       pure bill-payment normalization and scoring
  services/       orchestration: balances, budgets, bills, matching, imports,
                  dashboard, forecast, shopping, assistant tools
  models/         SQLAlchemy models
  schemas/        Pydantic request/response contracts
  imports/        CSV parsing, adapters, preview/commit pipeline
  security/       Argon2id hashing, JWT, cookie/CSRF dependencies
  ai/             provider interface and status (disabled in Phase 1)
  providers/      financial-provider interface for future bank sync
```

Requests use a per-request SQLAlchemy session that commits on success and rolls back on error. All queries are scoped by `user_id`; ownership is never taken from the request body.

## Data model (17 tables)

| Area | Tables |
| --- | --- |
| Identity | `users`, `user_preferences`, `notification_preferences` |
| Money | `financial_accounts`, `balance_adjustments`, `transactions` |
| Planning | `categories`, `budgets`, `budget_allocations`, `planned_reserves`, `income_sources` |
| Bills | `bills`, `bill_occurrences`, `bill_payment_matches`, `merchant_aliases` |
| Import | `transaction_imports`, `import_records` |

Money is `NUMERIC(14,2)` in the database and `Decimal` in Python. It is a decimal string on the wire and is never a float inside the backend.

## Safe-to-Spend

```
eligible_balance  = sum of balances of accounts that count as spendable cash
                    (credit cards and archived/excluded accounts never contribute)
pending_debits    = pending outflows not already linked to a bill
bill_reserves     = unpaid, non-skipped bill occurrences due inside the horizon,
                    minus payments already linked to them (no double counting)
minimum_buffer    = user preference
explicit_reserves = planned reserves (savings goals, sinking funds)

raw       = eligible_balance - pending_debits - bill_reserves - buffer - reserves
safe      = max(raw, 0)
shortfall = max(-raw, 0)
```

- **Horizon**: from today through the next payday, capped at `MAX_SAFE_TO_SPEND_HORIZON_DAYS` (45). Without a known payday, the fallback horizon (14 days) is used and a warning is emitted.
- **Negative results** are clamped to zero, but the shortfall is reported and explained; the app never shows a negative spendable amount.
- **Explanation** is generated alongside the result: each line carries a key, label, signed amount, kind (`credit`/`debit`/`result`) and optional detail. The UI renders the same lines the tests assert on.
- **Staleness** and missing-account conditions produce warnings rather than silently wrong numbers.

Category availability applies the same idea per budget category: allocation + carryover − posted spending − upcoming commitments, then `max_safe_purchase = min(category remaining, Safe-to-Spend)`, reporting which limit bound the answer.

## Bill matching

1. Normalize merchant text (case, punctuation, common processor prefixes/suffixes).
2. Score candidate occurrences using merchant similarity, merchant alias, amount tolerance (absolute and percent), and distance from the due date inside a configurable window.
3. A unique candidate above the auto-match threshold is confirmed automatically; any ambiguity only produces a suggestion.
4. Confirmation is idempotent and one transaction can pay only one occurrence. Partial payments accumulate and remain suggestions until the remainder is zero.
5. Editing or deleting a matched transaction reverts the occurrence, so the ledger and bills cannot drift apart.

## CSV import

Upload → detect delimiter/header → suggest a mapping → preview every row (`ok`, `duplicate`, `error` with a reason) → commit only ready rows. Duplicate detection uses a normalized fingerprint (date, amount, description, account) plus external IDs when present, so re-importing the same file adds nothing. Import records keep the source row for audit. After all rows exist, commit runs the normal bill-matching service per transaction and returns `matched_bills`, `auto_matched` and `suggested_matches`; ambiguous candidates stay suggestions, exactly as with manual entry.

## Web

React 18 + TypeScript + Vite. TanStack Query handles server state; a small typed API client centralizes cookies, CSRF headers and error shapes. Pages: dashboard, accounts, transactions (with import wizard), budgets, bills, calendar, shopping, settings. A single CSS design system provides light, dark and system themes plus responsive layouts down to phone widths.

## Android

Kotlin + Jetpack Compose (Material 3). OkHttp + kotlinx.serialization talk to the same API with a bearer token. DataStore holds the token, server URL and theme. Screens mirror the web app's core loop: Safe-to-Spend dashboard, ledger with transaction create/detail/edit, CSV import, bills with mark-paid and match-confirmation, budgets, shopping check and settings.

Writes are sent to the existing backend endpoints and the affected screens reload when they resume; no balance, budget or Safe-to-Spend value is computed on the device. CSV import uses the Storage Access Framework and streams the selected content URI to the server, so the app needs no storage permission and keeps no local copy. The form uses `BigDecimal` only for validation, and bill matching remains entirely server-side. There is no offline store; the app always reflects the server.

## AI readiness

`app/ai/provider.py` defines a provider interface and reports `disabled`. `app/services/assistant_tools.py` exposes a registry of read-only, permission-checked tools (`safe_to_spend`, `category_availability`, `upcoming_bills`, `forecast`, …) returning structured payloads. No prompt, free text or provider call is used to compute money; a future assistant can only call these tools.

## Deliberate Phase 1 decisions

- Single currency (USD) and single-user accounts. The schema has user ownership everywhere, so sharing can be added without migration pain.
- Server-owned arithmetic instead of client duplication: one implementation, one set of tests, identical web/Android numbers.
- No bank aggregator: CSV import is transparent and testable; the provider interface marks the seam for later.
- No location permissions: the Shopping Check works from category and cash data; location is explicitly deferred.
