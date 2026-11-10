"""Savings goal and contribution schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.models.enums import Frequency, SavingsMode, SavingsStatus
from app.schemas.common import APIModel, Money, ORMModel, clean_optional_text


class SavingsGoalCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Money = Field(gt=0)
    target_date: date | None = None
    mode: SavingsMode = SavingsMode.VIRTUAL
    saved_amount: Money = Field(default=Decimal("0"), ge=0)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    contribution_amount: Money | None = Field(default=None, gt=0)
    contribution_frequency: Frequency | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    notes: str | None = None
    mark_complete: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return value.strip()

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @model_validator(mode="after")
    def _rules(self):
        # An account-backed goal without an account is a contradiction the engine
        # cannot resolve; ask for the account instead of guessing later.
        if self.mode == SavingsMode.ACCOUNT and self.account_id is None:
            raise ValueError("Account-backed goals need the savings account they live in.")
        if self.contribution_amount is not None and self.contribution_frequency is None:
            raise ValueError("A planned contribution needs a frequency.")
        return self


class SavingsGoalUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: Money | None = Field(default=None, gt=0)
    target_date: date | None = None
    mode: SavingsMode | None = None
    saved_amount: Money | None = Field(default=None, ge=0)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    contribution_amount: Money | None = Field(default=None, ge=0)
    contribution_frequency: Frequency | None = None
    status: SavingsStatus | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    notes: str | None = None
    sort_order: int | None = None


class SavingsContributionCreate(APIModel):
    amount: Money = Field(gt=0)
    contributed_on: date | None = None
    note: str | None = None


class SavingsContributionOut(ORMModel):
    id: uuid.UUID
    goal_id: uuid.UUID
    amount: Decimal
    contributed_on: date
    note: str | None
    created_at: datetime


class SavingsGoalOut(ORMModel):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    target_date: date | None
    mode: SavingsMode
    saved_amount: Decimal
    account_id: uuid.UUID | None
    account_name: str | None = None
    account_balance: Decimal | None = None
    account_is_spendable: bool | None = None
    category_id: uuid.UUID | None
    contribution_amount: Decimal | None
    contribution_frequency: Frequency | None
    status: SavingsStatus
    color: str | None
    notes: str | None
    created_at: datetime
    # Derived.
    progress_percent: Decimal
    remaining_to_target: Decimal
    protected_amount: Decimal
    protects_money: bool
    next_contribution_date: date | None
    required_per_period: Decimal | None
    projected_completion: date | None


class SavingsSummary(APIModel):
    total_target: Decimal
    total_saved: Decimal
    total_protected: Decimal
    active_goals: int
    completed_goals: int
    monthly_commitment: Decimal
    goals: list[SavingsGoalOut]
