# Changelog

All notable changes to this project are recorded here. The product name is deliberately
temporary ("Personal Finance Companion").

Versions are internal to this repository; `0.1.0` is the Phase 1 baseline shipped in the
Android manifest and API metadata. Format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/).

---

## [0.6.8] — 2026-11-13 — the number catches up with the build

0.6.7 was merged but never tagged, so the build that names it never became a release. This
entry supersedes it: no code changed between the two, and the section below still describes
everything the build carries. What changes here is only the number, so a build can no longer
claim a version that has no release behind it.

### Changed

- **The manifest names `0.6.8` / `versionCode` 13.** 12 belonged to the 0.6.7 build that was
  never published; reusing it would leave two different trees sharing one install number.
  13 is the next free code — 0.6.2 shipped 9, the 0.6.0.1 maintenance build holds 11, and
  0.6.7 holds 12.

---

## [0.6.7] — 2026-11-13 — releases that check themselves, and two date bugs

Everything here was already on `master` while the manifest still named 0.6.6, which is why
this release exists at all: the tag gate now allows a manifest ahead of the tag, so a build
can name what it contains without waiting for the next numbered release.

### Added

- **`scripts/verify-apk`** checks a downloaded APK against the release that published it:
  its SHA-256 must equal a digest in one of that release's `.sha256` sidecars, and its
  signing certificate must be the project's release signer, pinned in the script. A sidecar
  is matched by digest rather than by file name, so a renamed download still verifies, and a
  release with no sidecar is rejected. Exit status separates `0` verified from `1` not
  verified and `2` could not verify — a file nobody could check is not a file that checked
  out.
- **`scripts/verify-ci` has a regression suite, run in the backend CI job**, so a change to
  the tag gate fails the build instead of waiting for a human to notice a release slipped
  through.

### Fixed

- **Two visits recorded at the same instant no longer double-notify.** The cooldown query
  compared against a strictly earlier visit, so a second detection in the same second was
  not suppressed.
- **The last server-clock reads are gone.** `complete_link`'s history window and manual
  account opening dates now come from the user's local day, so a container in UTC no longer
  dates a user's rows into their future.
- **A release whose notes drift from its changelog fails CI.** `scripts/verify-releases`
  runs in the web job, so notes edited on GitHub and entries rewritten here cannot diverge
  unnoticed.

### Changed

- **Release builds sign themselves.** `android/app/build.gradle.kts` reads the release key
  from `~/.pfc/release.properties` (or `PFC_KEYSTORE_*`), so `assembleRelease` produces a
  signed APK instead of requiring `apksigner` by hand; a missing key still yields an
  unsigned build rather than a failure.
- **The manifest now names `0.6.7` / `versionCode` 12.** The published 0.6.2 build holds 9
  and the 0.6.0.1 maintenance build holds 11, so 12 keeps every install path unambiguous.

---

## [0.6.6] — 2026-11-12 — a suite that checks the calendar and the documents

The last few releases taught the repository to verify its own releases. This one closes the
gaps those checks still left: dates that only fail on the day they are that date, documents
that point at images nobody committed, and a CLI deletion path that kept its own copy of a
bug already fixed in the service layer.

### Added

- **Backend suite on a shifted clock.** A `backend-calendar` matrix job runs the backend tests
  under `libfaketime` at three awkward dates — the 2028 leap day, 02:00 UTC on the 1st of a
  month (still the 30th in the Americas), and the February-to-March boundary. A fixture that
  assumes a 30-day November now fails on an ordinary day instead of on the day it matters. The
  preload is resolved by path and a step asserts the clock actually moved, because the
  `faketime` wrapper silently falls back to the real clock when it cannot find the library.
- **Documented images are checked.** `scripts/verify-doc-images` fails CI when a document
  references an image that is not in the repository, so a broken screenshot link cannot ship.
- **`scripts/verify-releases`** compares every published release body against its changelog
  section, so notes edited on GitHub and entries rewritten here cannot drift apart unseen.
- **The nightly failure issue closes itself.** The first green scheduled run afterwards
  comments on and closes the `ci-nightly` issue it opened, instead of leaving a stale alarm.
- **Phase 4 walkthrough captures.** Six screens — web loans, savings, obligations and shopping
  check; Android plan and shopping intelligence — are committed under `screenshots/` and
  referenced from the acceptance report.
- **CLI demo-reset tests**, so `pfc seed-demo --remove` is guarded by the same warning filter
  as the account deletion path, and a Phase 4 cascade test proving a deleted user takes their
  loans, savings goals, visits and tracked locations with them.

### Fixed

- **`pfc seed-demo --remove` deleted budget allocations twice.** It loaded each budget and let
  the ORM delete its allocations, which the category and user deletes had already removed by
  cascade, so SQLAlchemy reported "expected to delete N row(s); 0 were matched". Allocations
  are now deleted first, by bulk delete, as `delete_user_account` already did.
- **The link-history window is counted from the user's local day** rather than the server's
  clock, so an evening in the Americas no longer reads yesterday's window.
- **The sandbox institution has its own timezone** instead of the container's, so the same
  simulated input cannot produce fixtures dated a day into the user's future; test fixtures
  are dated from the user's clock for the same reason.

### Changed

- **The tag gate allows a manifest newer than its tag.** A release re-cut from a branch that
  has moved on builds today's tree under an older tag, so only a manifest *older* than the tag
  is refused — that is the case that ships an install predating the notes it is released with.
- **The Android manifest reports `0.6.6` / versionCode 10.** It had been left at `0.6.2` / 9
  while `0.6.3`–`0.6.5` shipped, so the gate could not verify any of those tags.
- **Changelog sections are ordered newest first again**, after `0.6.2` was moved to the head
  when it was re-cut.
- Removed the unused `seed_default_cash_account` helper rather than leaving a second place
  that decides which account is the default.

### Notes

- This is the first release cut after the drift: `v0.6.5` is the newest tag, so `0.6.6` is the
  next version, and the manifest, the sections above and this heading now agree with it.
- No APK has been built for this release yet, so the downloads folder and the `v0.6.2` release
  asset remain the newest installable build.

---

## [0.6.5] — 2026-11-12 — CI answers the merge queue

The four required checks could not describe a queued entry. A merge queue builds a
synthetic commit on a throwaway `gh-readonly-queue` ref, and only a `merge_group` run
reports on that commit, so without the trigger the queue would wait on a status nothing
could send. This release adds the trigger. It does not add a queue — see the notes.

### Changed

- **CI runs on `merge_group`** alongside `push`, `pull_request`, `workflow_dispatch` and
  `schedule`, so a queued entry is verified where it actually lands.
- **`Nightly suite is green` reports for `merge_group` too.** It ran only for
  `pull_request`, which would have left the fourth required check unreported in the queue.
  Its `nightly-fix` waiver now reads the pull request's labels through the number in the
  queue ref, because a `merge_group` payload carries none; a failed lookup says so and
  treats the change as unlabelled rather than waving it through.
- **`push` ignores `gh-readonly-queue/**`**, so the queue ref cannot start a second run of
  the same suite for the same tree.

### Notes

- No merge queue is enabled. GitHub offers one only for organization-owned repositories:
  this ruleset rejects the rule with `Invalid rule 'merge_queue'`, and GraphQL reports
  `repository.mergeQueue: null`. The trigger is inert until the repository moves to an
  organization, and correct if it ever does. `strict_required_status_checks_policy` on the
  ruleset already forces a pull request to include current `master` before merging.

---

## [0.6.4] — 2026-11-11 — a provider that cannot connect anybody says so

A provider switched on without usable credentials looked ready on the Providers screen: the
switch was on, the badge said "Ready", and the failure only appeared when a user searched
for their institution and was told nobody supported it. The cause was server-side, but
nothing on the page said so.

### Added

- **A "not ready to connect anyone yet" panel** on the Providers screen, listing every
  enabled provider that cannot serve a connection and why: credentials switched on but not
  saved (naming the missing fields), or saved but never tested, where a rejected key would
  stay invisible until a real user tried to link.
- **An `Untested` badge** for enabled providers whose credentials have never been tested,
  instead of `Ready`.

### Changed

- **The release tag is stamped by the image build.** Compose passes
  `PFC_RELEASE_TAG: v${PFC_IMAGE_TAG}` as a build argument and the API image bakes it in, so
  the `0.6.4` image reports `v0.6.4` and there is no constant to bump or forget. A build made
  with a bare `docker build` reports `release_tag: null` — the honest answer for something
  that is not a release, rather than the tag of whichever release happened to be last.

### Fixed

- **Card action rows wrap instead of squeezing** on the Android Loans, Savings and Shopping
  Check screens. A `Row` shrinks its children rather than wrapping, so a busy row collided two
  balance pills or broke a label mid-word ("Remov/e"). Each is a `FlowRow` now, with labels
  held to one line so a future squeeze ellipsises.

### Notes

- The page already fetched this state; nothing new is exposed and no credential value is
  rendered. Both warnings come from `configured`, `missing` and `last_test`, so an
  administrator sees the same facts the connection path acts on.

---

## [0.6.3] — 2026-11-11 — release identification

An installation could report the product version it runs (`2.1.0`) but not which release it
came from, so identifying a deployment meant shell access to its host. It now names its
release tag, which is what this entry is.

### Added

- **`release_tag` in `/server/info`**: the git tag the build was cut from, public because a
  tag names the source rather than a secret. `/server/settings`, `/server/setup` and pairing
  codes carry it too, since they all return the same connection facts.
- **Release tag row on the Server settings page**, under the server version and next to the
  other copyable connection facts.
- The 2026-11-10 walkthrough captures — web dashboard, accounts and insights; Android loans,
  savings and obligations — are kept under `screenshots/` with synthetic data.

### Changed

- `RELEASE_TAG` is a constant of its own rather than a re-use of `APP_VERSION`: the server has
  advertised `2.1.0` across every `0.6.x` release, so the two move independently.

### Notes

- Android needs no change: its client parses with `ignoreUnknownKeys`, so builds that predate
  the field ignore it.
- Producing this release moved the deployed images to `pfc-api:0.6.1` / `pfc-web:0.6.1`; the
  images now carry `org.opencontainers.image.ref.name` and `.revision` labels, which earlier
  builds claimed in `.env` but did not have.

---

## [0.6.2] — 2026-11-11 — release plumbing and the walkthrough defects

Two threads: making a release something the repository verifies rather than something a human
remembers to check, and clearing what the Phase 4 walkthroughs turned up. No version number in
the API changes — this is plumbing and repairs. The Android manifest was still `0.6.0`, which
is fixed here.

### Added

- **Teller live-verification harness** (`backend/scripts/verify_teller_live.py`): links an
  institution, syncs it and disconnects against the real API step by step, and refuses to
  report success for any step it could not run. Its fail-closed paths — missing configuration,
  a non-sandbox environment, an unreachable provider — have unit tests of their own.
- **Nightly CI** at 03:17 UTC against the default branch. Some breakage needs no push: a
  dependency publishing a breaking release, a test that only fails on one calendar date, a
  fixture that aged out. The schedule surfaces those overnight instead of during a release.
- **Android build-time address check** in CI: the app is assembled with `-PpfcApiBaseUrl` and
  the APK's dex is searched for the value, so a broken override fails the step rather than
  shipping an APK that still points at the emulator.
- **Plan tab** in Android, indexing Loans, Savings and Obligations. They were reachable only
  from a card low on the dashboard, which meant scrolling past the summary to find them and no
  route back once that card changed.

### Fixed

- **Deleting an account that has budgets** no longer deletes the budgets and their allocations
  twice. The backend suite now treats `SAWarning` as an error, so an "expected to delete N
  row(s); 0 were matched" cannot pass unnoticed a second time.
- **Insight empty states** no longer say a merchant's pattern is too weak while listing
  high-confidence findings above them; the message follows the history that actually exists.
- **Loan action row** flows to a second line instead of breaking a label mid-word
  ("Remov" / "e") when the three buttons do not fit on a narrow screen.
- **Android server address** can be baked in at build time with `-PpfcApiBaseUrl`, instead of
  the emulator loopback being the only default, and it is validated before it reaches the app.

### Changed

- PostgreSQL is published on `127.0.0.1:${PFC_DB_PORT:-5433}` for host-side diagnostics. It
  stays loopback-only, and `docs/remote-access.md` no longer claims no host port exists.
- **The Android manifest reports `0.6.2` / versionCode 9.** It had said `0.6.0` since the Phase 4
  build, so an installed APK could not be told apart from the first `0.6.0` one while the server
  had already moved on. There is no new app behaviour — the version is the change — and it is what
  the signed APK attached to this release was built from.

### Notes

- The tag was re-cut on 2026-11-12. `v0.6.2` pointed at a tree whose manifest said `0.6.4`, so
  the tag, the manifest and these notes disagreed; `0.6.3`–`0.6.5` were released from `master` in
  between and keep their own sections.

---

## [0.6.1] — 2026-11-10 — administrator-managed financial providers

The server owner now configures Teller (primary) and Plaid (fallback) once; users connect an
institution without ever choosing a provider.

### Added

- **Provider administration** (`/server/providers`, sidebar → Providers for the
  administrator): enable/disable, priority, environment, credentials, a real connection
  test per provider, automatic-selection switch, and a per-institution coverage report.
- **Institution-first connection flow** on the web: search institutions, consent, then the
  provider's own authorisation (Teller Connect, Plaid Link, or the simulated institution).
- **Teller adapter** against Teller's documented API: public institution directory, mTLS
  outside sandbox, Basic-auth access tokens, per-account balances and transactions,
  enrolment revocation, and capability flags taken from each institution's products.

### Changed

- The Connections page no longer lists providers and no longer shows a provider badge on a
  connection; unavailable institutions are explained instead of offered.
- Sync builds its adapter from saved configuration, so rotating a credential takes effect
  without a restart. A re-reported posted transaction now reconciles a stored pending row.
- The institution catalogue degrades with a short-lived negative cache instead of waiting on
  an unreachable provider for every request.

### Security

- Provider credentials are AES-GCM ciphertext keyed outside the database; the API returns
  presence and a masked hint only.
- Teller enrolments are verified against a user-bound, expiring, HMAC-signed nonce and
  Teller's ED25519 signature outside sandbox.

### Known limits

- No live Teller request succeeded from this machine, and no Plaid credentials exist, so no
  real institution link or provider coverage figure is claimed.
- Android has no connection-management screen; its existing endpoints are unchanged.

---

## [0.6.0.1] — 2026-11-12 — a 0.6.0 that still works today

A patch on the `0.6.0` maintenance line, carrying two fixes that 0.6.0 has needed since it
shipped. No new features: 0.6.0's release page stays as it is, and anyone installing the old
release today gets a build that connects.

### Fixed

- **Provider sync dates from the user's local today**, not the server's. A container in UTC
  while the user is in the Americas dated sandbox and Teller rows a day into their future,
  where "up to today" queries dropped them: sync reported `partial`, removals vanished and
  merchant history came back empty.
- **The sandbox's monthly fixtures stay detectable on any run date.** A fixed 90-day window
  could hold only two Netflix occurrences, so recurring detection found nothing and the
  suite failed on the calendar rather than on a change.

### Notes

- Backports only, on `release/0.6.0-maint`. `master` already carries both fixes, and the
  features, schema and API of 0.6.0 are unchanged.
- `versionCode` moves to 11: this installs over 0.6.0 rather than being treated as a
  downgrade, and over 0.6.2 as well. 0.6.2 shipped `versionCode` 9, so the first cut of
  this patch, also numbered 9, was refused on a device carrying 0.6.2 -- the very upgrade
  path it exists for. 10 belongs to 0.6.6 on `master`, so 11 is the next free number and
  the maintenance line no longer collides with any published release.

---

## [0.6.0] — 2026-11-10 — Phase 4 financial intelligence

The finance engine now sees the whole picture: what is borrowed, what is set aside, what is
owed, and what a trip to a particular shop actually costs. Every authoritative figure stays
deterministic; the assistant only explains it.

### Added

- **Loans & Advances** (`/loans`): personal loans, payday loans, cash advances, earned wage
  access, BNPL and instalments, with balances derived from confirmed principal repayments and
  `balance_is_estimate` / `payoff_is_estimate` when the terms are incomplete.
- **Repayment matching**: a transparent weighted score (amount 0.50, name 0.25, date 0.25),
  auto-linking only above the user's threshold with no close runner-up, and confirm/reject for
  everything else.
- **Unified obligations** (`/obligations`): bills, loan instalments and typed-in credit-card
  minimums in one ordered list, with overdue totals, due-before-payday cash flow and income
  reported separately.
- **Savings goals** (`/savings`): virtual allocations and account-backed goals, contribution
  schedules, and a guarantee that a dollar of savings is deducted at most once.
- **Safe-to-Spend breakdown**: explicit loan, savings, credit-card and obligation reserves plus
  an `explanation` list generated by the same function that does the arithmetic.
- **Merchant spending intelligence** (`/insights/merchants`): per-merchant profiles, spending
  increases, repeated small purchases, budget pressure and unusual purchases — each with
  evidence, a confidence level and a three-month/five-purchase history floor.
- **Location-aware Shopping Check**: opt-in geofences for saved places, low-power new-place
  discovery via Activity Recognition plus a single balanced-power fix, a swappable places
  provider (OSM/Overpass or none), visit history with retention and deletion, and notifications
  that respect quiet hours, cooldowns and per-place settings.
- **Structured recommendations** (`/recommendations`): explainable items with facts, confidence,
  period and data freshness, ready for the assistant to narrate.

### Changed

- Android **0.6.0**: Loans, Savings, Obligations and Shopping Intelligence screens, dashboard
  entry points, and the new location receivers (geofence, activity transition, notification
  actions, boot restore).
- Web: Loans, Savings and Obligations pages, the Safe-to-Spend breakdown panel, merchant
  insight evidence and the Shopping Intelligence settings section.
- Server advertises **2.1.0**.

### Notes

- No automatic money movement and no automatic loan payments in this phase.
- A detected visit is never a transaction; location history stays private to the account.

---

## [0.5.0] — 2026-11-08 — Android editing release

An Android-only release: `versionName` `0.5.0`, `versionCode` 7, application id
`com.pfc.companion`. The server (`APP_VERSION` `2.0.0`) and web app are unchanged. A minor
bump because the app gains capabilities the website already had, not repairs to its own.

### Added

- **Bills can be created, edited and deleted in the app.** The Bills tab has **Add bill**, and
  every bill carries **Edit**. The form covers name, merchant, expected and minimum amount,
  first due date, frequency (including a custom interval), payment account, category, notes,
  and the essential / reserve / active switches. Delete sits in the same form behind a
  confirmation. The first due date is fixed once a bill exists — moving it would rewrite
  occurrences the server has already generated — so it is shown read-only when editing.
- **Budgets are editable in the app.** **Edit budget** on the Budgets tab opens the month's
  planned income plus a limit for every category, with carry-forward per category. The whole
  allocation list is sent on save, so a category set to zero loses its allocation, matching
  the web editor.
- **Income sources and paydays are editable in the app.** Settings lists each source with its
  next payday and offers Add / Edit / Remove. A payday can also be cleared, which returns
  Safe-to-Spend to its fixed horizon — first-run setup previously set this once and left no
  way back.
- **Settings now carry the website's other options.** Profile (display name, timezone),
  appearance, Safe-to-Spend rules (buffer, horizon, both thresholds, both tolerances, pending
  debits, auto-match), notification toggles and quiet hours, categories (add, archive, delete),
  merchant aliases (add, remove), JSON export through the share sheet, sign out, and account
  deletion behind password plus `DELETE`.

### Changed

- **Exported APK** `personal-finance-companion-0.5.0-debug.apk`, replacing the `0.4.0` copy in
  `/opt/lampp/htdocs/downloads`.
- **Settings is split into sections.** `SettingsScreen` keeps the server connection and
  session actions; the newly reachable settings live in `SettingsSections.kt`.

### Not included

- Bills still cannot be marked unpaid, have an occurrence skipped, or be paid from the app;
  transaction deletion remains web-only. These are absent, not broken.

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
