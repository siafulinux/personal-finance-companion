"""Provider-independent financial connectivity contract.

Everything the sync engine needs from an aggregator lives here. Adding Teller, Finicity or
MX later means writing one adapter and registering it; the sync engine, the API and the
database are unaffected.

Adapters deal only in normalised, provider-neutral values. They never see a database
session and never decide how a transaction is stored.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class ProviderError(RuntimeError):
    """A provider call failed in a way the caller can reason about.

    ``retryable`` drives the link's backoff; ``requires_reauth`` means the user must
    reconnect before anything can succeed, so retrying on a timer is pointless.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        retryable: bool = True,
        requires_reauth: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.requires_reauth = requires_reauth


class ProviderNotConfigured(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider is not configured on this server.",
            code="not_configured",
            retryable=False,
        )


@dataclass(frozen=True)
class ProviderAccountData:
    external_id: str
    name: str
    account_type: str  # one of app.models.enums.AccountType values
    balance: Decimal
    currency: str = "USD"
    mask: str | None = None
    credit_limit: Decimal | None = None


@dataclass(frozen=True)
class ProviderTransactionData:
    external_id: str
    account_external_id: str
    description: str
    amount: Decimal  # always positive; direction is carried by ``tx_type``
    tx_type: str  # TransactionType value
    txn_date: date
    posting_date: date | None = None
    merchant: str | None = None
    pending: bool = False
    provider_category: str | None = None
    # Providers that replace a pending row with a new posted row set this to the old id,
    # which lets the sync engine reconcile in place instead of leaving an orphan.
    pending_external_id: str | None = None


@dataclass
class TransactionDelta:
    added: list[ProviderTransactionData] = field(default_factory=list)
    modified: list[ProviderTransactionData] = field(default_factory=list)
    # External ids only: a provider may report a removal it will not describe further.
    removed: list[str] = field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


@dataclass(frozen=True)
class LinkResult:
    """What ``complete_link`` yields after the user approves an institution."""

    access_token: str
    external_item_id: str
    institution_name: str
    institution_id: str | None = None
    history_start: date | None = None


class ProviderAdapter(ABC):
    """One aggregator."""

    name: str
    display_name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """True when this server holds the credentials needed to use the provider."""

    @abstractmethod
    def create_link_token(self, user_id: str) -> dict[str, object]:
        """Start a linking flow. Returns at least ``link_token`` and ``provider``."""

    @abstractmethod
    def complete_link(self, public_token: str) -> LinkResult:
        """Exchange the user's approval for a long-lived access token."""

    @abstractmethod
    def list_accounts(self, access_token: str) -> list[ProviderAccountData]: ...

    @abstractmethod
    def sync_page(
        self, access_token: str, cursor: str | None, count: int = 100
    ) -> TransactionDelta:
        """One page of incremental changes. ``cursor=None`` means "from the beginning"."""

    @abstractmethod
    def remove_item(self, access_token: str) -> None:
        """Revoke access at the provider. Must be safe to call twice."""

    # --- optional capability, implemented by adapters that support scheduled sync ---
    def can_schedule(self) -> bool:
        return False
