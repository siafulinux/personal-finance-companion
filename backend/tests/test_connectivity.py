"""Phase 2 connectivity: linking, sync, dedupe, reconciliation, failures, isolation."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import FinancialAccount, ProviderLink, SyncRun, Transaction, User
from app.models.enums import TransactionSource, TransactionStatus
from app.providers.base import ProviderError
from app.providers.registry import get_adapter
from app.providers.sandbox import advance, reset_state
from app.security.secrets import decrypt_text
from app.services import sync as sync_module
from app.services.sync import (
    connect_institution,
    disconnect_link,
    due_links,
    get_link,
    list_links,
    sync_link,
)
from app.services.users import register_user
from app.utils.dates import today_in

D = Decimal


@pytest.fixture(autouse=True)
def clean_sandbox():
    reset_state()
    yield
    reset_state()


def _connect(db, user):
    adapter = get_adapter("sandbox")
    token = adapter.create_link_token(str(user.id))
    return connect_institution(db, user, "sandbox", token["link_token"])


def _drain(db, user, link):
    """Sync until the provider has nothing more to report."""
    while True:
        run = sync_link(db, user, link)
        if run.added == 0 and run.modified == 0 and run.removed == 0:
            return run


@pytest.mark.parametrize(
    "today",
    [
        date(2026, 1, 1),
        date(2026, 2, 28),
        date(2026, 11, 11),
        date(2026, 11, 12),
        date(2026, 11, 25),
        date(2026, 12, 31),
    ],
)
def test_sandbox_subscriptions_stay_detectable_on_any_date(today):
    """The fixtures must carry three occurrences whatever day the suite runs.

    Recurring detection needs three occurrences and two gaps. A fixed 90-day window
    does not always hold three: on 2026-11-11 Netflix, billed on the 12th, had only
    two inside it, so detection found nothing and CI failed on the calendar rather
    than on a change. This pins that: every monthly fixture keeps three occurrences
    dated on or before the run date, and none of them is older than three months.
    """
    from app.providers.sandbox import _SUBSCRIPTIONS, _history

    rows = _history("sandbox-item", today)
    for merchant, *_ in _SUBSCRIPTIONS:
        dates = sorted(row.txn_date for row in rows if row.merchant == merchant)
        assert len(dates) >= 3, f"{merchant} has only {len(dates)} occurrences on {today}"
        assert max(dates) <= today
        assert (today - min(dates)).days <= 95, f"{merchant} reaches back to {min(dates)}"


def test_connect_imports_accounts_and_encrypts_token(db, user):
    link, accounts, run = _connect(db, user)

    assert link.provider == "sandbox"
    assert link.status == "active"
    assert link.institution_name == "Sandbox Credit Union"
    assert link.external_item_id.startswith("sbx-item-")

    # The token never sits in the database in the clear.
    assert link.secret is not None
    assert link.secret.ciphertext.startswith("v1:")
    assert "sbx-access" not in link.secret.ciphertext
    assert decrypt_text(link.secret.ciphertext).startswith("sbx-access-")

    assert len(accounts) == 3
    types = {a.account_type for a in accounts}
    assert types == {"checking", "savings", "credit_card"}

    # Credit cards are liabilities: stored negative, and never spendable cash.
    card = next(a for a in accounts if a.account_type == "credit_card")
    assert card.include_in_safe_to_spend is False
    assert card.opening_balance <= D("0")

    assert run.status == "success"
    assert run.added > 50
    assert run.accounts_linked == 3


def test_synced_transactions_land_in_the_normal_ledger(db, user):
    link, accounts, _ = _connect(db, user)
    _drain(db, user, link)

    txns = list(db.query(Transaction).filter(Transaction.user_id == user.id))
    assert len(txns) > 50
    assert {t.source for t in txns} == {TransactionSource.PROVIDER.value}
    assert all(t.dedupe_key for t in txns)
    assert all(t.external_id for t in txns)

    # Money types are mapped onto the existing taxonomy, not a parallel one.
    types = {t.tx_type for t in txns}
    assert "purchase" in types and "income" in types
    # Both legs of every provider transfer were collapsed into one internal transfer row.
    transfers = [t for t in txns if t.tx_type == "transfer"]
    assert len(transfers) >= 2
    assert all(t.transfer_account_id is not None for t in transfers)
    assert all(t.amount == D("200.00") for t in transfers)
    # No leg was left dangling as a separate income/adjustment row.
    assert not [t for t in txns if "provider-transfer-unpaired" in (t.tags or [])]
    # Transfers never count as spending.
    assert all(t.category_id is None for t in transfers)


def test_repeat_sync_creates_no_duplicates(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)
    count_after_first = db.query(Transaction).filter(Transaction.user_id == user.id).count()

    run = sync_link(db, user, link)
    assert run.added == 0
    assert run.skipped_duplicates == 0  # nothing was even re-reported
    assert db.query(Transaction).filter(Transaction.user_id == user.id).count() == count_after_first

    # A forced full refresh replays the whole history; dedupe must absorb all of it.
    replay = sync_link(db, user, link, full_refresh=True)
    assert replay.added == 0
    assert replay.skipped_duplicates > 50
    assert db.query(Transaction).filter(Transaction.user_id == user.id).count() == count_after_first


def test_pending_transaction_reconciles_in_place(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)

    pending = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id, Transaction.status == "pending")
        .one()
    )
    pending_id = pending.id
    assert pending.reconciled_at is None
    assert pending.external_id.endswith("pending-001")

    advance(link.external_item_id)
    run = sync_link(db, user, link)

    assert run.modified >= 1
    db.expire_all()
    reconciled = db.get(Transaction, pending_id)
    assert reconciled is not None, "the pending row must be updated, not replaced"
    assert reconciled.status == TransactionStatus.POSTED.value
    assert reconciled.reconciled_at is not None
    # Reconciliation does not create a second row for the same charge.
    same = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id, Transaction.amount == D("68.42"))
        .all()
    )
    assert len(same) == 1


def test_provider_removal_deletes_only_provider_rows(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)

    manual = Transaction(
        user_id=user.id,
        account_id=db.query(FinancialAccount).filter_by(user_id=user.id).first().id,
        description="Manual coffee",
        amount=D("5.00"),
        tx_type="purchase",
        status="posted",
        txn_date=today_in(user.timezone),
    )
    db.add(manual)
    db.commit()

    for _ in range(2):
        advance(link.external_item_id)
    advance(link.external_item_id)
    run = sync_link(db, user, link)
    assert run.removed == 1

    db.expire_all()
    assert db.get(Transaction, manual.id) is not None
    refund_rows = [
        t
        for t in db.query(Transaction).filter(Transaction.user_id == user.id)
        if t.description == "TARGET RETURN"
    ]
    assert refund_rows == []


def test_failed_sync_is_recorded_and_backed_off(db, user, monkeypatch):
    link, _, _ = _connect(db, user)
    adapter = get_adapter("sandbox")

    # The signature mirrors the adapter interface, including the caller's local
    # date, so the stub cannot drift from what sync_link actually passes.
    def boom(access_token, cursor, count=100, *, today=None):
        raise ProviderError("Provider is down.", code="provider_unavailable", retryable=True)

    # sync builds its adapter from the saved provider configuration now, so the
    # failure is injected at that seam rather than on a cached singleton.
    monkeypatch.setattr(sync_module, "adapter_for", lambda _db, _name: adapter)
    monkeypatch.setattr(adapter, "sync_page", boom)
    run = sync_link(db, user, link)

    assert run.status == "failed"
    assert run.error_code == "provider_unavailable"
    assert "down" in (run.error_message or "")
    db.refresh(link)
    assert link.status == "error"
    assert link.failure_count == 1
    assert link.next_retry_at is not None
    assert link.next_retry_at > link.last_attempt_at

    # A link waiting for its retry window is not attempted again immediately.
    assert link not in due_links(db)

    # Recovery clears the error state.
    monkeypatch.undo()
    from app.providers.sandbox import SandboxProvider

    monkeypatch.setattr(adapter, "sync_page", SandboxProvider().sync_page)
    link.next_retry_at = None
    run = sync_link(db, user, link)
    db.refresh(link)
    assert run.status == "success"
    assert link.status == "active"
    assert link.failure_count == 0
    assert link.error_code is None


def test_reauth_required_stops_retrying(db, user, monkeypatch):
    link, _, _ = _connect(db, user)
    adapter = get_adapter("sandbox")

    def needs_login(access_token, cursor, count=100, *, today=None):
        raise ProviderError(
            "Reconnect the institution.", code="ITEM_LOGIN_REQUIRED", requires_reauth=True
        )

    monkeypatch.setattr(sync_module, "adapter_for", lambda _db, _name: adapter)
    monkeypatch.setattr(adapter, "sync_page", needs_login)
    run = sync_link(db, user, link)
    db.refresh(link)
    assert run.status == "failed"
    assert link.status == "reauth_required"
    assert link.next_retry_at is None, "a reauth failure must not be retried on a timer"


def test_connections_are_isolated_between_users(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)

    other = register_user(
        db,
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123",
        display_name="Other",
        timezone="America/New_York",
    )
    db.commit()

    assert list_links(db, other.id) == []
    assert db.query(Transaction).filter(Transaction.user_id == other.id).count() == 0
    assert db.query(FinancialAccount).filter(FinancialAccount.user_id == other.id).count() == 0

    from app.services.errors import NotFoundError

    with pytest.raises(NotFoundError):
        get_link(db, other.id, link.id)


def test_disconnect_can_keep_or_delete_data(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)
    before = db.query(Transaction).filter(Transaction.user_id == user.id).count()
    assert before > 0

    result = disconnect_link(db, user, link, delete_data=False)
    db.refresh(link)
    assert link.status == "disconnected"
    assert link.secret is None, "the stored credential must not outlive the connection"
    assert result["deleted_transactions"] == 0
    assert db.query(Transaction).filter(Transaction.user_id == user.id).count() == before
    # Accounts survive as ordinary manual accounts.
    assert (
        db.query(FinancialAccount)
        .filter(FinancialAccount.user_id == user.id, FinancialAccount.provider_link_id.is_not(None))
        .count()
        == 0
    )


def test_disconnect_with_delete_removes_imported_data(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)
    result = disconnect_link(db, user, link, delete_data=True)
    db.refresh(link)

    assert result["deleted_transactions"] > 0
    assert result["deleted_accounts"] == 3
    assert db.query(Transaction).filter(Transaction.user_id == user.id).count() == 0
    assert db.query(FinancialAccount).filter(FinancialAccount.user_id == user.id).count() == 0


def test_sync_runs_are_listed_with_counts(db, user):
    link, _, _ = _connect(db, user)
    _drain(db, user, link)
    runs = db.query(SyncRun).filter(SyncRun.user_id == user.id).all()
    assert len(runs) >= 2
    assert all(r.started_at and r.finished_at for r in runs)
    assert any(r.trigger == "manual" for r in runs)


def test_unknown_provider_is_rejected(db, user):
    from app.providers.base import ProviderError

    with pytest.raises(ProviderError):
        connect_institution(db, user, "not-a-provider", "token")
