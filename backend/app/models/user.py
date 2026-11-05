"""User, preferences, notification preferences and income sources."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint, func, text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import IncomeFrequency, Theme


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    preferences: Mapped["UserPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    notification_preferences: Mapped["NotificationPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    accounts: Mapped[list["FinancialAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    income_sources: Mapped[list["IncomeSource"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )


class UserPreference(Base, TimestampMixin):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    minimum_balance_buffer: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, server_default="0"
    )
    safe_to_spend_horizon_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="14"
    )
    include_pending_debits: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    auto_bill_matching: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    match_window_before_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    match_window_after_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="7"
    )
    match_tolerance_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, server_default="2.00"
    )
    match_tolerance_percent: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, server_default="1.00"
    )
    auto_match_threshold: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, server_default="0.85"
    )
    suggestion_threshold: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, server_default="0.55"
    )
    week_starts_on: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    theme: Mapped[str] = mapped_column(
        str_enum(Theme, "theme_enum"), nullable=False, server_default="system"
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class NotificationPreference(Base, TimestampMixin):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    shopping_assistant_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    bill_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    low_money_warnings_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    favorite_store_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_hours_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Phase 5 (Android geofencing) reads these; no location is collected in Phase 1.
    location_features_opted_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    user: Mapped[User] = relationship(back_populates="notification_preferences")


class IncomeSource(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "income_sources"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    frequency: Mapped[str] = mapped_column(
        str_enum(IncomeFrequency, "income_frequency_enum"), nullable=False
    )
    next_payday: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="income_sources")

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_income_sources_user_name"),)
