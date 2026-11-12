# Docker deployment

A self-hosted Personal Finance Companion installation: one Compose project with its own
database, no dependency on a developer host, and nothing exposed except the reverse proxy.

Everything here was run on the machine that produced this document. Where a step was not
verified, it says so.

---

## 1. What runs

| Service | Image | Role | Port (host) |
| --- | --- | --- | --- |
| `db` | `postgres:17-alpine` | the only datastore, in the `db-data` volume | none — private to the stack |
| `api` | `pfc-api:2.0.0` | FastAPI + the financial engine; applies migrations on start | none — private |
| `worker` | `pfc-api:2.0.0` | `python -m app.worker`, the scheduled institution sync | none — private |
| `web` | `pfc-web:2.0.0` | the built React app, served by nginx | none — private |
| `caddy` | `caddy:2.8-alpine` | the only public entry point, and the only TLS terminator | `8088 → 80`, `8448 → 443` |

Only `caddy` publishes ports. PostgreSQL, the API and the web container publish nothing;
`docker compose ps` shows their ports without a host binding. The API is on a `backend`
bridge network, the web container on `edge`, and `caddy` joins both — which is why neither
half of the stack can reach the other's database or peers.

Why the image tag is `2.0.0` everywhere: `deploy/docker/compose.yaml` pins
`PFC_IMAGE_TAG`, and the release tag an image reports is stamped from it at build time.
Compose passes `PFC_RELEASE_TAG: v${PFC_IMAGE_TAG}` as a build argument, the API
`Dockerfile` bakes it into the image, and `/server/info` reads it back per request — so
the `0.6.3` image reports `v0.6.3` and there is no constant to bump or forget. A build
straight from `docker build` needs the argument explicitly:

```bash
docker build -f deploy/docker/Dockerfile.api \
  --build-arg PFC_RELEASE_TAG=v0.6.3 -t pfc-api:0.6.3 .
```

Omit it and the server reports `release_tag: null` — the honest answer for a build that is
not a release, rather than the tag of whatever release happened to be last.

Ports 8088/8448 were chosen because this host already runs services on 80/443. On a
dedicated machine use `PFC_HTTP_PORT=80` and `PFC_HTTPS_PORT=443`.

---

## 2. Requirements

- Docker Engine with the Compose v2 plugin (`docker compose version`).
- About 1 GB of RAM for the stack, and disk for the database volume.
- Two random secrets: `POSTGRES_PASSWORD` and `SECRET_KEY` (`openssl rand -base64 36`).

Nothing else: no Python, no Node, no virtualenv, no host database, no Caddy on the host.

---

## 3. Install

```bash
git clone <this repository> personal-finance && cd personal-finance/deploy/docker
cp .env.example .env
$EDITOR .env                     # set POSTGRES_PASSWORD and SECRET_KEY
docker compose up -d --build
```

`--build` is needed the first time. After that, `docker compose up -d` reuses the images.

Check it:

```bash
docker compose ps                          # every service "healthy"
curl -s http://127.0.0.1:8088/api/v1/health
curl -s http://127.0.0.1:8088/api/v1/server/info
```

`.env` is the whole configuration surface. It is git-ignored by design; never commit it.

### First start

The stack starts even before anything is configured. Visit `http://<server>:8088/` and the
web app shows the first-run wizard, because the database has no accounts:

1. Server name, your name, your email, a password (10+ characters).
2. Whether other people may register later (closed by default).
3. Optional public address, if phones will reach this server through a domain or tunnel.

The wizard creates the owner account, marks the installation set up, and signs you in.
`POST /server/setup` refuses a second attempt with **409**, and until setup finishes
`POST /auth/register` is refused with **403** (`OPEN_REGISTRATION_UNTIL_SETUP=false` is set
for the Docker stack), so a stranger who finds the URL cannot claim the installation.

If something goes wrong before setup, the state is recoverable: stop the stack, remove the
`db-data` volume, start again. That discards the database, so only do it before you have
data you care about.

---

## 4. Day-to-day commands

Run these from `deploy/docker/`.

| Task | Command |
| --- | --- |
| Start | `docker compose up -d` |
| Stop (keeps data) | `docker compose stop` |
| Stop and remove containers (keeps volumes) | `docker compose down` |
| Restart one service | `docker compose restart api` |
| Status + health | `docker compose ps` |
| Logs (follow) | `docker compose logs -f api worker caddy` |
| Apply migrations | `docker compose exec api alembic upgrade head` |
| Health check | `curl -fsS http://127.0.0.1:8088/api/v1/health` |
| Update to a newer checkout | `git pull && docker compose up -d --build` |

Migrations run automatically in the `api` container's entrypoint
(`deploy/docker/api-entrypoint.sh` waits for PostgreSQL, then `alembic upgrade head`). The
worker sets `RUN_MIGRATIONS=false`, so two containers never race on Alembic.

### Backups

Backups are unchanged by this deployment: the existing `scripts/backup-routine` and
`pfc-backup.timer` still operate on the host database container. For the Docker stack, dump
the volume's database with:

```bash
docker compose exec -T db pg_dump -U finance -d finance -Fc > finance-$(date +%Y%m%d-%H%M%S).dump
docker compose exec -T db pg_restore --list < finance-20260101-030000.dump | grep -c 'TABLE DATA'
```

The second command is the guard the project already uses: a dump with zero `TABLE DATA`
entries restores to nothing and must be discarded. Restore with
`docker compose exec -T db pg_restore -U finance -d finance --clean --if-exists --no-owner < dump`.

---

## 5. Moving an existing installation into Docker

If you already ran this application without Docker, the Compose stack starts with an empty
`db-data` volume — it does not see the host database. Copy it across with the script, which
refuses to guess when both sides hold data:

```bash
# target stack must already be running
scripts/docker-migrate-existing
```

It dumps the source container (default `pfc-db`, database `finance`), verifies the dump
contains table data, refuses a target that already has accounts unless `FORCE=1`, restores
with `--clean --if-exists`, brings the schema to head, restarts `api`/`worker`, then compares
row counts for `users`, `financial_accounts`, `transactions`, `bills`, `bill_occurrences`,
`budgets` and `categories`. A mismatch exits non-zero so you do not point clients at a
half-copied ledger.

Control the endpoints with `SOURCE_CONTAINER`, `SOURCE_DB`, `SOURCE_USER`, `PROJECT` and
`ENV_FILE`.

**Verified** on 2026-11-07 against a throwaway stack (`pfc-migrate`, ports 8109/8509):
26 tables of data copied, all seven counts equal (users 8, financial_accounts 16,
transactions 97, bills 12, bill_occurrences 141, budgets 4, categories 153), the second run
refused with exit 1, and the stack and volume were then removed. The production Docker stack
on this machine was **not** migrated onto: it keeps its own owner account, and the non-Docker
database remains untouched.

---

## 6. Restart behaviour

- Every service sets `restart: unless-stopped`, so a crashed process is restarted and a
  reboot brings the stack back as long as Docker itself is enabled at boot
  (`systemctl is-enabled docker`).
- `api` depends on `db` being *healthy*; `worker` depends on `api` being healthy; `caddy`
  depends on `api` and `web` being healthy. PostgreSQL's first start therefore completes
  before migrations run.
- Health checks: `pg_isready` for `db`; `/api/v1/health` for `api`; `/healthz` for `web`; the
  Caddy admin API for `caddy`; and a heartbeat file for `worker`, which has no HTTP port and
  writes `/tmp/pfc-worker-heartbeat` after every sync pass.
- Graceful shutdown: the worker handles SIGTERM/SIGINT by finishing the current pass, and the
  API is stopped by uvicorn's own signal handling. Docker's default stop timeout is enough
  for both.

**Verified:** `docker restart pfc-db-1` returned to healthy and the row count was unchanged
(1 user); `docker restart pfc-api-1` returned to healthy with `/api/v1/health` answering
`{"status":"ok","environment":"lan"}`.

**Not verified:** a host reboot. The restart policy is configured, but this machine was not
rebooted for this phase, so boot-time startup of the Docker stack remains untested.

---

## 7. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `api` restarts in a loop, log says `set POSTGRES_PASSWORD` | `.env` is missing or was not read; run from `deploy/docker/` or pass `--env-file`. |
| `api` unhealthy, log says `database not reachable within 60s` | `db` is still initialising, or the password in `.env` no longer matches the existing volume. Passwords are only applied on first initialisation. |
| Web page loads, API calls 502 | `api` is not healthy yet; `docker compose logs api`. |
| `https://host:8448` refuses the connection | Caddy is serving `:80` only (`PFC_SITE_ADDRESS=:80`). HTTPS needs a site address, see `docs/remote-access.md`. |
| Changes to `web/` do not appear | The web image is a static build: `docker compose up -d --build web`. |
| Setup wizard does not appear | The database already has accounts. Sign in instead; if the owner account is lost, restore a backup. |
| `docker compose` says the project name is already in use | Another install on this host uses `pfc`; set a distinct `COMPOSE_PROJECT_NAME` and ports in that `.env`. |

Logs are capped at 10 MB × 3 files per service, so a long-running stack cannot fill the disk
with container output.

---

## 8. Known limits

- **HTTPS is not working on this machine yet.** The stack publishes 8448, but the site address
  is `:80`, so no certificate is served. See `docs/remote-access.md` for the supported paths;
  none of them were exercised in this phase.
- **No host-reboot test.** Restart policies and health dependencies are configured, and
  container-level restarts were tested.
- **The worker exists but has nothing to do on a fresh install.** It syncs due provider links
  and does nothing when there are none; it is not a general job queue.
- Container images are built locally. There is no published registry, so "pull the images"
  means "clone and `--build`".
