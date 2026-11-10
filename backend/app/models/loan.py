"""Loans and advances, plus the bank transactions that repay them.

A loan is a liability the user tracks themselves unless a provider reports it.
The balance is derived from ``opening_balance`` (the outstanding amount when the
loan was added) minus the principal portion of confirmed repayments. When a
repayment was recorded without a principal/interest split the arithmetic still
works, but the result is flagged as an estimate rather than presented as fact.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import MONEY, QUANTITY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import (
    BalanceSource,
    Frequency,
    LoanStatus,
    LoanType,
    MatchStatus,
)


class Loan(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "loans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    lender: Mapped[str | None] = mapped_column(String(120), nullable=True)
    loan_type: Mapped[str] = mapped_column(
        str_enum(LoanType, "loan_type_enum"), nullable=False, server_default=LoanType.PERSONAL.value
    )
    original_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Outstanding balance at ``balance_as_of``. Never recomputed in place: the
    # service adds confirmed principal repayments to it, so editing history stays
    # explainable.
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    balance_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    balance_source: Mapped[str] = mapped_column(
        str_enum(BalanceSource, "loan_balance_source_enum"),
        nullable=False,
        server_default=BalanceSource.USER.value,
    )
    # Annual percentage rate, e.g. 24.990 for 24.99%. Nullable: many BNPL and
    # payday products do not publish one, and guessing would be worse than blank.
    apr: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    interest_charged: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    fees_charged: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    next_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scheduled_payment: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    payment_frequency: Mapped[str | None] = mapped_column(
        str_enum(Frequency, "loan_frequency_enum"), nullable=True
    )
    remaining_payments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The bank account repayments are debited from, when known.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        str_enum(LoanStatus, "loan_status_enum"),
        nullable=False,
        server_default=LoanStatus.ACTIVE.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    payments: Mapped[list["LoanPayment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_loans_user_name"),
        CheckConstraint("original_amount > 0", name="original_amount_positive"),
        CheckConstraint("opening_balance >= 0", name="opening_balance_non_negative"),
        CheckConstraint("apr IS NULL OR apr >= 0", name="apr_non_negative"),
        CheckConstraint(
            "scheduled_payment IS NULL OR scheduled_payment > 0",
            name="scheduled_payment_positive",
        ),
        Index("ix_loans_user_status", "user_id", "status"),
    )


class LoanPayment(Base, UUIDPrimaryKey, TimestampMixin):
    """A repayment, optionally linked to the bank transaction that paid it."""

    __tablename__ = "loan_payments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True
    )
    # Total that left the bank account.
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Split of that total. Null means "not broken down", which makes the derived
    # balance an estimate instead of a statement of fact.
    principal_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    interest_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    fee_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        str_enum(MatchStatus, "loan_payment_status_enum"),
        nullable=False,
        server_default=MatchStatus.CONFIRMED.value,
    )
    confidence: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, server_default="1.000")
    is_automatic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_ambiguous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    loan: Mapped[Loan] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount > 0", name="loan_payment_amount_positive"),
        CheckConstraint(
            "principal_amount IS NULL OR principal_amount >= 0",
            name="principal_non_negative",
        ),
        CheckConstraint(
            "interest_amount IS NULL OR interest_amount >= 0",
            name="interest_non_negative",
        ),
        CheckConstraint("fee_amount IS NULL OR fee_amount >= 0", name="fee_non_negative"),
        # One transaction cannot repay two loans.
        Index(
            "uq_loan_payments_transaction",
            "transaction_id",
            unique=True,
            postgresql_where=text("transaction_id IS NOT NULL"),
        ),
        Index("ix_loan_payments_user_paid", "user_id", "paid_on"),
        Index("ix_loan_payments_loan_status", "loan_id", "status"),
    )

    @property
    def effective_principal(self) -> Decimal:
        """Principal reduction, falling back to the whole amount when unsplit."""
        if self.principal_amount is not None:
            return self.principal_amount
        return self.amount
