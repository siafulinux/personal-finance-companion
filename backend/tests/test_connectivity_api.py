"""HTTP surface of Phase 2: linking over REST, authz, and the intelligence endpoints."""

from __future__ import annotations

import uuid

import pytest

from app.models import User
from app.providers.sandbox import advance, reset_state
from app.services.users import register_user

API = "/api/v1"


@pytest.fixture(autouse=True)
def clean_sandbox():
    reset_state()
    yield
    reset_state()


def _connect(auth_client):
    token = auth_client.post(f"{API}/connectivity/link-token", json={"provider": "sandbox"})
    assert token.status_code == 200, token.text
    link_token = token.json()["link_token"]
    response = auth_client.post(
        f"{API}/connectivity/exchange",
        json={"provider": "sandbox", "public_token": link_token, "consent": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_providers_list_explains_what_is_available(auth_client):
    response = auth_client.get(f"{API}/connectivity/providers")
    assert response.status_code == 200
    providers = {p["name"]: p for p in response.json()["providers"]}
    assert providers["sandbox"]["usable"] is True
    assert providers["sandbox"]["simulated"] is True
    assert providers["plaid"]["requires_credentials"] is True
    # No credential field is ever exposed (the note may name the env var, not its value).
    assert all("secret" not in field for p in providers.values() for field in p)
    assert all("token" not in field for p in providers.values() for field in p)


def test_link_requires_authentication(client):
    response = client.post(f"{API}/connectivity/link-token", json={"provider": "sandbox"})
    assert response.status_code == 401


def test_exchange_requires_consent(auth_client):
    response = auth_client.post(
        f"{API}/connectivity/exchange",
        json={"provider": "sandbox", "public_token": "sbx-link-x", "consent": False},
    )
    assert response.status_code == 422
    assert "consent" in response.text.lower()


def test_full_connect_and_sync_over_http(auth_client):
    payload = _connect(auth_client)
    link = payload["link"]
    assert link["provider"] == "sandbox"
    assert link["status"] == "active"
    assert link["has_stored_credential"] is True
    assert link["account_count"] == 3
    assert payload["sync"]["added"] > 50
    # The token itself must never be serialised.
    assert "sbx-access" not in str(payload)

    links = auth_client.get(f"{API}/connectivity/links").json()["links"]
    assert len(links) == 1

    synced = auth_client.post(f"{API}/connectivity/links/{link['id']}/sync")
    assert synced.status_code == 200
    assert synced.json()["sync"]["added"] == 0

    runs = auth_client.get(f"{API}/connectivity/sync-runs").json()["runs"]
    assert len(runs) >= 2
    assert all(run["status"] == "success" for run in runs)


def test_transactions_appear_in_the_normal_transaction_endpoint(auth_client):
    _connect(auth_client)
    response = auth_client.get(f"{API}/transactions?limit=200")
    body = response.json()
    assert body["total"] > 50
    assert all(item["source"] == "provider" for item in body["items"])


def test_pending_reconciliation_visible_over_http(auth_client, db):
    from app.models import ProviderLink

    payload = _connect(auth_client)
    pending = auth_client.get(f"{API}/transactions?status=pending").json()["items"]
    assert len(pending) == 1
    pending_id = pending[0]["id"]

    # Advance the simulated institution one day, then re-sync over HTTP.
    link = db.query(ProviderLink).filter_by(id=uuid.UUID(payload["link"]["id"])).one()
    advance(link.external_item_id)
    result = auth_client.post(
        f"{API}/connectivity/links/{payload['link']['id']}/sync"
    ).json()
    assert result["sync"]["status"] == "success"
    assert result["sync"]["modified"] >= 1

    # The same row is now posted; no duplicate transaction was created.
    updated = auth_client.get(f"{API}/transactions/{pending_id}").json()
    assert updated["status"] == "posted"
    assert auth_client.get(f"{API}/transactions?status=pending").json()["items"] == []


def test_deleting_a_connection_deletes_its_data(auth_client):
    payload = _connect(auth_client)
    response = auth_client.delete(
        f"{API}/connectivity/links/{payload['link']['id']}?delete_data=true"
    )
    assert response.status_code == 200
    assert response.json()["deleted_transactions"] > 50
    assert auth_client.get(f"{API}/transactions").json()["total"] == 0


def test_another_user_cannot_touch_a_connection(auth_client, db):
    payload = _connect(auth_client)
    other = register_user(
        db,
        email=f"intruder-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123",
        display_name="Intruder",
        timezone="America/New_York",
    )
    db.commit()

    login = auth_client.post(
        f"{API}/auth/login",
        json={"email": other.email, "password": "TestPassword123"},
    )
    assert login.status_code == 200
    auth_client.headers.update({"X-CSRF-Token": auth_client.cookies.get("pfc_csrf")})

    assert auth_client.get(f"{API}/connectivity/links").json()["links"] == []
    assert (
        auth_client.post(
            f"{API}/connectivity/links/{payload['link']['id']}/sync"
        ).status_code
        == 404
    )
    assert auth_client.get(f"{API}/transactions").json()["total"] == 0


def test_suggestions_can_be_reviewed_and_accepted(auth_client):
    _connect(auth_client)
    suggestions = auth_client.get(f"{API}/suggestions").json()
    assert suggestions["count"] > 0

    first = suggestions["items"][0]
    assert first["transaction"]["merchant"] or first["transaction"]["description"]
    assert first["category_name"]

    accepted = auth_client.post(f"{API}/suggestions/{first['id']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    txn = auth_client.get(f"{API}/transactions/{first['transaction_id']}").json()
    assert txn["category_id"] == first["category_id"]


def test_recurring_endpoint_detects_subscriptions(auth_client):
    _connect(auth_client)
    response = auth_client.post(f"{API}/recurring/detect")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items, "the sandbox history contains three monthly subscriptions"
    names = {item["display_name"] for item in items}
    assert {"Netflix", "Spotify"} <= names
    series = next(item for item in items if item["display_name"] == "Netflix")
    assert series["frequency"] == "monthly"
    assert series["is_subscription"] is True

    listed = auth_client.get(f"{API}/recurring").json()
    assert listed["items"]


def test_personal_insights_endpoint(auth_client):
    _connect(auth_client)
    response = auth_client.get(f"{API}/insights/personal")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["minimum_history"] == {"months": 3, "transactions": 5}
    assert isinstance(body["insights"], list)
    assert isinstance(body["unusual_transactions"], list)


def test_assistant_endpoints_are_read_only(auth_client):
    status = auth_client.get(f"{API}/assistant/status")
    assert status.status_code == 200
    assert status.json()["can_modify_data"] is False

    answer = auth_client.post(f"{API}/assistant/ask", json={"question": "What bills are due?"})
    assert answer.status_code == 200
    body = answer.json()
    assert body["mode"] == "deterministic"
    assert body["can_modify_data"] is False
    assert "plan" not in body  # no action plans, no side effects


def test_assistant_rejects_an_empty_question(auth_client):
    assert auth_client.post(f"{API}/assistant/ask", json={"question": ""}).status_code == 422


def test_preferences_can_disable_insights(auth_client):
    response = auth_client.patch(
        f"{API}/insights/preferences", json={"personalized_insights_enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["personalized_insights_enabled"] is False
    assert auth_client.get(f"{API}/insights/personal").json()["enabled"] is False
