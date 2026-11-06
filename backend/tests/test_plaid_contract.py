"""Plaid adapter contract tests against a local fake endpoint.

These tests prove the adapter speaks Plaid's documented shapes and maps them correctly.
They do **not** prove connectivity to Plaid's servers: this deployment has no Plaid
credentials, and nothing here touches the network.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.plaid import PlaidProvider

D = Decimal


def _provider(handler, **kwargs) -> PlaidProvider:
    return PlaidProvider(
        client_id="test-client",
        secret="test-secret",
        base_url="https://plaid.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def test_unconfigured_provider_refuses_to_run():
    provider = PlaidProvider(client_id=None, secret=None)
    assert provider.is_configured() is False
    with pytest.raises(ProviderError) as exc:
        provider.create_link_token("user-1")
    assert exc.value.code == "not_configured"


def test_link_token_request_shape():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        seen["path"] = request.url.path
        return httpx.Response(200, json={"link_token": "link-sandbox-abc", "expiration": "..."})

    data = _provider(handler).create_link_token("user-42")
    assert data["link_token"] == "link-sandbox-abc"
    assert seen["path"] == "/link/token/create"
    assert seen["client_id"] == "test-client"
    assert seen["user"] == {"client_user_id": "user-42"}
    assert seen["products"] == ["transactions"]
    assert seen["country_codes"] == ["US"]


def test_accounts_are_mapped_and_credit_is_signed_by_the_caller():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/accounts/get":
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "account_id": "acc-checking",
                            "name": "Plaid Checking",
                            "type": "depository",
                            "subtype": "checking",
                            "mask": "0000",
                            "balances": {"current": 110.5, "available": 100.0, "iso_currency_code": "USD"},
                        },
                        {
                            "account_id": "acc-card",
                            "name": "Plaid Credit Card",
                            "type": "credit",
                            "subtype": "credit card",
                            "mask": "3333",
                            "balances": {"current": 410.0, "limit": 2000, "iso_currency_code": "USD"},
                        },
                    ]
                },
            )
        raise AssertionError(request.url.path)

    accounts = _provider(handler).list_accounts("access-token")
    assert [a.external_id for a in accounts] == ["acc-checking", "acc-card"]
    assert accounts[0].account_type == "checking"
    assert accounts[0].balance == D("110.50")
    assert accounts[1].account_type == "credit_card"
    assert accounts[1].credit_limit == D("2000.00")


def test_transactions_sync_maps_direction_pending_and_transfers():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/accounts/get":
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "account_id": "acc-checking",
                            "name": "Checking",
                            "type": "depository",
                            "subtype": "checking",
                            "balances": {"current": 500, "iso_currency_code": "USD"},
                        },
                        {
                            "account_id": "acc-card",
                            "name": "Card",
                            "type": "credit",
                            "subtype": "credit card",
                            "balances": {"current": 100, "iso_currency_code": "USD"},
                        },
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "added": [
                    {
                        "transaction_id": "tx-out",
                        "account_id": "acc-checking",
                        "name": "WHOLE FOODS",
                        "merchant_name": "Whole Foods",
                        "amount": 42.5,
                        "date": "2026-11-01",
                        "pending": False,
                        "personal_finance_category": {"primary": "FOOD_AND_DRINK"},
                    },
                    {
                        "transaction_id": "tx-pending",
                        "account_id": "acc-card",
                        "name": "AMAZON",
                        "amount": 68.42,
                        "date": "2026-11-05",
                        "pending": True,
                    },
                    {
                        "transaction_id": "tx-transfer-out",
                        "account_id": "acc-checking",
                        "name": "TRANSFER TO SAVINGS",
                        "amount": 200.0,
                        "date": "2026-11-02",
                        "pending": False,
                        "personal_finance_category": {"primary": "TRANSFER_OUT"},
                    },
                    {
                        "transaction_id": "tx-refund",
                        "account_id": "acc-card",
                        "name": "TARGET RETURN",
                        "amount": -42.99,
                        "date": "2026-11-03",
                        "pending": False,
                    },
                    {
                        "transaction_id": "tx-payroll",
                        "account_id": "acc-checking",
                        "name": "ACME PAYROLL",
                        "amount": -2340.0,
                        "date": "2026-11-04",
                        "pending": False,
                    },
                ],
                "modified": [
                    {
                        "transaction_id": "tx-out",
                        "account_id": "acc-checking",
                        "name": "WHOLE FOODS",
                        "amount": 45.0,
                        "date": "2026-11-01",
                        "pending": False,
                    }
                ],
                "removed": [{"transaction_id": "tx-gone"}],
                "next_cursor": "cursor-2",
                "has_more": False,
            },
        )

    delta = _provider(handler).sync_page("access-token", "cursor-1")
    by_id = {t.external_id: t for t in delta.added}

    assert by_id["tx-out"].tx_type == "purchase"
    assert by_id["tx-out"].amount == D("42.50")
    assert by_id["tx-out"].merchant == "Whole Foods"

    # Pending-ness is a flag; the sync engine turns it into transaction status.
    assert by_id["tx-pending"].pending is True
    assert by_id["tx-pending"].posting_date is None

    # Transfer legs are surfaced as legs; the engine decides how to pair them.
    assert by_id["tx-transfer-out"].tx_type == "transfer_out"
    assert by_id["tx-transfer-out"].amount == D("200.00")

    # A negative amount on a credit account is a refund, on a depository account income.
    assert by_id["tx-refund"].tx_type == "refund"
    assert by_id["tx-payroll"].tx_type == "income"
    assert by_id["tx-payroll"].amount == D("2340.00")

    assert len(delta.modified) == 1
    assert delta.modified[0].amount == D("45.00")
    assert delta.removed == ["tx-gone"]
    assert delta.next_cursor == "cursor-2"
    assert delta.has_more is False


def test_pending_transaction_id_is_carried_for_reconciliation():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/accounts/get":
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "account_id": "acc-checking",
                            "name": "Checking",
                            "type": "depository",
                            "subtype": "checking",
                            "balances": {"current": 500},
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "added": [
                    {
                        "transaction_id": "tx-posted",
                        "pending_transaction_id": "tx-pending",
                        "account_id": "acc-checking",
                        "name": "AMAZON",
                        "amount": 68.42,
                        "date": "2026-11-06",
                        "pending": False,
                    }
                ],
                "modified": [],
                "removed": [],
                "next_cursor": "c",
                "has_more": False,
            },
        )

    delta = _provider(handler).sync_page("token", None)
    assert delta.added[0].pending_external_id == "tx-pending"


def test_reauth_error_is_classified():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error_type": "ITEM_ERROR",
                "error_code": "ITEM_LOGIN_REQUIRED",
                "error_message": "the login details of this item have changed",
                "display_message": "Please reconnect your account.",
            },
        )

    with pytest.raises(ProviderError) as exc:
        _provider(handler).sync_page("token", None)
    assert exc.value.code == "ITEM_LOGIN_REQUIRED"
    assert exc.value.requires_reauth is True
    assert exc.value.retryable is False


def test_rate_limit_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error_code": "RATE_LIMIT_EXCEEDED", "error_message": "slow down"}
        )

    with pytest.raises(ProviderError) as exc:
        _provider(handler).sync_page("token", None)
    assert exc.value.code == "rate_limited"
    assert exc.value.retryable is True
    assert exc.value.requires_reauth is False


def test_network_failure_is_retryable_and_leaks_nothing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(ProviderError) as exc:
        _provider(handler).sync_page("secret-access-token", None)
    assert exc.value.retryable is True
    assert "secret-access-token" not in exc.value.message
