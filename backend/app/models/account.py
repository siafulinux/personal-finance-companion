"""Financial accounts, balance adjustments and categories."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import AccountType, CategoryKind


class FinancialAccount(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "financial_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str] = mapped_column(
        str_enum(AccountType, "account_type_enum"), nullable=False
    )
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    opening_balance_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    include_in_safe_to_spend: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    institution: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Phase 4 integrations: which adapter produced this account, if any.
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped["User"] = relationship(back_populates="accounts")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_financial_accounts_user_name"),
        Index("ix_financial_accounts_user_active", "user_id", "is_archived"),
    )

    @property
    def is_liability(self) -> bool:
        return self.account_type == AccountType.CREDIT_CARD.value


class BalanceAdjustment(Base, UUIDPrimaryKey):
    """Immutable audit trail for manual balance corrections."""

    __tablename__ = "balance_adjustments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    previous_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    new_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )


class Category(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "categories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(
        str_enum(CategoryKind, "category_kind_enum"), nullable=False, server_default="expense"
    )
    color: Mapped[str] = mapped_column(String(9), nullable=False, server_default="#64748b")
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_categories_user_name"),
        Index("ix_categories_user_archived", "user_id", "is_archived"),
    )
