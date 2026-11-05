# Phase 1 acceptance report

The Android transaction-management and CSV-import work added afterwards is covered in
[the Phase 1.1 report](acceptance-phase-1.1.md).

Date: 2026-11-02. Environment: Linux, Python 3.12.13, PostgreSQL 17.11 (Docker), Node 24, Android emulator (API 36) with KVM.

## Automated checks

| Suite | Command | Result |
| --- | --- | --- |
| Backend | `cd backend && .venv/bin/python -m pytest -q` | **68 passed** |
| Web build/typecheck | `cd web && npm run build` | **passed** |
| Web tests | `cd web && npm test` | **9 passed** |
| Android build | `./gradlew :app:assembleDebug` | **BUILD SUCCESSFUL**, no Kotlin warnings |
| Android unit tests | `./gradlew :app:testDebugUnitTest` | **5 passed** |

The backend suite runs against an isolated `finance_test` database and covers acceptance scenarios A-J plus authentication, CSRF, cross-user isolation, duplicate detection and edge cases.

## Scenario results

| # | Scenario | Evidence | Result |
| --- | --- | --- | --- |
| A | Safe-to-Spend exact math | `test_scenario_a_exact_safe_to_spend`, `test_integration_scenario_a`; live demo: 570.11 − 40.00 − 0.00 − 0.00 − 100.00 = **430.11** on web and Android | Pass |
| B | Category budget allows / blocks a purchase | `test_scenario_b_category_allows_purchase_within_budget`, `test_scenario_b_over_budget_warns`; live Shopping Check: $250 Clothing blocked, $70 max recommended, "exceeds your Clothing budget by $180.00" | Pass |
| C | Cash constraint wins over a healthy category | `test_scenario_c_cash_constraint_wins`, `test_shopping_check_respects_cash_limit` | Pass |
| D | Unique high-confidence payment auto-matches a bill | `test_scenario_d_auto_match_marks_bill_paid`, `test_high_confidence_match_is_automatic` | Pass |
| E | Ambiguous payment requires confirmation | `test_scenario_e_ambiguous_match_requires_confirmation`, `test_two_close_candidates_are_ambiguous_and_never_auto`; `GET /match-suggestions` returns grouped candidates with confidence | Pass |
| F | Partial payments accumulate and never overpay | `test_scenario_f_partial_payment_accumulates`, `test_partial_overpayment_is_rejected` | Pass |
| G | Duplicate CSV import creates no duplicates | `test_scenario_g_duplicate_import_creates_no_duplicates` (imports the same file twice through the API) | Pass |
| H | Internal transfer changes no income or spending | `test_scenario_h_internal_transfer_does_not_change_income_or_spending` | Pass |
| I | Credit-card purchase counted once and never treated as cash | `test_scenario_i_credit_card_purchase_counted_once`, `test_credit_card_never_counts_as_cash`; live dashboard excludes the −$146.95 card balance from Safe-to-Spend | Pass |
| J | Shopping Check reflects real engine values | `test_scenario_j_shopping_check_is_allowed_with_5_left`, `test_shopping_api_uses_backend_engine`; live web check returned "Not recommended" with the category limit and bills-covered context | Pass |

## Manual verification

Web (live API, seeded demo account, browser preview):

- Dashboard: Safe-to-Spend $430.11 with breakdown, 14-day bill list ($310.30), accounts, month net, budget pulse, recent activity.
- Accounts: cash $3,070.11, credit debt $146.95, net worth; balances derived, archived toggle present.
- Transactions: 13 rows, totals (income $2,400, spending $3,336.84, refunds $9.50), filters, edit/delete, CSV import entry point.
- Budgets: November plan, $3,155 allocated, $18.75 spent, per-category rows with carryover and upcoming commitments.
- Bills: upcoming/overdue/paid/recurring tabs; 90-day upcoming window; status labels and due labels; pay, mark paid, skip flows.
- Calendar: November grid with occurrences, month totals, previous/next/today.
- Shopping Check: $250 Clothing at Target → "Not recommended", max $70, category remaining and post-purchase values.
- Settings: demo banner, profile, preferences, timezone, theme, import/matching thresholds.

Android (emulator, same API):

- Installed the debug APK, signed in with the demo account through the real login form.
- Dashboard rendered $430.11, the same breakdown, warnings and explanation lines as the web app.
- Bills tab listed real occurrences with correct due labels; Budgets tab matched the monthly plan; Settings showed the demo flag, server URL and theme controls.
- Bottom navigation and session persistence across an app restart verified.

API contract check: every field the Android models require was present in live responses for dashboard, Safe-to-Spend, explanation lines, transactions, bills, occurrences, budget rows, profile, categories and Shopping Check.

Operations:

- `pfc backup` produced a 62.1 KiB compressed dump.
- `pfc doctor` passed runtime, database, migration and tooling checks (warned only about the example `SECRET_KEY` and ports already used by this project's own servers).
- `pfc --help`, `pfc status`, `./scripts/app start/stop` exercised.

## Defects found during verification and fixed

1. **Writes were lost**: request sessions closed without committing. The session lifecycle now commits on success and rolls back on error.
2. **Budget API returned 500**: `BudgetSummary` rejected the `start_date`/`end_date` fields the service had begun returning. Schema updated and a regression test added (`test_budget_api_serializes_month_summary`).
3. **Dashboard hid bills**: the "14 days" panel actually used the shorter payday horizon. It now queries a 14-day display window while reserves keep using the payday horizon.
4. **Unformatted money in explanations**: Shopping Check said "exceeds ... by 180.00". Amounts are now formatted through a single `format_money` helper, with tests updated.
5. **Duplicate due dates in the bills table**: far-future dates printed the formatted date twice. Far dates now read "In 30 days", with a unit test.
6. **CLI crashed on every command**: Typer 0.15 is incompatible with the unpinned Click 8.5. Click is pinned to 8.1.8 and the CLI works.
7. **Android date label** showed the raw ISO payday (`UNTIL 2026-11-06`); it now reads `UNTIL NOV 6, 2026`.

Build-environment issues (not product defects): the system JDK 21 segfaults even on `java -version`, and the system Gradle is 4.4. The build uses a project-local Temurin JDK 17 and Gradle 8.11.1 under `.tools/` (gitignored).

## Not verified / known limits

- No clean-machine install was performed; the environment already had Docker, Python and Node.
- Restore was not rehearsed, only backup creation.
- Cookies/CSRF were tested through the browser and the API suite, but not under HTTPS with production cookies.
- Android was verified on an emulator only, not a physical device; cleartext HTTP is development-only.
- No AI provider is enabled; the registry and status endpoints are present but intentionally inert.
- Location-based shopping support is not implemented in Phase 1 and no location permission is requested.
- No performance or load testing was performed.
