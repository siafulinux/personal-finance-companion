# Acceptance report — administrator-managed financial providers

Phase: financial connectivity ownership — Teller primary, Plaid fallback, provider-neutral
user experience.
Date: 2026-11-09.
Server under test: the Docker stack in `deploy/docker` (`http://127.0.0.1:8088`, HTTPS
`8448`), database `finance`.

---

## 1. What was implemented

### Backend

| Area | Change |
| --- | --- |
| Model | `provider_configs` (enable, priority, environment, AES-GCM ciphertext of credentials, last test result) and `server_settings.provider_auto_select`. |
| Migration | `3f2c9a71b4d8_provider_configuration`, seeded with Teller at priority 10 and Plaid at 20. |
| Service | `app/services/provider_config.py` — encryption, environment fallback, masked descriptions, admin updates, test results, auto-select. |
| Service | `app/services/provider_selection.py` — institution catalogue, capability checks, priority selection, coverage report, short-lived caching including negative caching. |
| Provider | `app/providers/teller.py` — real Teller adapter: public institution directory, Basic-auth access tokens, per-account balances and transactions, mTLS outside sandbox, ED25519 enrolment verification, `DELETE /accounts` revocation, connection test. |
| Provider | `app/providers/plaid.py` — institution directory, institution-scoped link tokens, connection test; contract unchanged. |
| Registry | `adapter_for(db, name)` builds adapters from saved configuration; environment remains the fallback. |
| Sync | Builds its adapter from configuration; a re-reported posted row now reconciles a stored pending row in place (needed for Teller's window-based sync). |
| Security | `app/security/link_nonce.py` — HMAC-signed, user-bound, 30-minute nonce for the Teller hand-off. |
| API | Admin: `GET/PATCH /server/providers`, `PATCH /server/providers/selection`, `POST /server/providers/{name}/test`, `GET /server/providers/coverage`. User: `GET /connectivity/catalog`, `POST /connectivity/connect/start`, `POST /connectivity/connect/finish`. |
| Config | `TELLER_*`, `PLAID_PROVIDER_ENABLED`, `PROVIDER_AUTO_SELECT`, `SANDBOX_PROVIDER_ENABLED`; compose passes them to both API and worker. |

### Web

* **Connections** now has an institution search and one provider-neutral list; the provider
  picker is gone. A consent checkbox is required before authorisation.
* The connect dialog runs whichever flow the server chose: Teller Connect (script loaded on
  demand), Plaid Link (same), or the instant simulated flow.
* **Admin → Providers** (`/server/providers`, navigation visible only to the administrator)
  edits enablement, priority, environment and credentials, runs connection tests, toggles
  automatic selection, and reports per-institution coverage.
* Connected-institution cards no longer show a provider badge; they show health, last sync,
  accounts and reauthorisation state.

### Android

Unchanged. No endpoint it uses was altered or removed.

---

## 2. Verification evidence

### 2.1 Migration and defaults (running stack)

```
$ docker compose exec api alembic current
3f2c9a71b4d8 (head)

 name  | enabled | priority | environment | no_creds
-------+---------+----------+-------------+----------
 teller| t       |       10 | sandbox     | t
 plaid | t       |       20 | sandbox     | t

server_settings: provider_auto_select = t
```

### 2.2 Administrator configuration, over HTTP, against the deployed container

Performed with a temporary administrator account, which was deleted and whose
`admin_user_id` was restored afterwards.

| Check | Result |
| --- | --- |
| `GET /server/providers` | 200; Teller first, Plaid second; credential fields with `present`/`hint` only |
| `PATCH /server/providers/plaid` with credentials | 200; `configured: true`, `source: database` |
| Secret in the API response | absent; secret field returned `value: null`, `hint: "veri…text"` |
| Secret on disk | `credentials_ciphertext` starts `v1:`, and a `LIKE` search for the submitted plaintext across the column returns no rows |
| `POST /server/providers/plaid/test` | reached Plaid and returned `ok: false`, `code: INVALID_FIELD`, message *"client_id must be a properly formatted, non-empty string"* — a live response from `sandbox.plaid.com` to a deliberately fake credential, correctly surfaced and recorded |
| `POST /server/providers/teller/test` | `ok: false`, `code: network_error`, *"Could not reach Teller."* — this host cannot reach `api.teller.io` (see limitations) |
| `POST /server/providers/teller/test` unconfigured | `ok: false`, *"Teller is not configured yet: application_id missing."* |
| `PATCH /server/providers/selection` | `{"auto_select": false}` then `{"auto_select": true}`, persisted in `server_settings` |
| `GET /server/providers/coverage?names=USAA,Cash App` | per-provider report; unusable providers reported with the reason, not omitted |

### 2.3 Ordinary-user experience

| Check | Result |
| --- | --- |
| `GET /server/providers` as a normal user | `403 Only the server administrator can configure providers.` |
| `GET /connectivity/catalog` as a normal user | one entry (`Sandbox Credit Union`), no provider name anywhere in the payload, generic warning when a service is unreachable |
| Catalogue with two unavailable providers | degrades instead of failing: 24.6 s on the first call (connect timeout), 0.02 s on the next within the 60 s negative-cache window |
| `POST /connectivity/connect/start` + `/finish` (simulated institution) | `201`; link active, 3 accounts, 66 transactions imported into the ordinary ledger |
| Consent missing | `422`, nothing imported |

The temporary user, its link, accounts and 66 transactions were deleted afterwards; the
database is back to its two pre-existing accounts with zero test transactions and provider
credentials cleared.

### 2.4 Automated tests

* Backend: **218 passed** (`.venv/bin/python -m pytest`).
  * `tests/test_teller_contract.py` — 17 tests: unconfigured refusal, mTLS requirement,
    nonce binding, Basic auth shape, account and balance mapping, pending/income/category
    mapping, window cursor, signature accept/reject, unsigned-enrolment policy, revocation,
    institution capability flags, connection test, rate-limit vs reauth classification.
  * `tests/test_provider_config.py` — 17 tests: defaults, environment fallback, encryption
    and masking, database-over-environment precedence, partial updates, clearing, unreadable
    ciphertext, admin-only mutation, validation, priority reordering, HTTP admin surface,
    coverage endpoint, and that administration grants no access to another user's links.
  * `tests/test_provider_selection.py` — 14 tests: primary, fallback, unavailable with
    reason, pinned provider, disabled/unconfigured skipping, no provider names, deduplication,
    flow start, finish routing, bad key, sandbox end-to-end, negative caching, coverage.
  * `tests/test_institution_connect_api.py` — 8 tests: auth, provider-neutral catalogue,
    flow start, consent, full import, reconnect without duplication, unavailable institution,
    user isolation.
* Web: **30 passed** (`npm test`), including the new `providerConnect` mapping tests.
* Web typecheck: `tsc -b && tsc -p tsconfig.e2e.json` clean.
* Deployed web bundle contains the new institution search and admin route.

`tests/test_connectivity.py` was adjusted for one legitimate reason: the sync engine now
builds its adapter from configuration instead of a cached singleton, so the two failure
tests inject the failing adapter at that seam. Their assertions are unchanged.

---

## 3. Institution coverage

The coverage tool is implemented and verified against the running server. **Real coverage
numbers could not be collected here**, so none are claimed.

The current table lives in [financial-provider-coverage.md](financial-provider-coverage.md),
which is generated from the running server rather than typed by hand — so it cannot drift
from what the endpoint actually says. Its status line distinguishes "checked, and the
directory answered" from "could not ask". As of this report it reads **not verified**:

| Institution | Teller | Plaid | What is known |
| --- | --- | --- | --- |
| USAA | unknown | unknown | Both directories could not be queried from this host in the verification window (Teller: `api.teller.io` TCP 443 times out; Plaid: no sandbox credentials were available). |
| Cash App | unknown | unknown | Cash App is a payment app rather than a bank. No blanket claim is made; manual entry, CSV and statement import remain available. |
| Borrowing / cash-advance apps (Dave, EarnIn, Brigit, Klarna, Afterpay, Affirm) | unknown | unknown | Evaluated individually through the same endpoint; a provider that reads a checking account may not expose a loan balance or schedule. |

Regenerate the real table once the providers are configured (it writes the file itself):

```bash
cd deploy/docker
docker compose exec -T api python scripts/coverage_report.py --out - \
  > ../../docs/financial-provider-coverage.md
```

The script exits `0` only when a real provider answered; exit `2` means the run recorded a
missing configuration or an unreachable directory, not an absence of institution support.

A provider being listed is not treated as support: the selection service requires
`transactions` **and** `balance` for the institution before it will use that provider.

---

## 4. Pricing and limits (as documented by the providers)

* **Teller sandbox** — free, no real data, no mTLS required.
* **Teller development** — unbilled, hard limit of 100 enrolments.
* **Teller production** — billed per connected account and product; check the dashboard.
* **Plaid Trial** — free sandbox development with a small Item limit and no production
  access; production needs review and an agreement.

These are the providers' published terms; confirm them in each dashboard before relying on
them.

---

## 5. Security

* Credentials are AES-256-GCM ciphertext with a key derived from `PROVIDER_ENCRYPTION_KEY`
  (or `SECRET_KEY`), never stored beside the data it protects.
* Access tokens are encrypted per link; the API never serialises them and the sync engine
  decrypts only in memory.
* Teller enrolments are verified with a server-issued, user-bound, expiring nonce and an
  ED25519 signature outside sandbox.
* Admin endpoints are gated on the first-run administrator; a normal user receives 403.
* Administration does not grant access to any user's connections, accounts or transactions.
* Provider names and failures are withheld from the user-facing catalogue.
* Logs record which credential fields changed, never their values.

---

## 6. Remaining limitations

1. **No live Teller call has succeeded from this machine.** `api.teller.io` is unreachable
   here (DNS/connect), so Teller end-to-end linking and syncing against the real sandbox is
   unverified. The adapter is covered by contract tests and its failure path was exercised
   live. Plaid's API *is* reachable and rejected a deliberately fake client id correctly.
2. **No real Plaid credentials**, so no Plaid Item was created and no Plaid sync ran against
   the real API. The existing Plaid contract and sync tests still pass.
3. **Android has no connection-management screen.** The provider-independent flow is
   web-only; the app is unchanged and its API compatibility is preserved. Bringing the
   institution search, consent and Teller Connect/Android authorization into the app is
   outstanding work.
4. **No webhook handling.** Both providers offer webhooks; this release polls (manual,
   scheduled worker) and reports failures with backoff. Webhooks would reduce latency, not
   change correctness.
5. **Provider switching is a reconnection, not a migration.** A user disconnects and
   reconnects; history is deduplicated by provider external id within the new link.
6. **Teller amount sign convention** (money out is positive) follows Teller's documented
   examples and matches Plaid. It is exercised by contract tests against a fake endpoint,
   not against live Teller data.
7. **No automated browser test of the Teller Connect / Plaid Link dialogs.** They are
   provider-hosted scripts; the mapping around them is unit-tested, and the rest requires
   live credentials.
8. **`PROVIDER_ENCRYPTION_KEY` is not set on this installation.** Provider credentials
   therefore use a key derived from `SECRET_KEY`. Setting it now would make any existing
   stored credential unreadable, so it should be introduced before real credentials are
   saved, with the key backed up alongside the database.

---

## 7. Operating commands

```bash
cd deploy/docker

# Build and start with the new provider configuration
docker compose build api web && docker compose up -d

# Status, logs, health
docker compose ps
docker compose logs -f api
curl -s http://127.0.0.1:8088/api/v1/health

# Migrations
docker compose exec api alembic current
docker compose exec api alembic upgrade head

# Provider state (no secrets are printed by the API)
curl -s -H "Authorization: Bearer $PFC_TOKEN" \
  http://127.0.0.1:8088/api/v1/server/providers | jq '.providers[] | {name, enabled, priority, environment, configured, source}'

# Test and coverage
curl -s -X POST -H "Authorization: Bearer $PFC_TOKEN" \
  http://127.0.0.1:8088/api/v1/server/providers/teller/test | jq
curl -s -H "Authorization: Bearer $PFC_TOKEN" \
  "http://127.0.0.1:8088/api/v1/server/providers/coverage?names=USAA,Cash%20App" | jq
```

The web UI is at `http://127.0.0.1:8088` (LAN: `http://<host>:8088`), and the admin screen
appears as **Providers** in the sidebar for the account that completed setup.

---

## 8. Conclusion

Administrator-managed configuration works end to end on the deployed stack: both providers
appear with Teller primary, credentials are encrypted and never returned, tests run and are
recorded, priority and automatic selection are editable without code, and an ordinary user
sees only an institution list. Automatic selection, fallback, unavailability, duplicate
prevention and user isolation are covered by tests.

What is **not** demonstrated is a live institution link through either aggregator: this
machine cannot reach Teller, and there are no Plaid credentials. That is the next milestone,
and the coverage endpoint plus the connection test are the tools for it.
