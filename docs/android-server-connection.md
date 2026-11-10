# Android: connecting to your own server

The app ships with no fixed server. Whoever installs it points it at their own installation,
and can change that later without rebuilding anything.

---

## 1. Where to set it

**Settings → Server**.

| Control | Behaviour |
| --- | --- |
| Server address | The origin only — `192.168.1.100:8088` or `https://finance.example.com`. A bare host is assumed to be `https://`. |
| Test connection | Calls `GET /api/v1/server/info` on that address. Nothing is saved by testing. |
| Result | A **Reachable** pill with the server's name, version and API generation, or the reason it could not be reached. If the server still needs setup, the app says so and shows its web address. |
| Save server | Enabled **only after a successful test**, so a typo cannot strand the user on an address nothing answers at. |
| Current server | Shown above the field; the app also keeps up to five recently used servers as chips. |

The first launch after install defaults to `BuildConfig.API_BASE_URL`, which is the
developer address `https://10.0.2.2:8443/api/v1/` unless the build set it:

```bash
./gradlew assembleRelease -PpfcApiBaseUrl=https://finance.example.com
# or, equivalently for CI and scripts:
PFC_API_BASE_URL=https://finance.example.com ./gradlew assembleRelease
```

The Gradle property takes precedence over the environment variable, and both take
precedence over the emulator default. The value is normalised the way `ServerUrl` would
normalise it — a bare host gets `https://`, `/api/v1/` is added if missing — so an APK can
be handed to a user already pointed at their server. An unusable value fails the build.
Changing the address after install is still the expected first step on a real device or a
new emulator — no rebuild, no reinstall.

---

## 2. What counts as a valid address

`ServerUrl` (Kotlin, unit-tested) normalizes and validates before any request is built:

| Input | Result |
| --- | --- |
| `192.168.1.100:8088` | accepted → `http://192.168.1.100:8088/api/v1/` |
| `http://192.168.1.100:8088` | accepted (trusted LAN) |
| `http://localhost:8088` | accepted (loopback) |
| `https://finance.example.com` | accepted |
| `http://finance.example.com` | **rejected** — plain HTTP to a public host is never allowed |
| `finance.example.com/api/v1` | rejected — enter the origin; the app adds `/api/v1` |
| `https://user:pass@host` | rejected — credentials in a URL would be stored and displayed |
| `https://host/?x=1#y` | rejected — query strings and fragments are not part of an address |
| `ftp://host`, `host:99999` | rejected |

Plain HTTP is accepted only for addresses that cannot leave the local network: loopback,
`10/8`, `172.16/12`, `192.168/16`, link-local `169.254/16`, IPv6 unique-local `fc00::/7` and
link-local `fe80::/10`, `.local` / `.lan` / `.home.arpa`, and single-label LAN hostnames.

Why the policy lives in the app: Android's `network-security-config` can express "no
cleartext" or "cleartext", but not "cleartext to RFC1918 only" — its `<domain>` entries take
host names, not address ranges. Cleartext is therefore permitted at the platform level and
refused in code, before a request exists. HTTPS certificates are always verified, against the
system roots plus the project's own CA bundled as `res/raw/pfc_ca`; debug builds additionally
trust a user-installed CA for troubleshooting. **Certificate verification is never disabled.**

---

## 3. Sessions are per server

- The bearer token lives in `SecureTokenStore` (Android Keystore, AES/GCM) as an encrypted
  blob containing a map of *API base URL → token* (`TokenBook`).
- Saving a new server switches the address but does **not** import the previous server's
  token, so a token minted by one installation is never sent to another.
- Returning to an earlier server restores that server's token, so the user is not forced to
  sign in again.
- A single legacy token from a pre-0.3 build is adopted for the address it was used with, once.
- Signing out clears only the current server's token; the ledger stays on the server.

---

## 4. Connecting from an emulator

The emulator reaches the host at `10.0.2.2`.

- **Docker deployment on this machine:** enter `http://10.0.2.2:8088` (the published proxy
  port), test, save. This is plain HTTP, which is allowed because `10.0.2.2` is in `10/8`; the
  app shows the unencrypted-LAN warning on that screen.
- **Developer HTTPS front (`pfc-tls`, Phase 1.3):** `https://10.0.2.2:8443` still works and
  is the build default, verified by the bundled project CA.

Note on the stored AVD: `.tools/android-avd/pfc-api36` no longer parses (the emulator falls
back to an `arm` architecture and refuses to start). A fresh one from the installed image
boots:

```bash
ANDROID_AVD_HOME=$PWD/.tools/android-avd \
  .tools/android-sdk/cmdline-tools/19.0/bin/avdmanager create avd \
  -n pfc-verify -k "system-images;android-36;google_apis;x86_64" -d pixel_6
```

It runs without hardware acceleration on this machine, so give it several minutes to boot and
avoid scripted key bursts — a guest load average above 50 makes even the system UI ANR.

## 5. Connecting from a physical device

1. Build and install the debug APK:
   ```bash
   cd android && ./gradlew assembleDebug
   adb install -r app/build/outputs/apk/debug/app-debug.apk
   ```
   (or copy `app-debug.apk` to the phone and install it directly).
2. Put the phone on the same network as the server.
3. Settings → Server → enter the host's LAN address and port, e.g. `http://192.168.1.5:8088`.
4. **Test connection**, confirm the server name and version, then **Save server**.
5. Sign in, or complete onboarding if the account is new.

Plain HTTP on a trusted LAN needs no certificate on the phone. For `https://` with a domain,
the certificate must be publicly trusted; a LAN name using Caddy's internal CA needs that CA
installed on the device (`scripts/export-ca` produces it, `docs/remote-access.md` explains the
trade-off).

---

## 6. Tests

Run with `./gradlew testDebugUnitTest` (needs JDK 17 and the bundled SDK):

| Test | Covers |
| --- | --- |
| `ServerUrlTest` | normalization, https-by-default, HTTP restricted to local addresses, path/credential/query rejection, port validation, `displayAddress` |
| `TokenBookTest` | per-server keying, trailing-slash normalization, decode of unknown/corrupt blobs |
| `ServerConnectionViewModelTest` | test-then-save ordering, save disabled without a reachable server, unreachable and validation messaging, switching server keeps tokens separate |

Latest run on 2026-11-07: **53 unit tests, 0 failures**, and `assembleDebug` produced
`android/app/build/outputs/apk/debug/app-debug.apk` (version `0.3.0`, `versionCode` 3).
