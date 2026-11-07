# Server configuration and discovery

Each installation is independent: its own database, its own owner account, its own address.
Clients that know only a URL need a small, safe way to learn what they are talking to and
whether it is ready. That is `GET /api/v1/server/info`.

---

## 1. `GET /api/v1/server/info` (public, read-only)

No session, no CSRF token, no cookies required. It exposes installation facts only — never a
database URL, secret, provider token, or account data.

```json
{
  "app_name": "Personal Finance Companion",
  "server_name": "Lakeside Finance",
  "version": "2.0.0",
  "api_version": 1,
  "min_client_api_version": 1,
  "api_base_url": "http://192.168.1.5:8088/api/v1",
  "web_url": "http://192.168.1.5:8088",
  "status": "ok",
  "registration_enabled": false,
  "setup_required": false
}
```

Captured from the live deployment on 2026-11-07.

| Field | Meaning |
| --- | --- |
| `app_name` | The product name, identical for every install. |
| `server_name` | What the owner called *this* server; set in the wizard, editable later. |
| `version` | Product version (`backend/app/version.py`). |
| `api_version` / `min_client_api_version` | Contract generation. A client whose own version is lower than `min_client_api_version` should refuse to connect rather than guess. |
| `api_base_url` / `web_url` | The addresses a client should use. |
| `status` | `ok` while the API can reach its database. |
| `registration_enabled` | Whether `POST /auth/register` is open right now. |
| `setup_required` | True only while the installation has no accounts at all. |

The APK uses exactly these fields: `test connection` calls this endpoint and shows the server
name, version and web URL before the user is allowed to save the address.

### How the advertised address is derived

1. If the owner set a public address (wizard or `PATCH /server/settings`), that wins.
2. Otherwise the request's own scheme and `Host` header are used, so a phone that reached
   `http://192.168.1.5:8088` is told `http://192.168.1.5:8088`.
3. `PUBLIC_BASE_URL` in the environment is the fallback when the derived host is an internal
   one (`api`, `web`, `localhost`, `127.0.0.1`).

The internal compose hostname is therefore never handed to a client — "you are talking to
`api:8000`" is exactly the misleading answer this rule exists to prevent.

---

## 2. Who may register

| State | `OPEN_REGISTRATION_UNTIL_SETUP` | Result |
| --- | --- | --- |
| no accounts (fresh) | `true` (local development) | registration open, no wizard needed |
| no accounts (fresh) | `false` (Docker deployment) | registration **403**, only `POST /server/setup` creates the first account |
| set up, owner chose closed | ignored | registration **403** |
| set up, owner chose open | ignored | registration allowed |

The wizard records the owner in `server_settings.admin_user_id`. Only that account may change
server settings (`PATCH /server/settings`), and `GET /server/settings` requires a session.

`POST /server/setup` is refused with **409** once any account exists, so the wizard cannot be
replayed to mint a second administrator.

Both `/server/setup` and `/server/pair` are rate limited per client address (10 attempts per
minute), like login. The limiter is per process, which matches the project's existing login
guard.

---

## 3. Device pairing

`POST /server/pairing` (authenticated) mints a short-lived code that carries this server's
address, so a phone does not need the URL typed by hand:

```json
{
  "token": "…",
  "expires_at": "2026-11-07T12:10:00Z",
  "ttl_minutes": 10,
  "pairing_url": "http://192.168.1.5:8088/pair?token=…",
  "connection": { "app_name": "…", "server_name": "…", "web_url": "…" }
}
```

- Valid for **10 minutes**, single use: the first `POST /server/pair` consumes it, a second
  returns **409**.
- It contains **no credential**. Redeeming it returns only the same public facts as
  `/server/info`; signing in still requires the user's password. Storing the token hashed
  (`sha256`) in `pairing_tokens` is what lets that claim be checked rather than trusted.
- The web app shows the code and its address under **Server**; the QR/link is a convenience,
  not an authentication path.

---

## 4. Environment variables

Set in `deploy/docker/.env` (see `.env.example`). Only the ones that change behaviour are
listed; secrets are never logged.

| Variable | Default | Effect |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | required | database password; applied only on first initialisation |
| `SECRET_KEY` | required | signs sessions; 32+ characters required in `production` |
| `POSTGRES_USER` / `POSTGRES_DB` | `finance` | database role and name |
| `ENVIRONMENT` | `lan` | `lan` or `production`. `production` refuses to start without secure cookies and a strong secret. |
| `COOKIE_SECURE` | `false` | must be `true` under HTTPS; a Secure cookie is never sent over HTTP |
| `PFC_HTTP_PORT` / `PFC_HTTPS_PORT` | `8088` / `8448` | host ports published by Caddy |
| `PFC_SITE_ADDRESS` | `:80` | what Caddy serves: `:80`, `finance.example.com`, `https://pfc.lan` |
| `PUBLIC_BASE_URL` | empty | forces the advertised address (tunnels, NAT) |
| `TRUSTED_HOSTS` | `*` | Host header allowlist; `*` is required when a LAN is reached by IP |
| `CORS_ORIGINS` | empty | comma-separated extra origins; the Docker proxy serves web and API from one origin, so this is normally unnecessary |
| `ACCESS_TOKEN_TTL_MINUTES` | `720` | session lifetime |
| `OPEN_REGISTRATION_UNTIL_SETUP` | `false` in compose | see the table above |
| `WORKER_SYNC_INTERVAL_SECONDS` | `300` | how often the worker looks for due syncs |
| `PROVIDER_ENCRYPTION_KEY` | empty | encrypts provider tokens at rest; set it before linking an institution |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` / `PLAID_ENVIRONMENT` | empty / `sandbox` | optional real institution support |

---

## 5. Determining the address to give clients

- **Same network:** the host's LAN address, e.g. `http://192.168.1.5:8088` — this is what
  `/server/info` reports when a phone reaches it that way.
- **Find it on the server:** `ip -4 addr show scope global` (ignore `docker0`, `br-*` and
  `tailscale0`), or read it from the web app's **Server** page after setup.
- **Domain:** set `PFC_SITE_ADDRESS` to the domain and point DNS at the host; see
  `docs/remote-access.md`.
- **Tunnel:** keep `PFC_SITE_ADDRESS=:80` and set `PUBLIC_BASE_URL` to the tunnel's HTTPS
  address, then give phones that address.

Never hand out `localhost` or `10.0.2.2` except from an emulator on the same machine: they
mean "this device", not "this server".

---

## 6. Security notes

- `/server/info` is public on purpose; treat it as a fingerprint, not a secret. It is checked
  in the fresh-install test that no key containing `password`, `secret_key` or `postgres`
  appears in its response.
- `/server/settings` requires a session; `PATCH` additionally requires the administrator.
- Pairing codes are hashed, expire in 10 minutes and are single use.
- Registration is closed by default on a Docker install until the owner completes setup.
- The setup and pairing endpoints are throttled to 10 attempts/minute per client address.
- Nothing here weakens the existing session model: bearer tokens for the app, HttpOnly
  cookies plus CSRF for the browser.
