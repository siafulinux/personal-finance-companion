"""Loan and advance schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.models.enums import BalanceSource, Frequency, LoanStatus, LoanType, MatchStatus
from app.schemas.common import APIModel, Money, ORMModel, clean_optional_text


class LoanCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    lender: str | None = Field(default=None, max_length=120)
    loan_type: LoanType = LoanType.PERSONAL
    original_amount: Money = Field(gt=0)
    # Outstanding right now, not the amount originally borrowed.
    opening_balance: Money = Field(ge=0)
    balance_as_of: date | None = None
    apr: Decimal | None = Field(default=None, ge=0, le=1000)
    interest_charged: Money | None = Field(default=None, ge=0)
    fees_charged: Money | None = Field(default=None, ge=0)
    next_payment_date: date | None = None
    scheduled_payment: Money | None = Field(default=None, gt=0)
    payment_frequency: Frequency | None = None
    remaining_payments: int | None = Field(default=None, ge=0, le=2000)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    status: LoanStatus = LoanStatus.ACTIVE
    notes: str | None = None

    @field_validator("name", "lender")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class LoanUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    lender: str | None = Field(default=None, max_length=120)
    loan_type: LoanType | None = None
    original_amount: Money | None = Field(default=None, gt=0)
    # Correcting the starting balance is allowed; the audit trail is the payment list.
    opening_balance: Money | None = Field(default=None, ge=0)
    balance_as_of: date | None = None
    apr: Decimal | None = Field(default=None, ge=0, le=1000)
    interest_charged: Money | None = Field(default=None, ge=0)
    fees_charged: Money | None = Field(default=None, ge=0)
    next_payment_date: date | None = None
    scheduled_payment: Money | None = Field(default=None, gt=0)
    payment_frequency: Frequency | None = None
    remaining_payments: int | None = Field(default=None, ge=0, le=2000)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    status: LoanStatus | None = None
    notes: str | None = None


class LoanPaymentCreate(APIModel):
    amount: Money = Field(gt=0)
    paid_on: date | None = None
    principal_amount: Money | None = Field(default=None, ge=0)
    interest_amount: Money | None = Field(default=None, ge=0)
    fee_amount: Money | None = Field(default=None, ge=0)
    transaction_id: uuid.UUID | None = None
    notes: str | None = None
    # A payment recorded by hand is a statement of fact; a suggested match is not.
    confirm: bool = True

    @model_validator(mode="after")
    def _split_not_greater(self):
        parts = [
            value
            for value in (self.principal_amount, self.interest_amount, self.fee_amount)
            if value is not None
        ]
        if parts and sum(parts) > self.amount:
            raise ValueError("Principal, interest and fees cannot add up to more than the payment.")
        return self


class LoanPaymentUpdate(APIModel):
    amount: Money | None = Field(default=None, gt=0)
    paid_on: date | None = None
    principal_amount: Money | None = Field(default=None, ge=0)
    interest_amount: Money | None = Field(default=None, ge=0)
    fee_amount: Money | None = Field(default=None, ge=0)
    notes: str | None = None


class LoanPaymentOut(ORMModel):
    id: uuid.UUID
    loan_id: uuid.UUID
    transaction_id: uuid.UUID | None
    amount: Decimal
    principal_amount: Decimal | None
    interest_amount: Decimal | None
    fee_amount: Decimal | None
    paid_on: date
    status: MatchStatus
    confidence: Decimal
    is_automatic: bool
    is_ambiguous: bool
    reason: str | None
    notes: str | None
    created_at: datetime
    transaction_description: str | None = None
    transaction_merchant: str | None = None


class LoanOut(ORMModel):
    id: uuid.UUID
    name: str
    lender: str | None
    loan_type: LoanType
    original_amount: Decimal
    opening_balance: Decimal
    balance_as_of: date
    balance_source: BalanceSource
    apr: Decimal | None
    interest_charged: Decimal | None
    fees_charged: Decimal | None
    next_payment_date: date | None
    scheduled_payment: Decimal | None
    payment_frequency: Frequency | None
    remaining_payments: int | None
    account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    status: LoanStatus
    notes: str | None
    created_at: datetime
    # Derived, read-only. ``is_ensemble`` style flags make it obvious which
    # numbers are facts and which came from incomplete terms.
    current_balance: Decimal
    principal_repaid: Decimal
    interest_paid: Decimal
    fees_paid: Decimal
    total_repaid: Decimal
    balance_is_estimate: bool
    progress_percent: Decimal
    payment_count: int
    last_payment_date: date | None
    estimated_payoff_date: date | None
    payoff_is_estimate: bool
    remaining_installments: int | None


class LoanSummary(APIModel):
    total_outstanding: Decimal
    total_original: Decimal
    active_loans: int
    next_payment_date: date | None
    next_payment_total: Decimal
    loans: list[LoanOut]


class LoanPaymentSuggestion(APIModel):
    transaction_id: uuid.UUID
    description: str
    merchant: str | None
    amount: Decimal
    txn_date: date
    account_id: uuid.UUID
    confidence: Decimal
    reason: str
    is_ambiguous: bool


class LoanPaymentSuggestions(APIModel):
    loan_id: uuid.UUID
    loan_name: str
    items: list[LoanPaymentSuggestion]
