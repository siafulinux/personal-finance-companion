# Financial provider administration

This server can connect bank accounts through more than one aggregator. The owner of the
installation configures those aggregators **once**; everybody else just searches for their
institution and approves access. This document is for the owner.

Teller is the primary provider by default and Plaid is the fallback. Both are optional: an
installation that configures neither still works, with manual accounts, CSV import and
statement import.

---

## 1. What the administrator controls

| Setting | Where | Effect |
| --- | --- | --- |
| Enabled | Admin → Providers, or `TELLER_PROVIDER_ENABLED` | Whether new connections may use this provider. Existing connections keep syncing if you disable it. |
| Priority | Admin → Providers | Which provider is tried first. Lower runs first; Teller is seeded at 10, Plaid at 20. |
| Environment | Admin → Providers, or the provider's `*_ENVIRONMENT` variable | `sandbox`, `development` or `production`. |
| Credentials | Admin → Providers screen, or environment variables | Stored encrypted (see below). |
| Automatic selection | Admin → Providers | On: per-institution selection. Off: only the highest-priority ready provider is used. |

The credential fields are declared by the backend, and the screen renders whatever the
server says it needs, so a future provider does not require a new form.

---

## 2. Teller

### 2.1 Create credentials

1. Create an account at <https://teller.io> and open **Applications**.
2. Note the **Application ID** (`app_…`). This is public: Teller Connect shows it in the
   approval sheet.
3. For anything beyond sandbox, open **Certificates** and download `teller.zip`, which
   contains the client certificate and private key. mTLS is mandatory for development and
   production; sandbox is the only environment that does not require it.
4. Optionally copy the **Token Signing Key** from the application settings. It is the
   public key used to verify the enrolment Teller Connect hands back.

### 2.2 Enter them

Admin → Providers → Teller:

* **Application ID** — public, shown in clear.
* **Client certificate (PEM)** — paste the certificate file contents.
* **Client private key (PEM)** — paste the key file contents.

Or, for a Docker deployment, in `.env`:

```dotenv
TELLER_APPLICATION_ID=app_xxxxxxxxxxxx
TELLER_ENVIRONMENT=sandbox
# PEM contents, or absolute paths inside the container if you mount them as secrets.
TELLER_CERTIFICATE=/run/secrets/teller_cert.pem
TELLER_PRIVATE_KEY=/run/secrets/teller_key.pem
TELLER_SIGNING_KEY=/run/secrets/teller_signing.pem
TELLER_PROVIDER_ENABLED=true
```

Values saved on the admin screen take precedence over environment variables. Untouched
fields keep falling back to the environment, so the two can be mixed.

### 2.3 How Teller linking works

Teller has no server-side token exchange. The flow is:

1. The server returns a Teller Connect configuration: application id, environment,
   products (`balance`, `transactions`), the institution to preselect, and a **nonce**.
2. The browser opens Teller Connect, the user signs in at their institution, and Teller
   returns an enrolment containing an access token and a signature.
3. The server verifies the nonce (it is HMAC-signed by this installation, bound to the
   signed-in user, and expires after 30 minutes) and the ED25519 signature over
   `nonce.accessToken.userId.enrollmentId.environment` using the token signing key.
4. Only then is the access token encrypted and stored, and the first sync runs.

unsigned enrolments are accepted in **sandbox only**, because sandbox holds no real data.
Outside sandbox a missing signature or a missing signing key refuses the connection.

### 2.4 Teller limits

* Sandbox is free and unlimited for development.
* Development is unbilled and hard-limited (Teller documents 100 enrolments).
* Production billing is per connected account and product; check your dashboard for
  current rates.
* The API is rate limited per application. The adapter maps HTTP 429 to a retryable
  failure, so the link backs off instead of hammering.

---

## 3. Plaid

### 3.1 Create credentials

1. Create an account at <https://dashboard.plaid.com>.
2. Open **Team → Keys** and copy the **client ID** and the secret for the environment you
   intend to use (`sandbox`, `development`, `production`).

### 3.2 Enter them

Admin → Providers → Plaid: **client ID** and **secret**. Or:

```dotenv
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_sandbox_secret
PLAID_ENVIRONMENT=sandbox
PLAID_PROVIDER_ENABLED=true
```

### 3.3 How Plaid linking works

Plaid is the conventional flow: the server creates a link token (restricted to the
institution the user picked), the browser opens Plaid Link, and the public token comes back
to the server, which exchanges it for an access token. Plaid sends additions, modifications
and removals with a cursor, so syncing is incremental.

### 3.4 Plaid limits

* The Trial plan is enough to develop against sandbox: free, with a small Item limit and
  no production access.
* Production access requires an application review and an agreement; a real bank
  connection cannot be demonstrated with a Trial key.
* `/transactions/sync` is included in the Transactions product and is rate limited per
  Item; the adapter maps rate limits to a retryable failure.

---

## 4. Where credentials live

Credentials entered on the admin screen are written to `provider_configs` as
**AES-256-GCM ciphertext**. The key is derived with HKDF from `PROVIDER_ENCRYPTION_KEY`,
or from `SECRET_KEY` when that is not set. Set `PROVIDER_ENCRYPTION_KEY` on any real
deployment so that rotating `SECRET_KEY` does not make stored provider credentials
unreadable.

The database therefore never contains a usable secret on its own. If you lose the key, the
admin screen shows that the stored credentials cannot be read and asks you to re-enter
them; nothing crashes.

Nothing secret is ever returned by an API. The admin screen sees booleans, a masked hint
(`abcd…wxyz`) and the capture timestamp only. Logs record which fields changed, never their
values. An ordinary user cannot reach any of these endpoints, and being the administrator
does **not** grant access to another user's accounts, transactions or connections.

---

## 5. Testing the configuration

Use **Test connection** on each provider card. It performs a real, read-only call:

* **Teller** — fetches the public institution directory and reports how many institutions
  can supply transactions. It also tells you whether mTLS material is present and whether
  a signing key is configured.
* **Plaid** — calls `/institutions/get`, which validates the client id and secret and
  reports how many US institutions are visible.

A failure is stored next to the provider with the reason ("missing certificate",
"rejected secret", "provider unavailable"), and the result is cleared automatically when
you change a credential, because the old result only proved the old value.

From a shell:

```bash
# Public health, no credentials involved
curl -s http://127.0.0.1:8088/api/v1/server/info | jq

# Admin endpoints need the administrator's session or bearer token
curl -s -H "Authorization: Bearer $PFC_TOKEN" \
  http://127.0.0.1:8088/api/v1/server/providers | jq
curl -s -X POST -H "Authorization: Bearer $PFC_TOKEN" \
  http://127.0.0.1:8088/api/v1/server/providers/teller/test | jq
```

---

## 6. Rotating and disabling

* **Rotate a secret** — paste the new value and save. The old test result is discarded.
* **Remove a credential** — press *Remove saved …*; the field is deleted from the encrypted
  payload.
* **Disable a provider** — untick *Enabled*. New connections stop using it; existing links
  keep syncing, so a user's data is never stranded.
* **Change priority** — edit the number. 10 is tried before 20; any non-negative integer up
  to 1000 is accepted.
* **Pin one provider** — switch *Automatic provider selection* off. Only the first ready
  provider is used, and institutions it cannot serve are reported as unavailable.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Financial connections are not set up on this server yet" | No provider is enabled and configured | Add credentials, or accept manual entry / statement import |
| Test says *missing_mtls* | Teller environment is development/production without a certificate | Paste the certificate and key, or use sandbox |
| Test says *not_configured* | Required field empty | Fill it in |
| Test says the signing key is not a valid ED25519 key | Wrong PEM pasted into the signing key field | Paste the public key exactly as downloaded |
| A user's connection shows *Reconnect needed* | The institution revoked access (password change, MFA) | The user reconnects; the link is repaired rather than duplicated |
| Test succeeds but a link fails with `invalid_token` | The access token belongs to another environment | Check the provider environment matches the credentials |

---

## 8. What this document does not claim

No live Teller or Plaid request has been made from this installation: it has no provider
credentials and no outbound access to their APIs. The adapters are exercised against
documented request/response shapes in contract tests, and the admin flows are covered
against the running server. Live sandbox verification is the next step once credentials
exist — see `docs/financial-provider-selection.md` for the exact checks to run.
