"""First-run setup, registration policy, public server info and pairing codes.

These cover the deployment rules that decide who can get into a freshly installed
server, so they assert refusals as carefully as successes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.api import server as server_api
from app.config import settings
from app.version import RELEASE_TAG

SETUP = {
    "server_name": "Home Finance",
    "admin_email": "owner@example.com",
    "admin_name": "Owner",
    "admin_password": "SetupPassword123",
    "registration_enabled": False,
}


@pytest.fixture(autouse=True)
def _reset_anonymous_limits():
    """The setup/pair guard is per process; each test starts with a clean budget."""
    server_api._attempts.clear()
    yield
    server_api._attempts.clear()


def _setup(client, **overrides):
    payload = {**SETUP, **overrides}
    return client.post("/api/v1/server/setup", json=payload)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_info_is_public_and_reveals_no_secrets(client):
    response = client.get("/api/v1/server/info")
    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == settings.app_name
    assert body["setup_required"] is True
    assert body["status"] == "ok"
    assert body["api_base_url"].endswith("/api/v1")
    assert body["version"] and body["api_version"] >= 1
    # The release tag is public on purpose: it names the source this build came
    # from, so an installation can be identified without shell access.
    assert body["release_tag"] == RELEASE_TAG
    assert body["release_tag"].startswith("v")
    # The endpoint is unauthenticated: it must not describe the database, the
    # secret key, cookies or any account.
    lowered = response.text.lower()
    for forbidden in ("postgres", "password", "secret_key", "cookie", "@example.com"):
        assert forbidden not in lowered


def test_setup_creates_the_administrator_and_closes_the_wizard(client):
    response = _setup(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["server"]["server_name"] == "Home Finance"
    assert body["server"]["setup_required"] is False
    assert body["access_token"]

    info = client.get("/api/v1/server/info").json()
    assert info["setup_required"] is False
    assert info["registration_enabled"] is False

    # The wizard is closed for good, not merely hidden in the UI.
    again = _setup(client, server_name="Second Owner")
    assert again.status_code == 409
    assert "already been set up" in again.json()["detail"]


def test_registration_follows_the_policy_chosen_at_setup(client):
    token = _setup(client).json()["access_token"]

    closed = client.post(
        "/api/v1/auth/register",
        json={
            "email": "stranger@example.com",
            "password": "StrangerPass123",
            "display_name": "Stranger",
            "timezone": "America/New_York",
        },
    )
    assert closed.status_code == 403
    assert "Registration is closed" in closed.json()["detail"]

    opened = client.patch(
        "/api/v1/server/settings",
        json={"registration_enabled": True},
        headers=_bearer(token),
    )
    assert opened.status_code == 200
    assert opened.json()["settings"]["registration_enabled"] is True

    allowed = client.post(
        "/api/v1/auth/register",
        json={
            "email": "friend@example.com",
            "password": "FriendPass123",
            "display_name": "Friend",
            "timezone": "America/New_York",
        },
    )
    assert allowed.status_code == 201


def test_only_the_administrator_changes_server_settings(client):
    _setup(client)
    # Registration is closed, so open it once with the admin token to get a
    # second, ordinary account.
    admin = client.post("/api/v1/auth/login", json={"email": SETUP["admin_email"], "password": SETUP["admin_password"]})
    assert admin.status_code == 200
    admin_token = admin.json()["access_token"]
    client.patch(
        "/api/v1/server/settings",
        json={"registration_enabled": True},
        headers=_bearer(admin_token),
    )
    member_token = client.post(
        "/api/v1/auth/register",
        json={
            "email": "member@example.com",
            "password": "MemberPass123",
            "display_name": "Member",
            "timezone": "America/New_York",
        },
    ).json()["access_token"]

    denied = client.patch(
        "/api/v1/server/settings",
        json={"server_name": "Hijacked"},
        headers=_bearer(member_token),
    )
    assert denied.status_code == 403

    read = client.get("/api/v1/server/settings", headers=_bearer(member_token))
    assert read.status_code == 200
    assert read.json()["settings"]["is_admin"] is False


def test_public_registration_cannot_be_used_before_setup_when_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "open_registration_until_setup", False)
    attempted = client.post(
        "/api/v1/auth/register",
        json={
            "email": "first-come@example.com",
            "password": "FirstComePass123",
            "display_name": "First",
            "timezone": "America/New_York",
        },
    )
    assert attempted.status_code == 403

    # The owner can still claim the server through the wizard.
    assert _setup(client).status_code == 201


def test_pairing_code_is_short_lived_and_single_use(client):
    token = _setup(client).json()["access_token"]
    created = client.post(
        "/api/v1/server/pairing", json={"label": "Pixel"}, headers=_bearer(token)
    )
    assert created.status_code == 201
    body = created.json()
    code = body["token"]
    assert body["connection"]["api_base_url"].endswith("/api/v1")
    assert "/pair?token=" in body["pairing_url"]

    first = client.post("/api/v1/server/pair", json={"token": code})
    assert first.status_code == 200
    assert first.json()["paired"] is True
    assert first.json()["connection"]["server_name"] == "Home Finance"

    replay = client.post("/api/v1/server/pair", json={"token": code})
    assert replay.status_code == 409


def test_expired_pairing_code_is_rejected(client, db):
    token = _setup(client).json()["access_token"]
    code = client.post(
        "/api/v1/server/pairing", json={}, headers=_bearer(token)
    ).json()["token"]
    db.execute(text("update pairing_tokens set expires_at = now() - interval '1 minute'"))
    db.commit()

    response = client.post("/api/v1/server/pair", json={"token": code})
    assert response.status_code == 422
    assert "expired" in response.json()["detail"].lower()


def test_pairing_requires_the_administrator(client):
    _setup(client)
    admin_token = client.post(
        "/api/v1/auth/login", json={"email": SETUP["admin_email"], "password": SETUP["admin_password"]}
    ).json()["access_token"]
    client.patch(
        "/api/v1/server/settings",
        json={"registration_enabled": True},
        headers=_bearer(admin_token),
    )
    member_token = client.post(
        "/api/v1/auth/register",
        json={
            "email": "member2@example.com",
            "password": "MemberPass123",
            "display_name": "Member",
            "timezone": "America/New_York",
        },
    ).json()["access_token"]

    denied = client.post("/api/v1/server/pairing", json={}, headers=_bearer(member_token))
    assert denied.status_code == 403


def test_public_base_url_override_drives_advertised_addresses(client):
    token = _setup(client).json()["access_token"]
    updated = client.patch(
        "/api/v1/server/settings",
        json={"public_base_url": "https://finance.example.com/"},
        headers=_bearer(token),
    )
    assert updated.status_code == 200
    info = updated.json()["server"]
    assert info["web_url"] == "https://finance.example.com"
    assert info["api_base_url"] == "https://finance.example.com/api/v1"


def test_invalid_public_url_is_rejected(client):
    token = _setup(client).json()["access_token"]
    for bad in ("not a url", "ftp://example.com", "//example.com"):
        response = client.patch(
            "/api/v1/server/settings",
            json={"public_base_url": bad},
            headers=_bearer(token),
        )
        assert response.status_code == 422, bad


def test_registration_is_anonymous_safe_after_setup(client):
    """A closed server must not confirm whether an address exists."""
    _setup(client)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": SETUP["admin_email"],
            "password": "AnotherPass123",
            "display_name": "Duplicate",
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 403
    assert "already" not in response.json()["detail"].lower()
