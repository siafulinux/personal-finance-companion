# Backups: weekly routine, verification and restore

The database is the only place financial data lives. A dump that exists but does
not restore is worse than no dump at all, so every scheduled backup is proved by
restoring it before it is kept, and older dumps are pruned only after the new one
passes.

## The routine

`scripts/backup-routine` runs four steps, in this order:

1. **Dump** — `pfc backup` writes `backups/finance-<timestamp>.dump`. The CLI
   refuses to keep a dump with no table data, and deletes a partial file if
   `pg_dump` fails.
2. **Verify** — `pfc verify-backup` restores the dump into a throwaway database
   (`finance_verify_<timestamp>`), hashes every row of every public table in both
   the copy and production, compares the digests, and drops the scratch database.
   Row order does not affect the hash; column values do.
3. **Copy off-site** — the dump is written to a second destination and its
   SHA-256 is compared there before it is renamed into place. See
   [Off-site copies](#off-site-copies).
4. **Prune** — dumps beyond the retention count are deleted, newest first, then
   the off-site retention is applied.

Each step only runs if the previous one succeeded. A failed night therefore
leaves every older backup in place, and a dump that fails verification is moved
to `backups/rejected/<name>.unverified` instead of being mistaken for a good one.

## Off-site copies

A backup on the same disk as the database does not survive a disk failure, which
is the failure most likely to need it. The routine therefore copies each verified
dump to one of two destinations, configured in `.env`:

| Setting | Destination |
| --- | --- |
| `PFC_BACKUP_OFFSITE_DIR=/mnt/storage/pfc-backups` | a directory on another filesystem (external disk, NAS mount) |
| `PFC_BACKUP_OFFSITE_RSYNC=user@host:/srv/pfc-backups` | a remote host over ssh (needs key-based auth: the timer runs with `BatchMode=yes` and never prompts) |
| `PFC_BACKUP_OFFSITE_KEEP=12` | how many dumps to keep off-site (default: `PFC_BACKUP_KEEP`) |

Set one, not both. The copy is written as `.finance-<timestamp>.dump.part`, its
SHA-256 is compared with the local file, and only then is it renamed to its final
name. An interrupted or truncated copy therefore never appears in the off-site
directory as a usable backup; partials older than a day are removed on the next
run.

Three failures abort the run **before** anything is pruned:

- **The destination is on the same filesystem as `backups/`.** This is what an
  unmounted external disk looks like: `mkdir -p` silently creates the directory
  on the root filesystem. The routine compares device ids and refuses.
- **The copy cannot be written** (missing path, permissions, offline host).
- **The checksum at the destination does not match.**

If no destination is configured the routine still runs locally, logs a warning
that every dump shares a disk with the database, and prunes as before. That is
backward compatibility, not a recommendation.

`PFC_BACKUP_OFFSITE_ALLOW_SAME_DEVICE=1` overrides the filesystem check. It exists
for drills and tests; a copy on the same disk protects against nothing.

### A remote host instead of a disk

For a copy that survives theft, fire or a dead machine, send the dump to another
host. Set `PFC_BACKUP_OFFSITE_RSYNC` and use `PFC_BACKUP_OFFSITE_SSH_OPTS` for a
non-standard port, a dedicated key or a jump host:

```bash
PFC_BACKUP_OFFSITE_RSYNC=backup@host:/srv/pfc-backups
PFC_BACKUP_OFFSITE_SSH_OPTS="-p 2222 -i ~/.ssh/pfc_backup"
```

Requirements on the far side: `rsync`, `sha256sum`, and write access to the
directory. Authentication must be non-interactive — the routine runs with
`BatchMode=yes` and fails rather than prompting. Every network call is bounded by
`PFC_BACKUP_OFFSITE_TIMEOUT` (default 600 s) so a host that accepts the TCP
connection and then stalls cannot hang the unit until systemd's timeout.

The same guarantees apply as for the directory mode: the copy lands under a
`.finance-….dump.part` name, is checksummed on the far side, and is renamed only
on a match. A failed or unverifiable copy aborts before any pruning.

### Checking the destination without taking a backup

```bash
scripts/backup-routine --preflight
```

It reports reachability, whether `rsync` and `sha256sum` exist remotely, and
whether the directory is writable — without dumping, verifying or pruning. Run it
after any configuration change, and once after granting a new host access.

### Known blocker: the `vpsnetwork` host

`vpsnetwork` is **not** a working destination yet, and the routine is deliberately
not pointed at it:

- Its public address (`138.2.212.135`) does not answer on port 22 at all — ICMP
  and TCP both time out, so this is a firewall, not a slow host.
- Over Tailscale (`oracle-server`, `100.72.149.57`) the host is up, but it serves
  **Tailscale SSH in `check` mode**: the connection waits for an interactive
  browser approval (`https://login.tailscale.com/a/…`). A timer cannot satisfy
  that, and the check has to be repeated, so even a one-off approval is not a fix.

Either change the tailnet ACL for that host to `action: accept`, or run a normal
`sshd` on a spare port with a dedicated key and point `PFC_BACKUP_OFFSITE_SSH_OPTS`
at it. Then:

```bash
PFC_BACKUP_OFFSITE_RSYNC=ubuntu@100.72.149.57:/home/ubuntu/pfc-backups \
PFC_BACKUP_OFFSITE_SSH_OPTS="-p 2222 -i ~/.ssh/pfc_backup" \
  scripts/backup-routine --preflight
```

Until then the live destination stays `/mnt/storage/pfc-backups` (a separate
physical disk), which protects against disk failure but not against losing the
machine.

Verify an off-site copy the same way as a local one — the check does not care
where the file came from:

```bash
backend/.venv/bin/pfc verify-backup /mnt/storage/pfc-backups/finance-….dump
```

Run it by hand at any time:

```bash
scripts/backup-routine
```

Everything it prints is appended to `logs/backup.log` and to the journal.

## Schedule

`pfc-backup.timer` runs it every Sunday at 03:00 with up to 10 minutes of
randomised delay, and `Persistent=true` means a missed run happens after the next
boot instead of being skipped for a week.

```bash
systemctl --user list-timers pfc-backup.timer     # next and last run
systemctl --user start pfc-backup.service         # run now, same environment
journalctl --user -u pfc-backup.service -n 50     # what it did
```

Installed and enabled by `scripts/install-service`, alongside the API, web and TLS
units. Like those, the backup unit calls `~/.local/lib/pfc/pfc-run`, so it follows
the workspace pointer and survives moving the checkout.

## Retention

Default: keep the **8 newest** dumps (eight weeks). Change it per run:

```bash
PFC_BACKUP_KEEP=12 scripts/backup-routine
```

`PFC_BACKUP_DIR` overrides the dump directory, which is mainly useful for testing
the routine without touching real backups.

Only files matching `backups/finance-*.dump` are considered for pruning. Anything
in `backups/rejected/` is never pruned, so a failed verification stays available
for inspection until you delete it.

## Verification on demand

```bash
backend/.venv/bin/pfc verify-backup                       # newest dump
backend/.venv/bin/pfc verify-backup backups/finance-….dump # a specific one
```

Exit status is `0` only when every table's content matches production. `MISSING`
or `EXTRA` tables are reported and also count as failures.

To check the structural health of a dump without restoring it:

```bash
pg_restore --list backups/finance-….dump | grep -c 'TABLE DATA'   # must be > 0
```

## Restore drill

Verification answers "does this restore and match?". Restoring for real replaces
production data, so rehearse it deliberately:

```bash
./scripts/app restore backups/finance-….dump      # interactive confirmation
./scripts/app status                              # API and web healthy?
```

Before that, confirm the dump you are about to restore is the one that passed
verification — check the `logs/backup.log` line for that filename.

## What this routine does and does not cover

Covered: content equality of all public tables, schema revision (`alembic_version`
is compared as a table), refusal of empty dumps, retention, and a failure mode
that cannot prune good backups.

Not covered:

- **Off-site copies are configured, not enforced.** With no destination set the
  routine warns and continues locally; nothing checks that the configured disk is
  actually being rotated elsewhere. A copy on a second internal disk survives a
  disk failure but not theft, fire or a corrupted filesystem — a remote host is
  the stronger option and is only wired up if you set `PFC_BACKUP_OFFSITE_RSYNC`.
- **Encryption.** Dumps are plain `pg_dump` output containing real financial data.
  They are `chmod`-ed by the umask and excluded from git, but not encrypted at
  rest.
- **Indexes, constraints, sequences and ownership.** Verification hashes table
  contents; a restore missing an index would still pass.
- **Incremental or point-in-time recovery.** These are full nightly dumps only.
- **Cross-version restore.** A dump should be restored by the same PostgreSQL
  major version that produced it; this is not checked.

## Evidence from the last run

| Test | Result |
| --- | --- |
| `scripts/backup-routine` by hand | dump written (73.1 KiB, 19 tables), 19/19 tables content-identical, prune no-op, exit `0` |
| **Off-site copy to `/mnt/storage`** (separate device) | copied `finance-20261106-070011.dump`, SHA-256 `2468e28271a8…` matched at the destination, off-site retention reported 1 of 12, exit `0` |
| **Off-site file restores** — `pfc verify-backup /mnt/storage/pfc-backups/finance-20261106-070011.dump` | 19/19 tables content-identical to production, exit `0` |
| **Destination on the same filesystem** (`backups/offsite-test`) | `refusing a copy that is not off-site`, exit `1`, no partial file left, nothing pruned |
| **Destination that cannot be created** (`/proc/…`) | `FAIL off-site copy failed; nothing pruned`, exit `1` |
| **Off-site retention**, `PFC_BACKUP_OFFSITE_KEEP=2` with 4 seeded dumps in a temp directory | 3 oldest pruned, newest copied dump plus 1 older kept; a 2-day-old `.part` was removed, exit `0` |
| **Rsync mode against a real sshd** (throwaway sshd on `127.0.0.1:2222`, dedicated key, `PFC_BACKUP_OFFSITE_SSH_OPTS="-p 2222 -i …"`) | copied, remote `sha256sum` matched, renamed into place, no `.part` left, exit `0`; local and remote files `cmp`-identical |
| **Remote copy restores** — `pfc verify-backup /tmp/…/finance-….dump` | 19/19 tables content-identical, exit `0` |
| **Remote retention**, `PFC_BACKUP_OFFSITE_KEEP=2` with 3 seeded dumps | 3 oldest deleted over ssh, newest kept; a 2-day-old remote `.part` swept, exit `0` |
| **Remote unreachable** (wrong port, `KEEP=1`) | `FAIL off-site copy failed; nothing pruned`, exit `1`, local dump count unchanged |
| **`--preflight`** on a working destination | reachability, `rsync`/`sha256sum`, writability all `OK`, exit `0` |
| **`--preflight`** on `vpsnetwork` (public IP and Tailscale) | `cannot authenticate or connect`, exit `1`; the Tailscale attempt is cut off by `PFC_BACKUP_OFFSITE_TIMEOUT=15` instead of hanging |
| `systemctl --user start pfc-backup.service` | `Result=success`, `ExecMainStatus=0`, journal shows the off-site copy and retention |
| Retention with `PFC_BACKUP_KEEP=3` in a temporary directory holding 6 dumps | 3 oldest pruned, newest verified dump and the 2 next-newest kept, exit `0` |
| Database stopped, `PFC_BACKUP_KEEP=1` | `FAIL backup failed; nothing pruned`, exit `1`, dump count unchanged — nothing was deleted despite retention being 1 |
| `list-timers pfc-backup.timer` | `active`, next elapse Sun 2026-11-08 03:08 EST |

### Test collateral, 2026-11-06

One run of the routine was executed against the real `backups/` directory with
`PFC_BACKUP_KEEP=1` to check that a failed off-site copy blocks pruning; the copy
unexpectedly succeeded (`/tmp` is a separate tmpfs) so the run legitimately pruned
down to one local dump. Five older dumps were lost: `2026-11-02`,
`2026-11-03-090323` (the pre-data-loss dump) and three from `2026-11-05`.

No database data was affected — the live `finance` database is unchanged — and the
current data is covered by a verified dump on two filesystems. The lost files were
redundant snapshots of the same data. Retention and guard tests now use temporary
directories only (`PFC_BACKUP_DIR`), never the real one.
