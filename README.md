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
- **Dashboard and cash-flow forecast** — one screen for Safe-to-Spend, the month's budget pulse, upcoming bills and a projected balance.
- **Connected data (Phase 2)** — a provider-independent linking layer with a built-in **sandbox institution** (no bank credentials, no network) and a Plaid adapter that stays off until configured. Cursor-based incremental sync, duplicate suppression, pending→posted reconciliation, encrypted tokens and disconnect-with-deletion. With Plaid sandbox keys in `.env`, `backend/scripts/verify_plaid_live.py` proves link → sync → resync → revoke against Plaid's real API and writes evidence to `logs/plaid-live/`; without keys it fails closed.
- **Review queue and intelligence** — category suggestions with reasons (accepting makes them yours, so automation never overwrites them), recurring/subscription detection, and per-merchant unusual-transaction flags.
- **Personalised insights** — explainable observations that carry their own evidence and stay silent until there is enough history.
- **AI assistant foundation** — questions answered from the deterministic engine today; an optional model provider only ever explains those figures, and only after the user opts in.
- **Web app** (React + TypeScript) and **Android app** (Kotlin + Compose) against the same API.
- **Self-hosted Docker deployment** — one Compose project with PostgreSQL, the API, a background sync worker, the web app behind nginx and Caddy as the only public port. A first-run wizard claims the server and creates its owner, `/api/v1/server/info` tells a client what it connected to, and the Android app accepts any server address instead of a built-in one.
- **Android parity** — first-run onboarding, record, edit and inspect transactions; import CSVs through the system document picker; confirm or reject server-suggested bill payments; point the app at any self-hosted server and switch later. No financial calculation is duplicated on the device.
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
scripts/install-service             # install launcher + units, enable pfc.target, start it
systemctl --user start pfc.target   # or restart/stop; one handle for the whole stack
```

`pfc.target` brings up the API, web app and TLS front. Each runs as its own supervised unit,
so a crash restarts only that process. The API waits for the database, applies migrations
before serving, restarts on failure, and runs a single worker so the login limiter keeps its
guarantee. Service logs are appended to `logs/`; start/stop and early failures are in
`journalctl --user -u pfc-api.service`.

#### The units do not contain this project's path

Installing puts two things outside the workspace:

```
~/.local/lib/pfc/pfc-run            launcher: every unit's ExecStart calls this
~/.config/pfc/workspace -> <this checkout>
~/.config/systemd/user/pfc-*.service, pfc.target
```

The launcher resolves the workspace through that one symlink and loads `.env`, sets paths and
starts the right process. Because the units reference only the launcher, **moving the project
does not invalidate them** — no path substitution, no reinstall.

After moving (or renaming) the checkout, run this from the new location:

```bash
scripts/relocate        # re-points the symlink and restarts pfc.target
```

If the symlink points at a directory that no longer exists, the units fail fast with
`pfc-run: workspace pointer is stale: … (run scripts/relocate from the new location)` in the
journal, instead of a bare "No such file or directory". Check what is being served with
`~/.local/lib/pfc/pfc-run where`.

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
./scripts/app backup        # compressed PostgreSQL dump in ./backups (refuses an empty dump)
./scripts/app verify-backup  # restore newest dump into a scratch DB and compare every table's content
./scripts/backup-routine     # dump + verify + copy off-site + prune; what pfc-backup.timer runs weekly
./scripts/app restore FILE  # restore a dump (replaces current data)
./scripts/app doctor        # runtimes, migrations, configuration, ports
```

The backend CLI exposes the same operations directly: `backend/.venv/bin/pfc --help`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q     # 87 tests, scenarios A-J plus Phase 1.2/1.3 cases
cd web && npm test                              # 23 component/format tests (jsdom)
cd web && npm run test:e2e                      # 6 browser tests in Chromium (Playwright)
cd web && npm run typecheck                     # app and e2e TypeScript (also runs in npm run build)
cd android && ./gradlew :app:testDebugUnitTest  # 31 repository, ViewModel and format tests
```

On a first run, `npx playwright install chromium` fetches the browser. The browser suite drives real key events through dialogs, which jsdom cannot reproduce: a selected value is replaced by one key press, an add dialog keeps a collapsed caret, and every character survives React re-rendering per keystroke. It runs against `web/e2e/harness/index.html`, a page that mounts the real `Modal`; nothing from `e2e/` is in the production build. Type errors in the suite fail `npm run build`, not just the test run.

The backend suite runs against a separate `finance_test` database and covers the acceptance scenarios A-J, plus authentication, CSRF, ownership isolation, duplicate detection, session revocation, throttling and edge cases (negative Safe-to-Spend, stale balances, ambiguous matches).

## Release tags

Tag pushes do not start CI, so a release tag is only trustworthy if the commit under it was
already verified on a branch. Three small tools enforce that:

```bash
git config core.hooksPath .githooks   # once per clone
./scripts/verify-ci HEAD              # is this commit green? exit 0 = yes
./scripts/tag-release v0.6.0          # annotated tag, refused unless CI passed
```

`.githooks/pre-push` runs the same check for every tag being pushed (and only for tags), so
`git tag` + `git push` cannot slip an unverified release through. A tag whose CI run is still
in progress is refused with a message saying so; push the commit as a branch and wait.

One push produces **one** run, for the commit at its tip — not one run per commit. Pushing
three commits verifies only the third; the two beneath it have no run of their own, so a tag
on one of them is refused with `no CI run exists for <sha>` even though the code reached
GitHub. Tag a commit that was itself a tip instead (a squashed merge on `master` is one), or
push the older commit as the tip of its own branch first. A pull request's head commit is
verified by both the `push` and the `pull_request` runs, which is why PR checks can list the
same job twice.

The check reads the runs through the GitHub CLI, so `gh auth login` must have been done once.
When it cannot reach GitHub it refuses rather than allowing the tag — a release that cannot
be verified is not treated as verified.

CI can also be run on demand from the Actions tab, or with `gh workflow run CI --ref <ref>`.
The trigger comes from the workflow file at the ref being run, so a tag cut before this
trigger existed cannot be dispatched; run the commit as a branch, or cut a fresh tag from a
commit that contains it.

The same suite also runs **nightly at 03:17 UTC against `master`**, because some failures
arrive without a push: a dependency's new release, a test that only fails on a particular
date, or a fixture that aged out. Scheduled runs always use the default branch's copy of the
workflow, and GitHub disables the schedule after 60 days without repository activity — the
next push turns it back on.

A red night blocks the next merge. The `Nightly suite is green` job runs on every pull
request, reads the most recent completed scheduled run and fails while that run is red, so a
broken `master` cannot be merged over. The nightly itself cannot be the required check: a
`schedule`-only job never reports on a pull request's head commit, so requiring it directly
would leave every PR waiting on a status that can never be sent.

Because a green nightly cannot exist until the fix is merged, the job honours a
**`nightly-fix`** label as its one waiver — the fix PR still has to pass the three test
jobs, and the label stays visible in the PR timeline. A night that is `cancelled` or
`skipped` proves nothing and does not block; a night that cannot be read from the API
does, because an unverified night is not a verified one.

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

- The default API address is `https://10.0.2.2:8443/api/v1/` (the host machine from an emulator, through the TLS front). It can be baked in at build time with `-PpfcApiBaseUrl=https://finance.example.com` (or `PFC_API_BASE_URL`), so a downloaded APK starts out pointed at your server. For a physical device, open **Settings → Server address** and enter your machine's LAN URL.
- HTTPS is required outside loopback and the project CA is bundled in the APK; certificate verification is never disabled. The bearer token is encrypted with an Android Keystore key, and signing out revokes it server-side.
- The Android build pins Gradle's daemon to JDK 17 (`android/gradle/gradle-daemon-jvm.properties`), so `./gradlew` works even when the host's default JDK is newer; no `JAVA_HOME` needed.
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

## Self-hosted deployment (Docker)

For running the whole application on your own machine, independent of this repository's
development setup:

```bash
cd deploy/docker
cp .env.example .env            # set POSTGRES_PASSWORD and SECRET_KEY
$EDITOR .env
docker compose up -d --build
```

Then open `http://<server>:8088/` and complete the first-run wizard (server name, owner
account, registration policy). Point the Android app at the same address —
`http://192.168.1.5:8088` on a LAN, or `https://finance.example.com` behind TLS.

- [Docker deployment](docs/docker-deployment.md) — services, commands, migration of an
  existing database, troubleshooting.
- [Server configuration](docs/server-configuration.md) — `/server/info`, registration policy,
  pairing, environment variables.
- [Android server connection](docs/android-server-connection.md) — how a phone finds and
  trusts your server.
- [Provider administration](docs/financial-provider-administration.md) — configuring Teller
  and Plaid once, credential storage, connection tests and troubleshooting.
- [Provider selection](docs/financial-provider-selection.md) — how an institution is matched
  to a provider, fallback and reauthorisation rules, and what is unverified.
- [Remote access](docs/remote-access.md) — trusted LAN, public HTTPS, tunnels, and what is
  still unverified.

## Documentation

- [Architecture](docs/architecture.md) — engine, data model, import pipeline, decisions.
- [API](docs/api.md) — endpoints, authentication, examples.
- [Android](docs/android.md) — screens, transaction rules, CSV import, build and limits.
- [Acceptance report](docs/acceptance.md) — scenarios A-J and what was verified manually.
- [Phase 1.1 report](docs/acceptance-phase-1.1.md) — Android transaction/import tests and results.
- [Phase 1.2 report](docs/acceptance-phase-1.2.md) — end-to-end validation, hardening, backup/restore and security evidence.
- [Phase 1.3 report](docs/acceptance-phase-1.3.md) — recovery gate, service supervision, LAN TLS, session revocation and remaining risks.
- [Phase 2 Docker report](docs/acceptance-phase-2-docker.md) — the self-hosted deployment, first-run setup, Android connectivity and what remains unverified.
- [Provider configuration report](docs/acceptance-provider-configuration.md) — administrator-managed Teller/Plaid configuration, selection evidence and remaining gaps.
- [Institution coverage](docs/financial-provider-coverage.md) — generated table of what each provider's directory actually says about USAA, Cash App and common borrowing apps (currently unverified: see its status line).
- [Backups](docs/backups.md) — the weekly dump/verify/prune routine, retention, restore drill and what it does not cover.
- [Reboot verification](docs/boot-verification.md) — how to prove the supervised stack returns after a reboot, and what to check when it does not.
- [Changelog](CHANGELOG.md) — release history, including the 2026-11-03 data loss and the restore that produced the `v0.1.0-recovered` baseline.

## Limits

- Single currency (USD) and single user per account; no sharing or households.
- No live bank connections; data arrives by manual entry, CSV, or the sandbox institution.
- No AI provider is wired in; the tool layer and provider interface are ready for one.
- The Docker deployment serves plain HTTP on a trusted LAN by default; a public HTTPS
  deployment needs a domain and a certificate, and that path is documented but not yet
  verified on this machine.
- Android has no offline cache; it requires the server. Android onboarding creates one opening account, and the Android app matches the web settings screen: profile, income and payday, Safe-to-Spend rules, notifications, categories, merchant aliases, bills, budgets, data export and account deletion. Transaction deletion is still web-only.
- Bill reminders and location features are designed for later phases and off by default.
