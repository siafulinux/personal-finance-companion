# Changelog

All notable changes to this project are recorded here. The product name is deliberately
temporary ("Personal Finance Companion").

Versions are internal to this repository; `0.1.0` is the Phase 1 baseline shipped in the
Android manifest and API metadata. Format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/).

---

## [0.4.0] — 2026-11-08 — Change-password release

`versionName` `0.4.0`, `versionCode` 6, application id `com.pfc.companion`. A minor bump
rather than a patch because the release adds a capability users act on, not only repairs.
The server (`APP_VERSION` `2.0.0`) is unchanged.

### Added

- **A signed-in user can change their own password.** `POST /api/v1/auth/password` requires
  the current password, applies the same strength policy as registration, and refuses a new
  password identical to the old one. The change increments the account's `token_version`, so
  every token minted earlier stops verifying — other devices are signed out exactly, without
  timestamp granularity. The endpoint returns a fresh token for the device that made the
  change, so that one stays signed in. Exposed as **Settings → Change password** on the web
  and on Android, with field-level errors for a wrong current password and a weak or unchanged
  new one.

### Changed

- **Exported APK** `personal-finance-companion-0.4.0-debug.apk`, replacing the `0.3.2` copy in
  `/opt/lampp/htdocs/downloads`.

---

## [0.3.2] — 2026-11-08 — Android release, tag `v0.3.2-android`

An Android-only release: `versionName` `0.3.2`, `versionCode` 5, application id
`com.pfc.companion`. The server (`APP_VERSION` `2.0.0`) and web app are unchanged by it.

### Fixed

- **A stored server address can no longer 404 a healthy server.** The app builds every
  request by appending to the stored address, so a value that already carried part of the API
  path asked the wrong URL — `/api` became `/api/api/v1/auth/me` (404), and a bare origin
  without `/api/v1` asked `/auth/me`, got the web app's HTML with a 200 and surfaced as a
  parse error. `ServerUrl.apiBaseFromStored` now strips a whole or partial API path
  (`/api/v1`, `/api`, `/v1`, repeated) before appending the canonical one, and the Settings
  field shows the origin instead of a value the same form would reject. Storage is deliberately
  not rewritten: the bearer token is keyed by the stored address, so rewriting that key would
  sign the user out. A 404 now says the server is reachable but has no API at that address,
  and a 200 that is not JSON says the address may point at the web app.
- **`.gitignore` no longer hides the app's data layer.** The rule meant for the repository's
  own data directory was unanchored and also matched
  `android/app/src/main/java/com/pfc/companion/data`, so twelve sources and four test classes
  were never tracked. The rule is anchored, and those files enter the repository here.

### Changed

- **Android `0.3.0` → `0.3.2`.** `0.3.1` (repairing an address with no `/api/v1`) existed only
  in the version comment and was folded into `0.3.2`, so no build was ever labelled `0.3.1`.
- **Exported APK** `personal-finance-companion-0.3.2-debug.apk`, replacing the `0.3.0` copy in
  `/opt/lampp/htdocs/downloads`. It is byte-identical to
  `android/app/build/outputs/apk/debug/app-debug.apk` (MD5 `48cf378f…`), whose
  `output-metadata.json` records `versionCode` 5 / `versionName` `0.3.2`.
- `docs/android.md` states the shipped version and installation path, and documents the
  `Request failed (404)` troubleshooting the canonicalisation comes from.

### Verified

- Emulator, with a deliberately broken address injected: the previous build blocked sign-in
  with its own path validation, `0.3.2` signed in and loaded the dashboard from the server,
  kept the session across a cold restart, and ended with a canonical stored address.
- **61 Android unit tests pass**, 17 of them in `ServerUrlTest`; `assembleDebug` succeeds.

---

## [Unreleased] — Phase 2: Dockerised self-hosted deployment

### Added

- **A complete `docker compose` deployment** (`deploy/docker/`): `postgres:17-alpine`, the API,
  a background sync worker built from the same image, the built web app behind nginx, and
  Caddy as the only published port. Two networks and three volumes; every service restarts
  unless stopped and has a health check, and the API waits for PostgreSQL before applying
  migrations. Only the proxy publishes a port — the database and API are unreachable from
  outside the host.
- **First-run setup.** `POST /server/setup` creates the installation's owner, names the
  server and records its registration policy, then signs the owner in. It answers **409** once
  any account exists, and registration is refused before setup on a Docker install
  (`OPEN_REGISTRATION_UNTIL_SETUP=false`), so a stranger who finds the URL cannot claim it.
  The web app shows the wizard while `setup_required`.
- **`GET /api/v1/server/info`** — public, read-only connection facts (app/server name, version,
  API generation, API and web URLs, health, registration and setup state) with no secret in
  it. The advertised address follows the request, so an internal Docker hostname is never
  handed to a client.
- **Server administration and pairing.** `GET`/`PATCH /server/settings` (administrator only),
  and 10-minute single-use pairing codes stored hashed, which carry the server address but no
  credential.
- **Background worker** (`app/worker.py`) running the existing `sync_due_links` on an interval,
  with graceful SIGTERM handling and a heartbeat file used by its container health check.
- **Android 0.3.0** (`versionCode` 3): the app connects to any self-hosted server. Sign-in
  screen and Settings both offer an address field, **Test connection** against `/server/info`,
  the server's name and version on success, and **Save server** enabled only after a
  successful test. `ServerUrl` allows plain HTTP only for loopback, RFC1918, link-local, ULA,
  `.local`/`.lan`/`.home.arpa` and single-label hosts, and rejects credentials, paths and
  query strings. Tokens are stored per server in the Keystore-encrypted store, so switching
  addresses never leaks a session to another installation.
- **`scripts/docker-fresh-install-test`** — an isolated stack that proves the first-run path
  (20 checks) and removes itself.
- **`scripts/docker-migrate-existing`** — copies an existing non-Docker database into a running
  stack, refusing a non-empty target, verifying the dump holds table data, and comparing seven
  table counts afterwards.
- Migration `a7804f0fa670` (additive): `server_settings`, `pairing_tokens`.
- `docs/docker-deployment.md`, `docs/server-configuration.md`,
  `docs/android-server-connection.md`, `docs/remote-access.md` and
  `docs/acceptance-phase-2-docker.md`.
- **Browser-level tests for dialog focus and selection** (`web/e2e/`, `npm run test:e2e`,
  Playwright 1.64 on Chromium). The harness at `e2e/harness/index.html` mounts the real `Modal`
  under `StrictMode` with an inline `onClose` and controlled inputs — the exact shape that used
  to lose the caret — and six tests drive it with real key events: one key press replaces a
  selected value in an edit dialog, an add dialog keeps a collapsed caret, every character
  survives React re-rendering per keystroke, punctuation and `/` insert literally, a date field
  takes focus without erroring, and Escape closes. jsdom cannot reproduce browser typing, so
  this is the first coverage of selection-on-open that could actually regress unnoticed.
  Deliberately separate from `npm test`: the harness is never included in `vite build`.
  `tsconfig.e2e.json` type checks `e2e/` and `playwright.config.ts`, and `npm run build` runs
  it before bundling, so a broken spec fails the build gate instead of surfacing at test time.

### Changed

- `APP_VERSION` is now `2.0.0` and is read from `backend/app/version.py` by `/server/info`.
- The exported APK is `personal-finance-companion-0.3.0-debug.apk`; the `0.2.0` copy was
  removed from the download directory.
- **The Android build selects JDK 17 by itself.** `android/gradle/gradle-daemon-jvm.properties`
  (generated by `./gradlew updateDaemonJvm --jvm-version=17`) pins the build daemon to a 17
  toolchain of any vendor, so `./gradlew` works with no `JAVA_HOME` on a host whose default
  `java` is 25 — Gradle 8.11.1 will not start a build on JDK 25. Only the daemon compiles, so
  the launcher may be any JDK and a `JAVA_HOME` pointed at a newer one no longer breaks the
  build either. The constraint is a version, not a path, so it survives a workspace move and
  a different JDK vendor.

### Fixed

- **Typing in a dialog no longer throws focus to the browser's Find bar.** `Modal` re-ran its
  setup effect whenever `onClose` changed identity, and every page passes an inline arrow, so
  each keystroke re-focused the dialog container and pulled the caret out of the field being
  typed into. The next letter then landed outside the app (Firefox type-ahead find, or nothing
  at all elsewhere). Escape handling and scroll locking are unchanged; focus is now moved only
  when a dialog opens, and `onClose` is read through a ref. Covered by
  `web/src/components/ui.test.tsx`.
- **Form dialogs open with the first text field focused**, so a dialog can be typed into
  without clicking first. Selects, checkboxes, radios, colour pickers, read-only and disabled
  controls are skipped; a dialog with no text field (a confirmation) keeps focus on the
  container, where Escape works and Enter cannot land on a destructive button. When that
  first field already holds a value (an edit dialog, or a prefilled payment amount) the value
  is selected so typing replaces it; an empty field (an add dialog) keeps a collapsed caret.
  Date, time and number inputs reject selection, and then focus alone is applied.

### Verified

- Backend **154 passed**, web **11 passed** (plus a clean `tsc --noEmit`), Android **53 unit
  tests, 0 failures** (re-run with `--rerun-tasks`; the first attempt reported `UP-TO-DATE`),
  and `assembleDebug` succeeds.
- Fresh install: 20/20 checks, including registration refused before and after setup, setup
  replay refused, pairing single-use, and an authenticated `GET /dashboard`.
- Migration copy: 26 tables of data and all seven compared counts identical against a
  throwaway stack.
- Restart: `db` and `api` return to healthy with data and health intact.
- Android emulator: **Reachable · Lakeside Finance v2.0.0** from `http://10.0.2.2:8088`, with
  the matching `200` for `GET /api/v1/server/info` (`okhttp/4.12.0`) in the proxy log.

### Known limits

- **HTTPS is not configured on this machine.** Port 8448 is published but `PFC_SITE_ADDRESS`
  is `:80`, so no certificate is served and TLS connections are refused. `docs/remote-access.md`
  documents the domain/DNS/certificate procedure as unverified.
- A **host reboot** was not performed; restart policies and ordering are configured, and
  container-level restarts were tested.
- The Docker stack is a **separate, fresh installation**; the existing ledger was not migrated
  into it, though the migration script exists and was proven against a scratch stack.
- Android connection testing was verified on the emulator; signing in to the Docker stack from
  the app was not exercised in this phase.

---

## [Unreleased] — Phase 2.0 (connected data and intelligent finance foundation)

### Added

- **Provider-independent connectivity.** An adapter contract (`app/providers/base.py`)
  replacing the Phase 1 stub, a deterministic **sandbox institution** that needs no
  credentials or network, and a **Plaid** adapter (`/link/token/create`, item exchange,
  cursor-based `/transactions/sync`, pending→posted linkage, `revoke`) that stays disabled
  until `PLAID_CLIENT_ID` and `PLAID_SECRET` are set. The adapter also implements
  `/sandbox/public_token/create`, so a headless run can reach a real sandbox Item, and
  `scripts/verify_plaid_live.py` proves link → sync → resync (no duplicates) → balance
  agreement → revoke against `sandbox.plaid.com`. It is not yet run: this deployment holds no
  Plaid credential, and the script exits 2 without one rather than falling back to the
  simulated institution.
- **Sync engine.** Cursor-based incremental sync with per-run counters, duplicate
  suppression through the existing dedupe key, pending→posted reconciliation, removal
  handling, retry/backoff state, sync history, and disconnect with optional deletion of the
  accounts and transactions a link created. Provider access tokens are encrypted at rest and
  removed on disconnect (`app/security/secrets.py`).
- **Transaction intelligence.** Category suggestions with confidence, source and a stated
  reason; accepting records the value as the user's own choice so later automation cannot
  overwrite it, rejecting suppresses that rule. Recurring-series detection with subscription
  classification and `subscription_monthly_total`, plus per-merchant unusual-transaction flags.
- **Personalised insights.** Explainable observations (category over budget, habitually over
  budget, repeated small purchases) each carrying an `evidence` block, behind a minimum-history
  guard of three months and five transactions. Merchant profiles feed Shopping Check.
- **AI assistant foundation.** Provider ABC with `openai_compatible` and `disabled`
  implementations; the model only explains the output of the nine permission-checked tools and
  never calculates. Without a provider the same questions are answered deterministically, and
  figures leave the server only after explicit consent.
- **Web pages** for connections and sync history, the review queue, personalised insights and
  the assistant, wired into the existing shell and API client.
- **Scheduled sync.** `pfc sync-links` plus `pfc-sync.service` / `pfc-sync.timer`, rendered by
  `scripts/install-service`; the interval floor (`SYNC_MIN_INTERVAL_MINUTES`) keeps a frequent
  timer from hammering a provider.
- Migration `1d9d6ad34893` (additive only): `provider_links`, `provider_link_secrets`,
  `sync_runs`, `category_suggestions`, `recurring_series` and four preference columns.
- `docs/acceptance-phase-2.0.md`, `docs/phase-2-plan.md`, and
  `backend/scripts/smoke_phase2.py` (35-check live end-to-end run).

### Changed

- **Android version `0.1.0` → `0.2.0`** (`versionCode` 2). The installed app had not been rebuilt
  since before the bundled project CA (`res/raw/pfc_ca`) was wired into
  `network_security_config.xml`, so the exported debug APK predated TLS trust and the
  transaction/CSV-import/secure-storage work. Rebuilt and published as
  `personal-finance-companion-0.2.0-debug.apk`, replacing the `0.1.0` download.

### Fixed

- `formatDate()` no longer mixes `dateStyle`/`timeStyle` with day/month parts, which made
  `Intl.DateTimeFormat` throw and blanked the Connections page whenever a sync run existed.
- Insight and Shopping Check sentences now render amounts through `format_money` instead of
  interpolating raw decimals; their `evidence` blocks stay machine-readable.

### Known limits

- Sandbox only: no live institution has been connected. The Plaid adapter is contract-tested
  against a fake endpoint, never a real item. No webhook receiver yet. The AI assistant has
  never run against a real model, and Android has no Phase 2 screens.

---

## [Unreleased] — Phase 1.3 (reliability, transport and session hardening)

### Added

- **Supervised services.** `pfc.target` plus `pfc-api`, `pfc-web` and `pfc-tls` units
  replace the previous oneshot wrapper: database wait, migrations before serving,
  `Restart=on-failure`, start limits, graceful stop and log files under `logs/`.
  `scripts/install-service` renders and enables them.
- **LAN HTTPS.** `scripts/gen-tls` issues one project CA and a server certificate covering
  loopback, `10.0.2.2` (emulator → host) and the LAN address; Caddy serves it on 8443 with
  HSTS and security headers. `scripts/export-ca` bundles the CA into the Android app, which
  trusts it via `res/xml/network_security_config.xml` and still verifies certificates.
- **Token revocation.** `revoked_tokens` (migration `b9cb28b8b1a5`) plus `POST
  /auth/logout` revocation, so signing out ends a session from any client instead of only
  clearing cookies.
- **Android secure token storage.** The bearer token moved from plain preferences into a
  Keystore-encrypted store (AES/GCM).
- **Restore rehearsed.** The newest dump was restored into a scratch database, compared
  table-by-table against production (19/19 identical, same `alembic_version`) and the scratch
  database dropped.
- **Weekly verified backup routine.** `scripts/backup-routine` dumps, verifies the dump by
  content against production, then prunes; `pfc-backup.timer` runs it Sundays at 03:00
  (`Persistent=true`, so a missed run catches up after boot). A failed dump or a failed
  verification aborts before pruning, and an unverified dump is moved to `backups/rejected/`.
  Retention defaults to eight dumps (`PFC_BACKUP_KEEP`). Documented in `docs/backups.md`.
- **Remote off-site destination.** `PFC_BACKUP_OFFSITE_RSYNC=user@host:/path` copies dumps
  over ssh instead of to a local disk, with `PFC_BACKUP_OFFSITE_SSH_OPTS` for a non-standard
  port, dedicated key or jump host. Every network call is bounded by
  `PFC_BACKUP_OFFSITE_TIMEOUT` (600 s default), so a host that accepts the connection and then
  stalls cannot hang the unit. `scripts/backup-routine --preflight` checks reachability,
  `rsync`/`sha256sum` and write access without taking a dump. Verified against a throwaway
  sshd: copy, remote checksum, atomic rename, remote retention and the unreachable-host abort.
  `vpsnetwork` remains an unusable destination — see the blocker in `docs/backups.md`.
- **Off-site backup copies.** The weekly routine now copies each verified dump to a second
  filesystem (`PFC_BACKUP_OFFSITE_DIR`) or an rsync-over-ssh target
  (`PFC_BACKUP_OFFSITE_RSYNC`), checksums the copy at the destination and renames it into
  place only after the checksum matches, so a partial copy can never look like a backup. It
  refuses a destination on the same filesystem as `backups/` (the symptom of an unmounted
  disk), and a failed copy aborts before any pruning. Off-site retention is separate
  (`PFC_BACKUP_OFFSITE_KEEP`, default 12 weeks).
- **`pfc verify-backup [dump]`. Restores a dump into a scratch database, hashes every row
  of every public table and compares the digests with production, so a backup that restores
  with the right row counts but wrong contents is rejected. The scratch database is always
  dropped, and the command defaults to the newest dump in `backups/`.
- **Reboot verification harness.** `scripts/boot-test snapshot|verify` records and diffs the
  unit state, certificate, schema revision, row counts, TLS-checked HTTP and authenticated
  figures. Procedure in `docs/boot-verification.md`.
- `docs/acceptance-phase-1.3.md`, physical-device install instructions in `docs/android.md`.

### Changed

- Login throttling answers **429** instead of **401**, so clients no longer report a
  throttle as an expired session.
- Android default API address is now `https://10.0.2.2:8443/api/v1/`.
- The web app is served over HTTPS only: cookies are `Secure` and CORS lists the HTTPS
  origins, so a login started on `http://127.0.0.1:5183` is discarded by the browser.

### Fixed

- `scripts/export-ca` copied **Caddy's own root CA** instead of the CA that signs the
  server certificate, which would have shipped an APK unable to verify the server. It now
  exports the signing CA and refuses to proceed unless `openssl verify` passes.
- `backend/tests/test_imports.py` hardcoded November dates while the bill-matching window is
  relative to today, so the suite began failing as the calendar moved. The fixture now uses
  relative dates; no assertion was weakened.
- **`pfc backup` / `./scripts/app backup` now verifies what it wrote.** After dumping, it
  counts `TABLE DATA` entries with `pg_restore --list`; a dump with none (or one that cannot
  be listed) is deleted and the command exits non-zero with an explanation. Previously an
  empty database produced a small, valid-looking dump that restored to nothing. A failed
  `pg_dump` also no longer leaves a partial file behind.

### Fixed

- **Backup test collateral (2026-11-06).** While testing the off-site guard, a retention run
  was executed against the real `backups/` directory with `PFC_BACKUP_KEEP=1`, which pruned
  five earlier dumps (2026-11-02, 2026-11-03 and three from 2026-11-05). No database data was
  affected and the current database is covered by a verified dump on two filesystems, but
  that recovery history is gone. Retention tests now run only in temporary directories.

### Security notes

- Cookies `HttpOnly` + `SameSite=lax` + `Secure`; CORS restricted to HTTPS origins; CSRF
  still required for cookie-authenticated writes.
- API (`8010`) and web (`5183`) listen on loopback only; the TLS front is the sole
  networked listener.
- The login limiter remains per-process by design and the unit pins `--workers 1`;
  `/auth/register` is not throttled. Both are recorded as residual risks.

---

## [0.1.0-recovered] — 2026-11-04 — Phase 1.2 baseline, recovered

Tag: `v0.1.0-recovered` → commit `390a695`. The tag marks the first committed, known-good
state after the incident below; it is the baseline later phases build on.

### The data loss (2026-11-03)

- The development environment was lost and restored by the host tooling. The application
  data directory was recreated from scratch at 22:35, so the live PostgreSQL cluster was
  empty.
- Source was recovered from two snapshots taken before the loss:
  `~/.config/freebuff-desktop.bak-2026-11-03-1513` and
  `~/freebuff-pre-local-recovery-20261103-221311`.
- **Unrecoverable:** everything written between the 09:03 dump and the ~10:59 shutdown. That
  includes the account registered at 10:52 while the Android onboarding flow was being
  verified. `docs/recovery-report.md` records the full timeline and the evidence used.

### The restore

- Data restored from `backups/finance-20261103-090323.dump` into the live `finance`
  database, with the older `finance-20261102-171321.dump` kept untouched as a fallback.
- Restored revision `fced71fed827`, with row counts matching the Phase 1.2 acceptance
  report: users 4, transactions 30, categories 77, budgets 2, budget allocations 16,
  bills 11, bill occurrences 127, payment matches 3.
- The backend virtualenv was rebuilt at the current workspace path and the suite re-run.
- Git was initialised (the workspace had none), with ignore rules covering `.env`, `certs/`,
  virtualenvs, dumps, logs and generated artifacts; the recovered source became the first
  commit.

### Verified after recovery

- `docs/acceptance-phase-1.2.md` remains the last complete acceptance record: new-user
  validation, backup/restore rehearsal, security probes, Android parity. Its behaviour was
  re-confirmed rather than re-implemented.
- Known pre-existing issue, unrelated to the loss and not fixable by the restore: the demo
  account holds two future-dated posted expenses created before the future-date guard
existed (noted in `docs/acceptance-phase-1.2.md`).

### ⚠ Backup hazard found during Phase 1.3 — resolved

`backups/finance-20261104-151726.dump` was **not a usable backup**: 836 bytes, 4 TOC entries,
zero table data — it was taken while the database was still empty. A restore from it would
have silently produced an empty database.

It has been **deleted** (2026-11-05), and `pfc backup` now refuses to keep such a dump in the
first place, so the same trap cannot be recreated. Validate any older dump by hand with
`pg_restore --list <dump> | grep -c 'TABLE DATA'` before relying on it.

Known-good dumps at the time of writing: `finance-20261102-171321.dump` (fallback),
`finance-20261103-090323.dump` (the restore used in recovery) and
`finance-20261105-110231.dump` (post-recovery, 19 tables with data).
