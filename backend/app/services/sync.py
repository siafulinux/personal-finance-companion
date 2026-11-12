"""Provider-agnostic synchronisation engine.

Responsibilities, in order:

1. Persist a link and its encrypted token (never a bank password: the user approves the
   institution in the provider's own flow).
2. Materialise the provider's accounts as ordinary ``financial_accounts`` rows.
3. Pull incremental changes with the provider cursor and apply them through the *existing*
   transaction service, so dedupe, bill matching and the ledger behave exactly as they do
   for manual entry.
4. Reconcile a pending authorisation that later posts, without leaving an orphan.
5. Record every attempt, and back off on failure instead of hammering the provider.

The engine never computes a balance itself: it asks ``balances_for_accounts``.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    FinancialAccount,
    ProviderLink,
    ProviderLinkSecret,
    SyncRun,
    Transaction,
    User,
)
from app.models.enums import (
    AccountType,
    ProviderLinkStatus,
    SyncStatus,
    SyncTrigger,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.providers.base import (
    ProviderAccountData,
    ProviderError,
    ProviderTransactionData,
    TransactionDelta,
)
from app.providers.registry import adapter_for
from app.schemas.finance import TransactionCreate
from app.security.secrets import decrypt_text, encrypt_text, mask_token
from app.services.balances import balances_for_accounts
from app.services.bill_matching import match_transaction
from app.services.dedupe import transaction_fingerprint
from app.services.errors import ConflictError, DomainError, NotFoundError, ValidationError
from app.services.transactions import create_transaction
from app.utils.dates import today_in, utc_now
from app.utils.money import quantize

# Backoff schedule for a failing link: 15 min, 30, 60, … capped at 24 h.
_BACKOFF_BASE_MINUTES = 15
_BACKOFF_CAP_MINUTES = 24 * 60

# Provider transfer legs are matched on amount and a short date window.
_TRANSFER_PAIR_WINDOW_DAYS = 3


# --------------------------------------------------------------------------- links
def _store_token(db: Session, link: ProviderLink, access_token: str) -> None:
    ciphertext = encrypt_text(access_token)
    if link.secret is None:
        link.secret = ProviderLinkSecret(link_id=link.id, ciphertext=ciphertext, key_version=1)
    else:
        link.secret.ciphertext = ciphertext
    db.flush()


def token_for(link: ProviderLink) -> str:
    """Decrypt a link's access token. Raises if the secret is missing or unreadable."""
    if link.secret is None:
        raise ProviderError(
            "This connection has no stored credential; reconnect the institution.",
            code="missing_token",
            requires_reauth=True,
            retryable=False,
        )
    try:
        return decrypt_text(link.secret.ciphertext)
    except Exception as exc:  # noqa: BLE001 - any failure means "reconnect"
        raise ProviderError(
            "The stored credential cannot be read; reconnect the institution.",
            code="unreadable_token",
            requires_reauth=True,
            retryable=False,
        ) from exc


def list_links(db: Session, user_id: uuid.UUID) -> list[ProviderLink]:
    return list(
        db.scalars(
            select(ProviderLink)
            .where(ProviderLink.user_id == user_id)
            .order_by(ProviderLink.created_at.desc())
        )
    )


def get_link(db: Session, user_id: uuid.UUID, link_id: uuid.UUID) -> ProviderLink:
    link = db.scalar(
        select(ProviderLink).where(
            ProviderLink.id == link_id, ProviderLink.user_id == user_id
        )
    )
    if link is None:
        raise NotFoundError("Connected institution not found.")
    return link


def serialize_link(db: Session, link: ProviderLink) -> dict[str, Any]:
    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.provider_link_id == link.id,
                FinancialAccount.user_id == link.user_id,
            )
        )
    )
    last_run = db.scalar(
        select(SyncRun)
        .where(SyncRun.link_id == link.id)
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )
    return {
        "id": str(link.id),
        "provider": link.provider,
        "institution_name": link.institution_name,
        "institution_id": link.institution_id,
        "status": link.status,
        "last_synced_at": link.last_synced_at,
        "last_success_at": link.last_success_at,
        "next_retry_at": link.next_retry_at,
        "error_code": link.error_code,
        "error_message": link.error_message,
        "failure_count": link.failure_count,
        "consented_at": link.consented_at,
        "disconnected_at": link.disconnected_at,
        "history_start": link.history_start,
        "account_count": len(accounts),
        "accounts": [
            {
                "id": str(a.id),
                "name": a.name,
                "account_type": a.account_type,
                "external_account_id": a.external_account_id,
            }
            for a in accounts
        ],
        "last_run": {
            "id": str(last_run.id),
            "status": last_run.status,
            "started_at": last_run.started_at,
            "finished_at": last_run.finished_at,
            "added": last_run.added,
            "modified": last_run.modified,
            "removed": last_run.removed,
            "skipped_duplicates": last_run.skipped_duplicates,
            "error_message": last_run.error_message,
        }
        if last_run
        else None,
        "has_stored_credential": link.secret is not None,
    }


# ------------------------------------------------------------------------ accounts
def _signed_provider_balance(row: ProviderAccountData) -> Decimal:
    """Credit cards are stored as a negative liability, matching the rest of the app."""
    balance = quantize(row.balance)
    if row.account_type == AccountType.CREDIT_CARD.value:
        return -abs(balance)
    return balance


def _unique_account_name(db: Session, user_id: uuid.UUID, base: str, link: ProviderLink) -> str:
    name = base[:120]
    suffix = 1
    while db.scalar(
        select(FinancialAccount.id).where(
            FinancialAccount.user_id == user_id, FinancialAccount.name == name
        )
    ):
        suffix += 1
        tail = f" ({link.institution_name})" if suffix == 2 else f" ({link.institution_name} {suffix})"
        name = (base[: 120 - len(tail)] + tail)[:120]
        if suffix > 8:  # pragma: no cover - defensive
            name = f"{base[:100]} ({uuid.uuid4().hex[:6]})"
            break
    return name


def _upsert_accounts(
    db: Session, user: User, link: ProviderLink, rows: list[ProviderAccountData]
) -> tuple[dict[str, FinancialAccount], list[FinancialAccount]]:
    existing = {
        a.external_account_id: a
        for a in db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.provider_link_id == link.id,
                FinancialAccount.user_id == user.id,
            )
        )
        if a.external_account_id
    }
    mapping: dict[str, FinancialAccount] = {}
    created: list[FinancialAccount] = []
    opening_date = link.history_start or today_in(user.timezone)

    for row in rows:
        account = existing.get(row.external_id)
        if account is not None:
            # Never rewrite a user's name, type or Safe-to-Spend choice.
            account.institution = link.institution_name
            account.credit_limit = row.credit_limit or account.credit_limit
            account.provider = link.provider
            mapping[row.external_id] = account
            continue

        account = FinancialAccount(
            user_id=user.id,
            name=_unique_account_name(db, user.id, row.name, link),
            account_type=row.account_type,
            opening_balance=_signed_provider_balance(row),
            opening_balance_date=opening_date,
            currency=row.currency,
            include_in_safe_to_spend=row.account_type != AccountType.CREDIT_CARD.value,
            credit_limit=row.credit_limit,
            institution=link.institution_name,
            provider=link.provider,
            external_account_id=row.external_id,
            provider_link_id=link.id,
            description=f"Imported from {link.institution_name}",
        )
        db.add(account)
        db.flush()
        mapping[row.external_id] = account
        created.append(account)
    return mapping, created


def _rebase_opening_balances(
    db: Session, user: User, link: ProviderLink, created: list[FinancialAccount]
) -> None:
    """Make a freshly linked account show the institution's balance.

    The provider reports a current balance but no historical one, so importing history and
    *also* accepting that balance would count the same money twice. The opening balance is
    therefore back-solved as ``reported - sum(imported posted effects)`` once, at link time.
    Later runs never re-base: drift is reported instead of being silently absorbed.
    """
    if not created:
        return
    ids = [a.id for a in created]
    summaries = balances_for_accounts(db, user.id, ids)
    for account in created:
        summary = summaries.get(account.id)
        if summary is None:
            continue
        reported = quantize(account.opening_balance)  # signed, from the provider
        account.opening_balance = quantize(reported - summary.posted_delta)
        account.opening_balance_date = link.history_start or account.opening_balance_date
    db.flush()


def _balance_drift(
    db: Session, user: User, link: ProviderLink, rows: list[ProviderAccountData]
) -> list[dict[str, str]]:
    accounts = {
        a.external_account_id: a
        for a in db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.provider_link_id == link.id,
                FinancialAccount.user_id == user.id,
            )
        )
    }
    ids = [a.id for a in accounts.values() if a.id]
    summaries = balances_for_accounts(db, user.id, ids)
    drift: list[dict[str, str]] = []
    for row in rows:
        account = accounts.get(row.external_id)
        if account is None or account.id not in summaries:
            continue
        computed = summaries[account.id].posted_balance
        expected = _signed_provider_balance(row)
        if computed != expected:
            drift.append(
                {
                    "account": account.name,
                    "computed": str(computed),
                    "provider_reported": str(expected),
                    "difference": str(quantize(computed - expected)),
                }
            )
    return drift


# -------------------------------------------------------------------- transactions
def _find_provider_transaction(
    db: Session, user_id: uuid.UUID, external_id: str
) -> Transaction | None:
    return db.scalar(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.source == TransactionSource.PROVIDER.value,
            Transaction.external_id == external_id,
        )
    )


def _suggest_category_safely(db: Session, user: User, txn: Transaction) -> bool:
    """Attach a reversible category proposal. Never touches a confirmed category."""
    from app.services.intelligence import suggest_category

    if txn.category_id is not None:
        return False
    try:
        return suggest_category(db, user, txn) is not None
    except Exception:  # noqa: BLE001 - classification must never fail a sync
        return False


def _create_from_provider(
    db: Session,
    user: User,
    txn_data: TransactionCreate,
    counts: Counter,
) -> Transaction | None:
    try:
        txn, _ = create_transaction(
            db, user, txn_data, source=TransactionSource.PROVIDER
        )
    except ConflictError:
        # The provider re-reported a transaction we already hold: silently correct.
        counts["skipped_duplicates"] += 1
        return None
    except DomainError as exc:
        counts["rejected"] += 1
        counts.setdefault("errors", [])
        if isinstance(counts["errors"], list) and len(counts["errors"]) < 20:
            counts["errors"].append(
                {"external_id": txn_data.external_id, "reason": getattr(exc, "message", str(exc))}
            )
        return None
    counts["added"] += 1
    if _suggest_category_safely(db, user, txn):
        counts["suggestions"] += 1
    return txn


def _payload_for(
    row: ProviderTransactionData,
    account: FinancialAccount,
    *,
    transfer_account_id: uuid.UUID | None = None,
    tx_type: str | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> TransactionCreate:
    resolved_type = tx_type or row.tx_type
    if resolved_type == TransactionType.TRANSFER.value and transfer_account_id is None:
        # A one-sided transfer cannot be represented as an internal transfer. Record the
        # real cash effect and flag it instead of failing the row.
        resolved_type = TransactionType.ADJUSTMENT.value
        tags = [*(tags or []), "provider-transfer-unpaired"]
    return TransactionCreate(
        account_id=account.id,
        transfer_account_id=transfer_account_id,
        description=row.description[:255] or "Provider transaction",
        merchant=row.merchant[:160] if row.merchant else None,
        amount=quantize(row.amount),
        tx_type=TransactionType(resolved_type),
        status=TransactionStatus.PENDING if row.pending else TransactionStatus.POSTED,
        txn_date=row.txn_date,
        posting_date=row.posting_date,
        external_id=row.external_id[:160],
        tags=tags or [],
        notes=notes,
    )


def _find_existing_transfer(
    db: Session,
    user_id: uuid.UUID,
    source_account: uuid.UUID,
    target_account: uuid.UUID,
    amount: Decimal,
    txn_date: date,
) -> Transaction | None:
    """Idempotency for the credit leg of a paired provider transfer."""
    return db.scalar(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.source == TransactionSource.PROVIDER.value,
            Transaction.tx_type == TransactionType.TRANSFER.value,
            Transaction.account_id == source_account,
            Transaction.transfer_account_id == target_account,
            Transaction.amount == quantize(amount),
            Transaction.txn_date >= txn_date - timedelta(days=_TRANSFER_PAIR_WINDOW_DAYS),
            Transaction.txn_date <= txn_date + timedelta(days=_TRANSFER_PAIR_WINDOW_DAYS),
        )
    )


def _apply_added_legs(
    db: Session,
    user: User,
    delta: TransactionDelta,
    account_map: dict[str, FinancialAccount],
    counts: Counter,
    transfer_buffer: list[tuple[ProviderTransactionData, FinancialAccount]],
) -> None:
    """Import additions, deferring transfer legs so a pair can be completed.

    Both legs of an internal transfer may land in different pages, so legs are buffered
    for the whole run and resolved at the end. Pages are therefore not committed
    independently: the cursor only moves once the run succeeds, and a replayed run is
    harmless because the dedupe key absorbs every row it already created.
    """
    plain: list[tuple[ProviderTransactionData, FinancialAccount]] = []

    for row in delta.added:
        account = account_map.get(row.account_external_id)
        if account is None:
            counts["unknown_account"] += 1
            continue
        if row.tx_type in {"transfer_out", "transfer_in"}:
            transfer_buffer.append((row, account))
        else:
            plain.append((row, account))

    for row, account in plain:
        existing = _find_provider_transaction(db, user.id, row.external_id)
        if existing is not None:
            # A window-based provider (Teller) re-reports the same id after it posts.
            # Reconciling here is what stops a pending authorisation from staying
            # pending forever when no "modified" event is ever sent.
            if existing.status == TransactionStatus.PENDING.value and not row.pending:
                _apply_pending_reconciliation(db, user, existing, row, account, counts)
            else:
                counts["skipped_duplicates"] += 1
            continue
        # A new posted row may be the posted form of a pending row we already hold.
        if row.pending_external_id:
            pending = _find_provider_transaction(db, user.id, row.pending_external_id)
            if pending is not None:
                _apply_pending_reconciliation(db, user, pending, row, account, counts)
                continue
        _create_from_provider(db, user, _payload_for(row, account), counts)


def _flush_transfer_legs(
    db: Session,
    user: User,
    legs: list[tuple[ProviderTransactionData, FinancialAccount]],
    counts: Counter,
) -> None:
    """Collapse buffered provider transfer legs into internal transfers."""
    outs = [(r, a) for r, a in legs if r.tx_type == "transfer_out"]
    ins = [(r, a) for r, a in legs if r.tx_type == "transfer_in"]
    outs.sort(key=lambda pair: (pair[0].txn_date, pair[0].external_id))
    ins.sort(key=lambda pair: (pair[0].txn_date, pair[0].external_id))

    # Pair each outflow with an inflow of the same amount on a different account.
    for out_row, out_account in outs:
        partner = next(
            (
                (r, a)
                for r, a in ins
                if r.amount == out_row.amount
                and a.id != out_account.id
                and abs((r.txn_date - out_row.txn_date).days) <= _TRANSFER_PAIR_WINDOW_DAYS
            ),
            None,
        )
        if partner is not None and _find_existing_transfer(
            db, user.id, out_account.id, partner[1].id, out_row.amount, out_row.txn_date
        ):
            ins.remove(partner)
            counts["skipped_duplicates"] += 1
            continue

        if partner is None:
            # Only one leg visible (the other account may not be linked). Record the true
            # cash effect, tag it, and surface it in the run detail for review.
            counts["unpaired_transfers"] += 1
            _create_from_provider(
                db,
                user,
                _payload_for(
                    out_row,
                    out_account,
                    tx_type=TransactionType.ADJUSTMENT.value,
                    tags=["provider-transfer-unpaired"],
                    notes="Provider reported one side of an internal transfer.",
                ),
                counts,
            )
            continue

        in_row, in_account = partner
        ins.remove(partner)
        _create_from_provider(
            db,
            user,
            _payload_for(
                out_row,
                out_account,
                transfer_account_id=in_account.id,
                tx_type=TransactionType.TRANSFER.value,
                tags=["provider-transfer"],
                notes=f"Paired with provider transaction {in_row.external_id}.",
            ),
            counts,
        )

    for in_row, in_account in ins:
        # A credit leg with no outflow partner would inflate income, so it is imported as
        # an adjustment-tagged income row only when the cash really arrived.
        counts["unpaired_transfers"] += 1
        _create_from_provider(
            db,
            user,
            _payload_for(
                in_row,
                in_account,
                tx_type=TransactionType.INCOME.value,
                tags=["provider-transfer-unpaired"],
                notes="Provider reported one side of an internal transfer.",
            ),
            counts,
        )


def _apply_pending_reconciliation(
    db: Session,
    user: User,
    txn: Transaction,
    row: ProviderTransactionData,
    account: FinancialAccount,
    counts: Counter,
) -> None:
    """A pending authorisation became a posted transaction: update the same row."""
    txn.external_id = row.external_id[:160]
    txn.amount = quantize(row.amount)
    txn.status = TransactionStatus.POSTED.value
    txn.txn_date = row.txn_date
    txn.posting_date = row.posting_date or row.txn_date
    txn.reconciled_at = utc_now()
    if row.merchant:
        txn.merchant = row.merchant[:160]
    txn.account_id = account.id
    txn.dedupe_key = transaction_fingerprint(
        account_id=txn.account_id,
        txn_date=txn.txn_date,
        amount=txn.amount,
        description=txn.description,
        merchant=txn.merchant,
        tx_type=txn.tx_type,
        external_id=txn.external_id,
    )
    db.flush()
    counts["modified"] += 1
    counts["reconciled"] += 1
    try:
        match_transaction(db, user, txn)
    except Exception:  # noqa: BLE001 - matching must never fail a sync
        pass


def _apply_modified(
    db: Session,
    user: User,
    row: ProviderTransactionData,
    account_map: dict[str, FinancialAccount],
    counts: Counter,
) -> None:
    txn = _find_provider_transaction(db, user.id, row.external_id)
    if txn is None and row.pending_external_id:
        pending = _find_provider_transaction(db, user.id, row.pending_external_id)
        if pending is not None:
            _apply_pending_reconciliation(db, user, pending, row, account_map.get(
                row.account_external_id, pending.account
            ), counts)
            return
    if txn is None:
        # A provider may report a modification for a row we never saw: insert it.
        account = account_map.get(row.account_external_id)
        if account is None:
            counts["unknown_account"] += 1
            return
        if row.tx_type in {"transfer_out", "transfer_in"}:
            counts["unpaired_transfers"] += 1
            _create_from_provider(
                db,
                user,
                _payload_for(
                    row,
                    account,
                    tx_type=(
                        TransactionType.ADJUSTMENT.value
                        if row.tx_type == "transfer_out"
                        else TransactionType.INCOME.value
                    ),
                    tags=["provider-transfer-unpaired"],
                ),
                counts,
            )
            return
        _create_from_provider(db, user, _payload_for(row, account), counts)
        return

    became_posted = txn.status == TransactionStatus.PENDING.value and not row.pending
    txn.amount = quantize(row.amount)
    txn.status = TransactionStatus.PENDING.value if row.pending else TransactionStatus.POSTED.value
    txn.txn_date = row.txn_date
    if row.posting_date:
        txn.posting_date = row.posting_date
    if row.merchant:
        txn.merchant = row.merchant[:160]
    if row.description:
        txn.description = row.description[:255]
    if became_posted:
        txn.reconciled_at = utc_now()
        txn.posting_date = row.posting_date or row.txn_date
        counts["reconciled"] += 1
    txn.dedupe_key = transaction_fingerprint(
        account_id=txn.account_id,
        txn_date=txn.txn_date,
        amount=txn.amount,
        description=txn.description,
        merchant=txn.merchant,
        tx_type=txn.tx_type,
        external_id=txn.external_id,
    )
    db.flush()
    counts["modified"] += 1

    # Category automation must never overwrite a human decision.
    if txn.category_id is None:
        if _suggest_category_safely(db, user, txn):
            counts["suggestions"] += 1
    if became_posted and txn.tx_type in (
        TransactionType.PURCHASE.value,
        TransactionType.BILL_PAYMENT.value,
    ):
        try:
            match_transaction(db, user, txn)
        except Exception:  # noqa: BLE001
            pass


def _apply_removed(db: Session, user_id: uuid.UUID, external_id: str, counts: Counter) -> None:
    txn = _find_provider_transaction(db, user_id, external_id)
    if txn is None:
        counts["skipped_removals"] += 1
        return
    from app.services.transactions import delete_transaction

    user = db.get(User, user_id)
    assert user is not None
    delete_transaction(db, user, txn.id)
    counts["removed"] += 1


# ------------------------------------------------------------------------- syncing
def _apply_delta(
    db: Session,
    user: User,
    delta: TransactionDelta,
    account_map: dict[str, FinancialAccount],
    counts: Counter,
    transfer_buffer: list[tuple[ProviderTransactionData, FinancialAccount]],
) -> None:
    _apply_added_legs(db, user, delta, account_map, counts, transfer_buffer)
    for row in delta.modified:
        _apply_modified(db, user, row, account_map, counts)
    for external_id in delta.removed:
        if external_id:
            _apply_removed(db, user.id, external_id, counts)


def _schedule_retry(link: ProviderLink, error: ProviderError) -> None:
    now = utc_now()
    link.failure_count += 1
    link.error_code = error.code
    link.error_message = error.message[:500]
    if error.requires_reauth:
        link.status = ProviderLinkStatus.REAUTH_REQUIRED.value
        link.next_retry_at = None
        return
    link.status = ProviderLinkStatus.ERROR.value
    if not error.retryable:
        link.next_retry_at = None
        return
    minutes = min(_BACKOFF_BASE_MINUTES * (2 ** (link.failure_count - 1)), _BACKOFF_CAP_MINUTES)
    link.next_retry_at = now + timedelta(minutes=minutes)


def sync_link(
    db: Session,
    user: User,
    link: ProviderLink,
    *,
    trigger: SyncTrigger = SyncTrigger.MANUAL,
    full_refresh: bool = False,
) -> SyncRun:
    if link.status == ProviderLinkStatus.DISCONNECTED.value:
        raise ValidationError("This connection has been disconnected.")

    run = SyncRun(
        user_id=user.id,
        link_id=link.id,
        provider=link.provider,
        trigger=trigger.value,
        status=SyncStatus.RUNNING.value,
        started_at=utc_now(),
    )
    db.add(run)
    link.last_attempt_at = utc_now()
    db.flush()

    counts: Counter = Counter()
    # Built from the administrator's saved credentials, so a rotated key applies here
    # without a restart.
    adapter = adapter_for(db, link.provider)
    try:
        if not adapter.is_configured():
            raise ProviderError(
                f"The {link.provider} provider is not configured on this server.",
                code="not_configured",
                retryable=False,
            )
        token = token_for(link)

        account_rows = adapter.list_accounts(token)
        account_map, created = _upsert_accounts(db, user, link, account_rows)
        counts["accounts_linked"] = len(account_map)
        db.flush()

        cursor = None if full_refresh else link.cursor
        # One date for the whole run, and the user's rather than the server's: pages
        # must not disagree across a midnight boundary, and a server clock ahead of
        # the user would date rows into their future, outside every "today" query.
        local_today = today_in(user.timezone)
        pages = 0
        transfer_buffer: list[tuple[ProviderTransactionData, FinancialAccount]] = []
        while pages < settings.sync_max_pages:
            delta = adapter.sync_page(
                token, cursor, settings.sync_page_size, today=local_today
            )
            _apply_delta(db, user, delta, account_map, counts, transfer_buffer)
            cursor = delta.next_cursor or cursor
            pages += 1
            if not delta.has_more:
                break
        else:
            counts["page_limit_reached"] = 1

        _flush_transfer_legs(db, user, transfer_buffer, counts)
        # The cursor moves only now that the whole run has been applied, so a crash
        # replays the run instead of skipping rows (dedupe keeps the replay harmless).
        if not counts["page_limit_reached"]:
            link.cursor = cursor
        db.flush()

        if created:
            _rebase_opening_balances(db, user, link, created)

        drift = _balance_drift(db, user, link, account_rows)
        counts["accounts_created"] = len(created)
        if drift:
            counts["balance_drift"] = drift

        rejected = counts["rejected"]
        run.status = (
            SyncStatus.PARTIAL.value if rejected else SyncStatus.SUCCESS.value
        )
        link.status = ProviderLinkStatus.ACTIVE.value
        link.failure_count = 0
        link.error_code = None
        link.error_message = None
        link.next_retry_at = None
        link.last_success_at = utc_now()
    except ProviderError as exc:
        _schedule_retry(link, exc)
        run.status = SyncStatus.FAILED.value
        run.error_code = exc.code
        run.error_message = exc.message[:500]
    finally:
        link.last_synced_at = utc_now()
        run.finished_at = utc_now()
        run.accounts_linked = counts["accounts_linked"]
        run.added = counts["added"]
        run.modified = counts["modified"]
        run.removed = counts["removed"]
        run.skipped_duplicates = counts["skipped_duplicates"]
        run.suggestions_created = counts["suggestions"]
        run.unmatched_pending = counts["unpaired_transfers"]
        detail = {
            k: v
            for k, v in counts.items()
            if k
            in {
                "accounts_created",
                "reconciled",
                "rejected",
                "errors",
                "unknown_account",
                "skipped_removals",
                "unpaired_transfers",
                "balance_drift",
                "page_limit_reached",
            }
        }
        run.detail = detail or None
        db.flush()

    return run


def connect_institution(
    db: Session,
    user: User,
    provider: str,
    public_token: str,
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[ProviderLink, list[FinancialAccount], SyncRun]:
    """Complete a linking flow and run the first sync.

    ``payload`` carries whatever else the provider's flow returned (Teller mints its token
    in the client, so it also hands back the enrolment id and a signature to verify).
    """
    adapter = adapter_for(db, provider)
    if not adapter.is_configured():
        raise ProviderError(
            f"The {provider} provider is not configured on this server.",
            code="not_configured",
            retryable=False,
        )
    enriched = dict(payload or {})
    # Always verify a linking nonce against the signed-in user, whatever the caller sent.
    enriched["expected_user_id"] = str(user.id)
    # The history window is counted back from the user's day, the same clock the sync
    # below paginates on. Reading the host's date here dated the window -- and every
    # account's opening balance -- into the user's future on a UTC container in the
    # Americas evening, which the first sync then dropped from its "up to today" reads.
    result = adapter.complete_link(public_token, enriched, today=today_in(user.timezone))
    was_connected = False

    link = db.scalar(
        select(ProviderLink).where(
            ProviderLink.user_id == user.id,
            ProviderLink.provider == provider,
            ProviderLink.external_item_id == result.external_item_id,
        )
    )
    if link is None:
        link = ProviderLink(
            user_id=user.id,
            provider=provider,
            external_item_id=result.external_item_id,
            institution_name=result.institution_name,
            institution_id=result.institution_id,
            history_start=result.history_start,
            consented_at=utc_now(),
        )
        db.add(link)
        db.flush()
    else:
        link.institution_name = result.institution_name
        link.institution_id = result.institution_id
        link.history_start = result.history_start or link.history_start
        link.status = ProviderLinkStatus.ACTIVE.value
        link.disconnected_at = None
        link.consented_at = utc_now()
        was_connected = True
        link.cursor = None  # reconnect replays history; dedupe keeps it clean

    _store_token(db, link, result.access_token)
    db.flush()

    run = sync_link(
        db, user, link, trigger=SyncTrigger.RECONNECT if was_connected else SyncTrigger.MANUAL
    )
    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.provider_link_id == link.id,
                FinancialAccount.user_id == user.id,
            )
        )
    )
    return link, accounts, run


def disconnect_link(
    db: Session, user: User, link: ProviderLink, *, delete_data: bool
) -> dict[str, Any]:
    """Unlink and, when asked, delete the data the institution brought in."""
    adapter = adapter_for(db, link.provider)
    revoked = False
    try:
        token = token_for(link)
        adapter.remove_item(token)
        revoked = True
    except ProviderError:
        # Local cleanup must not depend on the provider being reachable.
        revoked = False

    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.provider_link_id == link.id,
                FinancialAccount.user_id == user.id,
            )
        )
    )
    deleted_transactions = 0
    deleted_accounts = 0

    if delete_data:
        from app.services.transactions import delete_transaction

        txn_ids = list(
            db.scalars(
                select(Transaction.id).where(
                    Transaction.user_id == user.id,
                    Transaction.source == TransactionSource.PROVIDER.value,
                    or_(
                        Transaction.account_id.in_([a.id for a in accounts]),
                        Transaction.transfer_account_id.in_([a.id for a in accounts]),
                    ),
                )
            )
        ) if accounts else []
        for txn_id in txn_ids:
            delete_transaction(db, user, txn_id)
            deleted_transactions += 1

        for account in accounts:
            account.provider_link_id = None
            db.flush()
            try:
                from app.services.accounts import delete_account

                delete_account(db, user.id, account.id)
                deleted_accounts += 1
            except ConflictError:
                # Still referenced (e.g. a manual transfer points at it): keep history.
                account.is_archived = True
                account.archived_at = utc_now()
                db.flush()

    for account in accounts:
        if account.provider_link_id == link.id:
            account.provider_link_id = None

    link.status = ProviderLinkStatus.DISCONNECTED.value
    link.disconnected_at = utc_now()
    link.cursor = None
    link.next_retry_at = None
    if link.secret is not None:
        db.delete(link.secret)
        link.secret = None
    db.flush()

    return {
        "revoked_at_provider": revoked,
        "deleted_transactions": deleted_transactions,
        "deleted_accounts": deleted_accounts,
        "kept_accounts": len(accounts) - deleted_accounts,
        "link_id": str(link.id),
    }


def due_links(db: Session, now: datetime | None = None) -> list[ProviderLink]:
    """Links a scheduler should attempt now."""
    now = now or utc_now()
    rows = list(
        db.scalars(
            select(ProviderLink).where(
                ProviderLink.status.in_(
                    [ProviderLinkStatus.ACTIVE.value, ProviderLinkStatus.ERROR.value]
                )
            )
        )
    )
    due: list[ProviderLink] = []
    for link in rows:
        if link.next_retry_at and link.next_retry_at > now:
            continue
        if link.last_attempt_at:
            elapsed = now - link.last_attempt_at
            if elapsed < timedelta(minutes=settings.sync_min_interval_minutes):
                continue
        due.append(link)
    return due


def sync_due_links(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    """Scheduled entry point. One link's failure never stops the others."""
    results: list[dict[str, Any]] = []
    for link in due_links(db)[:limit]:
        user = db.get(User, link.user_id)
        if user is None or not user.is_active:
            continue
        try:
            run = sync_link(db, user, link, trigger=SyncTrigger.SCHEDULED)
            results.append(
                {
                    "link_id": str(link.id),
                    "status": run.status,
                    "added": run.added,
                    "modified": run.modified,
                    "removed": run.removed,
                }
            )
        except Exception as exc:  # noqa: BLE001 - the scheduler must keep going
            db.rollback()
            results.append({"link_id": str(link.id), "status": "failed", "error": str(exc)})
    return results


def serialize_run(run: SyncRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "link_id": str(run.link_id) if run.link_id else None,
        "provider": run.provider,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "accounts_linked": run.accounts_linked,
        "added": run.added,
        "modified": run.modified,
        "removed": run.removed,
        "skipped_duplicates": run.skipped_duplicates,
        "suggestions_created": run.suggestions_created,
        "unmatched_pending": run.unmatched_pending,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "detail": run.detail,
    }
