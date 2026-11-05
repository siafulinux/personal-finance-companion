"""Assemble Safe-to-Spend inputs from the database and expose the explanation."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculations.safe_to_spend import (
    AccountSnapshot,
    BillReserveItem,
    CategoryAvailability,
    CategoryAvailabilityInputs,
    PendingItem,
    ReserveItem,
    SafeToSpendInputs,
    SafeToSpendResult,
    calculate_category_availability,
    calculate_safe_to_spend,
)
from app.config import settings
from app.models import (
    FinancialAccount,
    PlannedReserve,
    Transaction,
    User,
    UserPreference,
)
from app.models.enums import AccountType, TransactionStatus, TransactionType
from app.services.balances import balances_for_accounts, spending_by_category
from app.services.bills import horizon_candidates, next_payday_date
from app.services.budgets import budget_category_row
from app.services.errors import NotFoundError
from app.utils.dates import month_bounds, today_in, utc_now
from app.utils.money import ZERO, quantize

MAX_STALE_DAYS = 45


def _eligible_accounts(db: Session, user: User) -> list[FinancialAccount]:
    return list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.user_id == user.id,
                FinancialAccount.is_archived.is_(False),
            )
        )
    )


def last_transaction_date(db: Session, user_id: uuid.UUID) -> date | None:
    return db.scalar(
        select(Transaction.txn_date)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.txn_date.desc())
        .limit(1)
    )


def planning_horizon(
    db: Session, user: User, today: date
) -> tuple[date, date | None]:
    prefs = db.get(UserPreference, user.id)
    default_days = prefs.safe_to_spend_horizon_days if prefs else settings.default_safe_to_spend_horizon_days
    horizon_days = max(1, min(default_days, settings.max_safe_to_spend_horizon_days))
    payday = next_payday_date(db, user.id, today)
    if payday and payday > today:
        horizon_end = min(payday, today + timedelta(days=settings.max_safe_to_spend_horizon_days))
    else:
        payday = None
        horizon_end = today + timedelta(days=horizon_days)
    return max(horizon_end, today), payday


def build_inputs(db: Session, user: User, *, today: date | None = None) -> SafeToSpendInputs:
    today = today or today_in(user.timezone)
    prefs = db.get(UserPreference, user.id)
    accounts = _eligible_accounts(db, user)
    balances = balances_for_accounts(db, user.id)

    snapshots: list[AccountSnapshot] = []
    for account in accounts:
        summary = balances.get(account.id)
        snapshots.append(
            AccountSnapshot(
                id=account.id,
                name=account.name,
                account_type=account.account_type,
                balance=summary.posted_balance if summary else quantize(account.opening_balance),
                include_in_safe_to_spend=account.include_in_safe_to_spend,
                is_liability=account.account_type == AccountType.CREDIT_CARD.value,
                is_archived=account.is_archived,
            )
        )

    pending_rows = db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user.id,
            Transaction.status == TransactionStatus.PENDING.value,
            Transaction.tx_type.in_(
                [
                    TransactionType.PURCHASE.value,
                    TransactionType.BILL_PAYMENT.value,
                    TransactionType.TRANSFER.value,
                ]
            ),
        )
        .order_by(Transaction.txn_date)
    ).scalars().all()
    pending = [
        PendingItem(
            id=txn.id,
            account_id=txn.account_id,
            amount=txn.amount,
            tx_type=txn.tx_type,
            counter_account_id=txn.transfer_account_id,
        )
        for txn in pending_rows
    ]

    horizon_end, payday = planning_horizon(db, user, today)
    bill_reserves: list[BillReserveItem] = []
    for occurrence in horizon_candidates(db, user.id, today, horizon_end):
        bill = occurrence.bill
        if bill is None or not bill.is_active or not bill.reserve_in_safe_to_spend:
            continue
        if occurrence.remaining_amount <= ZERO:
            continue
        bill_reserves.append(
            BillReserveItem(
                occurrence_id=occurrence.id,
                bill_id=bill.id,
                bill_name=bill.name,
                due_date=occurrence.due_date,
                amount=occurrence.remaining_amount,
                is_overdue=occurrence.due_date < today,
                is_essential=bill.is_essential,
                category_id=bill.category_id,
            )
        )

    reserve_rows = db.scalars(
        select(PlannedReserve).where(
            PlannedReserve.user_id == user.id,
            PlannedReserve.is_active.is_(True),
            PlannedReserve.start_date <= today,
        )
    ).all()
    reserves = [
        ReserveItem(
            id=row.id,
            name=row.name,
            amount=quantize(row.amount),
            is_savings=row.is_savings,
        )
        for row in reserve_rows
        if row.end_date is None or row.end_date >= today
    ]

    return SafeToSpendInputs(
        today=today,
        horizon_end=horizon_end,
        accounts=snapshots,
        pending=pending,
        bills=bill_reserves,
        reserves=reserves,
        minimum_buffer=quantize(prefs.minimum_balance_buffer) if prefs else ZERO,
        include_pending_debits=prefs.include_pending_debits if prefs else True,
        payday=payday,
        currency=user.currency,
        last_transaction_date=last_transaction_date(db, user.id),
        as_of=utc_now(),
    )


def compute(db: Session, user: User) -> SafeToSpendResult:
    return calculate_safe_to_spend(build_inputs(db, user))


def category_availability(
    db: Session,
    user: User,
    category_id: uuid.UUID,
    *,
    overall: SafeToSpendResult | None = None,
    today: date | None = None,
) -> CategoryAvailability:
    today = today or today_in(user.timezone)
    overall = overall or compute(db, user)
    row = budget_category_row(db, user.id, today.year, today.month, category_id)
    if row is None:
        raise NotFoundError("Category not found.")
    horizon_end = overall.horizon_end
    from app.services.bills import horizon_candidates

    commitments = ZERO
    for occurrence in horizon_candidates(db, user.id, today, horizon_end):
        bill = occurrence.bill
        if bill and bill.category_id == category_id:
            commitments += occurrence.remaining_amount
    return calculate_category_availability(
        CategoryAvailabilityInputs(
            category_id=row.category_id,
            category_name=row.category_name,
            budgeted=row.allocated,
            spent=row.spent,
            carryover_in=row.carryover_in,
            upcoming_commitments=quantize(commitments),
        ),
        overall.safe_to_spend,
    )


def account_is_stale(db: Session, user: User, today: date | None = None) -> bool:
    today = today or today_in(user.timezone)
    latest = last_transaction_date(db, user.id)
    return latest is None or (today - latest).days > MAX_STALE_DAYS


def spending_last_month(
    db: Session, user: User, today: date | None = None
) -> Decimal:
    today = today or today_in(user.timezone)
    first, last = month_bounds(today.year, today.month)
    return quantize(sum(spending_by_category(db, user.id, first, last).values(), ZERO))
