"""Savings goals and the contributions made towards them.

Two kinds of saving are modelled, and they must never both be deducted:

``virtual``
    The money stays in a spend-eligible account but the engine treats the goal's
    saved amount as committed. It is subtracted from Safe-to-Spend.

``account``
    The money sits in its own savings account. If that account is excluded from
    spending (the usual case) nothing more is subtracted, because the balance was
    never spendable in the first place. If the owner deliberately keeps the
    savings account spend-eligible, its balance is protected by the goal instead
    of being counted twice.
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
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import Frequency, SavingsMode, SavingsStatus


class SavingsGoal(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "savings_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    mode: Mapped[str] = mapped_column(
        str_enum(SavingsMode, "savings_mode_enum"),
        nullable=False,
        server_default=SavingsMode.VIRTUAL.value,
    )
    # For ``virtual`` goals this is the protected amount. For ``account`` goals it
    # records how much of the linked balance belongs to this goal; it is never
    # used to protect the same money a second time.
    saved_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    contribution_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    contribution_frequency: Mapped[str | None] = mapped_column(
        str_enum(Frequency, "savings_frequency_enum"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        str_enum(SavingsStatus, "savings_status_enum"),
        nullable=False,
        server_default=SavingsStatus.ACTIVE.value,
    )
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    contributions: Mapped[list["SavingsContribution"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_savings_goals_user_name"),
        CheckConstraint("target_amount > 0", name="savings_target_positive"),
        CheckConstraint("saved_amount >= 0", name="savings_saved_non_negative"),
        CheckConstraint(
            "contribution_amount IS NULL OR contribution_amount > 0",
            name="savings_contribution_positive",
        ),
        Index("ix_savings_goals_user_status", "user_id", "status"),
    )


class SavingsContribution(Base, UUIDPrimaryKey, TimestampMixin):
    """A record that money was set aside. Never a transfer on its own."""

    __tablename__ = "savings_contributions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("savings_goals.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    contributed_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when the user says the money really moved between accounts.
    is_transfer_recorded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    goal: Mapped[SavingsGoal] = relationship(back_populates="contributions")

    __table_args__ = (
        CheckConstraint("amount > 0", name="contribution_amount_positive"),
        Index("ix_savings_contributions_goal_date", "goal_id", "contributed_on"),
    )


class InsightDismissal(Base, UUIDPrimaryKey):
    """A recommendation the user has hidden, keyed by its stable identity."""

    __tablename__ = "insight_dismissals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_insight_dismissals_user_key"),
    )
