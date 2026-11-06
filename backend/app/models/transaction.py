"""Transactions: the single source of truth for account balances."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import (
    CategorySource,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)


class Transaction(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    # Set only for internal transfers (including credit card payments).
    transfer_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tx_type: Mapped[str] = mapped_column(
        str_enum(TransactionType, "transaction_type_enum"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        str_enum(TransactionStatus, "transaction_status_enum"),
        nullable=False,
        server_default=TransactionStatus.POSTED.value,
    )
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # Who chose the category. ``user`` is never overwritten by automation.
    category_source: Mapped[str] = mapped_column(
        str_enum(CategorySource, "category_source_enum"),
        nullable=False,
        server_default=CategorySource.NONE.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default=text("'{}'::varchar[]")
    )
    source: Mapped[str] = mapped_column(
        str_enum(TransactionSource, "transaction_source_enum"),
        nullable=False,
        server_default=TransactionSource.MANUAL.value,
    )
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction_imports.id", ondelete="SET NULL"), nullable=True
    )
    # Stable fingerprint used to guarantee idempotent imports / no duplicates.
    dedupe_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["FinancialAccount"] = relationship(  # noqa: F821
        foreign_keys=[account_id]
    )
    transfer_account: Mapped["FinancialAccount | None"] = relationship(  # noqa: F821
        foreign_keys=[transfer_account_id]
    )
    category: Mapped["Category | None"] = relationship()  # noqa: F821
    bill_matches: Mapped[list["BillPaymentMatch"]] = relationship(  # noqa: F821
        back_populates="transaction", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(tx_type = 'transfer' AND transfer_account_id IS NOT NULL) OR "
            "(tx_type <> 'transfer' AND transfer_account_id IS NULL)",
            name="transfer_target_required",
        ),
        CheckConstraint(
            "transfer_account_id IS NULL OR transfer_account_id <> account_id",
            name="transfer_distinct_accounts",
        ),
        Index("ix_transactions_user_date", "user_id", "txn_date"),
        Index("ix_transactions_account_date", "account_id", "txn_date"),
        Index("ix_transactions_user_category_date", "user_id", "category_id", "txn_date"),
        Index("ix_transactions_user_merchant", "user_id", "merchant"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_transactions_user_dedupe_key"),
        Index("ix_transactions_import_id", "import_id"),
    )
