"""Auth, onboarding and preference schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import settings
from app.models.enums import IncomeFrequency, Theme
from app.schemas.common import APIModel, Money, ORMModel, clean_optional_text


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="America/New_York", max_length=64)
    currency: Literal["USD"] = "USD"

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Display name is required.")
        return cleaned


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(APIModel):
    """A password change, confirmed with the password that is in use now.

    There is no ``confirm_password`` field: matching the two new entries is a form
    concern, and a second copy of a secret in the payload buys nothing.
    """

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    csrf_token: str | None = None


class PreferenceOut(ORMModel):
    minimum_balance_buffer: Decimal
    safe_to_spend_horizon_days: int
    include_pending_debits: bool
    auto_bill_matching: bool
    match_window_before_days: int
    match_window_after_days: int
    match_tolerance_amount: Decimal
    match_tolerance_percent: Decimal
    auto_match_threshold: Decimal
    suggestion_threshold: Decimal
    week_starts_on: int
    theme: Theme


class NotificationPreferenceOut(ORMModel):
    shopping_assistant_enabled: bool
    bill_reminders_enabled: bool
    low_money_warnings_enabled: bool
    favorite_store_reminders_enabled: bool
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    quiet_hours_timezone: str | None
    location_features_opted_in: bool


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    timezone: str
    currency: str
    is_demo: bool
    onboarding_completed_at: datetime | None
    created_at: datetime


class ProfileOut(BaseModel):
    user: UserOut
    preferences: PreferenceOut
    notification_preferences: NotificationPreferenceOut


class ProfileUpdate(APIModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: Literal["USD"] | None = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Display name is required.")
        return cleaned


class IncomeSourceCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    amount: Money = Field(gt=0)
    frequency: IncomeFrequency
    next_payday: date | None = None
    account_id: uuid.UUID | None = None
    notes: str | None = None

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        return clean_optional_text(v)


class IncomeSourceUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    amount: Money | None = Field(default=None, gt=0)
    frequency: IncomeFrequency | None = None
    next_payday: date | None = None
    account_id: uuid.UUID | None = None
    is_active: bool | None = None
    notes: str | None = None


class IncomeSourceOut(ORMModel):
    id: uuid.UUID
    name: str
    amount: Decimal
    frequency: IncomeFrequency
    next_payday: date | None
    account_id: uuid.UUID | None
    is_active: bool
    notes: str | None


class PreferencesUpdate(APIModel):
    minimum_balance_buffer: Money | None = Field(default=None, ge=0)
    safe_to_spend_horizon_days: int | None = Field(default=None, ge=1, le=60)
    include_pending_debits: bool | None = None
    auto_bill_matching: bool | None = None
    match_window_before_days: int | None = Field(default=None, ge=0, le=30)
    match_window_after_days: int | None = Field(default=None, ge=0, le=60)
    match_tolerance_amount: Money | None = Field(default=None, ge=0, le=1000)
    match_tolerance_percent: Money | None = Field(default=None, ge=0, le=50)
    auto_match_threshold: Decimal | None = Field(default=None, ge=0.5, le=1)
    suggestion_threshold: Decimal | None = Field(default=None, ge=0, le=0.95)
    week_starts_on: int | None = Field(default=None, ge=0, le=6)
    theme: Theme | None = None


class NotificationPreferencesUpdate(APIModel):
    shopping_assistant_enabled: bool | None = None
    bill_reminders_enabled: bool | None = None
    low_money_warnings_enabled: bool | None = None
    favorite_store_reminders_enabled: bool | None = None
    quiet_hours_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_timezone: str | None = Field(default=None, max_length=64)
    location_features_opted_in: bool | None = None


class OnboardingAccount(APIModel):
    name: str = Field(min_length=1, max_length=120)
    account_type: str = "checking"
    opening_balance: Money = Field(default=Decimal("0"))
    include_in_safe_to_spend: bool = True


class OnboardingRequest(APIModel):
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(min_length=1, max_length=64)
    currency: Literal["USD"] = "USD"
    income_amount: Money | None = Field(default=None, gt=0)
    income_frequency: IncomeFrequency | None = None
    next_payday: date | None = None
    starting_balance: Money = Decimal("0")
    minimum_balance_buffer: Money = Field(default=Decimal("0"), ge=0)
    accounts: list[OnboardingAccount] = Field(default_factory=list, max_length=20)
    use_default_categories: bool = True
    seed_budget: bool = False

    @field_validator("accounts")
    @classmethod
    def _dedupe_accounts(cls, accounts: list[OnboardingAccount]) -> list[OnboardingAccount]:
        names = [a.name.strip().lower() for a in accounts]
        if len(names) != len(set(names)):
            raise ValueError("Account names must be unique.")
        return accounts


class DataExportOut(BaseModel):
    exported_at: datetime
    user: dict
    accounts: list[dict]
    categories: list[dict]
    transactions: list[dict]
    budgets: list[dict]
    bills: list[dict]
    bill_occurrences: list[dict]
    bill_payment_matches: list[dict]
    reserves: list[dict]
    income_sources: list[dict]
    imports: list[dict]


class DeleteAccountRequest(APIModel):
    password: str = Field(min_length=1, max_length=256)
    confirm: str = Field(description="Type DELETE to confirm permanent deletion.")

    @field_validator("confirm")
    @classmethod
    def _confirm(cls, v: str) -> str:
        if v != "DELETE":
            raise ValueError("Type DELETE exactly to confirm.")
        return v


def password_policy_hint() -> str:
    return f"At least {settings.password_min_length} characters, with letters and numbers."
