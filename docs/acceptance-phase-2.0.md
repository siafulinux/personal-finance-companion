# Phase 2.0 acceptance — connected financial data and intelligent finance

Status: **first milestone delivered and exercised end to end against the live stack.** The
connectivity layer is proven with the **bundled sandbox institution only**. No live bank, no
real Plaid item, and no external AI provider has been exercised. Read the limitations before
quoting any of this as production capability.

A **live Plaid verification harness** now exists (`backend/scripts/verify_plaid_live.py`). It
drives the real service layer against `sandbox.plaid.com` and fails closed: exit 2 with no
keys, exit 3 against any non-sandbox environment. **It has not been run**, because this
deployment holds no Plaid credentials — see section 7.1. Nothing below claims otherwise.

Baseline this work started from: `8f150aa` (Phase 1.3 checkpoint), database at Alembic
`fced71fed827`. The Phase 2 assessment and provider comparison live in
[phase-2-plan.md](phase-2-plan.md).

---

## 1. What was built

### Provider-independent connectivity (`app/providers`, `app/services/sync.py`)

| Piece | Where | Notes |
|---|---|---|
| Adapter contract | `providers/base.py` | `create_link_token`, `complete_link`, `fetch_accounts`, `fetch_transactions`, `revoke`, plus a typed `ProviderError`. Replaces the Phase 1 `financial.py` stub, which had no linking, cursor or token handling. |
| Sandbox institution | `providers/sandbox.py` | Deterministic, offline, seeded from the link token. Generates 3 accounts and ~65 transactions over 90 days including payroll, rent, groceries, two subscriptions, a transfer and **one pending card purchase** that posts on a later sync. No credentials, no network. |
| Plaid adapter | `providers/plaid.py` | Link token, `/item/public_token/exchange`, accounts, `/transactions/sync` cursor loop with `added`/`modified`/`removed`, pending→posted linkage, `revoke`, plus `/sandbox/public_token/create` so a headless run can reach a real sandbox Item without the Link UI. Disabled unless `PLAID_CLIENT_ID` + `PLAID_SECRET` are set; the sandbox bootstrap additionally refuses any non-sandbox environment. |
| Registry | `providers/registry.py` | `available_providers()` reports `configured` / `simulated` / `requires_credentials` and never returns a secret. |
| Sync engine | `services/sync.py` | Cursor-based incremental sync, per-run counters, duplicate suppression through the existing dedupe key, pending→posted reconciliation, removal handling, retry/backoff state, sync history, disconnect with optional data deletion. |
| Token protection | `security/secrets.py` | Provider access tokens encrypted at rest (Fernet, key derived from `SECRET_KEY`), deleted on disconnect. |

### Transaction intelligence (`app/matching`, `app/services/intelligence.py`)

- Merchant normalisation and identification reuses the Phase 1 matcher, so there is one
  merchant-identity implementation in the project.
- Category suggestions are stored with confidence, source and a human-readable reason. The
  original value is never overwritten silently: accepting records the value as user-confirmed,
  rejecting suppresses that rule for that transaction.
- Recurring detection groups posted purchases by normalised merchant over 180 days, infers
  cadence (weekly / biweekly / monthly / quarterly), and flags subscriptions from cadence and
  amount stability. The response carries `subscription_monthly_total`.
- Unusual-transaction detection compares a transaction to its own merchant's history only.

### Obligations and personalisation (`app/services/personal.py`)

- Explainable observations: category over budget, category habitually over budget, repeated
  small purchases. Every observation carries an `evidence` block with the raw numbers, and a
  minimum-history guard (3 months + 5 transactions) before any merchant or category judgement.
- Merchant profiles for Shopping Check: typical amount, monthly average, current-month spend
  and an explicit `has_enough_history` flag instead of a guess.
- Shopping Check now composes category headroom, Safe-to-Spend, upcoming bills and merchant
  tendency into one answer, and still returns `notification_context` for future geofencing.

### AI assistant foundation (`app/ai`, `app/services/assistant.py`, `api/assistant.py`)

- A provider ABC with an `openai_compatible` implementation and a `disabled` provider.
- The model never calculates: it receives the output of the nine permission-checked tools in
  `services/assistant_tools.py` and is asked to explain them. With no provider configured the
  same questions are answered deterministically and labelled `source: deterministic`.
- Consent is explicit (`PATCH /insights/preferences`, `POST /assistant/consent`); without it no
  figures leave the server.
- The assistant cannot mutate data — there is no write tool and no confirmation flow, because
  there is nothing to confirm yet.

### Web (`web/src/pages/{Connections,Review,Insights,Assistant}Page.tsx`)

Four new pages wired into the existing shell and API client, matching the existing component
vocabulary (`Card`, `PageHeader`, `Badge`, `Warnings`): connect/sync/disconnect institutions with
sync history, the review queue (accept/dismiss suggestions, confirm/dismiss recurring series),
personalised insights with evidence, and the assistant.

### Scheduled sync

`pfc sync-links` (CLI) + `deploy/systemd/pfc-sync.{service,timer}` run incremental sync on a
timer; `pfc-run sync` and `scripts/install-service` were extended so the unit survives a
workspace move like the Phase 1.3 units. The timer respects `SYNC_MIN_INTERVAL_MINUTES` so a
frequent timer cannot hammer a provider.

Installed and exercised on this machine: `pfc-sync.timer` is enabled (`OnBootSec=5min`, then
every 30 min with up to 5 min of jitter, `Persistent=true`), and a manual
`systemctl --user start pfc-sync.service` finished with `Result=success`, writing one line per
due link to `logs/sync.log`. The backup timer and its off-site configuration were not touched;
only the sync units and the `pfc-run` copy under `~/.local/lib/pfc/` were updated (the installed
runner predated the `sync` subcommand, which is what `scripts/install-service` normally does).

### Database

One additive migration, `1d9d6ad34893` (now head): `provider_links`, `provider_link_secrets`,
`sync_runs`, `category_suggestions`, `recurring_series`, plus the preference columns
`ai_consent`, `personalized_insights_enabled`, `insight_sensitivity`,
`recurring_detection_enabled`. No existing table was rewritten, no column dropped, no data
migrated.

## 2. Tests actually executed

| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && .venv/bin/python -m pytest -q` | **140 passed**, 0 failed (13 test modules) |
| Web | `cd web && npm test` | **11 passed** (2 files) |
| Android unit | `cd android && JAVA_HOME=../.tools/jdk17 ./gradlew --no-build-cache --rerun-tasks testDebugUnitTest` | **31 passed**, 0 failed, 0 skipped (forced re-execution, not a cached result) |
| Live API smoke | `backend/scripts/smoke_phase2.py` against the running service | **35/35 checks passed** |

New backend tests: `test_connectivity.py` (engine: linking, idempotent re-sync, pending→posted,
removal, disconnect/deletion, per-user isolation), `test_connectivity_api.py` (HTTP surface,
consent enforcement, ownership 404s), `test_intelligence.py` (suggestions, accept/reject
semantics, recurring detection, personalisation guards), `test_plaid_contract.py` (adapter
against a fake Plaid endpoint: cursor loop, `removed`, pending linkage, error mapping, and the
sandbox bootstrap request shape, its non-sandbox refusal and its missing-token case).

Backend suite after the Plaid harness work: **143 passed** (`cd backend && .venv/bin/python -m
pytest -q`, 103 s). A single earlier rerun stalled near the end of the run; the same command
then completed cleanly twice, and no test touches the network, so this is recorded as an
unexplained one-off rather than a known failure.

The smoke script drives the real service over HTTP and deletes the throwaway accounts it
creates even if a check aborts (an earlier version left active links behind, which the new
timer then kept syncing — that is why the cleanup is in the script now): register → login → providers → link token →
exchange (consent enforced) → first sync imports rows → second sync imports **zero** and leaves
the ledger total unchanged → pending rows visible → accept a suggestion and confirm the category
is written → recurring detection → personal insights, forecast, shopping context/check →
assistant status and a question while unconfigured → a second user cannot sync or delete the
first user's link and sees an empty ledger → disconnect with `delete_data=true` removes the
imported rows and keeps the link record as `disconnected` history.

## 3. Browser verification (real Chromium, real server)

A brand-new account (`phase2.web@example.com`) was created **through the register form**, taken
through onboarding, and exercised:

- **Connections**: sandbox institution connected from the UI → 3 accounts, link status
  `Connected`, sync history with `+65 added · ~0 updated · −0 removed · 56 suggestions`.
- **Review**: 50 pending suggestions listed with merchant, amount, date, suggested category,
  reason and confidence; **Accept** removed the row and the API then reported it as
  `accepted` with the chosen category.
- **Insights**: an explainable observation with its evidence block.
- **Assistant**: with no model configured, "What bills are due this week?" answered
  deterministically and cited `tools: upcoming_bills`.
- **Transactions**: imported rows are ordinary ledger rows — filters list the sandbox accounts,
  the pending card purchase shows as `Pending`, totals reflect provider data.

### Defect found and fixed during this verification

`formatDate()` spread `dateStyle`/`timeStyle` on top of `month`/`day`, which `Intl.DateTimeFormat`
rejects — the Connections page crashed to a blank screen as soon as a sync history row existed.
Fixed in `web/src/lib/format.ts` (style presets now take the whole format and parse the full
timestamp) with two regression tests in `format.test.ts`. Re-verified in the browser afterwards.

Also fixed while verifying: user-facing insight and Shopping Check sentences interpolated raw
decimals ("averaging 5.76") instead of the existing `format_money` helper; evidence blocks stay
machine-readable.

## 4. Android and web consistency

The Android app consumes the same endpoints, so provider-imported rows are ledger rows there
too. Verified on the emulator (`emulator-5554`, debug APK built with JDK 17 and installed):

- Signed in with the same account used on the web.
- Dashboard showed **Safe-to-Spend $7,762.63**; `GET /safe-to-spend` for that account returned
  `7762.63` at the same moment.
- Ledger showed **65 matching transactions**, income $16,380.00 and spending $1,937.54 —
  identical to the web ledger — with the Amazon card purchase marked `pending` and the sandbox
  accounts named on each row.

Phase 2 added no Android screens: connecting, reviewing and asking remain web-only for now, as
scoped. No physical device testing was performed.

## 5. Acceptance criteria

| # | Criterion | Result |
|---|---|---|
| 1 | Connect a supported sandbox institution | Met (sandbox, from UI and API) |
| 2 | Accounts imported and displayed | Met (3 accounts, web + Android) |
| 3 | Transactions synchronise into the existing ledger | Met (65 rows, same rows on both clients) |
| 4 | Repeated sync creates no duplicates | Met (second run added 0; ledger total unchanged) |
| 5 | Pending/posted reconcile correctly | Met by tests (pending row created, posts with `pending_transaction_id` linkage); the live sandbox pending row was observed, but a live posted transition needs a later sync run than this session allowed |
| 6 | Transactions categorised and reviewable | Met (suggestions with reasons; accept writes the category) |
| 7 | Sync failures recoverable and visible | Met by tests (error status, backoff, history rows); no live failure was staged |
| 8 | Web and Android display consistent data | Met (identical totals and ledger on both) |
| 9 | Existing manual workflows still work | Met (Phase 1 suites pass; manual ledger and form unchanged) |
| 10 | Financial data isolated per user | Met (tests + live two-account check) |

## 6. Limitations and remaining work

1. **No live institution.** Only the sandbox provider has run end to end. The Plaid adapter is
   written against Plaid's documented contract and tested against a fake endpoint; it has never
   exchanged a real token or synced a real item. A harness that would prove exactly that now
   exists (section 7.1) but is unrun: **no Plaid credential exists in this deployment**, and
   Plaid issues sandbox keys only through its dashboard. Do not describe this as bank
   connectivity.
2. **Plaid production requirements** (approval, pricing, redirect URIs, webhook verification) are
   unaddressed; the webhook URL is a setting nothing validates yet.
3. **No webhook receiver.** Scheduled polling (`pfc-sync.timer`) is the only automatic path.
4. **AI assistant untested against a real model.** No provider key was configured, so only the
   deterministic path and the graceful "not configured" state were exercised. Token accounting,
   prompt-injection resistance and cost controls are unvalidated.
5. **Categorisation is rule-based.** It covers uncategorised purchases with a recognised
   merchant; it does not learn from corrections beyond suppressing a rejected rule.
6. **Recurring detection is a cadence heuristic.** Amount changes and gaps degrade it; it does
   not replace declared bills and never posts a bill payment on its own.
7. **Geofencing is not implemented** — only the `notification_context` contract the Android
   client will need.
8. **Android has no Phase 2 UI** (connections, review, insights, assistant).
9. **Pending→posted was not observed live** — the sandbox pending row posts on a later sync, and
   the reconciliation path is covered by tests only.
10. **Sandbox data is synthetic.** Merchant names are real-world brands chosen to exercise the
    matcher; no real transaction ever enters the sandbox.

## 7. Reproducing this verification

```bash
# services
systemctl --user status pfc-api pfc-web pfc-tls

# suites
cd backend && .venv/bin/python -m pytest -q
cd web && npm test
cd android && JAVA_HOME=../.tools/jdk17 ./gradlew --no-build-cache --rerun-tasks testDebugUnitTest

# live end-to-end (creates and removes its own throwaway accounts)
cd backend && .venv/bin/python scripts/smoke_phase2.py

# scheduled sync, once
cd backend && ./.venv/bin/pfc sync-links
```

### 7.1 Live Plaid verification (implemented, not yet run)

```bash
cd backend && .venv/bin/python scripts/verify_plaid_live.py
# exit 0 verified · 2 not configured · 3 wrong environment · 4 a step failed
```

Requires `PLAID_CLIENT_ID` and `PLAID_SECRET` in `.env` (Dashboard → Team settings → API keys).
The run is self-contained: it creates an ephemeral user, creates a **real sandbox Item** at
First Platypus Bank (`ins_109508`) through `/sandbox/public_token/create`, and then asserts, one
step at a time:

1. the registry reports `plaid` as configured and not simulated (wiring, not a hand-built adapter);
2. `/link/token/create` returns a `link-sandbox-…` token — prefix recorded, never the value;
3. `connect_institution` imports accounts and transactions through the normal service layer;
4. the cursor is persisted and the access token is stored only as ciphertext (the plaintext is
   asserted absent from the stored column);
5. a second sync adds **zero** rows and leaves the ledger count unchanged (duplicate suppression);
6. every local balance matches the balance the institution reports for that account;
7. `disconnect_link(delete_data=True)` reports `revoked_at_provider=true`, removes the imported
   rows and destroys the stored credential;
8. re-using the revoked access token is rejected **by Plaid** (`INVALID_ACCESS_TOKEN`), which is
   the only real proof the revoke reached the provider;
9. the ephemeral user and all its financial data are deleted.

Evidence (counts, statuses, Plaid error codes — never a token) is written to
`logs/plaid-live/<timestamp>.json`. A failed run still revokes the Item and deletes the user.

**Current state: not executed.** Without keys the script exits 2 before opening a session or
making any call, so no partial data and no live request exist.
