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
- **Server connection** — set and test the address of any self-hosted installation, save it, and switch between servers later. Sessions are per server. Details: `docs/android-server-connection.md`.
- **Settings** — account, server connection, theme and sign-out.

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
- The base URL is whatever server the user saved; the build only supplies a first-launch
  default (`https://10.0.2.2:8443/api/v1/`, the emulator's view of the host). Pointing the
  app at another installation requires no rebuild — see `docs/android-server-connection.md`.
- The session token lives in `SecureTokenStore`: encrypted with an AES/GCM key held by the
  Android Keystore, never in plain preferences. It is stored per server, so switching
  addresses never carries a token across. Only the server URL and theme stay in DataStore.
- Signing out calls `POST /auth/logout`, which records the token ID server-side, so the
  token stops working immediately even if it was copied off the device. Expired or revoked
  tokens produce a `401` and the app returns to the sign-in screen.

## Build and test

```bash
cd android
./gradlew :app:testDebugUnitTest      # 53 unit tests
./gradlew :app:assembleDebug          # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:assembleDebugAndroidTest
```

No `JAVA_HOME` is needed. `gradle/gradle-daemon-jvm.properties` pins the build daemon to a
JDK 17 toolchain (any vendor), so the wrapper builds even when the host's default `java` is
newer — Gradle 8.11.1 refuses to run a build on JDK 25, and AGP 8.10 targets 17. The launcher
JVM is only a bootstrap: it starts the daemon and hands over, so `java -version` showing 25 is
fine, and a `JAVA_HOME` pointed at another version does not override the pin. The build
machine still needs a JDK 17 installed (`apt install openjdk-17-jdk`); to change the pin later,
regenerate the file with `./gradlew updateDaemonJvm --jvm-version=17`.

### Release builds sign themselves

The release key is never in the repository. `android/app/build.gradle.kts` reads it from a
properties file — `~/.pfc/release.properties` by default, or `PFC_KEYSTORE_PROPERTIES` —
holding `storeFile`, `storePassword`, `keyAlias` and `keyPassword`; the same four are
accepted from `PFC_KEYSTORE_FILE`, `PFC_KEYSTORE_PASSWORD`, `PFC_KEY_ALIAS` and
`PFC_KEY_PASSWORD`.

```bash
./gradlew :app:assembleRelease         # APK: app/build/outputs/apk/release/app-release.apk
/usr/lib/android-sdk/build-tools/36.0.0/apksigner verify --print-certs \
  app/build/outputs/apk/release/app-release.apk
```

With no key present the build still succeeds, just unsigned as
`app-release-unsigned.apk`, so a contributor never needs the release key to compile. This
was backported from `master`, where a signed `assembleRelease` replaced signing the artifact
by hand with `apksigner` afterwards.

## Installing on a physical device

The APK is not tied to the emulator or to this machine. Version `0.3.2` (`versionCode` 5) is
built from this tree; the exported copy is
`personal-finance-companion-0.3.2-debug.apk` in `/opt/lampp/htdocs/downloads`.

1. **Build** the debug APK (see above) — `app/build/outputs/apk/debug/app-debug.apk`.
2. **Enable developer options and USB debugging** on the phone, then confirm the host sees
   it: `adb devices`.
3. **Install**: `adb install -r app/build/outputs/apk/debug/app-debug.apk`.
4. **Point the app at your server**: the sign-in screen has **Server settings**, and after
   sign-in it is **Settings → Server**. Enter the address, tap **Test connection**, then
   **Save server**. A Docker install on the LAN is `http://<host-lan-ip>:8088`; a public
   domain is `https://finance.example.com`.
5. **Sign in** with a real account on that server. No certificate warning appears for the
   project CA: it is bundled and verification stays enabled. Plain HTTP is accepted only
   for private network addresses, and the screen says so when it is in use.

The phone must be on the same trusted network as the host. If it cannot connect, check
that the host firewall allows TCP 8443 — the API and web server themselves listen on
loopback only.

No runtime permissions are needed: there is no storage, location or contacts request, and
CSV files are read through the system document picker.

## "Request failed (404)" on a working server

A 404 from a server that is obviously up is almost always the address, not the deployment.
The app builds every request by appending to the stored server address, so a stored value
that already carries part of the API path makes the app ask the wrong URL:

| Stored address | Request | Result |
| --- | --- | --- |
| `https://192.168.1.5:8443/api` | `/api/api/v1/auth/me` | **404** |
| `https://192.168.1.5:8443` (no path) | `/auth/me` | web app HTML with 200 — a JSON parse error |
| `https://192.168.1.5:8443` (correct) | `/api/v1/auth/me` | 200 |

App data survives reinstallation, so a value written by an older build keeps failing after
the code that wrote it is gone. Since 0.3.2 the app canonicalises the address when it builds
a request (and when it shows the address in Settings), so `/api`, `/api/v1`, `/v1` and a bare
origin all resolve to `origin/api/v1/`. Nothing in storage is rewritten — the bearer token is
keyed by the stored address, and rewriting that key would silently sign the user out.

To check a server by hand, ask for a route that requires authentication; 401 means the route
exists and only the token is missing, while 404 means the path is wrong:

```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://192.168.1.5:8443/api/v1/auth/me
# 401 expected; compare with /auth/me, which answers 200 with the web app's HTML
```

A 200 that is not JSON is reported as such on screen, and a 404 now says the server is
reachable but has no API at that address — both point at the address, not at an outage.

## Security notes

- The manifest requests only `INTERNET`; there is no storage, location or contacts
  permission.
- CSVs are streamed from the content URI to the server and are not copied into app
  storage.
- Credentials and tokens are never logged; API errors are reduced to readable messages
  without exposing server internals.
- HTTPS with certificate verification is mandatory. The project CA that signs the server
  certificate is bundled at `res/raw/pfc_ca.crt` and trusted through
  `res/xml/network_security_config.xml`; the app does not trust every user CA, and it never
  runs with verification disabled. Debug builds additionally accept a user-installed CA
  for ad-hoc troubleshooting.
- Cleartext is permitted only for `127.0.0.1` and `localhost`, so `adb reverse` debugging
  keeps working. Every other host must be HTTPS.
- The bundled CA is a public certificate; the CA private key never leaves `certs/` on the
  server machine. Run `scripts/gen-tls && scripts/export-ca` and rebuild the APK if the CA
  or the LAN address changes.
- Trusting the CA on a desktop browser (for the web app) is a separate, manual step — see
  the README.

## Current limits

- No offline mode; the app requires the backend, and it must be reachable over HTTPS with
  the project CA trusted.
- Only the emulator was used for end-to-end verification in Phase 1.3; no physical device
  has been tested.
- Onboarding can create an opening account. Settings then covers the same ground as the web
  settings page: display name, timezone, Safe-to-Spend rules, notifications, income sources and
  their next payday, categories, merchant aliases, and data export or account deletion.
- Bills can be added, edited and deleted from the Bills tab, and the month's budget is edited
  from Budgets. The bill's first due date is fixed once it exists, because moving it would
  rewrite occurrences that were already generated.
- No transaction deletion in the Android UI (the backend endpoint exists).
- Single currency (USD), matching the backend's Phase 1 scope.
