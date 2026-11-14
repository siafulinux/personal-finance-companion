# API

Base URL: `http://127.0.0.1:8010/api/v1` (or your configured host/port). Interactive docs: `/api/docs`, OpenAPI: `/api/openapi.json`.

## Authentication

- `POST /auth/register` — `{email, password, display_name, timezone?, currency?}` → `{access_token, token_type, expires_in}` and session cookies.
- `POST /auth/login` — `{email, password}` → same token response.
- `POST /auth/logout` — clears cookies.
- `POST /auth/password` — `{current_password, new_password}` → a fresh token response. The current password must be correct (otherwise `401`) and the new one must satisfy the policy (`422`); it must also differ from the current one. The change bumps the account's token version, so **every other session is refused from its next request**, while this device is signed back in with the returned token and refreshed cookies.
- `GET /auth/me` — profile, preferences and notification preferences.
- `PATCH /auth/profile`, `PATCH /auth/preferences`, `PATCH /auth/notification-preferences`
- `POST /auth/onboarding` — guided first-run setup.
- `GET /account/export` — full JSON export of the user's data.
- `POST /account/delete` — deletes the account and its rows (requires password confirmation).

Two authentication modes are supported:

| Client | Credential | CSRF |
| --- | --- | --- |
| Browser | httpOnly session cookie | `X-CSRF-Token` header must match the `pfc_csrf` cookie on POST/PATCH/DELETE |
| Native/CLI | `Authorization: Bearer <access_token>` | not required |

All responses are `Cache-Control: no-store` and carry `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`.

## Endpoints

### Accounts and categories

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/accounts` | Balances, pending/available totals, cash and debt |
| POST | `/accounts` | Create an account |
| GET/PATCH/DELETE | `/accounts/{id}` | Read, rename/reconfigure, delete |
| POST | `/accounts/{id}/archive` | Archive instead of delete |
| GET/POST | `/accounts/{id}/adjustments` | Balance adjustment audit trail |
| GET/POST | `/categories` | List or create categories |
| GET/PATCH/DELETE | `/categories/{id}` | Manage a category |
| POST | `/categories/{id}/archive` | Archive a category |

### Transactions

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/transactions` | Filter by `search`, `account_id`, `category_id`, `tx_type`, `status`, dates, amount range; `sort`, `limit`, `offset`. Returns totals for income, spending, transfers and refunds |
| POST | `/transactions` | Create a transaction (transfers need two accounts). A posted row dated after the user's local today returns `422`; use `pending` for scheduled future money. |
| GET/PATCH/DELETE | `/transactions/{id}` | Read, correct, delete (reverts linked bill payments). Edits that would leave a posted row in the future are rejected. |

### Budgets

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/budgets/current` | Ensures and returns the current month |
| GET | `/budgets/{year}/{month}` | Month summary with per-category rows |
| POST | `/budgets` | Create a month |
| PATCH | `/budgets/{id}` | Update name/notes/income and allocations |
| POST | `/budgets/wizard` | Create from income, bills, savings and priorities |
| POST | `/budgets/copy` | Copy a month's allocations forward |
| GET | `/budgets/{year}/{month}/categories/{category_id}` | Category headroom |

### Bills and matching

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/bills` | List with next due date and summary, or create |
| GET/PATCH/DELETE | `/bills/{id}` | Manage a recurring bill |
| GET | `/bill-occurrences` | Occurrences by `status`, dates, `overdue_only`, `limit` |
| POST | `/bill-occurrences/{id}/mark-paid` | Mark fully paid without a transaction |
| POST | `/bill-occurrences/{id}/unpaid` | Reopen |
| POST | `/bill-occurrences/{id}/skip` | Skip this cycle |
| POST | `/bill-occurrences/{id}/record-payment` | Create a payment transaction from an account, partial allowed |
| GET | `/bills/calendar?year=&month=` | Month grid with totals |
| GET | `/match-suggestions` | Grouped suggestions, never auto-applied when ambiguous |
| POST | `/matches/{id}/confirm` | Confirm; amount optional for partials |
| POST | `/matches/{id}/reject` | Reject a suggestion |
| POST | `/matches/link` | Link an occurrence to a specific transaction |
| GET/POST/DELETE | `/merchant-aliases` | Merchant alias rules that strengthen matching |

### Imports

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/imports` | Upload a CSV (multipart, `account_id`); returns headers, suggested mapping and an automatic preview when possible |
| POST | `/imports/{id}/preview` | Parse with a mapping; returns row statuses, headers and summary |
| POST | `/imports/{id}/commit` | Commit ready rows exactly once; returns imported/duplicate/rejected counts plus `matched_bills`, `auto_matched`, `suggested_matches` and `match_suggestions` |
| GET | `/imports` | Import history |
| GET | `/imports/{id}` | One import with counts |
| GET | `/imports/{id}/records` | Per-row audit trail |

### Insights

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/safe-to-spend` | Full calculation with explanation, warnings, reserves and bills |
| GET | `/safe-to-spend/category/{category_id}` | Category headroom and recommended maximum |
| GET | `/dashboard` | Safe-to-Spend, accounts, budget pulse, category spending, upcoming bills, recent activity |
| GET | `/forecast?days=` | Projected balance and lowest point, bill-driven |
| GET | `/shopping/context` | Categories and current context for Shopping Check |
| POST | `/shopping/check` | `{store_name, category_id, expected_amount?}` → verdict, limits, bills covered |
| GET | `/ai/status` | Provider status (`disabled` unless a model provider is configured) |
| GET | `/ai/tools` | Tool registry |
| GET | `/ai/tools/{name}` | Run a read-only tool payload |

### Connectivity (Phase 2)

Provider-independent institution linking and synchronisation. `consent: true` is required to
import anything; tokens are encrypted at rest and never returned.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/connectivity/providers` | Providers with `configured` / `simulated` flags (no secrets) |
| POST | `/connectivity/link-token` | `{provider}` → link token for the provider's own approval flow |
| POST | `/connectivity/exchange` | `{provider, public_token, consent}` → link, imported accounts, first sync run |
| GET | `/connectivity/links` | Links with status, last sync and cursor state |
| POST | `/connectivity/links/{id}/sync` | Manual sync (`?full_refresh=true` to ignore the cursor) |
| DELETE | `/connectivity/links/{id}?delete_data=` | Disconnect; optionally delete the accounts and transactions it created |
| GET | `/connectivity/sync-runs` | Sync history: added / modified / removed / skipped duplicates / errors |

### Intelligence (Phase 2)

Automated proposals the user reviews. Accepting writes the value and records it as a
user-confirmed choice so later automation never overwrites it.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/suggestions?status=` | Category suggestions with confidence, source and reason |
| POST | `/suggestions/{id}/accept` | Apply the suggested category |
| POST | `/suggestions/{id}/reject` | Dismiss; the same transaction won't be suggested again for that rule |
| GET | `/recurring` | Detected series, subscriptions and `subscription_monthly_total` |
| POST | `/recurring/detect` | Re-run detection over the last 180 days |
| POST | `/recurring/{id}/confirm` \| `/dismiss` | Keep or suppress a series |
| GET | `/insights/personal` | Explainable observations, each with its own evidence block |
| GET | `/insights/merchant?merchant=` | Merchant profile: typical amount, monthly average, tendency |
| PATCH | `/insights/preferences` | Insight sensitivity, personalisation and AI consent toggles |

### Assistant (Phase 2)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/assistant/status` | Whether a model provider is configured and whether the user opted in |
| POST | `/assistant/ask` | `{question}` → answer, `tools_used`, `source` (`deterministic` or `model`) |
| POST | `/assistant/consent` | `{consent}` — required before anything is sent to a model provider |

### Meta

`GET /health` (database check) and `GET /meta` (account types, categories, frequencies, defaults, AI status) require no authentication.

## Example

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8010/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"DemoPassword123!"}' | jq -r .access_token)

curl -s http://127.0.0.1:8010/api/v1/safe-to-spend \
  -H "Authorization: Bearer $TOKEN" | jq '{amount: .safe_to_spend, payday, warnings}'
```

## Errors

Domain errors return `{"detail": "readable message", "extra": {...}}`. Validation errors return `422` with `{"detail": "Please check the highlighted fields.", "errors": [...]}`. Authentication failures are deliberately generic and do not reveal whether an email exists.

See [a page that is gone](phase-9-imaginary.md).
