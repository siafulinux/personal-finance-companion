# Acceptance — Phase 2: Dockerised self-hosted deployment and app connectivity

Date: 2026-11-07. Everything below was run in this workspace on this machine. Claims that were
not verified are listed as unverified, not softened.

---

## 1. What was implemented

**Backend**

- `GET /api/v1/server/info` — public, read-only connection facts (app name, server name,
  version, API generation, API/web URLs, health, registration state, setup state).
- First-run setup: `POST /server/setup` creates the owner account, names the server, records
  the registration policy, and signs the owner in. It returns **409** while any account
  exists, and registration is refused (**403**) before setup when
  `OPEN_REGISTRATION_UNTIL_SETUP=false`.
- `GET`/`PATCH /server/settings` — session required; changes require the administrator.
- `POST /server/pairing` / `POST /server/pair` — 10-minute, single-use, hashed pairing code
  carrying the server address. It contains no credential.
- `app/worker.py` — the scheduled sync loop (`sync_due_links`), with graceful SIGTERM and a
  heartbeat file for its health check. It wraps the existing engine; no new financial logic.
- `app/version.py` — one source for `APP_VERSION = "2.0.0"` and `API_VERSION = 1`.
- Migration `a7804f0fa670` (additive): `server_settings`, `pairing_tokens`.
- 20 new tests in `backend/tests/test_server_setup.py`.

**Deployment** (`deploy/docker/`)

- `compose.yaml` with five services, two networks, three volumes, health checks, ordering,
  `restart: unless-stopped`, log rotation, dropped capabilities and `no-new-privileges`.
- `Dockerfile.api` (single image for API and worker, unprivileged uid 10001, entrypoint waits
  for PostgreSQL then runs `alembic upgrade head`), `Dockerfile.web` (Vite build → nginx with
  SPA fallback and `no-store` on `index.html`), `Caddyfile`, `nginx.conf`, `.env.example`.
- `scripts/docker-fresh-install-test` — isolated-stack proof of the first-run path.
- `scripts/docker-migrate-existing` — verified copy of an existing non-Docker database into a
  running stack.

**Web**

- `SetupPage` (first-run wizard, shown while `setup_required`) and `ServerPage` (server name,
  registration policy, public address, connection details, pairing code), wired into the
  existing shell, router, API client and icons.

**Android 0.3.0**

- Server connection on the sign-in screen and in Settings: address field, **Test connection**
  against `/server/info`, server name/version/API shown on success, **Save server** enabled
  only after a successful test, current server display, five recent servers.
- `ServerUrl` policy: https by default, plain HTTP only for loopback/RFC1918/link-local/ULA/
  `.local`/`.lan`/`.home.arpa`/single-label hosts, rejecting credentials, query strings,
  fragments and paths.
- `TokenBook` + `SecureTokenStore`: one Keystore-encrypted bearer token **per server**, so
  switching addresses never sends a token to the wrong installation; legacy single-token
  installs are migrated once.
- 22 new unit tests (`ServerUrlTest`, `TokenBookTest`, `ServerConnectionViewModelTest`).

---

## 2. Docker services and images

| Service | Image | State at report time |
| --- | --- | --- |
| `db` | `postgres:17-alpine` | Up, healthy |
| `api` | `pfc-api:2.0.0` | Up, healthy |
| `worker` | `pfc-api:2.0.0` | Up, healthy |
| `web` | `pfc-web:2.0.0` | Up, healthy |
| `caddy` | `caddy:2.8-alpine` | Up, healthy |

Compose project `pfc`; container names `pfc-api-1`, `pfc-web-1`, `pfc-worker-1`, `pfc-db-1`,
`pfc-caddy-1`. Images are built locally from this tree (no registry is published).

## 3. Health checks

| Service | Check | Observed |
| --- | --- | --- |
| `db` | `pg_isready` | healthy |
| `api` | `GET /api/v1/health` | healthy; body `{"status":"ok","environment":"lan"}` |
| `web` | `GET /healthz` | healthy |
| `worker` | heartbeat file newer than 900 s | healthy |
| `caddy` | admin API `/config/` | healthy |

## 4. Ports

Published (only the proxy): `0.0.0.0:8088 → 80/tcp`, `0.0.0.0:8448 → 443/tcp`.

Private (no host binding): PostgreSQL `5432`, API `8000`, web `80`. `docker compose ps` shows
their ports without a host address, and the API/database are on the `backend` bridge that no
other service publishes.

## 5. Volumes

`pfc_db-data` (PostgreSQL data), `pfc_caddy-data` (certificates/state),
`pfc_caddy-config`. `alembic_version` in the running stack: `a7804f0fa670`.

## 6. Server discovery endpoint

`GET /api/v1/server/info`, captured live:

```json
{"app_name":"Personal Finance Companion","server_name":"Lakeside Finance","version":"2.0.0",
 "api_version":1,"min_client_api_version":1,"api_base_url":"http://127.0.0.1:8088/api/v1",
 "web_url":"http://127.0.0.1:8088","status":"ok","registration_enabled":false,
 "setup_required":false}
```

Reached through the LAN address it reports the LAN address
(`http://192.168.1.5:8088`), so the answer is derived from the request rather than from an
internal Docker hostname. Full contract: `docs/server-configuration.md`.

## 7. Android server configuration

Verified on an emulator (API 36, x86_64, this project's AVD):

1. Fresh install → sign-in screen → **Server settings**.
2. Entered `http://10.0.2.2:8088` (the host as the emulator sees it) and tapped
   **Test connection**.
3. The app displayed **Reachable · Lakeside Finance v2.0.0**.
4. Server side confirms the same request through the proxy:
   `GET /api/v1/server/info` → `200`, `User-Agent: okhttp/4.12.0`, `Host: 10.0.2.2:8088`.

Not verified on the emulator: signing in against the Docker stack (no credential was created
for that installation in this session). Authentication against a deployed stack is proven at
the API level — see §11 — and Android sign-in was verified against the development server in
Phase 1.

The emulator was unstable under machine load: two system ANRs (Digital Wellbeing, System UI)
and one input-dispatch ANR on the app were recorded while the guest load average was 51 and
CPU pressure 91 %. After the load fell to 13, the same flow completed without an app-side
error, and the ANR trace showed an undelivered `MotionEvent`, not a blocked main thread.

## 8. First-run setup

`scripts/docker-fresh-install-test` starts a second stack (`pfc-fresh`, ports 8099/8499, its
own volumes and `.env`), then removes it. Latest run — **20 checks, all PASS**:

| # | Check | Result |
| --- | --- | --- |
| 1 | registration refused before setup | 403 |
| 2 | `setup_required` reported | true |
| 3 | public info leaks no secret | true |
| 4 | setup accepted | 201 |
| 5 | wizard signs the owner in | true |
| 6 | server name applied | "Fresh Install Test" |
| 7 | advertised web URL is the request's address | true |
| 8 | second setup refused | 409 |
| 9 | `setup_required` false afterwards | true |
| 10 | registration refused after setup | 403 |
| 11 | owner is admin | true |
| 12 | `/server/settings` without a session | 401 |
| 13 | pairing code minted | 201 |
| 14 | code TTL | 10 minutes |
| 15 | first redemption | 200 |
| 16 | code carries no credential | true |
| 17 | second redemption refused | 409 |
| 18 | login with the owner account | 200 |
| 19 | authenticated `GET /dashboard` | 200 |
| 20 | throwaway database is independent (1 user) | true |

The production financial database was never used for this test.

## 9. LAN connectivity

- `curl http://192.168.1.5:8088/api/v1/server/info` → 200 with `web_url
  http://192.168.1.5:8088`, so the proxy is bound on the LAN interface, not loopback.
- `http://127.0.0.1:8088/` served the React app (`200 text/html`) and rendered the sign-in page
  in a browser, including the expected form fields, with no console errors observed.
- The Android emulator reached the same stack through `10.0.2.2:8088` (§7).

Not exercised: a second physical device on the LAN. The LAN tests above were issued from this
host to its own LAN address.

## 10. Remote HTTPS

**Not configured, not verified.** The stack publishes 8448, but `PFC_SITE_ADDRESS=:80`, so
Caddy serves no certificate and `https://127.0.0.1:8448/api/v1/server/info` fails to connect
(curl exit 35). No domain, DNS record or public certificate was set up.

`docs/remote-access.md` documents the exact procedure (domain, ports 80/443,
`ENVIRONMENT=production`, `COOKIE_SECURE=true`, `TRUSTED_HOSTS`, verification with
`curl -I` and `openssl s_client`) and states that it is unverified. Cloudflare Tunnel and
Tailscale are documented as options and were not configured.

## 11. Test results (fresh runs)

| Suite | Command | Result |
| --- | --- | --- |
| Backend | `cd backend && .venv/bin/python -m pytest -q` | **154 passed**, exit 0 |
| Web | `cd web && npm test` | **11 passed** in 2 files, exit 0 |
| Web types | `cd web && npx tsc --noEmit` | clean, exit 0 |
| Android unit | `cd android && ./gradlew testDebugUnitTest --rerun-tasks` | **53 tests, 0 failures, 0 skipped**, 3m01s |
| Android build | `./gradlew assembleDebug` | BUILD SUCCESSFUL |
| Fresh install | `scripts/docker-fresh-install-test` | 20/20 PASS |
| Migration copy | `scripts/docker-migrate-existing` against a scratch stack | 7/7 table counts equal |

The Android run was forced with `--rerun-tasks` because Gradle reported `UP-TO-DATE` on the
first attempt — a cached result is not evidence.

Regression scope: no existing assertion was changed or removed for this phase. The new
endpoints are additive and the existing suites pass unchanged.

## 12. Migration and persistence

- Schema in the running stack is at `a7804f0fa670`; migrations applied automatically by the
  API entrypoint on start.
- `docker restart pfc-db-1` → healthy, data intact (`users = 1`).
- `docker restart pfc-api-1` → healthy, `/api/v1/health` answering.
- Copying an existing installation: `scripts/docker-migrate-existing` was run against a
  throwaway stack and the **existing development database** (read-only source). It copied 26
  tables of data and matched every compared count — users 8, financial_accounts 16,
  transactions 97, bills 12, bill_occurrences 141, budgets 4, categories 153 — then refused a
  second run without `FORCE=1`. The throwaway stack and volume were removed afterwards.
- The existing non-Docker database is untouched (still 8 users / 97 transactions), as are the
  backup schedule, destinations and retention.

## 13. Remaining limitations

1. **No HTTPS on this machine.** 8448 is published but nothing serves TLS. Do not describe
   this deployment as secure over the internet.
2. **Host reboot untested.** `restart: unless-stopped` and the health dependency order are
   configured; only container-level restarts were exercised.
3. **The Docker stack is a separate, fresh install**, not a copy of the existing ledger. The
   migration script exists and was proven, but was deliberately not applied to the production
   stack (it holds its own owner account created during verification).
4. **Android → Docker sign-in not exercised**; connection test was. Authentication on a
   deployed stack is proven by the fresh-install run.
5. **Emulator reliability:** the guest ANRed under host load; the flow succeeded once load
   dropped. Physical-device testing was not performed.
6. **Images are local.** "Pull the images" means clone and `docker compose up -d --build`.
7. **Web polish:** the sign-in page still offers "Create your ledger" when registration is
   closed; the API correctly answers 403, but the link is misleading.
8. **Login/setup/pair rate limiting is per process**, unchanged from earlier phases. The API
   still runs a single uvicorn process inside the container.
9. **Pairing has no QR renderer**; the web page shows the code and URL, which is what the
   contract returns.

## 14. Commands

From `deploy/docker/`:

```bash
docker compose up -d --build          # start / rebuild after a source change
docker compose ps                     # status + health
docker compose logs -f api worker caddy
docker compose restart api worker
docker compose down                   # stop, keep the volumes
docker compose exec api alembic upgrade head
curl -fsS http://127.0.0.1:8088/api/v1/health
curl -fsS http://127.0.0.1:8088/api/v1/server/info
```

From the repository root:

```bash
scripts/docker-fresh-install-test     # prove the first-run path on an isolated stack
scripts/docker-migrate-existing       # copy an existing non-Docker database in
```

## 15. Addresses to enter in the Android app

| Client | Address |
| --- | --- |
| Phone or tablet on the same Wi-Fi as this machine | `http://192.168.1.5:8088` |
| Emulator on this machine | `http://10.0.2.2:8088` |
| Another host on the LAN | `http://192.168.1.5:8088` (subject to the firewall) |

Enter it under **Server settings** on the sign-in screen (or **Settings → Server** after
sign-in), tap **Test connection**, confirm the name `Lakeside Finance` and version `2.0.0`,
then **Save server**.

The matching APK is `personal-finance-companion-0.3.0-debug.apk` (version `0.3.0`,
`versionCode` 3), also at `/opt/lampp/htdocs/downloads/`.
