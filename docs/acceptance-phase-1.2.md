# Phase 1.2 acceptance report — end-to-end validation and hardening

Date: 2026-11-03. Environment: Linux, Python 3.12.13, PostgreSQL 17.11 (Docker),
Node 24, Android SDK 36, project-local Temurin JDK 17, Gradle 8.11.1, API 36
x86_64 emulator (`emulator-5554`).

Scope: validate a completely new user from registration through onboarding, accounts,
income/payday, categories, budgets, bills, transactions, Safe-to-Spend and Shopping
Check; compare web and Android against the same backend; rehearse backup/restore and a
fresh migration; review security and service operation. No feature area was rebuilt.

## Changes made during validation

Correctness and reliability fixes:

- Weak passwords now return the domain `422` message instead of an unhandled `500`.
- Bills reject another user's `category_id` on create and update.
- Archived accounts keep their derived balance when listed.
- A paid bill occurrence is no longer reported as the next due occurrence.
- Stale or same-day paydays are projected forward using the income frequency.
- Pending debits are always deducted until posted, including bill-linked payments.
- Pending transfers out of spendable cash reduce Safe-to-Spend; transfers between two
  spendable accounts net to zero.
- Production startup rejects a default/short `SECRET_KEY`, insecure cookies, or wildcard
  CORS.
- Posted transactions can no longer be dated in the future, so a future paycheck cannot
  enter balances before it arrives. Pending future rows remain allowed.
- Web transaction date input and the Android date picker prevent future dates.
- Android gained the missing first-run onboarding flow (profile check, opening account,
  income, buffer, completion).
- Android dashboard recent activity no longer prefixes expenses with `+`.

## Automated checks

| Check | Command | Result |
| --- | --- | --- |
| Backend suite | `cd backend && .venv/bin/pytest -q` | **81 passed** |
| Web suite | `cd web && npm test -- --run` | **9 passed** |
| Web production build | `cd web && npm run build` | **BUILD SUCCESSFUL** |
| Android unit tests | `cd android && JAVA_HOME=../.tools/jdk17 PATH=../.tools/jdk17/bin:$PATH ./gradlew testDebugUnitTest assembleDebug` | **31 passed**, 0 failures; **BUILD SUCCESSFUL** |

The backend total includes new regression tests for expected future income, rejected
future posted income, rejected future edits, CSRF/auth, ownership isolation, pending
transfers, payday projection, archived balances and the production configuration guard.

## New-user scenario results

A fresh web registration (`phase12.validation@example.com`) completed all three
onboarding steps with no pre-existing data.

| Area | Observed result |
| --- | --- |
| Registration / login | Web registration created the account and set session + CSRF cookies; login and `/auth/me` succeeded. |
| Onboarding | Profile saved; timezone `America/New_York`; income `$2,800` biweekly; next payday `2026-11-13`; buffer `$250`; checking `$4,200`; savings `$8,000`. |
| Accounts | Two accounts created; total cash `$12,200`; 19 default expense categories seeded. |
| Custom category | `Hobbies & Fun` created and visible in both clients. |
| Budget | November plan: planned income `$5,600`, allocations `$2,900` (Housing `$1,800`, Groceries `$650`, Restaurants `$250`, Hobbies `$200`), unallocated `$2,700`. |
| Bills | Rent `$1,800` due Nov 10, City Power `$120` due Nov 5, annual insurance `$600` due Dec 1, Gym `$50` due Nov 14; occurrences generated and paid rows advanced correctly. |
| Ledger | Posted income, purchases, refund, transfer, credit-card purchase and pending purchase created. Credit card debt stayed outside cash. |
| Bill matching | City Power transaction auto-matched (confidence 0.99). A 0.72 Gym charge appeared under Bills and was confirmed on Android, paying the occurrence and advancing the next due date. |
| Budget math | Published spending `$390.15`; Electricity and Shopping showed negative unbudgeted remaining, correctly highlighted rather than hidden. |
| Safe-to-Spend | `$12,504.10` at the final state (available `$14,596.60` − pending `$42.50` − bills `$1,800` − buffer `$250`), identical via web, Android and API. |
| Shopping Check | Web and Android both returned “This $75.00 purchase fits your Hobbies & Fun budget and leaves $125.00”; max recommended `$200.00`. |
| CSV import | Android imported 2 rows, skipped 1 duplicate, rejected 1 invalid date with a readable reason. |
| Future income | A posted `$2,800` paycheck dated Nov 13 returned `422` in a live API call. Automated test `test_expected_paycheck_is_not_counted_as_available_cash` proves a stored future paycheck changes the horizon but not available cash (`$900` opening, `$100` buffer → safe `$800`). |

## Cross-platform consistency

- Web-created `Web-created coffee` (`$63.25`) appeared in the Android ledger.
- Android-created `Android coffee` (`$28.75`) appeared in the web ledger and was edited
  on web to `$31.25`; the API reflected the edit.
- Android bill-match confirmation updated the web/API bill state.
- Android and web each displayed Safe-to-Spend `$12,504.10` for the same database.
- Final Android dashboard showed expenses without a `+`, income/refunds with one.

## Backup and restore rehearsal

- `./scripts/app backup` produced `backups/finance-20261103-090323.dump` (70,075 bytes,
  18 table-data entries).
- The dump was restored with `pg_restore` into a temporary database; the active database
  was never restored over.
- Active vs restored counts matched exactly: users 4, accounts 9, transactions 30,
  categories 77, budgets 2, allocations 16, bills 11, occurrences 127, matches 3.
- At backup time the validation user had 3 accounts, 12 transactions and 4 bills in
  both; checking balance was `$6,054.10` in both; Alembic revision `fced71fed827` in
  both.
- The temporary database was dropped and the rehearsal proved no active data was lost.

## Fresh migration and service checks

- A temporary empty database migrated through both revisions to `fced71fed827` (head)
  and produced 18 public tables; the temporary database was dropped.
- `pfc.service` is enabled for `default.target`; user linger is `yes`.
- `systemctl --user restart pfc.service` replaced the API and web PIDs; the old PIDs
  stopped, health returned `ok`, web returned HTTP 200, and exactly one listener remained
  on each of ports 8010 and 5183.
- No stale project API/web processes or duplicate listeners were found.

## Security review evidence

| Control | Result |
| --- | --- |
| Session cookie | `pfc_session` is `HttpOnly`, `SameSite=Lax`, `Path=/`, 12-hour `Max-Age`; no `Secure` in development HTTP. CSRF cookie is readable by design. |
| CSRF | Cookie-authenticated `POST` without `X-CSRF-Token` returned `403`; bearer-token request succeeded. Login/register are exempt. |
| CORS | Allowed origin received `Access-Control-Allow-Origin`; unknown origin did not. Production guard rejects `*`. |
| Authentication expiry | 12-hour TTL; a deliberately expired token returned `401 Session expired`; a tampered token returned `401 Invalid session token`. |
| Passwords | Argon2id; weak registration returned `422`; wrong password returned generic `401 Incorrect email or password`. |
| Ownership | Phase 1.2 ↔ demo cross-user transaction and bill reads returned `404`; existing suite covers list/mutation isolation. |
| Browser storage / XSS | No tokens in `localStorage`; only theme preference is stored. CSRF token is read from its cookie. |
| Android token storage | Token lives in app-private DataStore (not encrypted at rest); see limitations. |
| Logging | No request bodies, amounts, passwords or tokens logged; IDs remain in uvicorn access logs. |
| Secrets | The development `SECRET_KEY` was rotated; its value is not printed in docs or API responses. Production startup rejects the shipped placeholder. `.env` is local and is never served as a static asset. |
| Transport | API/web are bound to `0.0.0.0` for LAN/emulator use over plain HTTP; this is development-only. No HSTS is sent because there is no TLS listener. |

## Implemented, tested, and not verified

**Implemented:** all fixes and UI additions above, including Android onboarding and the
future-date guards.

**Tested:** 81 backend tests, 9 web tests, 31 Android unit tests, production web build,
Android APK build, the new-user web workflow, Android install/login/session persistence,
transaction create/edit, bill-match confirmation, Shopping Check, CSV import,
backup/restore, fresh migrations, restart and API security probes.

**Not verified / limitations:**

- No physical Android device was available; all device evidence is from the API 36
  x86_64 emulator. No instrumented UI test was executed.
- The Android onboarding screen was built and installed, but the validation user was
  already onboarded before it was installed, so the fresh Android onboarding flow was not
  exercised end-to-end. Its API contract is covered by the web onboarding test and the
  backend suite.
- A full machine reboot was not performed on this shared workstation. Boot enablement and
  linger were inspected, and a service restart was exercised; actual boot-time start
  remains unverified.
- `pfc.service` is a `Type=oneshot` wrapper (`active (exited)`, `MainPID=0`). It starts
  API/web as detached process groups and stops them via pidfiles, but does not supervise
  or auto-restart a crashed child. Production should split API/web into supervised units.
- Browser session uses stateless JWT; logout clears cookies but does not revoke an already
  stolen token. There is no refresh-token rotation or server-side denylist.
- The login rate limiter is per-process and in-memory (8 attempts/minute per IP + email);
  it resets on restart and is not shared across workers.
- Android stores the bearer token unencrypted in app-private DataStore. Device backup or
  root access could expose it.
- Development traffic is HTTP on the LAN; cookies are not `Secure` and tokens travel in
  clear text. Use HTTPS, `COOKIE_SECURE=true`, a real secret and rotated demo credentials
  before any non-local exposure.
- Demo credentials are intentionally published for the seeded demo account. Remove or
  rotate the demo account before sharing the deployment.
- Uvicorn access logs still include object UUIDs (no amounts, bodies or credentials).
- The new guard blocks future posted writes, but existing rows are not rewritten. The
  demo account still contains two future-dated posted expenses from earlier seed/testing;
  audit and correct legacy rows before a production upgrade.
- Single currency (USD), English-only UI, no offline mode, no bank connections.

This report is evidence for Phase 1.2 validation, not a production-readiness sign-off.
The unverified items and the supervision, TLS, token-revocation and rate-limiting gaps
must be closed for a production deployment.
