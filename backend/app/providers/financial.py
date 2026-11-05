"""Financial data provider adapter (Phase 4 live bank connections).

Phase 1 never connects to an institution. The interface exists so accounts,
transactions and imports keep one shape when a supported aggregator is added.
Credentials must come from an authorized OAuth flow, never from user-entered
banking passwords.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ProviderAccount:
    external_id: str
    name: str
    account_type: str
    balance: Decimal
    currency: str = "USD"


@dataclass(frozen=True)
class ProviderTransaction:
    external_id: str
    account_external_id: str
    posted_on: date
    description: str
    amount: Decimal
    merchant: str | None = None
    pending: bool = False


class FinancialDataProvider(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def list_accounts(self, user_id: str) -> list[ProviderAccount]: ...

    @abstractmethod
    def list_transactions(
        self, user_id: str, since: date, until: date | None = None
    ) -> list[ProviderTransaction]: ...


class NoFinancialProvider(FinancialDataProvider):
    """Phase 1: manual accounts only."""

    name = "manual"

    def is_configured(self) -> bool:
        return True

    def list_accounts(self, user_id: str) -> list[ProviderAccount]:
        return []

    def list_transactions(
        self, user_id: str, since: date, until: date | None = None
    ) -> list[ProviderTransaction]:
        return []
