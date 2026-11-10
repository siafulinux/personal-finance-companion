# Financial provider selection

How this server decides which aggregator serves a connection, why users never see that
decision, and what happens when a provider cannot help.

---

## 1. The user-visible flow

```
Search institution  →  pick from one list  →  approve at the institution  →  connected
```

The user is shown an institution name, whether it is available, and what will be shared.
They are never shown a provider, an API key, an environment, or a reason framed in vendor
terms. Institutions that cannot be served are listed as unavailable with a plain-language
reason and a fallback (manual entry, CSV or statement import), instead of a Connect button
that fails halfway through.

Endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/connectivity/catalog?query=…` | Institutions this server can connect, already resolved to a provider. No provider names in the response. |
| `POST /api/v1/connectivity/connect/start` | Begins the chosen provider's authorisation for one institution. Returns only what that flow needs. |
| `POST /api/v1/connectivity/connect/finish` | Verifies the approval, stores the connection, runs the first sync. |

The older `/connectivity/link-token` and `/connectivity/exchange` endpoints remain for
compatibility and tests; the web client no longer uses them.

---

## 2. The selection algorithm

```
providers = enabled and configured providers, ordered by priority
if automatic selection is off:
    providers = [first ready provider]

for institution in matching directory entries, in provider order:
    if provider supports transactions AND balances for it:
        choose it and stop
if nothing qualifies:
    report unavailable, with the missing capability
```

Properties this buys:

* **Priority is data, not code.** The administrator can make Plaid primary by editing two
  numbers.
* **Capability, not listing.** Both aggregators publish per-institution products because
  coverage varies. An institution listed without `transactions` is not chosen for syncing,
  even if it is the primary provider's only match.
* **One connection, one provider.** The chosen provider is fixed for the life of the link.
  There is no silent mid-flight switch.
* **Explicit unavailability.** If no provider qualifies, the user is told which data
  cannot be shared rather than being routed to a failing flow.
* **Deterministic keys.** The catalogue key is derived from the normalised institution name
  (`inst_` + a truncated SHA-256), never from the provider or its id, so the client has no
  provider-specific identifier to leak.

Directory listings are cached for `PROVIDER_INSTITUTION_CACHE_SECONDS` (default 900) per
provider and query. A provider that cannot be reached contributes a warning to the
catalogue rather than emptying it.

---

## 3. Fallback and reauthorisation

* **Primary cannot serve the institution** → the next provider that can is chosen at
  connect time. This is the only "fallback" that exists, and it happens *before* a
  connection is created.
* **An existing connection breaks** → the link goes to `error` or `reauth_required` with
  the provider's reason. The scheduled sync retries with backoff; it never opens a second
  connection through the other provider. Creating a duplicate would double count the user's
  history and is exactly what the dedupe and link uniqueness constraints exist to prevent.
* **Switching providers is a deliberate act.** The user disconnects the institution (with
  or without deleting its data) and connects it again. Transactions keep their stable
  provider external ids per link, so a reconnect replays history into the same ledger rows
  and duplicates are absorbed by the existing dedupe key.

---

## 4. Data integrity across providers

Both providers feed the same normalised model:

* Accounts are matched by the provider's stable account id within a link.
* Transactions carry the provider's stable external id; re-reporting one is a duplicate, not
  a new row.
* When a pending authorisation posts under the same id, the row is reconciled in place
  (`reconciled_at` set, status becomes posted). This matters most for Teller, which has no
  cursor and re-reports a window: the sync engine reconciles a re-reported posted row whose
  stored copy is still pending.
* Transfers are paired (same amount, different account, within three days) into a single
  internal transfer, so moving money between the user's own accounts is not counted as
  income or spending. When only one leg is visible, the row is tagged
  `provider-transfer-unpaired` and reported in the sync run instead of being guessed at.
* A category the user confirmed is never overwritten by a provider suggestion.

---

## 5. Teller specifics worth knowing

Teller has no cursor for transactions. Each sync re-reads a date window: the cursor stores
the last successful date and the request reaches ten days further back, because Teller's own
guidance notes that a pending transaction's date can change when it posts. Duplicate
suppression does the rest, and the run reports how many rows were skipped.

Balances are per account and are fetched for each account in the link. An account whose
balances the institution does not expose is imported with a zero balance and the drift
check surfaces the difference, rather than failing the whole sync.

Closed accounts (HTTP 410 `account.closed`) are reported as a reauthorisation problem, not
retried forever.

---

## 6. Security properties

* Provider credentials never leave the server and are encrypted at rest.
* Access tokens are encrypted per link and are never serialised to a client, a log or the
  Android app.
* Teller enrolments are verified against a server-issued nonce and Teller's ED25519
  signature. A replayed or forged enrolment is rejected.
* Every endpoint that touches a link or a transaction is scoped to the signed-in user.
* Administering providers grants no access to another user's connections.
* AI tools never receive provider credentials; they answer from aggregated financial tools.

---

## 7. Verifying selection with real credentials

Once credentials exist, in order:

```bash
# 1. Directory reachable with this server's credentials
curl -s -X POST -H "Authorization: Bearer $PFC_TOKEN" \
  http://127.0.0.1:8088/api/v1/server/providers/teller/test | jq
curl -s -X POST -H "Authorization: Bearer $PFC_TOKEN" \
  http://127.0.0.1:8088/api/v1/server/providers/plaid/test | jq

# 2. Per-institution coverage, including providers that cannot serve it
curl -s -H "Authorization: Bearer $PFC_TOKEN" \
  "http://127.0.0.1:8088/api/v1/server/providers/coverage?names=USAA,Cash%20App" | jq

# 3. What a normal user sees
curl -s -H "Authorization: Bearer $PFC_USER_TOKEN" \
  "http://127.0.0.1:8088/api/v1/connectivity/catalog?query=USAA" | jq
```

Compare (2) and (3): the catalogue must reduce each institution to one available entry and
must not mention a provider name.

---

## 8. Known limitations

* **No live provider call has been made from this installation.** No Teller or Plaid
  credentials are configured, and this machine cannot reach the provider APIs. Selection,
  admin configuration and the Teller adapter's request/response handling are covered by
  contract tests against local fakes and by the running server's admin endpoints; sandbox
  verification is pending credentials.
* **Institution coverage for USAA and Cash App is unverified here.** Plaid has
  traditionally supported USAA; Cash App is a payment app rather than a bank, and neither
  aggregator documents a standard account-link product for it. Treat both as *to be
  confirmed* with the coverage endpoint above, and rely on manual entry or statement import
  where no link exists. This documentation deliberately does not present those as verified
  facts. The current machine-generated answer, including its status line, is in
  [financial-provider-coverage.md](financial-provider-coverage.md); regenerate it with
  `backend/scripts/coverage_report.py` after configuring a provider.
* **Borrowing applications** (cash advance, short-term loans) are individual cases. A
  provider that can read a checking account cannot necessarily read a loan's balance or
  repayment schedule, so no blanket claim is made.
* **Teller signing keys and mTLS material** must be kept current by the owner; an expired
  certificate shows up as a failed connection test.
