"""Phase 2 connectivity: provider links, encrypted tokens and sync history."""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import (
    CategorySource,
    Frequency,
    ProviderLinkStatus,
    RecurringStatus,
    SuggestionSource,
    SuggestionStatus,
    SyncStatus,
    SyncTrigger,
)


class ProviderLink(Base, UUIDPrimaryKey, TimestampMixin):
    """One connected institution (a Plaid *Item*, a Teller enrollment, …).

    The cursor is the whole incremental-sync contract: it is written in the same
    transaction as the rows it produced, so a crash re-reads a page instead of
    skipping it.
    """

    __tablename__ = "provider_links"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_item_id: Mapped[str] = mapped_column(String(160), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(160), nullable=False)
    institution_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        str_enum(ProviderLinkStatus, "provider_link_status_enum"),
        nullable=False,
        server_default=ProviderLinkStatus.ACTIVE.value,
    )
    # Opaque provider cursor; untouched by the application except to store it.
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Explicit consent to pull data from this institution.
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    secret: Mapped[ProviderLinkSecret | None] = relationship(
        back_populates="link", cascade="all, delete-orphan", uselist=False
    )
    accounts: Mapped[list["FinancialAccount"]] = relationship(  # noqa: F821
        back_populates="provider_link"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "external_item_id", name="uq_provider_links_user_item"
        ),
        Index("ix_provider_links_user_status", "user_id", "status"),
        Index("ix_provider_links_due", "status", "next_retry_at"),
    )


class ProviderLinkSecret(Base):
    """AES-GCM ciphertext for a provider access token. Never serialised to a client."""

    __tablename__ = "provider_link_secrets"

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_links.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    link: Mapped[ProviderLink] = relationship(back_populates="secret")


class SyncRun(Base, UUIDPrimaryKey):
    """Immutable history of one sync attempt, successful or not."""

    __tablename__ = "sync_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_links.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger: Mapped[str] = mapped_column(
        str_enum(SyncTrigger, "sync_trigger_enum"),
        nullable=False,
        server_default=SyncTrigger.MANUAL.value,
    )
    status: Mapped[str] = mapped_column(
        str_enum(SyncStatus, "sync_status_enum"),
        nullable=False,
        server_default=SyncStatus.RUNNING.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accounts_linked: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    added: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    modified: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    removed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped_duplicates: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    suggestions_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unmatched_pending: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_sync_runs_user_started", "user_id", "started_at"),
        Index("ix_sync_runs_link_started", "link_id", "started_at"),
    )


class CategorySuggestion(Base, UUIDPrimaryKey, TimestampMixin):
    """A reversible category proposal. Accepting it sets ``category_source='user'``."""

    __tablename__ = "category_suggestions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source: Mapped[str] = mapped_column(
        str_enum(SuggestionSource, "suggestion_source_enum"),
        nullable=False,
        server_default=SuggestionSource.RULE.value,
    )
    status: Mapped[str] = mapped_column(
        str_enum(SuggestionStatus, "suggestion_status_enum"),
        nullable=False,
        server_default=SuggestionStatus.SUGGESTED.value,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "category_id", name="uq_category_suggestions_tx_category"
        ),
        Index("ix_category_suggestions_user_status", "user_id", "status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_unit_range"),
    )


class RecurringSeries(Base, UUIDPrimaryKey, TimestampMixin):
    """A charge pattern detected from history (candidate bill or subscription)."""

    __tablename__ = "recurring_series"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    merchant_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    average_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    last_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    frequency: Mapped[str] = mapped_column(
        str_enum(Frequency, "recurring_frequency_enum"), nullable=False
    )
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    next_expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    is_subscription: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        str_enum(RecurringStatus, "recurring_status_enum"),
        nullable=False,
        server_default=RecurringStatus.DETECTED.value,
    )
    bill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bills.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "merchant_key", name="uq_recurring_series_user_merchant"),
        Index("ix_recurring_series_user_status", "user_id", "status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_unit_range"),
    )


__all__ = [
    "CategorySuggestion",
    "CategorySource",
    "ProviderLink",
    "ProviderLinkSecret",
    "RecurringSeries",
    "SyncRun",
]
