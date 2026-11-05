"""Bills, their generated occurrences, payment matches and merchant aliases."""

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
from app.models.enums import Frequency, MatchStatus, OccurrenceStatus


class Bill(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "bills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    expected_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    minimum_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    frequency: Mapped[str] = mapped_column(
        str_enum(Frequency, "bill_frequency_enum"), nullable=False
    )
    custom_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_essential: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    reserve_in_safe_to_spend: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    auto_pay: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # How far back occurrences are generated / how far forward the calendar is materialised.
    occurrences_generated_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship()  # noqa: F821
    occurrences: Mapped[list["BillOccurrence"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("expected_amount > 0", name="expected_amount_positive"),
        CheckConstraint(
            "minimum_amount IS NULL OR (minimum_amount >= 0 AND minimum_amount <= expected_amount)",
            name="minimum_amount_valid",
        ),
        CheckConstraint(
            "frequency <> 'custom' OR custom_interval_days IS NOT NULL",
            name="custom_interval_required",
        ),
        Index("ix_bills_user_active", "user_id", "is_active"),
    )


class BillOccurrence(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "bill_occurrences"

    bill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(
        str_enum(OccurrenceStatus, "occurrence_status_enum"),
        nullable=False,
        server_default=OccurrenceStatus.UPCOMING.value,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    bill: Mapped[Bill] = relationship(back_populates="occurrences")
    matches: Mapped[list["BillPaymentMatch"]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("bill_id", "due_date", name="uq_bill_occurrences_bill_due"),
        CheckConstraint("paid_amount >= 0", name="paid_non_negative"),
        Index("ix_bill_occurrences_user_due", "user_id", "due_date"),
        Index("ix_bill_occurrences_user_status", "user_id", "status"),
    )

    @property
    def remaining_amount(self) -> Decimal:
        remaining = (self.expected_amount or Decimal("0")) - (self.paid_amount or Decimal("0"))
        return remaining if remaining > 0 else Decimal("0.00")


class BillPaymentMatch(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "bill_payment_matches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_occurrences.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(
        str_enum(MatchStatus, "match_status_enum"),
        nullable=False,
        server_default=MatchStatus.SUGGESTED.value,
    )
    is_automatic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_ambiguous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    occurrence: Mapped[BillOccurrence] = relationship(back_populates="matches")
    transaction: Mapped["Transaction"] = relationship(back_populates="bill_matches")  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "occurrence_id", name="uq_bill_payment_matches_tx_occurrence"
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_bill_payment_matches_user_status", "user_id", "status"),
        # A single transaction may fund at most one bill occurrence.
        Index(
            "uq_bill_payment_matches_confirmed_transaction",
            "transaction_id",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
    )


class MerchantAlias(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "merchant_aliases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    canonical_merchant: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "alias", name="uq_merchant_aliases_user_alias"),
        Index("ix_merchant_aliases_user", "user_id"),
    )
