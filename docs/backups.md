# Backups: weekly routine, verification and restore

The database is the only place financial data lives. A dump that exists but does
not restore is worse than no dump at all, so every scheduled backup is proved by
restoring it before it is kept, and older dumps are pruned only after the new one
passes.

## The routine

`scripts/backup-routine` runs three steps, in this order:

1. **Dump** — `pfc backup` writes `backups/finance-<timestamp>.dump`. The CLI
   refuses to keep a dump with no table data, and deletes a partial file if
   `pg_dump` fails.
2. **Verify** — `pfc verify-backup` restores the dump into a throwaway database
   (`finance_verify_<timestamp>`), hashes every row of every public table in both
   the copy and production, compares the digests, and drops the scratch database.
   Row order does not affect the hash; column values do.
3. **Prune** — dumps beyond the retention count are deleted, newest first.

Steps 2 and 3 only run if the previous step succeeded. A failed night therefore
leaves every older backup in place, and a dump that fails verification is moved
to `backups/rejected/<name>.unverified` instead of being mistaken for a good one.

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

- **Off-site copies.** Every dump lives on the same disk as the database. A disk
  failure loses both. An external copy (another machine, or an object bucket) is
  the obvious next step and is not implemented here.
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
| Retention with `PFC_BACKUP_KEEP=3` in a temporary directory holding 6 dumps | 3 oldest pruned, newest verified dump and the 2 next-newest kept, exit `0` |
| Database stopped, `PFC_BACKUP_KEEP=1` | `FAIL backup failed; nothing pruned`, exit `1`, dump count unchanged at 4 — nothing was deleted despite retention being 1 |
| `systemctl --user start pfc-backup.service` | `Result=success`, `ExecMainStatus=0`, new dump verified in the journal |
| `list-timers pfc-backup.timer` | `active`, next elapse Sun 2026-11-08 03:04 EST |
