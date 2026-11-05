# Android app

Kotlin + Jetpack Compose (Material 3), OkHttp and kotlinx.serialization against the same
FastAPI backend as the web app. The backend owns every financial calculation; the app
renders server responses and never computes balances locally.

## What the app can do

- **First-run onboarding** — profile confirmation, timezone, income and payday, buffer,
  and an opening account, using the same `/auth/onboarding` contract as the web app.
- **Dashboard** — Safe-to-Spend with the full explanation, account balances, upcoming
  bills and budget pulse.
- **Ledger** — filtered transaction list with income/spending/refund totals, empty and
  error states, and pull-through loading on resume.
- **Transaction detail** — every stored field, including merchant, notes, tags, transfer
  destination and status.
- **Add / edit transaction** — full manual entry against the existing transaction API.
- **CSV import** — Storage Access Framework document picker, server-side preview,
  column mapping, explicit review, idempotent commit and a result summary.
- **Bills** — recurring bills, occurrences, mark-paid, and the server's payment-match
  suggestions with confirm/reject actions.
- **Budgets and Shopping Check** — the same server engines the web app uses.
- **Settings** — server address, theme and sign-out.

Screens refresh when they resume, so a transaction created in the app is reflected in
budgets, bills and Safe-to-Spend without a separate local projection.

## Transaction entry

`Add transaction` on the ledger opens a Compose form with:

| Field | Control / rule |
| --- | --- |
| Type | Purchase, bill payment, income, refund, internal transfer. Bill payments (`bill_payment`) also cover paying a credit card; transfers move money between accounts. |
| Status | Posted or pending |
| Description | Required, 1–255 characters |
| Amount | Decimal keyboard, at most two decimals, always positive |
| Date | Material 3 date picker; dates after today are disabled. The server rejects a future date on a posted row (save it as pending instead). |
| Account | Selector over active accounts |
| Category | Selector; hidden for transfers, which cannot have one |
| Transfer destination | Selector over the other active accounts |
| Merchant, tags, notes | Optional |

Amounts are kept as strings and validated with `BigDecimal`; no `Double` or `Float` is
used for money. The app validates locally for fast feedback, but the server remains the
authority and its validation errors are shown inline.

Creating a transaction sends `POST /transactions`; editing sends `PATCH
/transactions/{id}` with explicit nulls so cleared optional fields really clear. After a
successful save the ledger is refreshed, the form is popped, and the other tabs reload
when shown.

## Bill matching feedback

Manual and imported transactions use the backend's existing matching service. The
create response's `match_info` drives the confirmation message:

- **Automatic match** (unambiguous, above the user's auto-match threshold and with
  automatic matching enabled) — "Saved. Matched the … bill."
- **Suggested match, including ambiguous matches** — "Saved. A possible bill match is
  waiting for review under Bills." The Bills tab lists candidates with confidence,
  remaining amount and an ambiguous badge; only an explicit Confirm pays the bill.
- **No match** — ordinary save confirmation; possible duplicate ledger entries are also
  reported.

Partial payments and the one-transaction/one-bill rule are enforced by the backend. The
Android app never runs its own matching algorithm.

## CSV import

The workflow mirrors the backend contract:

1. **Select the account** the rows belong to.
2. **Choose a CSV** with `ActivityResultContracts.OpenDocument()`. The app requests no
   storage permission; it reads only the chosen content URI.
3. **Upload** with `POST /imports` (multipart, streamed with progress). The response
   includes the detected headers, a suggested mapping, and an automatic preview when the
   columns can be mapped.
4. **Review the preview** — total/ready/duplicate/invalid counts, the ready total, and up
   to 40 rows with date, description, merchant, amount and status.
5. **Adjust the mapping** — date, description, amount, or separate debit/credit columns,
   merchant, type, category and external ID. `Update preview` calls `POST
   /imports/{id}/preview` with the same mapping contract as the web app.
6. **Confirm** in an explicit dialog, then commit with `POST /imports/{id}/commit`.
7. **Results** — imported, duplicates skipped, invalid rows, bills automatically matched
   and bill matches to review, plus the rejected rows and their reasons.

Safeguards:

- Nothing is committed before the confirmation dialog.
- The backend fingerprints every row, so uploading and importing the same file again
  adds no transactions; committing the same import twice is a no-op.
- A failed upload or commit leaves the preview intact and the commit can be retried; the
  server's transaction boundary prevents partial financial writes.
- Invalid rows are never silently discarded; their reasons are displayed.

## First run

After login, an account that has not completed onboarding is routed to the onboarding
form: confirm the display name and timezone, set income/payday and the cash buffer, and
create the opening checking account. It submits the same `/auth/onboarding` contract as
the web app. Completion is server-side, so both apps resume at the same place and the
app does not duplicate the onboarding calculation.

## Data flow

```
Compose screen → ViewModel → FinanceRepository → ApiClient (OkHttp)
                                                   │ bearer token
                                                   ▼
                                  FastAPI (same database as web)
```

- Only the access token, server URL and theme are stored on the device (DataStore).
- The ledger, accounts, bills and budgets are fetched on demand; there is no separate
  financial cache that could disagree with the web app.
- The default base URL is `http://10.0.2.2:8010/api/v1/` for an emulator; set a LAN or
  HTTPS URL in **Settings → Server address** for other devices.

## Build and test

```bash
cd android
./gradlew :app:testDebugUnitTest      # 31 unit tests
./gradlew :app:assembleDebug          # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:assembleDebugAndroidTest
```

If the system JDK is broken or older than 17, point `JAVA_HOME` at a JDK 17. This
workspace uses a project-local JDK and Gradle under `.tools/` (gitignored):

```bash
JAVA_HOME=../.tools/jdk17 PATH=../.tools/jdk17/bin:$PATH \
  ../.tools/gradle-8.11.1/bin/gradle :app:assembleDebug
```

## Security notes

- The manifest requests only `INTERNET`; there is no storage, location or contacts
  permission.
- CSVs are streamed from the content URI to the server and are not copied into app
  storage.
- Credentials and tokens are never logged; API errors are reduced to readable messages
  without exposing server internals.
- Cleartext HTTP is enabled only for local development. Point the app at HTTPS before
  distributing it.

## Current limits

- No offline mode; the app requires the backend.
- Onboarding can create an opening account. Categories, budgets and bills are created and
  edited in the web app; Android can record, correct and import transactions, mark bills
  paid and confirm matches.
- No transaction deletion in the Android UI (the backend endpoint exists).
- Single currency (USD), matching the backend's Phase 1 scope.
