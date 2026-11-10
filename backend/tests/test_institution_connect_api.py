"""The provider-independent institution flow over HTTP, using the simulated institution.

The sandbox adapter is the only provider a credential-free test can drive end to end, but
the flow is the same one Teller and Plaid go through: search a catalogue, start the
provider's authorisation, finish it, and sync.
"""

from __future__ import annotations

import pytest

from app.providers.sandbox import reset_state
from app.services.users import register_user

API = "/api/v1"


@pytest.fixture(autouse=True)
def clean_sandbox():
    reset_state()
    yield
    reset_state()


def _catalog(client, query: str = "Sandbox") -> dict:
    response = client.get(f"{API}/connectivity/catalog", params={"query": query})
    assert response.status_code == 200, response.text
    return response.json()


def _start(client, name: str, key: str | None = None) -> dict:
    body: dict = {"institution_name": name}
    if key:
        body["institution_key"] = key
    response = client.post(f"{API}/connectivity/connect/start", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_catalog_requires_authentication(client):
    assert client.get(f"{API}/connectivity/catalog").status_code == 401


def test_catalog_lists_institutions_without_naming_providers(auth_client):
    body = _catalog(auth_client)
    assert body["institutions"], body
    entry = body["institutions"][0]
    assert entry["name"] == "Sandbox Credit Union"
    assert entry["available"] is True
    assert entry["simulated"] is True
    assert "provider" not in entry
    assert "sandbox" not in str(entry["key"])


def test_starting_a_connection_returns_the_provider_flow(auth_client):
    entry = _catalog(auth_client)["institutions"][0]
    started = _start(auth_client, entry["name"], entry["key"])
    assert started["connection"]["name"] == entry["name"]
    assert started["flow"]["link_token"]
    # The client is told how to run the flow, never how to configure a provider.
    serialized = str(started).lower()
    assert "secret" not in serialized
    assert "certificate" not in serialized


def test_consent_is_required_before_importing(auth_client):
    entry = _catalog(auth_client)["institutions"][0]
    started = _start(auth_client, entry["name"], entry["key"])
    response = auth_client.post(
        f"{API}/connectivity/connect/finish",
        json={
            "institution_name": entry["name"],
            "institution_key": entry["key"],
            "public_token": started["flow"]["link_token"],
            "consent": False,
        },
    )
    assert response.status_code == 422
    assert "consent" in response.text.lower()


def test_full_connection_imports_accounts_and_transactions(auth_client):
    entry = _catalog(auth_client)["institutions"][0]
    started = _start(auth_client, entry["name"], entry["key"])
    response = auth_client.post(
        f"{API}/connectivity/connect/finish",
        json={
            "institution_name": entry["name"],
            "institution_key": entry["key"],
            "public_token": started["flow"]["link_token"],
            "consent": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["link"]["status"] == "active"
    assert body["link"]["account_count"] == 3
    assert body["sync"]["added"] > 0
    # No token in the response, ever.
    assert "sbx-access" not in response.text

    ledger = auth_client.get(f"{API}/transactions?limit=200").json()
    assert ledger["total"] > 0


def test_reconnecting_the_same_institution_does_not_duplicate_it(auth_client):
    entry = _catalog(auth_client)["institutions"][0]
    first = _start(auth_client, entry["name"], entry["key"])
    auth_client.post(
        f"{API}/connectivity/connect/finish",
        json={
            "institution_name": entry["name"],
            "institution_key": entry["key"],
            "public_token": first["flow"]["link_token"],
            "consent": True,
        },
    )
    second = _start(auth_client, entry["name"], entry["key"])
    again = auth_client.post(
        f"{API}/connectivity/connect/finish",
        json={
            "institution_name": entry["name"],
            "institution_key": entry["key"],
            "public_token": second["flow"]["link_token"],
            "consent": True,
        },
    )
    assert again.status_code == 201, again.text
    links = auth_client.get(f"{API}/connectivity/links").json()["links"]
    assert len(links) == 1
    # The reconnect replays history: dedupe absorbs it.
    assert again.json()["sync"]["added"] == 0


def test_an_unavailable_institution_is_refused_with_a_reason(auth_client):
    response = auth_client.post(
        f"{API}/connectivity/connect/start",
        json={"institution_name": "Not A Real Institution", "institution_key": "inst_missing"},
    )
    assert response.status_code == 422
    assert "not currently available" in response.text.lower()


def test_connections_are_isolated_between_users(auth_client, client, db):
    entry = _catalog(auth_client)["institutions"][0]
    started = _start(auth_client, entry["name"], entry["key"])
    auth_client.post(
        f"{API}/connectivity/connect/finish",
        json={
            "institution_name": entry["name"],
            "institution_key": entry["key"],
            "public_token": started["flow"]["link_token"],
            "consent": True,
        },
    )

    other = register_user(
        db,
        email="other-catalog@example.com",
        password="TestPassword123",
        display_name="Other",
        timezone="America/New_York",
    )
    db.commit()
    login = client.post(
        f"{API}/auth/login",
        json={"email": other.email, "password": "TestPassword123"},
    )
    assert login.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("pfc_csrf")})
    assert client.get(f"{API}/connectivity/links").json()["links"] == []
    assert client.get(f"{API}/transactions").json()["total"] == 0
