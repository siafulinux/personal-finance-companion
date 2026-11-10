# Remote access: LAN, domains and tunnels

Three deployment modes, in increasing order of exposure. Each is a different security
posture; do not describe one as another.

| Mode | Address a phone uses | Transport | Status on this machine |
| --- | --- | --- | --- |
| Local development | `http://127.0.0.1:5183` (web), `http://127.0.0.1:8010` (API) | loopback only | working (Phase 1.3 stack) |
| Trusted LAN (Docker default) | `http://192.168.1.5:8088` | plain HTTP | **verified** |
| Public HTTPS | `https://finance.example.com` | TLS via Caddy | **not configured or verified** |
| Private remote access | tunnel address | TLS at the tunnel edge | **not configured or verified** |

---

## 1. Trusted LAN over HTTP (the Docker default)

`PFC_SITE_ADDRESS=:80` makes Caddy serve plain HTTP on the published host port (8088 here).
That is the right default for a machine on your own network, and it is what was tested.

What is safe about it, and what is not:

- Traffic on the LAN is **unencrypted**. Anyone who can capture LAN traffic can read the
  session token. This mode is for a network you control.
- The API and web app share one origin through Caddy, so the browser needs no CORS exception
  and cookies stay first-party. `COOKIE_SECURE=false` because a Secure cookie is never sent
  over HTTP — setting it to `true` without TLS would silently break sign-in.
- `TRUSTED_HOSTS=*` is required to reach the server by IP address. Set the real domain there
  once you have one.
- The API (`8000`) and the web container (`80`) publish no host port at all, and only Caddy
  is reachable from the network. PostgreSQL is the one exception, and only on the loopback
  address (`127.0.0.1:${PFC_DB_PORT:-5433}` in the shipped compose file) so `psql` and
  `pg_dump` work on the host itself; it is never bound to a LAN interface. Confirm with
  `docker compose ps` and `ss -ltnp`.
- Authentication, CSRF and rate limiting are unchanged from the HTTPS deployment.

### Firewall

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8088 proto tcp
```

Allow the port from your subnet, not from the world. Do not expose 5432, 8000 or 2019.

---

## 2. Public HTTPS with a domain

This is the supported path to secure remote access. It has **not** been exercised on this
machine — no certificate has been obtained, so no HTTPS claim is made for this deployment.

Outline of the procedure:

1. **DNS.** Point an A/AAAA record (`finance.example.com`) at your public address. Caddy
   requires the name to resolve to the host before it can validate a certificate.
2. **Ports.** Forward TCP 80 and 443 from the router to the host (Caddy needs 80 for the
   HTTP-01 challenge or TLS-ALPN).
3. **Configure `deploy/docker/.env`:**

   ```ini
   PFC_SITE_ADDRESS=finance.example.com
   PFC_HTTP_PORT=80
   PFC_HTTPS_PORT=443
   PUBLIC_BASE_URL=https://finance.example.com
   TRUSTED_HOSTS=finance.example.com
   ENVIRONMENT=production
   COOKIE_SECURE=true
   ```

4. **Restart and watch Caddy obtain the certificate:**

   ```bash
   docker compose up -d
   docker compose logs -f caddy        # look for "certificate obtained successfully"
   ```

5. **Verify before telling anyone it works:**

   ```bash
   curl -fsSI https://finance.example.com/api/v1/server/info | head -5
   echo | openssl s_client -servername finance.example.com -connect finance.example.com:443 2>/dev/null \
     | openssl x509 -noout -issuer -dates -subject
   ```
   An issuer of a public CA (Let's Encrypt), a matching `subject`, and an unexpired `notAfter`
   are the evidence. A 200 over HTTP is not.

`ENVIRONMENT=production` makes the API refuse to start with a short `SECRET_KEY` or with
`COOKIE_SECURE=false`, so a half-configured public install fails loudly instead of serving
insecure sessions.

Caddy's data volume keeps the certificate across restarts, so renewals are automatic.

---

## 3. LAN HTTPS with an internal CA

Useful when you want TLS on a network with no public DNS, e.g. `https://pfc.lan`.

```ini
PFC_SITE_ADDRESS=https://pfc.lan
PUBLIC_BASE_URL=https://pfc.lan
TRUSTED_HOSTS=pfc.lan
COOKIE_SECURE=true
```

Caddy issues from its internal CA. Every device must trust that CA — `docker compose exec
caddy cat /data/caddy/pki/authorities/local/root.crt` — or its browser and the Android app
will reject the certificate. The Android app already trusts the project's own CA
(`res/raw/pfc_ca`, from `scripts/export-ca`); that is the Phase 1.3 certificate, not
necessarily the one this stack generates, so check the fingerprint before installing.

Do not work around trust problems by disabling verification, and do not add a "trust all"
network-security-config to the app. The APK deliberately has none.

---

## 4. Private remote access without opening ports

Both options terminate TLS outside your router, so keep `PFC_SITE_ADDRESS=:80` inside and tell
clients the tunnel's HTTPS address:

### Cloudflare Tunnel

```bash
cloudflared tunnel create pfc
cloudflared tunnel route dns pfc finance.example.com
cloudflared tunnel run --url http://localhost:8088 pfc
```

Then set `PUBLIC_BASE_URL=https://finance.example.com`, `TRUSTED_HOSTS=finance.example.com`,
`COOKIE_SECURE=true`, `ENVIRONMENT=production`, and restart the stack. Cloudflare terminates
TLS; nothing is published on your router.

### Tailscale

Install Tailscale on the host and on the phone, keep the stack on `127.0.0.1:8088`, and give
the phone the tailnet address (`http://100.x.y.z:8088`). Because the tailnet is private, this
is closer to the LAN case than to a public deployment — it is still plain HTTP, so it relies on
WireGuard's encryption rather than TLS.

Neither option was configured or tested in this phase; both are documented paths, not verified
features.

---

## 5. Security checklist before exposing anything

- [ ] `SECRET_KEY` is 32+ random characters, unique to this install.
- [ ] `POSTGRES_PASSWORD` was set **before** the first start (it is not applied to an existing
      volume).
- [ ] `ENVIRONMENT=production` and `COOKIE_SECURE=true` with real TLS.
- [ ] `TRUSTED_HOSTS` lists the real hostname, not `*`.
- [ ] Only the proxy port is reachable from outside: `ss -ltnp | grep -E '8088|8448|5432|8000'`.
- [ ] `/server/info` exposes no secrets (the fresh-install test asserts this).
- [ ] The owner account exists, the wizard returns 409, and registration is closed unless you
      want it open.
- [ ] A verified backup exists before the first public exposure (see `docs/backups.md`).
- [ ] Certificates are verified, never bypassed, on the phone and in the browser.

## 6. What is not verified

- No public certificate has been obtained; `https://…:8448` currently refuses connections
  because the site address is `:80`.
- No tunnel or tailnet was configured.
- Host reboot recovery of the Docker stack was not tested (`docs/acceptance-phase-2-docker.md`).
