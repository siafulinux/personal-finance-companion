# Phase 1.1 acceptance report — Android transactions and CSV import

Date: 2026-11-03. Environment: Linux, Python 3.12.13, PostgreSQL 17.11 (Docker),
Node 24, Android SDK (platform 36, build-tools 36), project-local Temurin JDK 17 and
Gradle 8.11.1 under `.tools/`.

Scope: manual transaction create/edit, transaction detail, bill-matching feedback, and
native CSV import in the Android app, reusing the existing backend engine. No database
migration was added and no financial calculation moved into the client.

## Automated checks

| Check | Command | Result |
| --- | --- | --- |
| Backend regression | `cd backend && .venv/bin/python -m pytest` | **68 passed** in 20.39s |
| Android unit tests | `cd android && ./gradlew :app:testDebugUnitTest` | **31 passed**, 0 failures |
| Android debug APK | `cd android && ./gradlew :app:assembleDebug` | **BUILD SUCCESSFUL** |
| Instrumented test APK | `cd android && ./gradlew :app:assembleDebugAndroidTest` | **BUILD SUCCESSFUL** (compiled only) |
| Web (unchanged) | `cd web && npm test -- --run` | **9 passed** |

Backend import coverage includes automatic bill matching during commit
(`test_scenario_g_duplicate_import_creates_no_duplicates` asserts `auto_matched == 1`),
the ambiguous-match rules, partial payments, one-transaction/one-bill, and idempotent
commits. Android coverage is split across `FinanceRepositoryTest`,
`TransactionDraftTest`, `TransactionFormViewModelTest`, `ImportViewModelTest`,
`LedgerViewModelTest` and `FormatTest`.

## Scenario results

| # | Scenario | Evidence | Result |
| --- | --- | --- | --- |
| 1 | Create a normal expense | `FinanceRepositoryTest` posts the contract fields; live API check created a 1.23 purchase and Safe-to-Spend moved by exactly 1.23 | Pass |
| 2 | Create income | `TransactionDraftTest` accepts income and emits the shared contract; form exposes the type | Pass |
| 3 | Create an internal transfer | `TransactionDraftTest` requires a distinct destination; `FinanceRepositoryTest` sends both accounts; backend scenario H | Pass |
| 4 | Edit an existing transaction | `TransactionFormViewModelTest` loads and PATCHes; live API edit changed 1.23 → 2.34 and cleared merchant/notes | Pass |
| 5 | Invalid transaction data | `TransactionDraftTest` and `TransactionFormViewModelTest` prove invalid drafts never reach the server; backend 422 messages render on the form | Pass |
| 6 | Transaction pays an outstanding bill | Backend `test_scenario_d_auto_match_marks_bill_paid`, `test_high_confidence_match_is_automatic`; form reports "Matched the … bill" | Pass (server/VM) |
| 7 | Ambiguous bill match | Backend `test_two_close_candidates_are_ambiguous_and_never_auto`, `test_scenario_e_ambiguous_match_requires_confirmation`; form reports review needed; Bills tab offers confirm/reject | Pass (server/VM) |
| 8 | Import a valid CSV | Backend scenario G imports 3 rows and auto-matches 1 bill; `ImportViewModelTest` renders preview counts and commit results | Pass |
| 9 | Reject a malformed CSV | Backend `test_invalid_rows_are_rejected_with_reasons`; `ImportViewModelTest` shows a 422 upload error and keeps no file; invalid rows display their reasons | Pass |
| 10 | Detect duplicates | Backend scenario G re-uploads the same file (3 duplicates, 0 imported) and recommits (no-op); import preview shows duplicate counts | Pass |
| 11 | Retry an unsuccessful import | `ImportViewModelTest` fails a commit, keeps the preview, then retries and receives the result | Pass |
| 12 | Android and web agree | Same API/database and no local financial math. Live bearer-token check: Safe-to-Spend 213.36 → 212.13 → 211.02 → 213.36 and account balance 98.00 → 96.77 → 95.66 → 98.00 across create/edit/delete | Pass at API level |

The live check used the demo account, a payload identical to `TransactionWrite`
(`account_id`, description, merchant, amount as a string, `tx_type`, `status`,
`txn_date`, category, notes, tags), then read `/dashboard` and `/transactions/{id}`.
The verification transaction was deleted and both totals returned to their baseline.

## Android capabilities delivered

- Ledger actions: **Add transaction** and **Import CSV**.
- Form: type (purchase, bill/card payment, income, refund, transfer), status, amount,
  date picker, account, category, transfer destination, merchant, tags, notes.
- Validation mirrors the backend; amounts are `BigDecimal`-safe and sent as strings.
- Detail screen with edit action; success confirmation and inline error states.
- Import: SAF document picker, account selection, streamed multipart upload with
  progress, server preview, editable mapping, explicit confirmation, commit results,
  rejected-row reasons, safe retry.
- Bill matching remains server-side; high-confidence automatic matches are reported,
  medium/ambiguous matches appear under Bills for confirmation.
- Dashboard, budgets, bills and ledger refresh on resume after a write.
- No storage permission; only `INTERNET` is declared.

## Backend changes

- `POST /imports/{id}/commit` now reports match outcomes after all rows exist:
  `matched_bills`, `auto_matched`, `suggested_matches`, and `match_suggestions`, in
  addition to `imported`, `duplicates`, `rejected` and `already_committed`.
- `tests/test_imports.py` asserts automatic matching and the one-commit/idempotent
  re-import behaviour.
- No schema or migration change.

## API endpoints reused

- `POST /transactions`, `GET/PATCH/DELETE /transactions/{id}`, `GET /transactions`
- `POST /imports`, `POST /imports/{id}/preview`, `POST /imports/{id}/commit`,
  `GET /imports/{id}/records`
- `GET /match-suggestions`, `POST /matches/{id}/confirm`, `POST /matches/{id}/reject`
- `GET /accounts`, `GET /categories`, `GET /dashboard`, `GET /bills`,
  `GET /bill-occurrences`, `GET /budgets/current`

## Build and APK

- Build: `BUILD SUCCESSFUL`.
- APK: `android/app/build/outputs/apk/debug/app-debug.apk` (12,464,402 bytes).
- Instrumented test APK: `android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`.

## Emulator and device verification

Not performed in this session. The installed Android SDK contains platform,
build-tools and platform-tools but **no emulator package and no system image**; `adb
devices` lists no devices, and the `inkflow` AVD references a system image that is not
installed. The debug APK and instrumented test APK build, but they were not installed
or exercised here. No physical-device testing was performed. The Phase 1 emulator run
recorded in `docs/acceptance.md` predates these screens.

## Remaining limitations

- No on-device run of the new screens in this environment (see above); the Compose UI
  test compiles but was not executed.
- No offline cache; the app requires the backend.
- Accounts, categories, budgets and bills are still created in the web app. Android can
  mark bills paid, confirm/reject matches, and manage transactions.
- No transaction deletion in the Android UI (the backend endpoint exists).
- English-only labels; single USD currency.
- Cleartext HTTP is allowed for local development only.
