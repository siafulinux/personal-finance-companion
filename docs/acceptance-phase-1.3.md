# Phase 1.3 acceptance report — recovery, service supervision, LAN TLS, session hardening

Date: 2026-11-05. Environment: Linux, Python 3.12.13, PostgreSQL 17.11 (Docker
`pfc-db`), Node 24.15.0, Caddy 2.6.2, Temurin JDK 17.0.21, Gradle 8.11.1, Android
SDK 33/x86_64 emulator `emulator-5554` (AVD `pfc-api36`).

Scope: finish the reliability, security and boot-ability items that Phase 1.2 left out —
supervised services, practical HTTPS on the LAN, secure token storage with real
revocation, and a re-verified recovery gate. No feature area was rebuilt and no database
recovery was repeated.

## Status of the recovered baseline

The recovery work below was completed in the previous session and is **not** redone here;
the values are re-confirmed, not re-executed.

| Item | State |
| --- | --- |
| Backend virtualenv | Rebuilt at the current workspace path; `backend/.venv/bin/python` is 3.12.13 and imports the package in place. |
| Database | `finance` restored from the 2026-11-03 dump; container `pfc-db` healthy. |
| Alembic revision | `fced71fed827` restored, now advanced to `b9cb28b8b1a5` by this phase's migration. |
| Schema drift | None: `alembic upgrade head` applies only the new `revoked_tokens` table. |
| Test fixture defect | `backend/tests/test_imports.py` no longer hardcodes November dates; the bill window is now relative to `today`. |
| Git | Initialised after the recovery report; baseline commit `390a695`, this phase committed as `11352ae`. |
| Existing accounts | Untouched. `demo@example.com` and the Phase 1.2 validation account still exist; Phase 1.3 testing used its own account. |

## Changes implemented in this phase

### 1. Service supervision (`deploy/systemd/`)

The API previously ran as a `Type=oneshot` wrapper, so a crash left the service dead and a
stale PID file behind.

| Unit | Role |
| --- | --- |
| `pfc.target` | One handle for the whole stack; `AllowIsolate`, wanted by `default.target`. |
| `pfc-api.service` | `ExecStartPre` waits for the database, then runs `alembic upgrade head`; serves with `--workers 1`. |
| `pfc-web.service` | Vite dev server, ordered after the API. |
| `pfc-tls.service` | Caddy TLS front, ordered after the API and web. |

Behaviour that is now explicit rather than accidental: `Restart=on-failure` with
`RestartSec=3`, `StartLimitIntervalSec=60`/`StartLimitBurst=5` so a permanently broken
listener cannot spin forever, `KillSignal=SIGTERM` with `TimeoutStopSec`, output appended
to `logs/`, and `EnvironmentFile=-.env`. `scripts/wait-for-db` exists so startup ordering
does not depend on the container happening to be ready.

`--workers 1` is deliberate: the login limiter is an in-process structure, so adding
workers would silently multiply the allowance. That trade-off is documented in the unit
file itself.

### 2. Practical LAN HTTPS (`deploy/Caddyfile`, `scripts/gen-tls`, `scripts/export-ca`)

- One project CA (`certs/pfc-ca.crt`, 10-year validity) signs one server certificate whose
  SANs cover `localhost`, `127.0.0.1`, `10.0.2.2` (emulator → host) and the LAN address, so
  a client connecting by any of those names gets a certificate that matches the name it
  used. This replaced the earlier per-address self-signed certificate, which only carried
  `127.0.0.1` and therefore failed hostname verification from the emulator.
- Caddy serves HTTPS on **8443** (port 443 belongs to the machine-wide Caddy instance),
  proxies `/api/*` to the API and everything else to Vite, and adds HSTS, `nosniff`,
  `DENY`, `Referrer-Policy` and strips `Server`.
- Certificate verification is never disabled. The Android app bundles the CA as
  `res/raw/pfc_ca.crt` and trusts it through `res/xml/network_security_config.xml`, which
  also forbids cleartext except for loopback (`adb reverse` debugging) and allows a
  user-installed CA in debug builds only.

One defect found and fixed while checking the trust path: `scripts/export-ca` still
copied **Caddy's built-in local root** into the APK, while the served certificate is signed
by the project CA. Running it would have replaced the bundled certificate with one that
cannot validate the server. It now exports `certs/pfc-ca.crt`, refuses to copy unless
`openssl verify` confirms that CA signs `certs/pfc-server.crt`, and verifies as
`certs/pfc-server.crt: OK`. `docs/android.md` and `.env.example` now state the single
`PFC_LAN_IP` knob that `scripts/gen-tls` actually reads.

### 3. Session handling (`backend`, `android`)

- **Revocation is real.** `POST /auth/logout` records the token's `jti` in a new
  `revoked_tokens` table (migration `b9cb28b8b1a5`); `get_current_user` rejects revoked
  IDs. Previously logout only cleared cookies, so a copied token stayed valid for the full
  12-hour TTL. Revoking twice is idempotent, and signing out one device does not affect
  another.
- **Android token storage.** The bearer token moved from plain `SharedPreferences` into
  `SecureTokenStore`, which encrypts it with a Keystore-held key (`AES/GCM`, random IV per
  write). Server URL and theme stay in DataStore; the token does not.
- **Throttling is distinguishable.** A tripped login limiter now raises `RateLimitError`
  → HTTP `429` instead of `401`. Previously Android rendered `401` as "Your session
  expired. Sign in again.", so a throttle looked like a broken session. The correct
  message is now shown. Covered by
  `test_repeated_failed_logins_are_throttled_with_429`.

## Tests actually executed

All results below are from this session, after the last code change.

| Check | Command | Result |
| --- | --- | --- |
| Backend suite | `cd backend && .venv/bin/python -m pytest` | **87 passed** in 45.11s |
| Web suite | `cd web && npm test -- --run` | **9 passed** (2 files) |
| Android unit tests | `./gradlew :app:testDebugUnitTest --rerun-tasks` | **31 passed**, 0 failures (`FinanceRepositoryTest` 7, `TransactionDraftTest` 7, `ImportViewModelTest` 5, `TransactionFormViewModelTest` 5, `FormatTest` 5, `LedgerViewModelTest` 2) |

The backend total grew from 81 by six session tests (`test_sessions.py`) covering logout
revocation, per-device isolation, idempotent revocation, unknown-user tokens and the 429
throttle.

Android must be run with a JDK 17; the system `java` is 25 and Gradle 8.11.1 fails on it
with a bare `25.0.5` error. Use `JAVA_HOME=../.tools/jdk17`.

### Supervision and failure recovery (live, not simulated)

| Test | Observed |
| --- | --- |
| `systemctl --user kill -s SIGKILL pfc-api` | Restarted in ~5s, `NRestarts=1`, `Result=success`, `GET /health` → `200` |
| `systemctl --user stop pfc-api` | `Result=success`, exit by SIGTERM, port 8010 released |
| `systemctl --user restart pfc.target` | All three services active; API `200`, TLS `200`, and an existing session still authenticated |
| Unit drift | Installed units under `~/.config/systemd/user/` are byte-identical to `deploy/systemd/`; the files are static and carry no workspace path |

### Path independence and relocation (live, not simulated)

The Phase 1.2 wrapper hard-coded the workspace in `WorkingDirectory=` and broke outright when
the tree moved during recovery. The units now contain no project path at all. Each
`ExecStart` calls `~/.local/lib/pfc/pfc-run`, which resolves the workspace through
`~/.config/pfc/workspace` and loads `.env` itself.

| Test | Observed |
| --- | --- |
| `./scripts/install-service` | Launcher at `~/.local/lib/pfc/pfc-run`; pointer set; all three units plus target `active`, none failed |
| Units reference the workspace | `grep -rn '/home/\|@ROOT@' deploy/systemd deploy/bin` → no matches |
| `scripts/relocate /tmp/pfc-relocated-workspace` (pointer retargeted, **no reinstall**) | Stack restarted and healthy; `pfc-run where` resolved to the real path; units byte-identical before and after |
| Stale pointer (symlink to a deleted directory) | `pfc-api.service` failed fast with `pfc-run: workspace pointer is stale: … -> /nonexistent/… (run scripts/relocate from the new location)`, exit `78/CONFIG`, no partial start |
| Recovery | `scripts/relocate` re-pointed the symlink; API, web and TLS back `active`, HTTPS health `ok` |
| Authenticated request over TLS after relocation | Login → `200`, `GET /api/v1/accounts` → `200`, `GET /api/v1/safe-to-spend` → `200`, `/dashboard` → `200` |

Service output is appended to `logs/{api,web,tls}.log` in whichever directory the pointer
resolves to; start/stop and early failures remain in the journal.

### Authentication probes (live service, HTTPS through Caddy)

| Probe | Result |
| --- | --- |
| Nine wrong passwords for one address | `401` ×8, then `429` with "Too many sign-in attempts. Try again in a minute." |
| Session cookie flags | `HttpOnly`, `SameSite=lax`, `Secure`, 12-hour lifetime |
| Tampered/absent session | `401` |
| Logout then reuse token | `401` (automated test) |
| Second device after first logs out | Still `200` (automated test) |

## Android on the emulator

A genuinely new account (`phase13.android@example.com`) was created **through the app UI**
after clearing only the app's local data; the restored accounts were untouched.
Onboarding, entry and verification were all driven through the UI:

| Step | Evidence |
| --- | --- |
| First-run login | `artifacts/p13-01-login.png` |
| Registration form | `p13-02-register.png`, `p13-03-register-filled.png` |
| Onboarding (income, payday, buffer, opening account) | `p13-04-after-register.png`, `p13-05-onboarding-filled.png` |
| Dashboard after onboarding | `p13-06-dashboard.png` — Safe-to-Spend `$3,950.00` (`$4,200` − `$250` buffer) |
| Empty ledger | `p13-07-ledger-empty.png` |
| Add-transaction form | `p13-08-add-form.png` |
| Save confirmation | `p13-09-after-save.png` — "Transaction saved."; server agreed at `$3,904.50` |
| Bill matching from Android | `p13-10-bill-match.png` — "Saved. Matched the City Power bill." |
| Bills / budgets / Shopping Check | `p13-11-bills.png`, `p13-12-budgets.png`, `p13-13-shopping-check.png` |
| Cold restart | `p13-14-relaunch.png` — session and data still present |
| After the supervision, 429 and TLS work | `p13-15-after-supervision.png` — same Safe-to-Spend, available and buffer, read through the supervised TLS front |

Bill matching was exercised end to end without an Android-side algorithm: a `City Power`
`$120` bill due Nov 6 was created on the server, paid from the Android form, auto-matched
(confidence above the auto threshold), and its next due date advanced to Dec 6.

Secure storage was checked on the device: no JWT string appears in the app's preference
file, only ciphertext, and the session survived a cold start.

Budgets showed a transient "cannot reach the server" once while the API was being
restarted for the 429 change; reloading after the restart succeeded. That was a restart
window, not a defect.

## Cross-platform consistency

The same account was read through the web origin (`https://127.0.0.1:8443`, the origin the
SPA uses) and compared with what the Android dashboard displayed:

| Value | Android UI | Web origin / API |
| --- | --- | --- |
| Safe-to-Spend | `$3,784.50` | `3784.50` |
| Available | `$4,034.50` | `4034.50` |
| Buffer | `−$250.00` | `250.00` |
| Horizon | Until Nov 13, 2026 | `horizon_end 2026-11-13` |
| Budget | "overspent by 45.50" | `total_spent 45.50`, `total_remaining −45.50` |
| Transactions | 2 rows | `City Power November $120.00`, `Grocery run $45.50` |

Both clients call the same endpoints and neither computes balances locally, so agreement
here is expected — the point of the check was that it still holds after the TLS and
session changes.

The report is deliberately precise about one thing: the web **UI** was not rendered in the
agent's browser during this phase. The bundled Chromium does not trust the project CA, and
adding it to the desktop trust store is a user-level decision, not something to do
silently. The comparison above uses the exact same-origin HTTP surface the SPA reads, and
the SPA itself (plus its `/src/main.tsx` module) serves `200` over TLS. A rendered
side-by-side was last performed in Phase 1.2 (see `docs/acceptance-phase-1.2.md`).

The onboarding-created budget is a bare month container (`seed_budget: false` is sent by
both web and Android), so the `$45.50` purchase legitimately shows as negative remaining
and the dashboard flags it. That is correct arithmetic for an unallocated budget, not a
regression.

## Boot startup

Configured but **not boot-verified**:

- `pfc.target` is `enabled` and appears in `default.target`'s `Wants`.
- `loginctl` reports `Linger=yes`, so user units are allowed to start without a login.
- The installed unit files match the repository copies.

No reboot was performed — this is the user's workstation and a reboot was not authorised.
The last boot (2026-11-03) predates these units, so "starts after a power cycle" remains
unproven.

A repeatable harness now closes the gap: `scripts/boot-test snapshot` records the good
state (unit enablement, unit-file drift, certificate fingerprint/SANs/expiry, schema
revision, row counts, HTTP with certificate verification, and authenticated Safe-to-Spend,
cash and ledger totals), and `scripts/boot-test verify` diffs against it after the reboot
and exits non-zero on any difference. A baseline was captured at commit `4b09b96` and
matches on all 38 comparisons; the harness was self-tested against a deliberately altered
value to confirm it fails rather than passing silently. Procedure and failure guide:
[docs/boot-verification.md](boot-verification.md).

## Security review

| Area | Finding |
| --- | --- |
| Cookies / CORS / CSRF | `COOKIE_SECURE=true` and CORS restricted to the HTTPS origins. CSRF still required for cookie-authenticated writes; the TLS front is same-origin for the SPA, so no wildcard origin is needed. |
| Network exposure | API (`8010`) and web (`5183`) bind to loopback only. The only non-loopback listener is Caddy on `:8443`, which terminates TLS and re-checks nothing else. |
| Certificate handling | Verification stays on in both clients; the CA is pinned rather than all user CAs. Cleartext is limited to loopback. |
| Rate limiting | Per-process, keyed by client address and e-mail, 8 attempts/minute. Real client addresses survive the proxy because uvicorn runs with `--proxy-headers --forwarded-allow-ips 127.0.0.1` and Caddy supplies `X-Forwarded-For`. |
| Tokens | Argon2id passwords; JWT with `jti`; revocation checked on every request; TTL 12h. |
| Logging | Credentials and tokens are never logged; sizes/amounts are not written to the access log. |

## Remaining limitations and risks

1. **Boot startup unverified** (see above).
2. **The limiter is single-process.** It is honest only because the unit pins
   `--workers 1`. A second instance, or a reverse proxy in front of two API processes,
   would double the allowance. Fixing it properly needs shared state (Redis or a database
   counter).
3. **`/auth/register` is not throttled.** Sign-up flooding is limited only by the trust in
   the LAN.
4. **Caddy listens on `*:8443`**, so it is reachable from every interface, including the
   Tailscale address on this host, not only the trusted LAN. Binding to
   `127.0.0.1` + the LAN address would tighten this. The host firewall could not be
   inspected without root, so the effective exposure is unknown.
5. **Web access is HTTPS-only now.** Because of `Secure` cookies and the CORS list,
   `http://127.0.0.1:5183` will accept a login that the browser then discards. Desktop
   browsers must trust `certs/pfc-ca.crt` (documented in the README). This is a workflow
   change from Phase 1.2, not a bug.
6. **The CA certificate is committed** at `android/app/src/main/res/raw/pfc_ca.crt` so a
   clean clone builds a working APK. The CA private key never leaves `certs/` (ignored).
   Regenerating the CA means re-running `scripts/gen-tls` and rebuilding the APK.
7. **No physical device was tested.** All Android evidence is emulator-only.
8. **Under-allocated budget UX**: an unallocated month reports "overspent" for any spend.
   Unchanged from Phase 1.2 and left alone deliberately.

## Reproducing this

```bash
# Services
./scripts/install-service            # installs launcher + static units, points ~/.config/pfc/workspace, enables pfc.target
./scripts/relocate                   # after moving the checkout: re-points the symlink, restarts
systemctl --user restart pfc.target

# TLS material (regenerates CA + multi-SAN certificate, exports the CA into the APK)
scripts/gen-tls
scripts/export-ca

# Tests
cd backend && .venv/bin/python -m pytest
cd web && npm test -- --run
cd android && JAVA_HOME=../.tools/jdk17 PATH=../.tools/jdk17/bin:$PATH ./gradlew :app:testDebugUnitTest
```
