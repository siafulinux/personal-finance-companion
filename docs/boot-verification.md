# Reboot verification

The stack runs as systemd **user** units behind `pfc.target`, enabled and lingering, but a
reboot had never been performed. Until one is, "starts automatically after a power cycle"
is a claim, not a fact. This page is the procedure that turns it into evidence.

Tooling: [`scripts/boot-test`](../scripts/boot-test). It snapshots the known-good state
and later compares against it.

## What the test proves

| Claim | How it is checked |
| --- | --- |
| The stack starts without anyone logging in | `pfc.target` is `enabled`, `Linger=yes`, and the target is `active` after boot |
| Every service came back | `pfc-api`, `pfc-web`, `pfc-tls` all `active` |
| A reboot would not run stale units | Installed unit files are byte-identical to `deploy/systemd/` (`units.drift` = 0) |
| TLS still works, with verification on | `https://127.0.0.1:8443/` answers through the project CA — no `-k`, no trust override |
| The certificate did not expire or change | CA fingerprint, SANs and expiry match the baseline |
| The database is intact | Alembic revision and row counts for users, accounts, transactions, bills, occurrences, allocations and categories match |
| Auth still gates the API | An unauthenticated request returns `401` |
| The figures survived | Safe-to-Spend, total cash and ledger total match, read with a real session |

Volatile values (`run.at`, `run.uptime_s`, PID, restart counter) are printed as
informational and never fail the run.

## Procedure

### 1. Take the baseline

The snapshot is compared including the git revision, so take it **after** your last commit
and as the very last step before rebooting. Any commit or legitimate financial activity in
between will legitimately show up as a difference (that is the point — the run proves the
same code and the same data came back).

```bash
export PFC_BOOT_EMAIL='you@example.com'
read -r -s PFC_BOOT_PASSWORD && export PFC_BOOT_PASSWORD

scripts/boot-test snapshot      # writes logs/boot-test/pre-boot.txt
```

Use the same account for both runs. Without credentials the authenticated checks are
reported as `SKIP` and the verdict says so — it never claims them as passed. If the
baseline contains authenticated values and the `verify` run has no credentials, those
comparisons fail with "baseline has a value but no credentials were supplied" rather than
silently passing.

The snapshot contains no credentials and no amounts beyond the three figures above; the
session token exists only in a temporary cookie jar that is removed on exit.

### 2. Reboot

```bash
sudo systemctl reboot
```

Do not start the services by hand afterwards — that would defeat the test.

### 3. Verify

```bash
export PFC_BOOT_EMAIL='you@example.com'
read -r -s PFC_BOOT_PASSWORD && export PFC_BOOT_PASSWORD

scripts/boot-test verify        # exit 0 = pass, exit 1 = difference found
```

`verify` retries a failed connection up to three times, so a slow boot does not produce a
false failure. A `000` result means the probe never connected.

### 4. Keep the evidence

```bash
cp logs/boot-test/pre-boot.txt "logs/boot-test/post-boot-$(date +%Y%m%d-%H%M).txt"
```

`logs/` is git-ignored on purpose: row counts and balances are not committed.

## Reading a failure

| Symptom | Likely cause |
| --- | --- |
| `unit.active.*` not active | Docker/db not up yet; `pfc-api` waits then gives up. Check `journalctl --user -u pfc-api.service -n 80` |
| `unit.enabled.pfc.target` not `enabled` | `scripts/install-service` was never run, or the unit was disabled |
| `linger` not `yes` | User units cannot start at boot: `loginctl enable-linger "$USER"` |
| `http.* = 000` | TLS front or API down, or the firewall blocks 8443 |
| `http.health` not `200` but `health` works directly on 8010 | TLS front only: check `logs/tls.log` |
| `cert.chain` broken / fingerprint differs | The CA or server certificate was regenerated; re-run `scripts/export-ca` and rebuild the APK |
| `db.revision` differs | A migration ran (expected if you deployed one) — otherwise investigate |
| `db.rows.*` differ | Data changed, or the wrong database was restored |
| `data.*` differ with `auth.status=200` | A real discrepancy between the baseline and now |

## Status

- **Baseline captured:** 2026-11-05, commit at the time of the run, 38 comparisons, all
  matching, on a stack that had been up for ~1 day 21 hours (`logs/boot-test/pre-boot.txt`,
  git-ignored). Re-take it after any commit, as described above.
- **Reboot executed:** no. The procedure is prepared and the harness is self-tested (a
  deliberate one-value change is detected and exits non-zero); the boot itself has not
  happened, so automatic startup remains **unverified**.

Do not describe boot startup as working until a `verify` run has passed after an actual
reboot.
