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
class ProviderInstitution:
    """One institution as a provider's directory describes it.

    The flags are the point: a provider listing an institution does not mean it can serve
transactions and balances for it, and the selection service must not assume otherwise.
    """

    provider: str
    institution_id: str
    name: str
    products: tuple[str, ...] = ()
    supports_transactions: bool = False
    supports_balances: bool = False
    account_types: tuple[str, ...] = ()
    note: str | None = None

    def supports(self, *, transactions: bool = True, balances: bool = True) -> bool:
        if transactions and not self.supports_transactions:
            return False
        if balances and not self.supports_balances:
            return False
        return True


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
    def create_link_token(
        self, user_id: str, institution_id: str | None = None
    ) -> dict[str, object]:
        """Start a linking flow. Returns at least ``link_token`` and ``provider``.

        ``institution_id`` lets the caller start the flow on the institution the user
        already chose, instead of asking them to pick it twice. Adapters whose flow has
        no institution handle simply ignore it.
        """

    @abstractmethod
    def complete_link(
        self,
        public_token: str,
        payload: dict | None = None,
        *,
        today: date | None = None,
    ) -> LinkResult:
        """Exchange the user's approval for a long-lived access token.

        ``public_token`` is the credential the provider's own flow returned. ``payload``
        carries the rest of the provider's hand-off for adapters that mint their token in
        the client instead of exchanging one server-side (Teller Connect does this).

        ``today`` is the *user's* local date, not the server's, for the same reason
        ``sync_page`` takes it: ``history_start`` is ``today`` minus the adapter's
        history window, and the caller dates the opening balance of every account from
        it. A server clock ahead of the user (a UTC container, an evening in the
        Americas) would otherwise open a connection whose window, and whose opening
        balance, start in the user's future, where every "up to today" query drops
        them. Adapters that let the provider decide the window ignore it.
        """

    @abstractmethod
    def list_accounts(self, access_token: str) -> list[ProviderAccountData]: ...

    @abstractmethod
    def sync_page(
        self,
        access_token: str,
        cursor: str | None,
        count: int = 100,
        *,
        today: date | None = None,
    ) -> TransactionDelta:
        """One page of incremental changes. ``cursor=None`` means "from the beginning".

        ``today`` is the *user's* local date, not the server's. An adapter that
        describes recent activity has to date it from the day the user is living in:
        a server clock in a timezone ahead of theirs (a UTC container, an evening in
        the Americas) would otherwise stamp rows into the user's future, where every
        "today"-relative query drops them. Adapters driven by a provider cursor
        ignore it.
        """

    @abstractmethod
    def remove_item(self, access_token: str) -> None:
        """Revoke access at the provider. Must be safe to call twice."""

    # --- optional capability, implemented by adapters that support scheduled sync ---
    def can_schedule(self) -> bool:
        return False

    # --- optional directory + health, used by provider selection and the admin screen ---
    def list_institutions(self, query: str | None = None) -> list[ProviderInstitution]:
        """The provider's institution directory, optionally filtered by name.

        Raising here is meaningful: a provider without a directory cannot take part in
        institution-first selection, and the caller reports that instead of offering a
        picker that would fail later.
        """
        raise ProviderError(
            f"{self.display_name} does not publish an institution directory.",
            code="no_directory",
            retryable=False,
        )

    def check_connection(self) -> dict[str, object]:
        """Prove this server's credentials work, for the administrator's test button.

        Returns a small, non-secret summary. Raises :class:`ProviderError` with a code
        the admin UI can explain (``not_configured``, ``bad_credentials``, …).
        """
        raise ProviderError(
            f"{self.display_name} does not support a connection test.",
            code="unsupported",
            retryable=False,
        )
