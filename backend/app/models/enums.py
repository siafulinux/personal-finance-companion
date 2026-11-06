"""Enumerations shared across models, schemas and services."""

from __future__ import annotations

from enum import StrEnum


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    DIGITAL_WALLET = "digital_wallet"
    PAYMENT_APP = "payment_app"
    CREDIT_CARD = "credit_card"
    OTHER = "other"

    @classmethod
    def cash_like(cls) -> set[str]:
        return {
            cls.CHECKING.value,
            cls.SAVINGS.value,
            cls.CASH.value,
            cls.DIGITAL_WALLET.value,
            cls.PAYMENT_APP.value,
            cls.OTHER.value,
        }


class TransactionType(StrEnum):
    INCOME = "income"
    PURCHASE = "purchase"
    BILL_PAYMENT = "bill_payment"
    REFUND = "refund"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"


class TransactionSource(StrEnum):
    MANUAL = "manual"
    CSV = "csv"
    PROVIDER = "provider"


class CategoryKind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    SAVINGS = "savings"
    DEBT = "debt"


class Frequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    EVERY_TWO_MONTHS = "every_two_months"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"
    CUSTOM = "custom"


class OccurrenceStatus(StrEnum):
    UPCOMING = "upcoming"
    PARTIAL = "partial"
    PAID = "paid"
    SKIPPED = "skipped"


class MatchStatus(StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ImportStatus(StrEnum):
    UPLOADED = "uploaded"
    PREVIEWED = "previewed"
    COMMITTED = "committed"
    FAILED = "failed"


class ImportRowStatus(StrEnum):
    IMPORTED = "imported"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class IncomeFrequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    SEMIMONTHLY = "semimonthly"
    MONTHLY = "monthly"
    IRREGULAR = "irregular"


class ProviderLinkStatus(StrEnum):
    ACTIVE = "active"
    ERROR = "error"
    REAUTH_REQUIRED = "reauth_required"
    DISCONNECTED = "disconnected"


class SyncStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class SyncTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    RECONNECT = "reconnect"


class SuggestionSource(StrEnum):
    RULE = "rule"
    HISTORY = "history"
    PROVIDER = "provider"


class SuggestionStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class CategorySource(StrEnum):
    """Who decided a transaction's category. Guards user-confirmed choices."""

    NONE = "none"
    USER = "user"
    RULE = "rule"
    IMPORT = "import"
    PROVIDER = "provider"


class RecurringStatus(StrEnum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class InsightSensitivity(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"
