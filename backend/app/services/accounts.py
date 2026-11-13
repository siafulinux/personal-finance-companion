"""Financial account management with audited balance adjustments."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BalanceAdjustment, FinancialAccount, Transaction, User
from app.models.enums import AccountType
from app.schemas.finance import AccountCreate, AccountUpdate
from app.services.balances import BalanceSummary, account_balance, balances_for_accounts
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.money import quantize


def get_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> FinancialAccount:
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id, FinancialAccount.user_id == user_id
        )
    )
    if account is None:
        raise NotFoundError("Account not found.")
    return account


def list_accounts(
    db: Session, user_id: uuid.UUID, *, include_archived: bool = False
) -> list[tuple[FinancialAccount, BalanceSummary]]:
    query = select(FinancialAccount).where(FinancialAccount.user_id == user_id)
    if not include_archived:
        query = query.where(FinancialAccount.is_archived.is_(False))
    accounts = list(
        db.scalars(query.order_by(FinancialAccount.sort_order, FinancialAccount.created_at))
    )
    balances = balances_for_accounts(db, user_id, include_archived=include_archived)
    return [(account, balances[account.id]) for account in accounts]


def account_payload(account: FinancialAccount, summary: BalanceSummary | None) -> dict[str, object]:
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "opening_balance": account.opening_balance,
        "opening_balance_date": account.opening_balance_date,
        "include_in_safe_to_spend": account.include_in_safe_to_spend,
        "credit_limit": account.credit_limit,
        "minimum_payment": account.minimum_payment,
        "description": account.description,
        "institution": account.institution,
        "is_archived": account.is_archived,
        "created_at": account.created_at,
        "balance": summary.posted_balance if summary else quantize(account.opening_balance),
        "pending_balance": summary.pending_balance if summary else Decimal("0.00"),
        "available_balance": summary.available_balance if summary else quantize(account.opening_balance),
        "total_inflows": summary.inflows if summary else Decimal("0.00"),
        "total_outflows": summary.outflows if summary else Decimal("0.00"),
        "transaction_count": summary.transaction_count if summary else 0,
    }


def create_account(
    db: Session, user_id: uuid.UUID, payload: AccountCreate, *, today: date
) -> FinancialAccount:
    """Open a manually tracked account.

    ``today`` is the *user's* local date, not this host's. It dates an account the
    caller did not date itself, which is what keeps a UTC container from opening it
    on tomorrow's date for a user in the Americas -- an opening balance in their
    future, where every "up to today" balance and forecast read leaves it out.

    An explicit ``opening_balance_date`` wins: back-dating an account to when it was
    really opened is a normal thing to want, and the server has no way to improve on
    a date the user chose.
    """
    account = FinancialAccount(
        user_id=user_id,
        name=payload.name.strip(),
        account_type=payload.account_type.value,
        opening_balance=quantize(payload.opening_balance),
        opening_balance_date=payload.opening_balance_date or today,
        currency=payload.currency,
        include_in_safe_to_spend=payload.include_in_safe_to_spend,
        credit_limit=quantize(payload.credit_limit) if payload.credit_limit is not None else None,
        minimum_payment=quantize(payload.minimum_payment)
        if payload.minimum_payment is not None
        else None,
        description=payload.description,
        institution=payload.institution,
        sort_order=payload.sort_order,
    )
    if payload.account_type == AccountType.CREDIT_CARD:
        account.include_in_safe_to_spend = False
    db.add(account)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An account with that name already exists.") from exc
    return account


def update_account(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID, payload: AccountUpdate
) -> FinancialAccount:
    account = get_account(db, user_id, account_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("opening_balance") is not None:
        raise ConflictError(
            "Opening balances are immutable. Use a balance adjustment to correct the balance "
            "and keep an audit trail."
        )
    if "opening_balance_date" in data and data["opening_balance_date"] is not None:
        raise ConflictError("Opening balance dates are immutable after creation.")
    if "account_type" in data and data["account_type"] is not None:
        new_type = data["account_type"]
        new_type = new_type.value if hasattr(new_type, "value") else new_type
        data["account_type"] = new_type
        if new_type == AccountType.CREDIT_CARD.value:
            data["include_in_safe_to_spend"] = False
    if "name" in data and data["name"]:
        data["name"] = data["name"].strip()
    if data.get("is_archived") is True:
        from app.utils.dates import utc_now

        account.archived_at = utc_now()
    if data.get("is_archived") is False:
        account.archived_at = None
    for field, value in data.items():
        if field == "minimum_payment" and value is not None:
            value = quantize(value)
        setattr(account, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Another account already uses that name.") from exc
    return account


def archive_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> FinancialAccount:
    account = get_account(db, user_id, account_id)
    account.is_archived = True
    from app.utils.dates import utc_now

    account.archived_at = utc_now()
    db.flush()
    return account


def delete_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> None:
    account = get_account(db, user_id, account_id)
    tx_count = db.scalar(
        select(func.count(Transaction.id)).where(
            (Transaction.account_id == account_id)
            | (Transaction.transfer_account_id == account_id)
        )
    )
    adjustments = db.scalar(
        select(func.count(BalanceAdjustment.id)).where(
            BalanceAdjustment.account_id == account_id
        )
    )
    if tx_count or adjustments:
        raise ConflictError(
            "This account has financial history. Archive it instead of deleting so balances "
            "and reports stay accurate."
        )
    db.delete(account)
    db.flush()


def adjust_balance(
    db: Session,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    target_balance: Decimal,
    reason: str,
) -> BalanceAdjustment:
    """Reconcile to a real-world balance while preserving an audit trail."""
    account = get_account(db, user_id, account_id)
    if account.account_type == AccountType.CREDIT_CARD.value:
        target_balance = -abs(quantize(target_balance))
    summary = account_balance(db, user_id, account_id)
    previous = summary.posted_balance if summary else quantize(account.opening_balance)
    target = quantize(target_balance)
    delta = quantize(target - previous)
    if delta == 0:
        raise ValidationError("The account already has that balance.")
    adjustment = BalanceAdjustment(
        user_id=user_id,
        account_id=account.id,
        amount=delta,
        previous_balance=previous,
        new_balance=target,
        reason=reason.strip(),
    )
    db.add(adjustment)
    db.flush()
    return adjustment


def list_adjustments(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID
) -> list[BalanceAdjustment]:
    get_account(db, user_id, account_id)
    return list(
        db.scalars(
            select(BalanceAdjustment)
            .where(
                BalanceAdjustment.user_id == user_id,
                BalanceAdjustment.account_id == account_id,
            )
            .order_by(BalanceAdjustment.created_at.desc())
        )
    )


def totals(db: Session, user_id: uuid.UUID) -> dict[str, Decimal]:
    rows = list_accounts(db, user_id)
    cash = Decimal("0.00")
    debt = Decimal("0.00")
    for account, summary in rows:
        if account.account_type == AccountType.CREDIT_CARD.value:
            debt += abs(summary.posted_balance)
        else:
            cash += summary.posted_balance
    return {
        "total_cash": quantize(cash),
        "total_debt": quantize(debt),
        "net_worth": quantize(cash - debt),
    }
