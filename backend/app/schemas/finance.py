"""Account, category and transaction schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.models.enums import (
    AccountType,
    CategoryKind,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.schemas.common import APIModel, Money, ORMModel, clean_optional_text


class AccountCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    account_type: AccountType
    opening_balance: Money = Decimal("0")
    # Optional on purpose: a client that omits it gets the *user's* local today from
    # the server, so a device whose clock is wrong (or in another timezone) cannot
    # date the opening balance into the user's future. An explicit value is kept as
    # given, because back-dating an account is a legitimate thing to do.
    opening_balance_date: date | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    include_in_safe_to_spend: bool = True
    credit_limit: Money | None = Field(default=None, ge=0)
    # A minimum payment the owner typed in. Safe-to-Spend reserves it; nothing
    # derives it from the balance.
    minimum_payment: Money | None = Field(default=None, ge=0)
    description: str | None = None
    institution: str | None = None
    sort_order: int = 0

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        if v.upper() != "USD":
            raise ValueError("Phase 1 supports USD accounts only.")
        return "USD"

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return clean_optional_text(v)

    @model_validator(mode="after")
    def _credit_card_rules(self):
        if self.account_type == AccountType.CREDIT_CARD:
            # Credit is a liability: never part of spendable cash.
            self.include_in_safe_to_spend = False
        return self


class AccountUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    account_type: AccountType | None = None
    opening_balance: Money | None = None
    opening_balance_date: date | None = None
    include_in_safe_to_spend: bool | None = None
    credit_limit: Money | None = Field(default=None, ge=0)
    minimum_payment: Money | None = Field(default=None, ge=0)
    description: str | None = None
    institution: str | None = None
    sort_order: int | None = None
    is_archived: bool | None = None


class AccountBalanceOut(ORMModel):
    id: uuid.UUID
    name: str
    account_type: AccountType
    currency: str
    opening_balance: Decimal
    opening_balance_date: date
    include_in_safe_to_spend: bool
    credit_limit: Decimal | None
    minimum_payment: Decimal | None = None
    description: str | None
    institution: str | None
    is_archived: bool
    created_at: datetime


class AccountOut(AccountBalanceOut):
    balance: Decimal
    pending_balance: Decimal
    available_balance: Decimal
    total_inflows: Decimal
    total_outflows: Decimal
    transaction_count: int


class AccountAdjustmentCreate(APIModel):
    target_balance: Money
    reason: str = Field(min_length=3, max_length=255)


class AccountAdjustmentOut(ORMModel):
    id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    previous_balance: Decimal
    new_balance: Decimal
    reason: str
    created_at: datetime


class CategoryCreate(APIModel):
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind = CategoryKind.EXPENSE
    color: str = Field(default="#64748b", pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str | None = Field(default=None, max_length=40)
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class CategoryUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str | None = Field(default=None, max_length=40)
    is_archived: bool | None = None
    sort_order: int | None = None


class CategoryOut(ORMModel):
    id: uuid.UUID
    name: str
    kind: CategoryKind
    color: str
    icon: str | None
    is_archived: bool
    is_system: bool
    sort_order: int


class TransactionCreate(APIModel):
    account_id: uuid.UUID
    description: str = Field(min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=160)
    amount: Money = Field(gt=0)
    tx_type: TransactionType
    status: TransactionStatus = TransactionStatus.POSTED
    txn_date: date
    posting_date: date | None = None
    category_id: uuid.UUID | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    transfer_account_id: uuid.UUID | None = None
    external_id: str | None = Field(default=None, max_length=160)
    source: TransactionSource = TransactionSource.MANUAL

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Description is required.")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _tags(cls, tags: list[str]) -> list[str]:
        cleaned = [t.strip()[:40] for t in tags if t.strip()]
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def _transfer_rules(self):
        if self.tx_type == TransactionType.TRANSFER:
            if not self.transfer_account_id:
                raise ValueError("Transfers require a destination account.")
            if self.transfer_account_id == self.account_id:
                raise ValueError("A transfer needs two different accounts.")
        elif self.transfer_account_id is not None:
            raise ValueError("Only transfers can target a second account.")
        return self


class TransactionUpdate(APIModel):
    account_id: uuid.UUID | None = None
    description: str | None = Field(default=None, min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=160)
    amount: Money | None = Field(default=None, gt=0)
    tx_type: TransactionType | None = None
    status: TransactionStatus | None = None
    txn_date: date | None = None
    posting_date: date | None = None
    category_id: uuid.UUID | None = None
    notes: str | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    transfer_account_id: uuid.UUID | None = None


class TransactionOut(ORMModel):
    id: uuid.UUID
    account_id: uuid.UUID
    transfer_account_id: uuid.UUID | None
    description: str
    merchant: str | None
    amount: Decimal
    tx_type: TransactionType
    status: TransactionStatus
    txn_date: date
    posting_date: date | None
    category_id: uuid.UUID | None
    notes: str | None
    tags: list[str]
    source: TransactionSource
    external_id: str | None
    import_id: uuid.UUID | None
    created_at: datetime
    account_name: str | None = None
    transfer_account_name: str | None = None
    category_name: str | None = None
    category_color: str | None = None


class TransactionPage(ORMModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int
    totals: dict[str, str]


class TransactionListParams(APIModel):
    search: str | None = None
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    merchant: str | None = None
    tx_type: TransactionType | None = None
    status: TransactionStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_amount: Money | None = None
    max_amount: Money | None = None
    sort: str = "-txn_date"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=100000)


class DuplicateCandidate(APIModel):
    transaction_id: uuid.UUID
    description: str
    amount: Decimal
    txn_date: date
    account_id: uuid.UUID
    reason: str


class TransactionCreateResponse(APIModel):
    transaction: TransactionOut
    match_info: dict | None = None
    possible_duplicates: list[DuplicateCandidate] = Field(default_factory=list)


class AccountSummary(APIModel):
    total_cash: Decimal
    total_debt: Decimal
    net_worth: Decimal
    accounts: list[AccountOut]
