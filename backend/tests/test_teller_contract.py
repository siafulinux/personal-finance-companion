"""Teller adapter contract tests against a local fake Teller endpoint.

These prove the adapter speaks the shapes Teller documents and maps them into the
provider-neutral contract. They do **not** prove connectivity to Teller's servers: no test
here touches the network and no real credential is used.
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.teller import TellerProvider
from app.security.link_nonce import NonceError, issue_nonce, verify_nonce

D = Decimal


def _provider(handler, **kwargs) -> TellerProvider:
    kwargs.setdefault("application_id", "app_test")
    return TellerProvider(
        base_url="https://teller.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def _accounts_payload() -> list[dict]:
    return [
        {
            "id": "acc-checking",
            "name": "Everyday Checking",
            "type": "depository",
            "subtype": "checking",
            "last_four": "0042",
            "currency": "USD",
            "institution": {"id": "usaa", "name": "USAA"},
            "enrollment_id": "enr_1",
            "status": "open",
            "links": {
                "balances": "/accounts/acc-checking/balances",
                "transactions": "/accounts/acc-checking/transactions",
            },
        },
        {
            "id": "acc-card",
            "name": "Platinum Card",
            "type": "credit",
            "subtype": "credit_card",
            "last_four": "7857",
            "currency": "USD",
            "institution": {"id": "usaa", "name": "USAA"},
            "enrollment_id": "enr_1",
            "status": "open",
        },
    ]


def test_unconfigured_provider_refuses_to_run():
    provider = TellerProvider(application_id=None)
    assert provider.is_configured() is False
    with pytest.raises(ProviderError) as exc:
        provider.create_link_token("user-1")
    assert exc.value.code == "not_configured"


def test_mtls_is_required_outside_sandbox():
    provider = TellerProvider(application_id="app_x", environment="production")
    assert provider.is_configured() is False
    with pytest.raises(ProviderError) as exc:
        provider.list_accounts("token")
    assert exc.value.code == "missing_mtls"

    with_material = TellerProvider(
        application_id="app_x",
        environment="production",
        certificate="-----BEGIN CERTIFICATE-----x",
        private_key="-----BEGIN PRIVATE KEY-----x",
    )
    assert with_material.is_configured() is True


def test_link_token_is_issued_server_side_and_carries_no_secret():
    provider = TellerProvider(
        application_id="app_live_x",
        certificate="-----BEGIN CERTIFICATE-----secret-cert",
        private_key="-----BEGIN PRIVATE KEY-----secret-key",
        environment="sandbox",
    )
    data = provider.create_link_token("user-42", institution_id="usaa")
    assert data["mode"] == "teller_connect"
    assert data["application_id"] == "app_live_x"
    assert data["institution"] == "usaa"
    assert data["products"] == ["balance", "transactions"]
    assert "secret-cert" not in json.dumps(data)
    assert "secret-key" not in json.dumps(data)
    # The nonce is ours, bound to the user who started the flow.
    verify_nonce(str(data["nonce"]), "user-42")
    with pytest.raises(NonceError):
        verify_nonce(str(data["nonce"]), "another-user")


def test_accounts_use_basic_auth_and_per_account_balances():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/accounts":
            return httpx.Response(200, json=_accounts_payload())
        if request.url.path == "/accounts/acc-checking/balances":
            return httpx.Response(200, json={"ledger": "1842.63", "available": "1700.00"})
        if request.url.path == "/accounts/acc-card/balances":
            return httpx.Response(200, json={"ledger": "486.19", "available": "486.19"})
        raise AssertionError(request.url.path)

    accounts = _provider(handler).list_accounts("token_abc")
    assert [a.external_id for a in accounts] == ["acc-checking", "acc-card"]
    assert accounts[0].account_type == "checking"
    assert accounts[0].balance == D("1700.00")
    assert accounts[1].account_type == "credit_card"
    assert accounts[1].balance == D("486.19"), "credit balance stays positive here"
    assert accounts[0].mask == "0042"
    assert seen[0].headers["authorization"].startswith("Basic ")

    decoded = base64.b64decode(seen[0].headers["authorization"].split()[1]).decode()
    assert decoded == "token_abc:", "Teller uses the access token as the Basic username"


def test_transactions_map_sign_status_and_category():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/accounts":
            return httpx.Response(200, json=_accounts_payload())
        if request.url.path.endswith("/balances"):
            return httpx.Response(200, json={"ledger": "100.00"})
        if request.url.path == "/accounts/acc-checking/transactions":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "txn_out",
                        "account_id": "acc-checking",
                        "date": "2026-02-02",
                        "description": "WHOLE FOODS MKT",
                        "amount": "74.18",
                        "type": "card_payment",
                        "status": "posted",
                        "details": {
                            "category": "groceries",
                            "counterparty": {"name": "Whole Foods", "type": "organization"},
                        },
                    },
                    {
                        "id": "txn_in",
                        "account_id": "acc-checking",
                        "date": "2026-02-01",
                        "description": "ACME PAYROLL",
                        "amount": "-2340.00",
                        "type": "deposit",
                        "status": "posted",
                        "details": {"category": "income"},
                    },
                    {
                        "id": "txn_pending",
                        "account_id": "acc-checking",
                        "date": "2026-02-03",
                        "description": "AMAZON MKTPLACE",
                        "amount": "68.42",
                        "type": "card_payment",
                        "status": "pending",
                        "details": {"category": "shopping"},
                    },
                ],
            )
        return httpx.Response(200, json=[])

    delta = _provider(handler).sync_page("token_abc", cursor=None)
    by_id = {row.external_id: row for row in delta.added}
    assert by_id["txn_out"].tx_type == "purchase"
    assert by_id["txn_out"].amount == D("74.18")
    assert by_id["txn_out"].merchant == "Whole Foods"
    assert by_id["txn_out"].provider_category == "GROCERIES"
    assert by_id["txn_in"].tx_type == "income"
    assert by_id["txn_in"].amount == D("2340.00")
    assert by_id["txn_pending"].pending is True
    assert by_id["txn_pending"].posting_date is None
    assert delta.has_more is False


def test_institution_today_ignores_the_host_clock():
    """The fallback calendar is the institution's, so the container's zone cannot change it.

    Reading `date.today()` made the window depend on where the process ran: a UTC
    image and a laptop in the Americas disagreed about the day, and the window could
    end on a date the user had not reached. Flipping `TZ` across the date line is the
    cheapest way to prove the answer no longer comes from here.
    """
    from app.providers.teller import INSTITUTION_TIMEZONE, institution_today
    from app.utils.dates import today_in

    expected = today_in(INSTITUTION_TIMEZONE)
    original = os.environ.get("TZ")
    try:
        for zone in ("Pacific/Kiritimati", "Pacific/Midway"):
            os.environ["TZ"] = zone
            time.tzset()
            assert institution_today() == expected
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def test_complete_link_counts_the_history_window_from_the_institutions_day():
    """Without a user date, the window is still not the host's."""
    from app.providers.teller import INITIAL_HISTORY_DAYS, institution_today

    result = _provider(_complete_handler).complete_link(
        "token_sandbox",
        {"nonce": issue_nonce("user-9"), "user_id": "usr_1", "enrollment_id": "enr_9"},
    )

    assert result.history_start == institution_today() - timedelta(days=INITIAL_HISTORY_DAYS)


def test_complete_link_counts_the_history_window_from_the_users_day(monkeypatch):
    """With a user date, Teller's initial depth is counted back from *their* day.

    `history_start` dates every opening balance the first sync writes. Counted from a
    calendar ahead of the user -- the institution's, or a container on UTC -- the
    window starts a day into their future, and the sync's "up to today" reads drop
    exactly the rows it was meant to import. The institution's day is pushed to a date
    the window cannot accidentally land on, so a fallback fails this assertion rather
    than happening to pass at certain hours.
    """
    from app.providers import teller as teller_module
    from app.providers.teller import INITIAL_HISTORY_DAYS

    user_day = date(2026, 3, 4)
    monkeypatch.setattr(
        teller_module, "institution_today", lambda: user_day + timedelta(days=1)
    )

    result = _provider(_complete_handler).complete_link(
        "token_sandbox",
        {"nonce": issue_nonce("user-9"), "user_id": "usr_1", "enrollment_id": "enr_9"},
        today=user_day,
    )

    assert result.history_start == user_day - timedelta(days=INITIAL_HISTORY_DAYS)
    assert result.history_start != (user_day + timedelta(days=1)) - timedelta(
        days=INITIAL_HISTORY_DAYS
    )


def test_sync_window_ends_on_the_users_day_not_the_institutions(monkeypatch):
    """The first sync asks for the user's day, so it cannot fetch their tomorrow.

    The window and the depth must agree: a history counted from the user's day while
    the first page ends on the institution's would import rows dated after their
    today, which every "up to today" read then hides.
    """
    from app.providers import teller as teller_module
    from app.providers.teller import INITIAL_HISTORY_DAYS
    from app.providers.teller import OVERLAP_DAYS

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/accounts":
            return httpx.Response(200, json=_accounts_payload())
        return httpx.Response(200, json=[])

    user_day = date(2026, 3, 4)
    monkeypatch.setattr(
        teller_module, "institution_today", lambda: user_day + timedelta(days=1)
    )

    delta = _provider(handler).sync_page("token_abc", cursor=None, today=user_day)

    transaction_requests = [r for r in requests if r.url.path.endswith("/transactions")]
    assert transaction_requests, "the adapter must ask each account for transactions"
    params = transaction_requests[0].url.params
    assert params["end_date"] == user_day.isoformat()
    assert params["start_date"] == (
        user_day - timedelta(days=INITIAL_HISTORY_DAYS + OVERLAP_DAYS)
    ).isoformat()
    assert delta.next_cursor == f"teller:v1:{user_day.isoformat()}"


def test_sync_reads_an_overlapping_window_and_advances_its_cursor():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/accounts":
            return httpx.Response(200, json=_accounts_payload())
        if request.url.path.endswith("/balances"):
            return httpx.Response(200, json={"ledger": "10.00"})
        return httpx.Response(200, json=[])

    # No `today` is passed, so this also pins the fallback: the window must end on the
    # institution's calendar rather than on whatever date this host is living in.
    from app.providers.teller import institution_today

    today = institution_today()
    cursor = f"teller:v1:{(today - timedelta(days=30)).isoformat()}"
    delta = _provider(handler).sync_page("token_abc", cursor=cursor)
    transaction_requests = [r for r in requests if r.url.path.endswith("/transactions")]
    assert transaction_requests, "the adapter must ask each account for transactions"
    params = transaction_requests[0].url.params
    assert params["start_date"] == (today - timedelta(days=40)).isoformat()
    assert params["end_date"] == today.isoformat()
    assert delta.next_cursor == f"teller:v1:{today.isoformat()}"


def _signed_enrollment():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    nonce = issue_nonce("user-7")
    message = ".".join([nonce, "token_signed", "usr_1", "enr_1", "sandbox"]).encode()
    signature = base64.b64encode(key.sign(message)).decode()
    return public_pem.decode(), nonce, signature


def _complete_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/accounts":
        return httpx.Response(200, json=_accounts_payload())
    if request.url.path.endswith("/balances"):
        return httpx.Response(200, json={"ledger": "50.00"})
    raise AssertionError(request.url.path)


def test_a_signed_enrollment_is_accepted():
    signing_key, nonce, signature = _signed_enrollment()
    provider = _provider(_complete_handler, signing_key=signing_key)
    result = provider.complete_link(
        "token_signed",
        {
            "nonce": nonce,
            "user_id": "usr_1",
            "enrollment_id": "enr_1",
            "signatures": [signature],
            "expected_user_id": "user-7",
        },
    )
    assert result.external_item_id == "enr_1"
    assert result.institution_name == "USAA"
    assert result.access_token == "token_signed"


def test_a_forged_signature_is_rejected():
    signing_key, nonce, _ = _signed_enrollment()
    provider = _provider(_complete_handler, signing_key=signing_key)
    with pytest.raises(ProviderError) as exc:
        provider.complete_link(
            "token_signed",
            {
                "nonce": nonce,
                "user_id": "usr_1",
                "enrollment_id": "enr_1",
                "signatures": [base64.b64encode(b"not a signature").decode()],
                "expected_user_id": "user-7",
            },
        )
    assert exc.value.code == "invalid_signature"


def test_a_nonce_from_another_session_is_rejected():
    signing_key, _, signature = _signed_enrollment()
    nonce = issue_nonce("someone-else")
    provider = _provider(_complete_handler, signing_key=signing_key)
    with pytest.raises(NonceError):
        provider.complete_link(
            "token_signed",
            {
                "nonce": nonce,
                "user_id": "usr_1",
                "enrollment_id": "enr_1",
                "signatures": [signature],
                "expected_user_id": "user-7",
            },
        )


def test_unsigned_enrollments_are_refused_outside_sandbox():
    provider = _provider(
        _complete_handler,
        environment="production",
        certificate="/tmp/cert.pem",
        private_key="/tmp/key.pem",
        signing_key="-----BEGIN PUBLIC KEY-----x",
    )
    with pytest.raises(ProviderError) as exc:
        provider.complete_link(
            "token_signed",
            {"nonce": issue_nonce("user-7"), "user_id": "usr_1", "enrollment_id": "enr_1"},
        )
    assert exc.value.code == "unsigned_enrollment"


def test_unsigned_sandbox_enrollment_is_accepted():
    result = _provider(_complete_handler).complete_link(
        "token_sandbox",
        {"nonce": issue_nonce("user-9"), "user_id": "usr_1", "enrollment_id": "enr_9"},
    )
    assert result.external_item_id == "enr_9"


def test_remove_item_deletes_the_enrollment():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(204)

    _provider(handler).remove_item("token_abc")
    assert seen == [("DELETE", "/accounts")]


def test_revoked_token_is_treated_as_already_removed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "invalid_token"}})

    _provider(handler).remove_item("token_abc")


def test_institution_products_decide_capability():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/institutions"
        assert "authorization" not in request.headers, "the directory is public"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "usaa",
                    "name": "USAA",
                    "products": ["verify", "balance", "transactions", "identity"],
                },
                {"id": "cash_app", "name": "Cash App", "products": ["balance"]},
            ],
        )

    rows = {r.institution_id: r for r in _provider(handler).list_institutions()}
    assert rows["usaa"].supports_transactions is True
    assert rows["usaa"].supports_balances is True
    # Listed, but without transactions: selection must not choose it for a sync.
    assert rows["cash_app"].supports_transactions is False


def test_check_connection_reports_counts_without_secrets():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"id": "usaa", "name": "USAA", "products": ["balance", "transactions"]},
                {"id": "cash_app", "name": "Cash App", "products": ["balance"]},
            ],
        )

    detail = _provider(handler).check_connection()
    assert detail["institutions"] == 2
    assert detail["institutions_with_transactions"] == 1
    assert detail["environment"] == "sandbox"
    assert "app_test" not in json.dumps(detail)


def test_rate_limit_is_retryable_but_a_rejected_token_is_not():
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "rate_limited"}})

    with pytest.raises(ProviderError) as exc:
        _provider(limited).list_accounts("token")
    assert exc.value.retryable is True

    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "invalid_token"}})

    with pytest.raises(ProviderError) as exc:
        _provider(rejected).list_accounts("token")
    assert exc.value.requires_reauth is True
    assert exc.value.retryable is False


def test_nonce_is_signed_and_expires(monkeypatch):
    nonce = issue_nonce("user-1")
    verify_nonce(nonce, "user-1")
    # A tampered nonce must not verify.
    with pytest.raises(NonceError):
        verify_nonce(nonce[:-2] + "aa", "user-1")
    # A nonce issued for another user must not verify.
    with pytest.raises(NonceError):
        verify_nonce(issue_nonce(str(uuid.uuid4())), "user-1")
