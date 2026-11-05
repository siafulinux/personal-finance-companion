# Personal Finance Companion

A privacy-conscious personal finance app: a shared deterministic finance engine, a responsive web app, and a native Android app, all backed by PostgreSQL and a single API. The product name is deliberately temporary.

This is a working application, not a prototype: every number on screen is computed from rows in the database by the same engine.

## What exists

- **Safe-to-Spend engine** — exact decimal arithmetic with an inspectable explanation of every credit and debit.
- **Accounts and ledger** — cash, checking, savings, credit cards, wallets; transfers, refunds, pending transactions, corrections with balance adjustment audit trail.
- **Budgets** — monthly allocations, carryover, spending per category, setup wizard, category headroom.
- **Bills** — recurring schedules, generated occurrences, deterministic payment matching, partial payments, reserves, calendar.
- **CSV import** — column mapping, validation, duplicate detection, idempotent commit; try `samples/sample-transactions.csv`.
- **Shopping Check** — "should I buy this?" answered from cash and category budget, never from a guess.
- **Dashboard, cash-flow forecast, AI-ready tool registry** — structured, permission-checked payloads for a future assistant; no AI provider is called in Phase 1.
- **Web app** (React + TypeScript) and **Android app** (Kotlin + Compose) against the same API.
- **Android parity** — first-run onboarding, record, edit and inspect transactions; import CSVs through the system document picker; confirm or reject server-suggested bill payments. No financial calculation is duplicated on the device.
- **Operations** — migrations, demo seeding, backup/restore, health checks, test suites.

## Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic |
| Database | PostgreSQL 17 (project-owned Docker container) |
| Web | React 18, TypeScript, Vite, TanStack Query, custom CSS design system |
| Android | Kotlin, Jetpack Compose (Material 3), OkHttp, kotlinx.serialization, DataStore |
| Auth | Argon2id passwords, JWT bearer tokens, httpOnly session cookies + CSRF for the browser |

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Docker with Compose
- For Android: JDK 17 and the Android SDK (platform 36, build-tools 35+)

## Quick start

```bash
cp .env.example .env
# Generate a real secret before using the app beyond your machine:
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d db

cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/pfc seed-demo        # optional: clearly flagged demo data
cd ..

./scripts/app start            # database + migrations + API + web
```

- Web app: <https://127.0.0.1:8443>
- API: <https://127.0.0.1:8443/api/v1/health>
- API docs: <https://127.0.0.1:8443/api/docs>

The ports are configurable in `.env`; the defaults avoid the often-occupied 5173/8000.

### HTTPS and the project CA

Session cookies are `Secure` and CORS only allows the HTTPS origins, so the app is reached
over TLS through a local Caddy front on **8443** (`443` is often taken by another
service). `scripts/gen-tls` creates one long-lived project CA and a server certificate
covering `localhost`, `127.0.0.1`, `10.0.2.2` (the emulator's view of the host) and the
LAN address, so the app works whichever name you use without ever disabling certificate
verification.

A browser will warn until it trusts that CA. Import `certs/pfc-ca.crt` into your browser or
OS trust store once per machine (for the web app). The Android app already trusts it via
`res/raw/pfc_ca.crt`. If the CA or the LAN address changes, re-run `scripts/gen-tls &&
scripts/export-ca` and rebuild the APK.

Plain `http://127.0.0.1:5183` still serves the SPA but a login there is discarded by the
browser, because the cookie is `Secure`. Use the HTTPS URL.

### Running as a service

```bash
scripts/install-service          # renders deploy/systemd units and enables pfc.target
systemctl --user start pfc.target   # or restart/stop; one handle for the whole stack
```

`pfc.target` brings up the API, web app and TLS front. The API waits for the database,
applies migrations before serving, restarts on failure, and runs a single worker so the
login limiter keeps its guarantee. Logs are appended to `logs/`.

### Demo account

`pfc seed-demo` (or `./scripts/app seed`) creates a flagged demo account:

- Email: `demo@example.com`
- Password: `DemoPassword123!`

Demo data is visibly marked in both apps and can be removed with `./scripts/app seed-remove` without touching real accounts.

## Everyday commands

```bash
./scripts/app status        # database, API and web health
./scripts/app logs          # tail API and web logs
./scripts/app stop          # stop only the processes this project started
./scripts/app test          # backend test suite
./scripts/app test-web      # frontend tests
./scripts/app build-web     # production web build
./scripts/app backup        # compressed PostgreSQL dump in ./backups
./scripts/app restore FILE  # restore a dump (replaces current data)
./scripts/app doctor        # runtimes, migrations, configuration, ports
```

The backend CLI exposes the same operations directly: `backend/.venv/bin/pfc --help`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q     # 87 tests, scenarios A-J plus Phase 1.2/1.3 cases
cd web && npm test                              # 9 component/format tests
cd android && ./gradlew :app:testDebugUnitTest  # 31 repository, ViewModel and format tests
```

The backend suite runs against a separate `finance_test` database and covers the acceptance scenarios A-J, plus authentication, CSRF, ownership isolation, duplicate detection, session revocation, throttling and edge cases (negative Safe-to-Spend, stale balances, ambiguous matches).

## Android app

```bash
cd android
./gradlew :app:assembleDebug        # APK at app/build/outputs/apk/debug/
./gradlew :app:testDebugUnitTest    # 31 tests
./gradlew :app:assembleDebugAndroidTest
```

The app is a full participant in the ledger, not a read-only companion:

- **Add or edit a transaction** from the ledger: purchase, bill/card payment, income, refund or internal transfer, with account, category, date picker, status, merchant, tags and notes. Amounts are validated as decimals and sent to the server unchanged. Posted transactions cannot be dated in the future.
- **First-run onboarding** — confirm timezone, set income and payday, buffer, and an opening account without switching to the web app.
- **Transaction detail** shows every stored field and links to editing.
- **CSV import** uses the Storage Access Framework: pick an account, choose a file, stream it to `POST /imports`, review the server preview and mapping, confirm explicitly, then see imported/duplicate/invalid counts plus bill-matching results. Re-importing the same file is safe.
- **Bill matching** stays server-side. Automatic matches are reported after saving; suggested and ambiguous matches wait under **Bills** for confirm or reject.
- The app requests no storage permission, keeps only the token, server URL and theme on the device, and refreshes dashboard, budgets, bills and Safe-to-Spend from the server.

- The default API address is `https://10.0.2.2:8443/api/v1/` (the host machine from an emulator, through the TLS front). For a physical device, open **Settings → Server address** and enter your machine's LAN URL.
- HTTPS is required outside loopback and the project CA is bundled in the APK; certificate verification is never disabled. The bearer token is encrypted with an Android Keystore key, and signing out revokes it server-side.
- If your system JDK is broken or older than 17, run Gradle with a JDK 17: `JAVA_HOME=/path/to/jdk-17 ./gradlew ...`.
- See [docs/android.md](docs/android.md) for the form rules, import workflow and security notes.

## Configuration

All settings live in `.env` (see `.env.example`): network ports, database URL, secret key, token TTL, financial defaults, demo credentials. Financial defaults include the Safe-to-Spend horizon cap and the fallback horizon used when no payday is known.

## Security and privacy

- Financial arithmetic is server-side and exact; the browser never computes balances.
- Every query is scoped to the authenticated user; cross-user access is covered by tests.
- Browser sessions use httpOnly cookies with CSRF protection on state changes; non-browser clients use bearer tokens. Signing out revokes the token's ID server-side, so it stops working from every client.
- Transport is TLS with a pinned project CA; the API and web server bind to loopback and only the TLS front listens on the network. Login attempts are throttled per address and account (429 when tripped).
- Responses are `no-store`; security headers are applied globally; passwords use Argon2id; login errors are generic.
- No external analytics, bank aggregators, or AI calls in Phase 1. Location is not requested or stored.

## Documentation

- [Architecture](docs/architecture.md) — engine, data model, import pipeline, decisions.
- [API](docs/api.md) — endpoints, authentication, examples.
- [Android](docs/android.md) — screens, transaction rules, CSV import, build and limits.
- [Acceptance report](docs/acceptance.md) — scenarios A-J and what was verified manually.
- [Phase 1.1 report](docs/acceptance-phase-1.1.md) — Android transaction/import tests and results.
- [Phase 1.2 report](docs/acceptance-phase-1.2.md) — end-to-end validation, hardening, backup/restore and security evidence.
- [Phase 1.3 report](docs/acceptance-phase-1.3.md) — recovery gate, service supervision, LAN TLS, session revocation and remaining risks.
- [Reboot verification](docs/boot-verification.md) — how to prove the supervised stack returns after a reboot, and what to check when it does not.

## Limits

- Single currency (USD) and single user per account; no sharing or households.
- No bank connections; data arrives by manual entry or CSV.
- No AI provider is wired in; the tool layer and provider interface are ready for one.
- Android has no offline cache; it requires the server. Android onboarding creates one opening account; categories, budgets and bills are still created in the web app, and transaction deletion is web-only.
- Bill reminders and location features are designed for later phases and off by default.
