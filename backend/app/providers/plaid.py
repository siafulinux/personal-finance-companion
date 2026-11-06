"""Plaid adapter (first real aggregator).

Only the endpoints the application actually needs are implemented: Link token creation,
public-token exchange, accounts, ``/transactions/sync`` and item removal. Everything is
translated into the provider-neutral types in ``app.providers.base`` and nothing about
Plaid leaks into the sync engine.

``/transactions/sync`` is the reason Plaid was chosen: it returns ``added`` / ``modified``
/ ``removed`` with an opaque cursor, which maps directly onto the sync contract.

**Status: not exercised against Plaid's servers.** This deployment holds no Plaid
credentials. The adapter is covered by contract tests against a local fake endpoint that
implements Plaid's documented request/response shapes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx

from app.config import settings
from app.providers.base import (
    LinkResult,
    ProviderAccountData,
    ProviderAdapter,
    ProviderError,
    ProviderTransactionData,
    TransactionDelta,
)
from app.utils.money import quantize

_ENVIRONMENTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}

# Plaid account type/subtype -> this application's AccountType values.
_ACCOUNT_TYPE_MAP = {
    ("depository", "checking"): "checking",
    ("depository", "savings"): "savings",
    ("depository", "cd"): "savings",
    ("depository", "money market"): "savings",
    ("depository", "paypal"): "digital_wallet",
    ("depository", "prepaid"): "payment_app",
    ("credit", "credit card"): "credit_card",
    ("credit", "paypal"): "credit_card",
    ("loan", "student"): "other",
    ("loan", "mortgage"): "other",
    ("investment", "brokerage"): "other",
}

_REAUTH_CODES = {
    "ITEM_LOGIN_REQUIRED",
    "INVALID_ACCESS_TOKEN",
    "ITEM_LOCKED",
    "ITEM_NOT_FOUND",
    "ACCESS_NOT_GRANTED",
    "PENDING_EXPIRATION",
}
_RATE_LIMIT_CODES = {"RATE_LIMIT_EXCEEDED", "TRANSACTIONS_LIMIT"}


def _map_account_type(plaid_type: str | None, subtype: str | None) -> str:
    return _ACCOUNT_TYPE_MAP.get(
        ((plaid_type or "").lower(), (subtype or "").lower()), "other"
    )


def _txn_date(raw: str | None) -> date:
    if not raw:
        raise ProviderError(
            "A provider transaction is missing its date.", code="bad_payload", retryable=False
        )
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ProviderError(
            "A provider transaction has an unparseable date.",
            code="bad_payload",
            retryable=False,
        ) from exc


def _map_transaction(
    row: dict, account_types: dict[str, str], account_currency: dict[str, str]
) -> ProviderTransactionData:
    account_id = row.get("account_id")
    if not account_id:
        raise ProviderError(
            "A provider transaction is missing its account.",
            code="bad_payload",
            retryable=False,
        )
    # Plaid: positive amount = money leaving the account.
    raw_amount = Decimal(str(row.get("amount", "0")))
    category = (
        (row.get("personal_finance_category") or {}).get("primary")
        or (row.get("category") or [None])[0]
    )
    category = str(category) if category else None
    is_credit_account = account_types.get(account_id) == "credit_card"

    if category in {"TRANSFER_IN", "TRANSFER_OUT"} or str(
        (row.get("personal_finance_category") or {}).get("detailed", "")
    ).startswith(("TRANSFER_IN", "TRANSFER_OUT")):
        # Resolved into a single internal transfer by the sync engine.
        tx_type = "transfer_out" if raw_amount > 0 else "transfer_in"
        amount = abs(raw_amount)
    elif raw_amount < 0:
        tx_type = "refund" if is_credit_account else "income"
        amount = -raw_amount
    else:
        tx_type = "purchase"
        amount = raw_amount

    return ProviderTransactionData(
        external_id=str(row.get("transaction_id")),
        account_external_id=str(account_id),
        description=(row.get("name") or row.get("merchant_name") or "Provider transaction")[:255],
        amount=quantize(amount),
        tx_type=tx_type,
        txn_date=_txn_date(row.get("date")),
        posting_date=_txn_date(row.get("authorized_date")) if row.get("authorized_date") else None,
        merchant=(row.get("merchant_name") or None),
        pending=bool(row.get("pending", False)),
        provider_category=category,
        pending_external_id=row.get("pending_transaction_id") or None,
    )


class PlaidProvider(ProviderAdapter):
    name = "plaid"
    display_name = "Plaid"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        secret: str | None = None,
        environment: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.client_id = client_id or settings.plaid_client_id
        self.secret = secret or settings.plaid_secret
        self.environment = (environment or settings.plaid_environment).lower()
        env_url = _ENVIRONMENTS.get(self.environment, _ENVIRONMENTS["sandbox"])
        self.base_url = (base_url or settings.plaid_base_url or env_url).rstrip("/")
        self._client = client
        self._timeout = timeout

    # --- plumbing -----------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.client_id and self.secret)

    def can_schedule(self) -> bool:
        return True

    def _post(self, path: str, payload: dict) -> dict:
        if not self.is_configured():
            raise ProviderError(
                "Plaid is not configured on this server (PLAID_CLIENT_ID / PLAID_SECRET).",
                code="not_configured",
                retryable=False,
            )
        body = {"client_id": self.client_id, "secret": self.secret, **payload}
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            response = client.post(f"{self.base_url}{path}", json=body)
        except httpx.HTTPError as exc:
            # Network failures are retryable; the message never includes the payload, so
            # no token can leak into logs.
            raise ProviderError(
                "Could not reach the financial data provider.", code="network_error"
            ) from exc
        finally:
            if self._client is None:
                client.close()

        if response.status_code >= 500:
            raise ProviderError(
                "The financial data provider is temporarily unavailable.",
                code="provider_unavailable",
            )
        if response.status_code >= 400:
            try:
                error = response.json()
            except ValueError:
                error = {}
            code = str(error.get("error_code") or f"http_{response.status_code}")
            message = str(
                error.get("display_message")
                or error.get("error_message")
                or "The financial data provider rejected the request."
            )
            if code in _REAUTH_CODES:
                raise ProviderError(message, code=code, requires_reauth=True, retryable=False)
            if code in _RATE_LIMIT_CODES:
                raise ProviderError(message, code="rate_limited", retryable=True)
            raise ProviderError(
                message, code=code, retryable=code.startswith("INTERNAL_SERVER")
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                "The financial data provider returned an unreadable response.",
                code="bad_payload",
            ) from exc

    # --- contract -----------------------------------------------------------
    def create_link_token(self, user_id: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "user": {"client_user_id": user_id},
            "client_name": "Personal Finance Companion",
            "products": ["transactions"],
            "country_codes": ["US"],
            "language": "en",
        }
        if settings.plaid_webhook_url:
            payload["webhook"] = settings.plaid_webhook_url
        data = self._post("/link/token/create", payload)
        return {
            "provider": self.name,
            "link_token": data.get("link_token"),
            "expires_in": 1800,
            "mode": "hosted",
            "environment": self.environment,
        }

    def complete_link(self, public_token: str) -> LinkResult:
        data = self._post("/item/public_token/exchange", {"public_token": public_token})
        access_token = data.get("access_token")
        item_id = data.get("item_id")
        if not access_token or not item_id:
            raise ProviderError(
                "The provider did not return an access token.", code="bad_payload"
            )
        institution_name = "Connected institution"
        institution_id = None
        try:
            item = self._post("/item/get", {"access_token": access_token})
            institution_id = (item.get("item") or {}).get("institution_id")
            if institution_id:
                info = self._post(
                    "/institutions/get_by_id",
                    {"institution_id": institution_id, "country_codes": ["US"]},
                )
                institution_name = (info.get("institution") or {}).get(
                    "name", institution_name
                )
        except ProviderError:
            # Naming is cosmetic: never fail a successful link over it.
            pass
        return LinkResult(
            access_token=access_token,
            external_item_id=item_id,
            institution_name=institution_name,
            institution_id=institution_id,
            history_start=None,
        )

    def list_accounts(self, access_token: str) -> list[ProviderAccountData]:
        data = self._post("/accounts/get", {"access_token": access_token})
        accounts: list[ProviderAccountData] = []
        for row in data.get("accounts", []):
            balances = row.get("balances") or {}
            current = balances.get("current")
            if current is None:
                current = balances.get("available") or "0"
            # A credit-card balance from the provider is money owed; this application
            # stores it as a positive liability figure.
            accounts.append(
                ProviderAccountData(
                    external_id=str(row.get("account_id")),
                    name=str(row.get("name") or "Account")[:120],
                    account_type=_map_account_type(row.get("type"), row.get("subtype")),
                    balance=quantize(abs(Decimal(str(current)))),
                    currency=str(balances.get("iso_currency_code") or "USD"),
                    mask=row.get("mask"),
                    credit_limit=(
                        quantize(Decimal(str(balances["limit"])))
                        if balances.get("limit") is not None
                        else None
                    ),
                )
            )
        return accounts

    def sync_page(
        self, access_token: str, cursor: str | None, count: int = 100
    ) -> TransactionDelta:
        payload: dict[str, object] = {"access_token": access_token, "count": count}
        if cursor:
            payload["cursor"] = cursor
        data = self._post("/transactions/sync", payload)

        accounts = self.list_accounts(access_token)
        account_types = {a.external_id: a.account_type for a in accounts}
        account_currency = {a.external_id: a.currency for a in accounts}

        def convert(rows: list[dict]) -> list[ProviderTransactionData]:
            return [_map_transaction(r, account_types, account_currency) for r in rows]

        return TransactionDelta(
            added=convert(data.get("added") or []),
            modified=convert(data.get("modified") or []),
            removed=[str(r.get("transaction_id")) for r in (data.get("removed") or [])],
            next_cursor=data.get("next_cursor"),
            has_more=bool(data.get("has_more", False)),
        )

    def remove_item(self, access_token: str) -> None:
        try:
            self._post("/item/remove", {"access_token": access_token})
        except ProviderError as exc:
            # Already revoked is a success for our purposes.
            if exc.code in {"ITEM_NOT_FOUND", "INVALID_ACCESS_TOKEN"}:
                return
            raise
