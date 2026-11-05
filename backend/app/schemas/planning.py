"""Budgets, bills, reserves and calendar schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.models.enums import Frequency, MatchStatus, OccurrenceStatus
from app.schemas.common import APIModel, Money, ORMModel, clean_optional_text
from app.utils.money import money as to_money


class BudgetAllocationInput(APIModel):
    category_id: uuid.UUID
    amount: Money = Field(ge=0)
    carryover_enabled: bool = False
    notes: str | None = None


class BudgetCreate(APIModel):
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    planned_income: Money | None = Field(default=None, ge=0)
    allocations: list[BudgetAllocationInput] = Field(default_factory=list, max_length=100)

    @field_validator("allocations")
    @classmethod
    def _unique_categories(cls, items: list[BudgetAllocationInput]):
        ids = [i.category_id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each category may only appear once in a budget.")
        return items


class BudgetUpdate(APIModel):
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    planned_income: Money | None = Field(default=None, ge=0)
    allocations: list[BudgetAllocationInput] | None = Field(default=None, max_length=100)

    @field_validator("allocations")
    @classmethod
    def _unique_categories(cls, items: list[BudgetAllocationInput] | None):
        if items is None:
            return None
        ids = [i.category_id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each category may only appear once in a budget.")
        return items


class CategoryBudgetRow(APIModel):
    category_id: uuid.UUID
    category_name: str
    category_color: str
    category_kind: str
    allocated: Decimal
    carryover_in: Decimal
    carryover_enabled: bool
    spent: Decimal
    remaining: Decimal
    percent_used: Decimal
    upcoming_commitments: Decimal
    previous_month_spent: Decimal
    trend_percent: Decimal | None
    transaction_count: int


class BudgetSummary(APIModel):
    id: uuid.UUID
    year: int
    month: int
    start_date: date | None = None
    end_date: date | None = None
    name: str | None
    notes: str | None
    planned_income: Decimal | None = None
    total_allocated: Decimal
    total_carryover: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    percent_used: Decimal
    income_this_month: Decimal
    unallocated: Decimal
    rows: list[CategoryBudgetRow]
    created_from_wizard: bool


class BudgetCopyRequest(APIModel):
    source_year: int = Field(ge=2000, le=2200)
    source_month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    adjust_percent: Decimal = Field(default=Decimal("0"), ge=-100, le=100)


class WizardPriority(APIModel):
    category_id: uuid.UUID
    weight: int = Field(ge=0, le=10, default=3)


class BudgetWizardRequest(APIModel):
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    expected_income: Money = Field(gt=0)
    savings_target_percent: Decimal = Field(default=Decimal("10"), ge=0, le=80)
    priorities: list[WizardPriority] = Field(default_factory=list, max_length=50)
    include_existing_bills: bool = True
    notes: str | None = None


class BillCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    merchant: str | None = Field(default=None, max_length=160)
    expected_amount: Money = Field(gt=0)
    minimum_amount: Money | None = Field(default=None, ge=0)
    due_day: int | None = Field(default=None, ge=1, le=31)
    anchor_date: date | None = None
    first_due_date: date | None = None
    frequency: Frequency = Frequency.MONTHLY
    custom_interval_days: int | None = Field(default=None, ge=1, le=400)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    notes: str | None = None
    is_essential: bool = True
    reserve_in_safe_to_spend: bool = True
    is_active: bool = True
    auto_pay: bool = False

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        return clean_optional_text(v)

    @model_validator(mode="after")
    def _schedule(self):
        if self.anchor_date is None and self.first_due_date is None:
            raise ValueError("Provide the first due date for this bill.")
        if self.frequency == Frequency.CUSTOM and not self.custom_interval_days:
            raise ValueError("Custom schedules require custom_interval_days.")
        if (
            self.minimum_amount is not None
            and self.minimum_amount > self.expected_amount
        ):
            raise ValueError("Minimum amount cannot exceed the expected amount.")
        return self


class BillUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    merchant: str | None = Field(default=None, max_length=160)
    expected_amount: Money | None = Field(default=None, gt=0)
    minimum_amount: Money | None = Field(default=None, ge=0)
    due_day: int | None = Field(default=None, ge=1, le=31)
    anchor_date: date | None = None
    frequency: Frequency | None = None
    custom_interval_days: int | None = Field(default=None, ge=1, le=400)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    notes: str | None = None
    is_essential: bool | None = None
    reserve_in_safe_to_spend: bool | None = None
    is_active: bool | None = None
    auto_pay: bool | None = None


class BillOut(ORMModel):
    id: uuid.UUID
    name: str
    merchant: str | None
    expected_amount: Decimal
    minimum_amount: Decimal | None
    due_day: int | None
    anchor_date: date
    frequency: Frequency
    custom_interval_days: int | None
    account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    notes: str | None
    is_essential: bool
    reserve_in_safe_to_spend: bool
    is_active: bool
    auto_pay: bool
    created_at: datetime


class BillWithSummary(BillOut):
    next_due_date: date | None = None
    next_remaining: Decimal = Decimal("0")
    is_overdue: bool = False
    paid_this_year: Decimal = Decimal("0")


class OccurrenceOut(APIModel):
    id: uuid.UUID
    bill_id: uuid.UUID
    bill_name: str | None
    merchant: str | None
    category_id: uuid.UUID | None
    account_id: uuid.UUID | None
    due_date: date
    expected_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    status: OccurrenceStatus
    is_overdue: bool
    is_essential: bool
    is_partial: bool
    confirmed_at: datetime | None
    notes: str | None


class BillCalendarOut(APIModel):
    year: int
    month: int
    start_date: date
    end_date: date
    occurrences: list[OccurrenceOut]
    totals: dict[str, str]


class BillPaymentCreate(APIModel):
    occurrence_id: uuid.UUID
    transaction_id: uuid.UUID | None = None
    amount: Money | None = Field(default=None, gt=0)
    account_id: uuid.UUID | None = None
    paid_on: date | None = None
    notes: str | None = None
    confirm: bool = True

    @model_validator(mode="after")
    def _needs_source(self):
        if self.transaction_id is None and self.account_id is None:
            raise ValueError("Provide a transaction to link or an account to pay from.")
        return self


class RecordPaymentRequest(APIModel):
    amount: Money | None = Field(default=None, gt=0)
    account_id: uuid.UUID
    paid_on: date | None = None
    notes: str | None = None


class MarkPaidRequest(APIModel):
    notes: str | None = None


class MatchOut(APIModel):
    id: uuid.UUID
    occurrence_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: Decimal
    confidence: Decimal
    status: MatchStatus
    is_automatic: bool
    is_ambiguous: bool
    reason: str | None
    confirmed_at: datetime | None
    bill_name: str | None = None
    due_date: date | None = None
    transaction_description: str | None = None
    transaction_amount: Decimal | None = None
    transaction_date: date | None = None
    transaction_merchant: str | None = None


class MatchSuggestion(APIModel):
    transaction_id: uuid.UUID
    transaction_description: str
    transaction_merchant: str | None
    transaction_amount: Decimal
    transaction_date: date
    account_id: uuid.UUID
    candidates: list[dict]


class ReserveCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    amount: Money = Field(gt=0)
    is_savings: bool = False
    category_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    start_date: date
    end_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date.")
        return self


class ReserveUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    amount: Money | None = Field(default=None, gt=0)
    is_savings: bool | None = None
    category_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class ReserveOut(ORMModel):
    id: uuid.UUID
    name: str
    amount: Decimal
    is_savings: bool
    category_id: uuid.UUID | None
    account_id: uuid.UUID | None
    start_date: date
    end_date: date | None
    is_active: bool
    notes: str | None


class MerchantAliasCreate(APIModel):
    alias: str = Field(min_length=2, max_length=160)
    canonical_merchant: str = Field(min_length=2, max_length=160)
    notes: str | None = None


class MerchantAliasOut(ORMModel):
    id: uuid.UUID
    alias: str
    canonical_merchant: str
    notes: str | None


def normalize_amount(value: Decimal) -> Decimal:
    return to_money(value)
