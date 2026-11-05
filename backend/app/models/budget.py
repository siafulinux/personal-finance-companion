"""Monthly budgets, category allocations and planned reserves."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey


class Budget(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "budgets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Income the user planned this budget around (used for the unallocated figure).
    planned_income: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    created_from_wizard: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    allocations: Mapped[list["BudgetAllocation"]] = relationship(
        back_populates="budget", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uq_budgets_user_period"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
        Index("ix_budgets_user_period", "user_id", "year", "month"),
    )


class BudgetAllocation(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "budget_allocations"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    carryover_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    budget: Mapped[Budget] = relationship(back_populates="allocations")
    category: Mapped["Category"] = relationship()  # noqa: F821

    __table_args__ = (
        UniqueConstraint("budget_id", "category_id", name="uq_budget_allocations_budget_category"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )


class PlannedReserve(Base, UUIDPrimaryKey, TimestampMixin):
    """Explicit money the user wants set aside (savings or future expenses)."""

    __tablename__ = "planned_reserves"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    is_savings: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        Index("ix_planned_reserves_user_active", "user_id", "is_active"),
    )
