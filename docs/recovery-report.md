# Recovery report — Personal Finance Companion

Date: 2026-11-04. Assessment only: no application source was modified. Environment actions
taken during the assessment: the stopped `pfc-db` container was started; a source-only
checkpoint archive was written; a dump was restored into a temporary database and dropped.

## 1. Last known-good production version

**Phase 1.2 baseline, `0.1.0`, Alembic head `fced71fed827`.**

Evidence, in order of strength:

- `docs/acceptance-phase-1.2.md` (2026-11-03 09:48) is the last completed acceptance report:
  81 backend tests, 9 web tests, 31 Android unit tests, successful web build and APK build,
  full new-user validation, backup/restore rehearsal, security probes.
- The database dump `backups/finance-20261103-090323.dump` (2026-11-03 09:03) restores to
  exactly the row counts that report records: users 4, transactions 30, categories 77,
  budgets 2, allocations 16, bills 11, occurrences 127, matches 3, revision `fced71fed827`.
- **No source file was modified after that report.** A `find -newermt` sweep over the whole
  tree shows the only post-09:48 changes are screenshots (`artifacts/` 10:03–10:46), runtime
  logs (to 10:59) and pid files. The APK at `android/app/build/outputs/apk/debug/app-debug.apk`
  was rebuilt at 23:48 from that same unchanged source.

The source baseline therefore equals the Phase 1.2 release and its documented state.

## 2. Current project state

| Aspect | State |
| --- | --- |
| Source code | **Intact.** Byte-identical to two recovery copies (see §3). |
| Version control | **None.** No `.git` in the workspace or any copy: no commits, branches, tags, or revert points. |
| Backend environment | **Broken by the move.** `backend/.venv` contains 25 console scripts (`alembic`, `pfc`, `uvicorn`, …) whose shims hardcode the old absolute path `/home/siafulinux/.config/freebuff-desktop/local-projects/…`, which no longer exists. The interpreter symlink itself resolves, so `python -V` works but `alembic`/`pfc` fail. |
| Database | **Data lost.** The workspace move produced a fresh, empty cluster. `pfc-db` is healthy on `127.0.0.1:55432` but the `finance` database contains **zero tables**; `finance_test` no longer exists (the suite recreates it). |
| Web environment | Healthy. 9/9 tests pass. |
| Android environment | Healthy. 31/31 unit tests pass; SDK, JDK 17 and Gradle 8.11.1 present under `.tools/`. |
| Runtime services | Down. No listeners on 8010/5183, no emulator attached. `pfc.service` reports a stale `active (exited)`. |
| Service unit | **Points at the dead path.** `WorkingDirectory` is the old `…/.config/freebuff-desktop/local-projects/…`; it cannot start the app. |
| Changelog / release notes | Absent. |
| Documentation | Complete and consistent with the code: README, architecture, api, android, acceptance (Phase 1), acceptance 1.1, acceptance 1.2. |

## 3. What happened after the baseline

Confirmed facts:

- 2026-11-03 10:03–10:59: emulator verification of the Android first-run flow — screenshots of
  login, registration, registration filled, relaunch, onboarding start — and an API log
  showing a `POST /auth/register` → `201` at the end. This addresses the Phase 1.2 limitation
  that Android onboarding had not been exercised end-to-end. **No source change** accompanied it.
- 2026-11-03 15:13: a config backup was taken (`~/.config/freebuff-desktop.bak-2026-11-03-1513`),
  already containing a workspace whose `data/postgres` is **empty**.
- 2026-11-03 22:13: a second recovery snapshot (`~/freebuff-pre-local-recovery-20261103-221311`).
- 2026-11-03 22:35: the current `data/postgres` cluster was created (fresh `initdb`).
- The project was relocated from `~/.config/freebuff-desktop/local-projects/<project>/threads/<thread>/`
  to `~/Freebuff-Projects/<project>/threads/<thread>/`.

Consequences:

- The **code** survived the relocation intact; three copies exist and their source trees are
  identical (`diff -rq` over source, excluding build output). `~/Freebuff-Projects-Preserved/…`
  is the recommended fallback copy.
- The **database volume did not survive**. The bind-mounted `data/postgres` was re-initialised,
  so the live cluster is empty. The pre-wipe cluster copy inside
  `~/.config/freebuff-desktop.bak-2026-11-03-1513/…/data/postgres` was inspected read-only and
  is **an empty directory**, not the old cluster — there is no shadow copy of the live data.
- The **Python virtualenv** was moved without being relocatable, so its entry points are dead.
- The **systemd unit** still references the pre-move directory.

Assumption, stated explicitly: the post-09:48 emulator work did not edit source. The mtime
sweep supports this, but with no VCS there is no diff to prove it beyond file timestamps.

## 4. Confirmed regressions and outstanding problems

Environment regressions (all caused by the move, none in the code):

1. `backend/.venv` entry points unusable; backend suite cannot start (fails at
   `RuntimeError: Alembic failed` in `conftest`).
2. Live database empty; the application has no data and no schema.
3. `~/.config/systemd/user/pfc.service` points at a non-existent `WorkingDirectory`.
4. API, web and emulator were not running.

Data loss:

5. Everything written between the 09:03 dump and the ~10:59 shutdown is unrecoverable, including
   the account registered at 10:52 during the Android onboarding check. `docs/acceptance-phase-1.2.md`
   already notes a pre-existing issue not fixable by restore: the demo account holds two
   future-dated posted expenses created before the future-date guard.

Pre-existing gaps carried over from Phase 1.2 (not regressions, still open):

6. `pfc.service` is a `Type=oneshot` wrapper that does not supervise children.
7. Android stores its bearer token unencrypted in app-private DataStore.
8. Stateless JWT sessions cannot be revoked; login rate limiting is in-process.
9. HTTP-only local transport, published demo credentials, no CHANGELOG, no VCS.

## 5. Features that were working and must keep working

Per the Phase 1, 1.1 and 1.2 reports, and still present in the source:

- Exact-decimal Safe-to-Spend engine with an inspectable explanation.
- Accounts and ledger: cash/checking/savings/credit/wallet, transfers, refunds, pending rows,
  audited balance corrections.
- Budgets: allocations, carryover, per-category headroom.
- Bills: schedules, occurrences, deterministic matching, partial payments, reserves, calendar.
- CSV import: mapping, validation, duplicate detection, idempotent commit.
- Shopping Check.
- Dashboard, cash-flow forecast, AI-ready tool registry (no provider wired).
- Web app (React/TypeScript) and Android app (Kotlin/Compose) on one API.
- Android: onboarding, add/edit/detail transaction, CSV import via SAF, bill-match review.
- Operations: migrations, demo seed, backup/restore, health checks, three test suites.

## 6. Features that were incomplete at the baseline

- Android onboarding existed and was installed, but its end-to-end run was the very work in
  progress when the workspace was lost. The flow is in the source; the evidence is screenshots.
- Android has no transaction deletion (web-only) and no offline cache.
- Categories, budgets and bills are still created in the web app.
- No instrumented Compose test had been executed on the emulator (the test APK compiles).

## 7. Recommended recovery sequence

Recovery work only; no new features until step 6 passes.

1. **Rebuild the backend virtualenv at the new path** with the pinned dependencies
   (`uv venv --python 3.12 .venv` + `uv pip install -e ".[dev]"`, versions fixed in
   `backend/pyproject.toml`). Confirm `pfc --help` and `alembic current` work.
2. **Restore the last-known-good data** from `backups/finance-20261103-090323.dump` into the
   live `finance` database, then confirm `alembic current` = `fced71fed827` and the §1 counts.
   Keep the 11-02 dump untouched as the older fallback.
3. **Re-run all three suites** on the recovered workspace: backend, web, Android unit tests.
   This is the gate that proves the Phase 1.2 baseline is intact after recovery.
4. **Repair the runtime**: point `pfc.service` at the new workspace, then `./scripts/app start`
   and verify health, web `200`, and a single listener per port. (Optional but recommended:
   replace the oneshot wrapper with supervised API/web units, per the Phase 1.2 limitation.)
5. **Establish version control and a changelog** before any further feature work — an initial
   commit of the recovered baseline, a tag for the recovered release, and a CHANGELOG entry
   recording the data loss and the restore.
6. **Re-verify the Android flows on the emulator** (the interrupted Phase 1.2 follow-up):
   onboarding, create/edit transaction, bill-match confirmation, CSV import, cross-app parity.
7. Only then resume feature development (Android budget/bill creation, Android deletion, etc.).

## 8. Risks, dependencies, missing information

- **Irreplaceable asset is the dump.** Two dumps exist (11-02, 11-03); both are intact and the
  11-03 one was proven restorable. Take a fresh dump immediately after step 2 and copy it
  outside the workspace.
- **No VCS** means no attribution or rollback for the recovery itself. Creating the repository
  (step 5) is cheap insurance and should not wait for feature work.
- **Post-09:03 writes are gone.** Any expectation that the 10:52 validation account still exists
  is unfounded; it must be recreated if needed.
- **Docker volume is a bind mount** to `data/postgres`, which is how the move was able to
  re-initialise it. Prefer a named volume, or document that `data/` must move with the project.
- **The systemd unit path is a snapshot of the old layout.** Any future workspace relocation
  will break it the same way; make the unit read its directory from a stable location.
- **Unknown:** whether the interruption also left a half-applied state anywhere else. Nothing in
  the source, migrations or test suites suggests it; the venv and service unit are the only
  path-dependent artefacts found (`grep` for the old path outside `.venv` returns nothing).
- **Not verified:** physical Android device behaviour, boot-time service start, and any behaviour
  that depends on the lost post-09:03 data.

## Recommended single next action

Rebuild `backend/.venv` at the new path so the pinned dependencies and the `pfc`/`alembic`
entry points are valid again. It is the prerequisite for restoring the verified dump through the
project's own tooling and for re-running the backend suite that gates the recovery.
