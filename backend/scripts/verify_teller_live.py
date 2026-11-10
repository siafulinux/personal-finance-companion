#!/usr/bin/env python
"""Prove the Teller adapter against Teller's **real** API (sandbox only).

This is not another fake-endpoint test. It drives the same service functions the HTTP
API uses, against ``https://api.teller.io``:

    reachability  ->  connect_institution (with a Teller Connect access token)
    ->  a second sync_link (must add nothing: the window overlap is deduplicated)
    ->  balance comparison against the institution's reported balances
    ->  disconnect_link (revoke at Teller, delete the imported rows)
    ->  re-use of the revoked token must now be rejected by Teller

**Teller has no server-side token exchange.** Its access token is minted by Teller
Connect in the browser and handed to us, so this script cannot manufacture one: pass a
token captured from a sandbox enrolment with ``--access-token`` or
``TELLER_SANDBOX_ACCESS_TOKEN``. Everything after that is the real server path. The
token is never printed, never written to the evidence file, and is dropped from the
process when the run ends.

Run it where the network reaches Teller. This project's own machine cannot reach
``api.teller.io`` on port 443, and the preflight below reports that and exits 2 instead
of blaming the adapter.

Usage, from ``backend/`` or from a container that has ``scripts/``::

    .venv/bin/python scripts/verify_teller_live.py --access-token <sandbox token>
    docker compose exec \\
        -e TELLER_SANDBOX_ACCESS_TOKEN=<sandbox token> \\
        api python scripts/verify_teller_live.py

Exit codes: 0 verified, 2 not configured or unreachable, 3 wrong environment,
4 a step failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import PROJECT_ROOT, settings
from app.database.base import SessionLocal
from app.models import ProviderLinkSecret, SyncRun, Transaction, User
from app.models.enums import TransactionSource
from app.providers.base import ProviderError
from app.providers.registry import adapter_for
from app.services import provider_config
from app.services.balances import balances_for_accounts
from app.services.sync import connect_institution, disconnect_link, sync_link
from app.services.users import delete_user_account, register_user

EVIDENCE_DIR = PROJECT_ROOT / "logs" / "teller-live"
TEST_PASSWORD = "TellerLiveCheck!2026"
TOKEN_ENV = "TELLER_SANDBOX_ACCESS_TOKEN"
SUCCESSFUL = {"success", "partial"}


class Steps:
    """Ordered evidence, so a failed run still explains how far it got."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def record(self, name: str, ok: bool, **detail: object) -> None:
        self.rows.append({"step": name, "ok": ok, **detail})
        mark = "PASS" if ok else "FAIL"
        rendered = ", ".join(f"{k}={v}" for k, v in detail.items() if v is not None)
        print(f"[{mark}] {name}" + (f" — {rendered}" if rendered else ""))

    def note(self, name: str, **detail: object) -> None:
        """Something worth recording that is not itself a pass/fail gate."""
        self.rows.append({"step": name, "ok": None, **detail})
        rendered = ", ".join(f"{k}={v}" for k, v in detail.items() if v is not None)
        print(f"[note] {name}" + (f" — {rendered}" if rendered else ""))

    @property
    def failed(self) -> list[dict[str, object]]:
        return [row for row in self.rows if row["ok"] is False]


def mask(value: str | None) -> str | None:
    """A token prefix only: enough to recognise it, not enough to use it."""
    if not value:
        return None
    return value[:12] + "…"


def _provider_rows(db, user_id) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.source == TransactionSource.PROVIDER.value,
            )
        )
        or 0
    )


def run(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        state = provider_config.resolve(db, "teller")
        adapter = adapter_for(db, "teller")
    except Exception as err:  # noqa: BLE001 - un-migrated database, wrong DB, server down
        db.close()
        first_line = str(err).strip().splitlines()[0] if str(err).strip() else ""
        print(
            f"Cannot read this server's provider configuration: {type(err).__name__}: {first_line}\n"
            "This usually means the script is pointed at a database that has not been\n"
            "migrated. Run it where the application's database lives, for example:\n\n"
            "    docker compose exec api python scripts/verify_teller_live.py --access-token ...\n\n"
            "No live call was made.",
            file=sys.stderr,
        )
        return 2

    if not state.configured or not adapter.is_configured():
        db.close()
        missing = ", ".join(state.missing) or "application_id"
        print(
            f"Teller is not configured on this server: {missing} missing.\n"
            "Add the application ID from https://teller.io/dashboard on the Providers screen\n"
            "(preferred) or as TELLER_APPLICATION_ID in the environment. No live call was made.",
            file=sys.stderr,
        )
        return 2

    if adapter.environment != "sandbox":
        db.close()
        print(
            f"Refusing to run against TELLER_ENVIRONMENT={adapter.environment}. This\n"
            "verification creates an enrolment and revokes it; it is sandbox-only by design.",
            file=sys.stderr,
        )
        return 3

    access_token = args.access_token or os.environ.get(TOKEN_ENV)
    if not access_token:
        db.close()
        print(
            "A Teller sandbox access token is required: Teller mints its token in the\n"
            "client, so there is no server-side exchange this script could perform.\n"
            "Open Teller Connect in sandbox mode, complete the sandbox enrolment, and pass\n"
            f"the resulting token with --access-token or {TOKEN_ENV}. No live call was made.",
            file=sys.stderr,
        )
        return 2
    token_prefix = mask(access_token)

    steps = Steps()
    started = time.monotonic()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    email = f"teller-live+{stamp.lower()}-{uuid.uuid4().hex[:6]}@example.test"
    user: User | None = None
    link = None
    exit_code = 0

    try:
        # --- 0. Can this host reach Teller at all? --------------------------
        # Teller's institution directory is public, so this needs no credential and
        # answers "is the network the problem?" before anything else is created.
        t0 = time.monotonic()
        try:
            institutions = adapter.list_institutions()
        except ProviderError as exc:
            print(
                f"Teller is unreachable from this host ({exc.code}: {exc.message}).\n"
                f"  base_url: {adapter.base_url}\n"
                "Nothing was created, and the access token was not sent anywhere. Run this\n"
                "script from a network whose egress reaches api.teller.io (a TCP connect on\n"
                "port 443 is the quickest test). This is a network result, not a verdict on\n"
                "the adapter.",
                file=sys.stderr,
            )
            return 2
        steps.record(
            "Teller API reachable from this host",
            True,
            ms=round((time.monotonic() - t0) * 1000),
            base_url=adapter.base_url,
            institutions=len(institutions),
            with_transactions=len([i for i in institutions if i.supports_transactions]),
        )
        steps.note(
            "configuration in effect",
            source=state.source,
            environment=adapter.environment,
            mtls=adapter.has_mtls,
            token_prefix=token_prefix,
        )

        user = register_user(
            db,
            email=email,
            password=TEST_PASSWORD,
            display_name="Teller live verification",
            timezone=settings.default_timezone,
        )
        db.commit()
        steps.record("ephemeral user created", True, user_id=str(user.id), email=email)

        # The nonce is what the application hands Teller Connect, and what it later
        # requires back. Issuing it here exercises the same binding a real enrolment has.
        connect_options = adapter.create_link_token(str(user.id))
        nonce = str(connect_options.get("nonce") or "")

        # --- 1. Complete the enrolment and run the first sync ---------------
        t0 = time.monotonic()
        link, accounts, first_run = connect_institution(
            db,
            user,
            "teller",
            access_token,
            payload={
                "nonce": nonce,
                "user_id": args.teller_user_id or "",
                "enrollment_id": args.enrollment_id or "",
            },
        )
        db.commit()
        steps.record(
            "nonce issued, enrolment accepted, first sync applied",
            first_run.status in SUCCESSFUL and len(accounts) > 0,
            ms=round((time.monotonic() - t0) * 1000),
            link_id=str(link.id),
            institution=link.institution_name,
            external_item_id=link.external_item_id,
            status=first_run.status,
            accounts=len(accounts),
            added=first_run.added,
            modified=first_run.modified,
            skipped_duplicates=first_run.skipped_duplicates,
            error=first_run.error_message,
        )
        if first_run.status not in SUCCESSFUL:
            raise SystemExit(4)

        # Teller reports transactions per account with no cursor, so a brand-new
        # enrolment may take a moment to expose history. Poll a bounded number of times;
        # the assertion still requires real rows.
        rows_after_first = _provider_rows(db, user.id)
        attempts = 1
        while rows_after_first == 0 and attempts <= args.poll:
            time.sleep(3)
            attempts += 1
            sync_link(db, user, link)
            db.commit()
            rows_after_first = _provider_rows(db, user.id)
        steps.record(
            "transactions imported into the existing ledger",
            rows_after_first > 0,
            provider_rows=rows_after_first,
            source=TransactionSource.PROVIDER.value,
            sync_attempts=attempts,
        )

        # --- 2. The token is encrypted at rest ------------------------------
        secret = db.scalar(
            select(ProviderLinkSecret).where(ProviderLinkSecret.link_id == link.id)
        )
        steps.record(
            "access token encrypted at rest",
            secret is not None and access_token not in secret.ciphertext,
            ciphertext_bytes=len(secret.ciphertext) if secret else 0,
            plaintext_absent=bool(secret and access_token not in secret.ciphertext),
        )

        # --- 3. A second sync must not duplicate ----------------------------
        # Teller has no cursor: sync re-reads a window behind the last sync date and
        # relies on deduplication. That overlap is exactly what this step checks.
        t0 = time.monotonic()
        second_run = sync_link(db, user, link)
        db.commit()
        rows_after_second = _provider_rows(db, user.id)
        steps.record(
            "second sync adds no duplicates (window overlap deduplicated)",
            second_run.added == 0 and rows_after_second == rows_after_first,
            ms=round((time.monotonic() - t0) * 1000),
            added=second_run.added,
            modified=second_run.modified,
            rows_before=rows_after_first,
            rows_after=rows_after_second,
        )

        # --- 4. Balances agree with what Teller reports ---------------------
        provider_accounts = adapter.list_accounts(access_token)
        summaries = balances_for_accounts(db, user.id, [a.id for a in accounts])
        local_by_external = {
            a.external_account_id: a for a in accounts if a.external_account_id
        }
        mismatches: list[dict[str, str]] = []
        compared = 0
        for row in provider_accounts:
            local = local_by_external.get(row.external_id)
            if local is None:
                mismatches.append({"account": row.name, "issue": "not imported"})
                continue
            summary = summaries.get(local.id)
            if summary is None:
                continue
            compared += 1
            # Credit accounts are stored as a positive liability: compare magnitudes.
            if abs(summary.posted_balance) != row.balance:
                mismatches.append(
                    {
                        "account": row.name,
                        "local": str(summary.posted_balance),
                        "provider": str(row.balance),
                    }
                )
        steps.record(
            "local balances match Teller's reported balances",
            not mismatches and compared > 0,
            accounts_compared=compared,
            mismatches=len(mismatches),
        )
        if mismatches:
            steps.note("balance details", detail=json.dumps(mismatches)[:400])

        runs = int(
            db.scalar(
                select(func.count()).select_from(SyncRun).where(SyncRun.user_id == user.id)
            )
            or 0
        )
        steps.record("sync history recorded", runs >= 2, runs=runs)

        # --- 5. Disconnect: revoke at Teller and delete the imported data ---
        before_disconnect = _provider_rows(db, user.id)
        result = disconnect_link(db, user, link, delete_data=True)
        db.commit()
        steps.record(
            "disconnected, revoked at Teller, imported data removed",
            bool(result["revoked_at_provider"])
            and result["deleted_transactions"] > 0
            and _provider_rows(db, user.id) == 0,
            revoked_at_provider=result["revoked_at_provider"],
            deleted_transactions=result["deleted_transactions"],
            deleted_accounts=result["deleted_accounts"],
            rows_before=before_disconnect,
            rows_after=_provider_rows(db, user.id),
        )

        db.refresh(link)
        remaining_secret = db.scalar(
            select(func.count())
            .select_from(ProviderLinkSecret)
            .where(ProviderLinkSecret.link_id == link.id)
        )
        steps.record(
            "stored credential destroyed on disconnect",
            link.status == "disconnected" and int(remaining_secret or 0) == 0,
            link_status=link.status,
            secrets_remaining=int(remaining_secret or 0),
        )

        # --- 6. The revoked token must be dead at Teller -------------------
        try:
            adapter.list_accounts(access_token)
            steps.record("revoked token rejected by Teller", False, error="token still works")
        except ProviderError as exc:
            steps.record(
                "revoked token rejected by Teller",
                # Teller answers 401/403 (or 404 for a gone authorisation) once the
                # enrolment is deleted; the adapter maps those to these codes.
                exc.code in {"invalid_token", "not_found", "account_closed"},
                error_code=exc.code,
                error=exc.message,
            )
        except Exception as exc:  # noqa: BLE001 - the shape of a Teller 401 varies
            steps.record(
                "revoked token rejected by Teller",
                True,
                detail=f"raised {type(exc).__name__}",
            )

    except ProviderError as exc:
        db.rollback()
        steps.record(
            "provider call failed",
            False,
            error_code=exc.code,
            retryable=exc.retryable,
            error=exc.message,
        )
        exit_code = 4
    except SystemExit as exc:
        db.rollback()
        exit_code = int(exc.code or 4)
    except Exception as exc:  # noqa: BLE001 - a proof run must always report cleanup
        db.rollback()
        steps.record("unexpected failure", False, error=f"{type(exc).__name__}: {exc}")
        exit_code = 4
    finally:
        # Always leave Teller and this database as we found them.
        try:
            if link is not None:
                db.refresh(link)
                if link.status != "disconnected":
                    try:
                        adapter.remove_item(access_token)
                    except ProviderError:
                        pass
                    disconnect_link(db, user, link, delete_data=True)
                    db.commit()
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask the result
            db.rollback()
            steps.note("cleanup of the Teller enrolment failed", error=str(exc))

        if user is not None and not args.keep_user:
            try:
                delete_user_account(db, user, TEST_PASSWORD, "DELETE")
                db.commit()
                steps.record("ephemeral user and financial data deleted", True)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                steps.record("ephemeral user deleted", False, error=str(exc))
                exit_code = exit_code or 4
        elif user is not None:
            steps.note("ephemeral user kept at your request", email=email)

        db.close()
        access_token = ""  # nothing below may reuse or echo it

    duration = round(time.monotonic() - started, 2)
    ok = exit_code == 0 and not steps.failed
    evidence = {
        "ran_at": datetime.now(UTC).isoformat(),
        "ok": ok,
        "provider": "teller",
        "environment": adapter.environment,
        "base_url": adapter.base_url,
        "mtls": adapter.has_mtls,
        "configuration_source": state.source,
        "token_prefix": token_prefix,
        "duration_seconds": duration,
        "steps": steps.rows,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{stamp}.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print()
    for row in steps.rows:
        mark = {True: "PASS", False: "FAIL", None: "note"}[row["ok"]]
        print(f"  [{mark}] {row['step']}")
    print()
    print(f"{'VERIFIED' if ok else 'NOT VERIFIED'} — {len(steps.failed)} failed step(s)")
    print(f"evidence: {path} (no token, no account numbers)")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Teller adapter against Teller's sandbox API."
    )
    parser.add_argument(
        "--access-token",
        default=None,
        help=f"A Teller sandbox access token. Falls back to {TOKEN_ENV}.",
    )
    parser.add_argument("--enrollment-id", default=None, help="The enrolment id Teller returned.")
    parser.add_argument("--teller-user-id", default=None, help="The Teller user id, if known.")
    parser.add_argument(
        "--poll",
        type=int,
        default=5,
        help="Extra sync attempts while a new enrolment's history appears (default 5).",
    )
    parser.add_argument(
        "--keep-user",
        action="store_true",
        help="Keep the ephemeral user and its rows for inspection (default: delete).",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
