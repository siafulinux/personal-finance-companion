# Changelog

All notable changes to this project are recorded here. The product name is deliberately
temporary ("Personal Finance Companion").

Versions are internal to this repository; `0.1.0` is the Phase 1 baseline shipped in the
Android manifest and API metadata. Format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/).

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
