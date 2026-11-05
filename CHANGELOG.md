# Changelog

All notable changes to this project are recorded here. The product name is deliberately
temporary ("Personal Finance Companion").

Versions are internal to this repository; `0.1.0` is the Phase 1 baseline shipped in the
Android manifest and API metadata. Format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/).

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
