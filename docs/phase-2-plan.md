# Phase 2.0 — Connected Financial Data and Intelligent Finance

Assessment of the existing financial architecture, provider comparison, and the implementation plan for
Phase 2. Written before any Phase 2 code was added.

Baseline at assessment time: `8f150aa`, backend **87 tests passing**, web **9 passing**, Android
**unit tests passing**, database at Alembic revision `fced71fed827`.

---

## 1. What already exists

The Phase 1 foundation was built around a deterministic money engine, and it is in better shape for
Phase 2 than the brief assumes. Nothing below needs re-architecting.

### Deterministic financial core (`app/calculations`, `app/services`)

| Capability | Where | State |
|---|---|---|
| Safe-to-Spend with reserves, buffers, pending debits | `calculations/safe_to_spend.py`, `services/safe_to_spend.py` | Complete, tested. Pure function over an inputs dataclass; every component is returned for explanation. |
| Category availability for a single category | `services/safe_to_spend.py::category_availability` | Complete |
| Cash-flow forecast (bills + scheduled income, labelled separately) | `services/forecast.py` | Complete, deterministic, 7–365 days |
| Bill occurrence generation (all frequencies, clamping) | `services/bills.py` | Complete |
| Bill ↔ transaction matching with confidence and explanations | `matching/engine.py` | Complete and pure: merchant 0.45 / amount 0.30 / date 0.15 / account 0.10, ambiguity margin, partial-payment floor, auto-threshold. |
| Merchant normalisation (noise tokens, legal suffixes, card digits) | `matching/normalize.py` | Complete, reused by dedupe and matching |
| Duplicate fingerprints | `services/dedupe.py` | Complete: `ext|<account>|<external_id>` when a source supplies an id, otherwise a content hash |
| Shopping Check | `services/shopping.py` | Complete; already carries a `notification_context` block intended for geofencing |

### Data model already shaped for Phase 2

- `transactions.source` — `manual | csv | provider`, plus `external_id`, `dedupe_key`, `reconciled_at`,
  and a unique `(user_id, dedupe_key)` index. **The provider path is already plumbed into
  `create_transaction(source=PROVIDER)`**, so synced rows must not get a second bookkeeping path.
- `financial_accounts.provider` / `external_account_id` — provider identity already reserved.
- `bill_payment_matches` — unique partial index already prevents one transaction confirming two bills.
- `notification_preferences` — assistant toggles and a location opt-in flag that nothing writes to yet.

### Interfaces that exist but do nothing

- `app/providers/financial.py` — an ABC (`list_accounts`, `list_transactions(since, until)`) plus a
  `NoFinancialProvider`. It is a *stub*: no linking, no cursor, no tokens, no webhooks.
- `app/ai/provider.py` — an `AIProvider` ABC with a `NullAIProvider` that raises.
- `app/services/assistant_tools.py` — nine permission-checked tools already written against the
  deterministic engine (`accounts`, `spending`, `budget`, `upcoming_bills`, `recurring_payments`,
  `safe_to_spend`, `forecast`, `category_trends`, `category_availability`). This is a genuinely
  usable tool layer for an AI assistant and should be the only door a model gets.

### What is genuinely missing

1. Institution linking: no institutions, no links, no token storage, no consent record.
2. Incremental sync: no cursor, no sync history, no pending→posted reconciliation, no removal handling.
3. Provider account import: accounts are manual only.
4. Categorisation: transactions get a category only when a human or a CSV mapping supplies one.
5. Recurring detection from history: bills are declared by the user; nothing detects subscriptions.
6. Merchant-level spending profiles / overspend warnings: nothing exists beyond per-category budget rows.
7. AI: an interface with no implementation and no HTTP surface.
8. Web UI for any of the above.

## 2. Provider comparison

Facts below are from each provider's published developer documentation. Coverage, pricing and
production-approval requirements change often and are contractual — **re-verify before production**.

| | **Plaid** | **Teller** | **Finicity (Mastercard)** | **MX / Akoya** |
|---|---|---|---|---|
| Self-serve sandbox | Yes — instant, no approval | Yes — dev plan, certificates downloaded from dashboard | Limited; sandbox exists but is partner-oriented | No; enterprise contract |
| US checking/savings | Yes | Yes (primary focus) | Yes | Yes |
| Credit cards | Yes | Limited / inconsistent | Yes | Yes |
| Incremental sync | `POST /transactions/sync` with opaque `cursor`, returns `added` / `modified` / `removed`, `has_more` | Cursor-like pagination via `from_id`/`count`; polling | Cursor-style paging over accounts and transactions | Varies by data provider |
| Pending transactions | Yes, with `pending` flag and `pending_transaction_id` linking to the posted row | Limited | Yes | Varies |
| Initial history | Up to 24 months | Up to 24 months (plan-dependent) | Typically 24 months | Varies |
| Webhooks | Yes (`SYNC_UPDATES_AVAILABLE`, `TRANSACTIONS_REMOVED`, item errors) | Yes (newer) — polling remains the safe assumption | Yes | Yes |
| Balance updates | Yes (`/accounts/get`, balances product) | Yes | Yes | Yes |
| Mobile link flow | Link SDK / hosted Link — good Android story | Strong native mobile SDK | Hosted Connect | Hosted |
| Cost shape | Per connected item/month, billed at production; sandbox free | Free tier for development | Contract | Contract |

**Decision: Plaid as the first real adapter, with a bundled sandbox provider for development.**

- Plaid has the only genuinely instant sandbox, the cleanest cursor contract (`/transactions/sync` is
  exactly the shape this sync engine needs), explicit pending→posted linkage, and a documented webhook.
- Teller is a strong second adapter (US-only, simple, good mobile SDK) and the adapter interface below
  is designed to accept it without touching the sync engine.
- Finicity and MX/Akoya are excluded from the first milestone purely because neither can be evaluated
  end-to-end without a partner agreement.

**Plaid requires live credentials**, which this project does not have and must not invent. So the
milestone ships two adapters behind one interface:

1. `sandbox` — a fully local, deterministic simulated institution. No network, no credentials. This is
   what proves the whole pipeline end to end, today, in tests and in the UI.
2. `plaid` — the real HTTP adapter against `sandbox.plaid.com`, activated by `PLAID_CLIENT_ID` /
   `PLAID_SECRET`. Its code path is exercised against a local fake Plaid endpoint in tests, but it has
   **not** been run against Plaid's servers.

That split is deliberate: it keeps the acceptance criteria demonstrable without pretending we have
live bank connectivity.

## 3. Architecture

```
                    ┌──────────────────────────────┐
  web / android ──► │  /connectivity  /assistant   │  HTTP (session or bearer auth)
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  services/sync.py            │  accounts upsert, cursor loop,
                    │  (provider-agnostic engine)  │  pending→posted, removals, retries
                    └───┬──────────────────┬───────┘
                        │                  │
        ┌───────────────▼──────┐   ┌───────▼────────────────────────┐
        │ providers/sandbox.py │   │ providers/plaid.py             │
        │ providers/base.py    │◄──│ (httpx, error mapping)         │
        └───────────────┬──────┘   └────────────────────────────────┘
                        │
        ┌───────────────▼──────────────────────────────────────────┐
        │ existing write path: create_transaction(source=provider) │
        │ → dedupe_key, bill matching, ledger, Safe-to-Spend       │
        └──────────────────────────────────────────────────────────┘
```

Rules this architecture enforces:

- **One accounting path.** Sync never writes `Transaction` rows directly; it calls the existing
  service, so bill matching, dedupe and the ledger stay identical to manual entry.
- **The engine stays pure.** No provider, AI or personalisation code computes money. They read the
  deterministic services.
- **Adapters are interchangeable.** `ProviderAdapter` exposes linking, account listing, cursored
  transaction sync and unlink. Adding Teller means one new module plus a registry entry.
- **Secrets never leave the server.** Access tokens are encrypted at rest (AES-GCM, key derived from a
  dedicated `PROVIDER_ENCRYPTION_KEY` or the app secret via HKDF) and are never serialised to a client.

### New tables

| Table | Purpose |
|---|---|
| `provider_links` | One connected institution: provider, external item id, institution name, `status` (`active`/`error`/`disconnected`), `cursor`, `last_synced_at`, `error_code`, `next_retry_at`, backoff state |
| `provider_link_secrets` | Encrypted access token + `key_version`, 1:1 with a link |
| `sync_runs` | Sync history: trigger, status, counts (added/modified/removed/skipped), error detail, timings |
| `category_suggestions` | Reversible classification proposals: transaction, category, confidence, reason, `suggested`/`accepted`/`rejected` |
| `recurring_series` | Detected recurring charges/subscriptions: merchant key, cadence, amount stats, occurrence count, confidence, `detected`/`confirmed`/`dismissed` |

Column additions: `financial_accounts.provider_link_id`; `transactions.category_source`
(`none`/`user`/`rule`/`import`/`provider`) to make "never overwrite a user-confirmed category" a
schema guarantee rather than a convention; `user_preferences.ai_consent`, `insight_sensitivity`,
`personalized_insights_enabled`, `recurring_detection_enabled`.

### Intelligence, in dependency order

- **Normalisation** already exists (`matching/normalize.py`). Category suggestion builds on it:
  deterministic merchant→category rules first, then the user's own historical merchant→category
  choice, then the provider's category name mapped onto the user's categories. Every suggestion is
  stored with its confidence and a plain-language reason, and is dismissible.
- **Recurring detection** groups posted purchase transactions by normalised merchant over 180 days,
  requires ≥3 occurrences at a stable interval (coefficient of variation guard) and a stable amount
  (±15%), and emits a confidence. `is_subscription` is a heuristic on cadence and amount, clearly
  labelled as heuristic. Confirming a series offers a bill; it never silently creates one.
- **Personalisation** computes merchant and category profiles (monthly mean/median, month count,
  trend vs. prior period) with a **minimum-history guard** (≥3 distinct months *and* ≥5 transactions)
  before any judgement is emitted. Every warning carries its evidence.

### AI assistant

- `AssistantProvider` implementations: a `DeterministicAssistant` (always available — routes a
  question to the existing tools and narrates their exact values) and an `OpenAICompatProvider` for a
  configurable OpenAI-compatible endpoint.
- The model receives **only** the JSON returned by `assistant_tools`, never a session, never raw SQL,
  and consent (`user_preferences.ai_consent`) is required before any data leaves the server.
- No assistant path can mutate financial data. Actions require an explicit endpoint with its own
  confirmation, and none is added in this milestone.
- When no LLM is configured the endpoints still work through the deterministic assistant, so the
  application degrades instead of failing.

## 4. Milestone scope

**In scope for Phase 2.0** (the ten acceptance criteria in the brief):

1. Connect a sandbox institution → link record, encrypted token, accounts imported.
2. Accounts appear in the existing accounts UI and balances.
3. Transactions sync into the existing ledger via `create_transaction`.
4. Re-sync is idempotent (dedupe key + external id).
5. Pending → posted reconciliation via `external_id`, with `reconciled_at`.
6. Category suggestions, reviewable and reversible.
7. Failures recorded per link and per run, visible, retryable with backoff.
8. Web and Android read the same rows (Android needs no new screen for this: synced rows are ordinary
   ledger rows).
9. Manual account/transaction/CSV flows untouched.
10. Every query scoped by `user_id`, with cross-user tests.

Plus: subscription detection, personalized insights, extended Shopping Check, assistant.

**Explicitly deferred:** Plaid production approval and real-bank verification; Teller/Finicity
adapters; Android institution-linking UI (Plaid Link is a hosted web flow — the Android app gains it
via the hosted browser in a later milestone); geofencing and any location collection; webhook
receivers (manual and scheduled sync only in this milestone); multi-currency.

**Out of scope by instruction:** backups, the Oracle VPS, and the backup timer are not touched.

## 5. Risks

| Risk | Mitigation |
|---|---|
| Plaid adapter is unverified against the real service | Documented as unverified; exercised against a fake endpoint; sandbox provider is the acceptance path |
| Cursor sync can double-count if a page is committed then the cursor is lost | Cursor is written in the same transaction as the page's rows |
| Provider "removed" events could delete a user's manual edits | Removals only apply to `source=provider` rows owned by that link; user-categorised data is preserved |
| Duplicate detection across pending→posted | Reconcile by `external_id` first, content fingerprint second |
| Personalized warnings overfit small samples | Minimum-history guard; sensitivity setting; every warning exposes its evidence |
| Sending financial data to a model | Consent gate, aggregated tool payloads only, provider configurable, deterministic fallback |
