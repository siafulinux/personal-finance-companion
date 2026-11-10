#!/usr/bin/env python
"""Prove the Plaid adapter against Plaid's **real** API (sandbox only).

This is not another fake-endpoint test. It drives the same service functions the HTTP
API uses, against ``sandbox.plaid.com``:

    create_link_token  ->  /sandbox/public_token/create  ->  connect_institution
    ->  a second sync_link (must add nothing: dedupe)
    ->  balance comparison against the institution's reported balances
    ->  disconnect_link (revoke at Plaid, delete imported rows)
    ->  re-use of the revoked access token must now be rejected by Plaid

Everything printed is a count, a local row id, a status or a Plaid error code. Access
tokens, link tokens and secrets are never printed and never written to the evidence file.

Usage, from ``backend/``::

    .venv/bin/python scripts/verify_plaid_live.py
    .venv/bin/python scripts/verify_plaid_live.py --institution ins_109508 --keep-user

Requires ``PLAID_CLIENT_ID`` and ``PLAID_SECRET`` for the sandbox environment. Plaid
issues those only from its dashboard (https://dashboard.plaid.com/team/keys); there is
no keyless sandbox. This script never invents credentials and never falls back to the
simulated institution — a missing key is a failure, not a silent substitution.

Exit codes: 0 verified, 2 not configured, 3 wrong environment, 4 a step failed.
"""

from __future__ import annotations

import argparse
import json
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
from app.providers.plaid import SANDBOX_INSTITUTION_ID
from app.providers.registry import available_providers, build_adapter
from app.services import provider_config
from app.services.balances import balances_for_accounts
from app.services.sync import (
    connect_institution,
    disconnect_link,
    sync_link,
    token_for,
)
from app.services.users import delete_user_account, register_user

EVIDENCE_DIR = PROJECT_ROOT / "logs" / "plaid-live"
TEST_PASSWORD = "PlaidLiveCheck!2026"


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
        return [r for r in self.rows if r["ok"] is False]


def _provider_count(db, user_id) -> int:
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
    # Resolve the configuration exactly the way the application does: the
    # administrator's saved values first, the environment second. Reading the
    # environment directly would make credentials entered on the Providers screen
    # invisible here, and a verification script that tests a different
    # configuration than production uses proves nothing.
    check_db = SessionLocal()
    try:
        state = provider_config.resolve(check_db, "plaid")
    except Exception as err:  # un-migrated database, wrong DB, server down
        print(
            "Cannot read this server's provider configuration: "
            f"{type(err).__name__}: {err}\n"
            "Run the script where the application's database lives, for example:\n\n"
            "    docker compose exec api python scripts/verify_plaid_live.py\n\n"
            "and make sure migrations are applied (api-entrypoint runs them). "
            "No live call was made.",
            file=sys.stderr,
        )
        return 2
    finally:
        check_db.close()
    adapter = build_adapter(
        "plaid",
        credentials={
            "client_id": state.credential("client_id") or "",
            "secret": state.credential("secret") or "",
        },
        environment=state.environment,
    )

    if not state.configured or not adapter.is_configured():
        missing = ", ".join(state.missing) or "PLAID_CLIENT_ID / PLAID_SECRET"
        print(
            "Plaid is not configured on this server: " + missing + " missing.\n"
            "Create an account at https://dashboard.plaid.com, then either (a) sign in as\n"
            "the server administrator, open Providers -> Plaid and save the client id and\n"
            "secret (stored encrypted, preferred), or (b) add them to .env as:\n\n"
            "    PLAID_CLIENT_ID=...\n"
            "    PLAID_SECRET=...\n"
            "    PLAID_ENVIRONMENT=sandbox\n\n"
            "Then re-run this script. No live call was made.",
            file=sys.stderr,
        )
        return 2

    print(f"plaid configuration source: {state.source} (environment {state.environment})")

    if adapter.environment != "sandbox":
        print(
            f"Refusing to run against PLAID_ENVIRONMENT={adapter.environment}. This\n"
            "verification creates Items and revokes them; it is sandbox-only by design.",
            file=sys.stderr,
        )
        return 3

    steps = Steps()
    started = time.monotonic()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    email = f"plaid-live+{stamp.lower()}-{uuid.uuid4().hex[:6]}@example.test"

    db = SessionLocal()
    user: User | None = None
    link = None
    access_token: str | None = None
    exit_code = 0

    try:
        # --- wiring: the registry, not a hand-built adapter ------------------
        providers = {p["name"]: p for p in available_providers()}
        plaid_row = providers.get("plaid", {})
        # The registry's own flags come from the environment; the saved admin
        # configuration is authoritative, so the gate reads the resolved state.
        resolved = provider_config.resolve(db, "plaid")
        steps.record(
            "provider registered and usable",
            plaid_row.get("name") == "plaid" and resolved.configured and resolved.enabled,
            name=plaid_row.get("name"),
            configured=resolved.configured,
            enabled=resolved.enabled,
            configuration_source=resolved.source,
            simulated=plaid_row.get("simulated"),
        )

        user = register_user(
            db,
            email=email,
            password=TEST_PASSWORD,
            display_name="Plaid live verification",
            timezone=settings.default_timezone,
        )
        db.commit()
        steps.record("ephemeral user created", True, user_id=str(user.id), email=email)

        # --- 1. Link token (real /link/token/create) -------------------------
        t0 = time.monotonic()
        link_token = adapter.create_link_token(str(user.id))
        token_value = str(link_token.get("link_token") or "")
        steps.record(
            "link token created at Plaid",
            token_value.startswith("link-sandbox-"),
            ms=round((time.monotonic() - t0) * 1000),
            environment=link_token.get("environment"),
            mode=link_token.get("mode"),
            # Prefix only: enough to prove it came from Plaid, not enough to use.
            prefix=token_value[:13] + "…" if token_value else None,
        )

        # --- 2. A real Item, without the Link UI -----------------------------
        t0 = time.monotonic()
        public_token = adapter.create_sandbox_public_token(
            args.institution, days_requested=args.days
        )
        steps.record(
            "sandbox item public token created at Plaid",
            bool(public_token),
            ms=round((time.monotonic() - t0) * 1000),
            institution=args.institution,
            days_requested=args.days,
        )

        # --- 3. Exchange + first sync through the service layer --------------
        t0 = time.monotonic()
        link, accounts, first_run = connect_institution(
            db, user, "plaid", public_token
        )
        db.commit()
        elapsed = round((time.monotonic() - t0) * 1000)
        steps.record(
            "institution connected and first sync applied",
            first_run.status in {"success", "partial"} and len(accounts) > 0,
            ms=elapsed,
            link_id=str(link.id),
            institution=link.institution_name,
            status=first_run.status,
            accounts=len(accounts),
            added=first_run.added,
            modified=first_run.modified,
            skipped_duplicates=first_run.skipped_duplicates,
            error=first_run.error_message,
        )
        if first_run.status not in {"success", "partial"}:
            raise SystemExit(4)

        access_token = token_for(link)
        db_provider_rows = _provider_count(db, user.id)
        # A freshly created Item is sometimes not queryable for transactions yet. Poll a
        # bounded number of times instead of failing on a timing artefact; the assertion
        # below still requires real rows.
        polls = 1
        while db_provider_rows == 0 and polls <= args.poll:
            time.sleep(3)
            polls += 1
            sync_link(db, user, link)
            db.commit()
            db_provider_rows = _provider_count(db, user.id)
        steps.record(
            "transactions imported into the existing ledger",
            db_provider_rows > 0,
            provider_rows=db_provider_rows,
            source="provider",
            sync_attempts=polls,
        )

        # --- 4. Cursor persisted, token encrypted --------------------------
        secret = db.scalar(
            select(ProviderLinkSecret).where(ProviderLinkSecret.link_id == link.id)
        )
        steps.record(
            "cursor stored and token encrypted at rest",
            bool(link.cursor) and secret is not None and access_token not in secret.ciphertext,
            cursor_present=bool(link.cursor),
            ciphertext_bytes=len(secret.ciphertext) if secret else 0,
            plaintext_absent=bool(secret and access_token not in secret.ciphertext),
        )

        # --- 5. Second sync must not duplicate ------------------------------
        t0 = time.monotonic()
        second_run = sync_link(db, user, link)
        db.commit()
        after_rows = _provider_count(db, user.id)
        steps.record(
            "second sync adds no duplicates",
            second_run.added == 0 and after_rows == db_provider_rows,
            ms=round((time.monotonic() - t0) * 1000),
            added=second_run.added,
            modified=second_run.modified,
            rows_before=db_provider_rows,
            rows_after=after_rows,
        )

        # --- 6. Balances agree with what the institution reports -----------
        provider_accounts = adapter.list_accounts(access_token)
        ids = [a.id for a in accounts]
        summaries = balances_for_accounts(db, user.id, ids)
        local_by_external = {
            a.external_account_id: a for a in accounts if a.external_account_id
        }
        mismatches: list[dict[str, str]] = []
        for row in provider_accounts:
            local = local_by_external.get(row.external_id)
            if local is None:
                mismatches.append({"account": row.name, "issue": "not imported"})
                continue
            summary = summaries.get(local.id)
            if summary is None:
                continue
            # Credit accounts are stored as a positive liability, so compare magnitudes.
            if abs(summary.posted_balance) != row.balance:
                mismatches.append(
                    {
                        "account": row.name,
                        "local": str(summary.posted_balance),
                        "provider": str(row.balance),
                    }
                )
        steps.record(
            "local balances match the institution's reported balances",
            not mismatches,
            accounts_compared=len(provider_accounts),
            mismatches=len(mismatches),
        )
        if mismatches:
            steps.note("balance details", detail=json.dumps(mismatches)[:400])

        sync_runs = db.scalar(
            select(func.count()).select_from(SyncRun).where(SyncRun.user_id == user.id)
        )
        steps.record(
            "sync history recorded",
            int(sync_runs or 0) >= 2,
            runs=int(sync_runs or 0),
        )

        # --- 7. Disconnect: revoke at Plaid and delete the imported data ----
        before_disconnect = _provider_count(db, user.id)
        result = disconnect_link(db, user, link, delete_data=True)
        db.commit()
        steps.record(
            "disconnected, revoked at Plaid, imported data removed",
            bool(result["revoked_at_provider"])
            and result["deleted_transactions"] > 0
            and _provider_count(db, user.id) == 0,
            revoked_at_provider=result["revoked_at_provider"],
            deleted_transactions=result["deleted_transactions"],
            deleted_accounts=result["deleted_accounts"],
            rows_before=before_disconnect,
            rows_after=_provider_count(db, user.id),
        )

        db.refresh(link)
        steps.record(
            "stored credential destroyed on disconnect",
            link.status == "disconnected"
            and db.scalar(
                select(func.count())
                .select_from(ProviderLinkSecret)
                .where(ProviderLinkSecret.link_id == link.id)
            )
            == 0,
            link_status=link.status,
        )

        # --- 8. The revoked token must be dead at Plaid --------------------
        try:
            adapter.list_accounts(access_token)
            steps.record("revoked token rejected by Plaid", False, error="token still works")
        except ProviderError as exc:
            steps.record(
                "revoked token rejected by Plaid",
                exc.code
                in {
                    "INVALID_ACCESS_TOKEN",
                    "ITEM_NOT_FOUND",
                    "ACCESS_NOT_GRANTED",
                    "ITEM_LOCKED",
                },
                error_code=exc.code,
            )
        access_token = None  # nothing further should reuse it

    except ProviderError as exc:
        db.rollback()
        steps.record("provider call failed", False, error_code=exc.code, error=exc.message)
        exit_code = 4
    except SystemExit as exc:
        db.rollback()
        exit_code = int(exc.code or 4)
    except Exception as exc:  # noqa: BLE001 - a proof run must always report cleanup
        db.rollback()
        steps.record("unexpected failure", False, error=f"{type(exc).__name__}: {exc}")
        exit_code = 4
    finally:
        # Always leave Plaid and this database as we found them.
        try:
            if link is not None and link.status != "disconnected":
                db.refresh(link)
                if access_token:
                    try:
                        adapter.remove_item(access_token)
                    except ProviderError:
                        pass
                disconnect_link(db, user, link, delete_data=True)
                db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            steps.note("cleanup of the Plaid item failed", error=str(exc))

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

    duration = round(time.monotonic() - started, 2)
    ok = exit_code == 0 and not steps.failed
    evidence = {
        "ran_at": datetime.now(UTC).isoformat(),
        "ok": ok,
        "environment": adapter.environment,
        "base_url": adapter.base_url,
        "institution": args.institution,
        "duration_seconds": duration,
        "steps": steps.rows,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{stamp}.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"{'VERIFIED' if ok else 'NOT VERIFIED'} in {duration}s against {adapter.base_url}")
    print(f"evidence: {path}")
    if not ok:
        print("failed steps: " + ", ".join(str(r["step"]) for r in steps.failed))
    return 0 if ok else (exit_code or 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--institution",
        default=SANDBOX_INSTITUTION_ID,
        help="Sandbox institution id (default: First Platypus Bank).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Days of transaction history to request (1-730).",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=3,
        help="Extra 3 s sync attempts if a new Item reports no transactions yet.",
    )
    parser.add_argument(
        "--keep-user",
        action="store_true",
        help="Leave the ephemeral user in place for inspection.",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
