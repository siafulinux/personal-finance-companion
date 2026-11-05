"""Consistent account balance derivation from openings, transactions and adjustments."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import BalanceAdjustment, FinancialAccount, Transaction
from app.models.enums import TransactionStatus, TransactionType
from app.models.transaction import Transaction as Tx
from app.utils.money import ZERO, quantize

# Effect of each transaction type on the *source* account.
# A transfer additionally credits ``transfer_account_id`` by +amount (handled separately).
_CREDIT_TYPES = (TransactionType.INCOME.value, TransactionType.REFUND.value)


def _signed_case():
    return case((Tx.tx_type.in_(_CREDIT_TYPES), Tx.amount), else_=-Tx.amount)


@dataclass(frozen=True)
class BalanceSummary:
    account_id: uuid.UUID
    opening_balance: Decimal
    posted_delta: Decimal
    pending_delta: Decimal
    adjustments: Decimal
    inflows: Decimal
    outflows: Decimal
    transaction_count: int

    @property
    def posted_balance(self) -> Decimal:
        return quantize(self.opening_balance + self.posted_delta + self.adjustments)

    @property
    def pending_balance(self) -> Decimal:
        return quantize(self.pending_delta)

    @property
    def available_balance(self) -> Decimal:
        return quantize(self.posted_balance + self.pending_delta)


def balances_for_accounts(
    db: Session,
    user_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = None,
    *,
    include_archived: bool = False,
) -> dict[uuid.UUID, BalanceSummary]:
    """Single source of truth for every balance the application displays."""
    query = select(FinancialAccount).where(FinancialAccount.user_id == user_id)
    if not include_archived:
        query = query.where(FinancialAccount.is_archived.is_(False))
    if account_ids is not None:
        query = query.where(FinancialAccount.id.in_(account_ids))
    accounts = list(db.scalars(query))
    if not accounts:
        return {}
    ids = [a.id for a in accounts]

    own_rows = db.execute(
        select(
            Tx.account_id,
            Tx.status,
            func.coalesce(func.sum(_signed_case()), 0),
            func.count(Tx.id),
        )
        .where(Tx.user_id == user_id, Tx.account_id.in_(ids))
        .group_by(Tx.account_id, Tx.status)
    ).all()

    transfer_rows = db.execute(
        select(
            Tx.transfer_account_id,
            Tx.status,
            func.coalesce(func.sum(Tx.amount), 0),
        )
        .where(
            Tx.user_id == user_id,
            Tx.tx_type == TransactionType.TRANSFER.value,
            Tx.transfer_account_id.in_(ids),
        )
        .group_by(Tx.transfer_account_id, Tx.status)
    ).all()

    adjustment_rows = db.execute(
        select(
            BalanceAdjustment.account_id,
            func.coalesce(func.sum(BalanceAdjustment.amount), 0),
        )
        .where(BalanceAdjustment.user_id == user_id, BalanceAdjustment.account_id.in_(ids))
        .group_by(BalanceAdjustment.account_id)
    ).all()

    adjustments = {row[0]: quantize(row[1]) for row in adjustment_rows}

    posted: dict[uuid.UUID, Decimal] = {i: ZERO for i in ids}
    pending: dict[uuid.UUID, Decimal] = {i: ZERO for i in ids}
    inflows: dict[uuid.UUID, Decimal] = {i: ZERO for i in ids}
    outflows: dict[uuid.UUID, Decimal] = {i: ZERO for i in ids}
    counts: dict[uuid.UUID, int] = {i: 0 for i in ids}

    for account_id, status, total, count in own_rows:
        total = quantize(total or 0)
        if status == TransactionStatus.POSTED.value:
            posted[account_id] += total
            counts[account_id] += int(count)
        else:
            pending[account_id] += total

    for account_id, status, total in transfer_rows:
        total = quantize(total or 0)
        if status == TransactionStatus.POSTED.value:
            posted[account_id] += total
        else:
            pending[account_id] += total

    # Inflow/outflow statistics exclude internal transfers by construction and
    # treat refunds as a reduction of outflows.
    stat_rows = db.execute(
        select(
            Tx.account_id,
            Tx.tx_type,
            func.coalesce(func.sum(Tx.amount), 0),
        )
        .where(
            Tx.user_id == user_id,
            Tx.account_id.in_(ids),
            Tx.status == TransactionStatus.POSTED.value,
            Tx.tx_type.in_(
                [
                    TransactionType.INCOME.value,
                    TransactionType.REFUND.value,
                    TransactionType.PURCHASE.value,
                    TransactionType.BILL_PAYMENT.value,
                ]
            ),
        )
        .group_by(Tx.account_id, Tx.tx_type)
    ).all()
    for account_id, tx_type, total in stat_rows:
        total = quantize(total or 0)
        if tx_type == TransactionType.INCOME.value:
            inflows[account_id] += total
        elif tx_type == TransactionType.REFUND.value:
            outflows[account_id] -= total
        else:
            outflows[account_id] += total

    return {
        account.id: BalanceSummary(
            account_id=account.id,
            opening_balance=quantize(account.opening_balance),
            posted_delta=posted[account.id],
            pending_delta=pending[account.id],
            adjustments=adjustments.get(account.id, ZERO),
            inflows=quantize(inflows[account.id]),
            outflows=quantize(outflows[account.id]),
            transaction_count=counts[account.id],
        )
        for account in accounts
    }


def account_balance(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> BalanceSummary | None:
    return balances_for_accounts(
        db, user_id, [account_id], include_archived=True
    ).get(account_id)


def cash_effect(tx_type: str, amount: Decimal) -> Decimal:
    """Signed effect of a transaction on its source account (used in tests/forecasts)."""
    return amount if tx_type in _CREDIT_TYPES else -amount


def spending_by_category(
    db: Session,
    user_id: uuid.UUID,
    start: date,
    end: date,
    *,
    include_pending: bool = False,
) -> dict[uuid.UUID | None, Decimal]:
    """Net spending per category. Transfers never appear; refunds reduce spending."""
    statuses = [TransactionStatus.POSTED.value]
    if include_pending:
        statuses.append(TransactionStatus.PENDING.value)
    rows = db.execute(
        select(
            Tx.category_id,
            func.coalesce(func.sum(_signed_case()), 0),
        )
        .where(
            Tx.user_id == user_id,
            Tx.txn_date >= start,
            Tx.txn_date <= end,
            Tx.status.in_(statuses),
            Tx.tx_type.in_(
                [
                    TransactionType.PURCHASE.value,
                    TransactionType.BILL_PAYMENT.value,
                    TransactionType.REFUND.value,
                ]
            ),
        )
        .group_by(Tx.category_id)
    ).all()
    result: dict[uuid.UUID | None, Decimal] = {}
    for category_id, total in rows:
        # _signed_case is negative for purchases/bill payments and positive for refunds.
        spent = quantize(-(total or 0))
        result[category_id] = spent if spent > ZERO else ZERO
    return result


def period_totals(
    db: Session, user_id: uuid.UUID, start: date, end: date, *, include_pending: bool = False
) -> dict[str, Decimal]:
    statuses = [TransactionStatus.POSTED.value]
    if include_pending:
        statuses.append(TransactionStatus.PENDING.value)
    rows = db.execute(
        select(Tx.tx_type, func.coalesce(func.sum(Tx.amount), 0))
        .where(
            Tx.user_id == user_id,
            Tx.txn_date >= start,
            Tx.txn_date <= end,
            Tx.status.in_(statuses),
        )
        .group_by(Tx.tx_type)
    ).all()
    totals = {t.value: ZERO for t in TransactionType}
    for tx_type, total in rows:
        totals[tx_type] = quantize(total or 0)
    income = totals[TransactionType.INCOME.value]
    spending = (
        totals[TransactionType.PURCHASE.value]
        + totals[TransactionType.BILL_PAYMENT.value]
        - totals[TransactionType.REFUND.value]
    )
    transfers = totals[TransactionType.TRANSFER.value]
    return {
        "income": quantize(income),
        "spending": quantize(spending if spending > ZERO else ZERO),
        "transfers": quantize(transfers),
        "refunds": totals[TransactionType.REFUND.value],
        "net": quantize(income - spending),
    }
