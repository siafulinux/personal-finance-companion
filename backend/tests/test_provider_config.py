"""Administrator-managed provider configuration, at the service and HTTP layers."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import ProviderConfig, ServerSettings, User
from app.models.server import SETTINGS_ID
from app.security.secrets import decrypt_text
from app.services import provider_config, provider_selection
from app.services.errors import ForbiddenError, ValidationError
from app.utils.dates import utc_now

API = "/api/v1"


@pytest.fixture(autouse=True)
def fresh_selection_cache():
    provider_selection.clear_cache()
    yield
    provider_selection.clear_cache()


@pytest.fixture
def admin(db, user) -> User:
    """The account created by the first-run wizard."""
    row = ServerSettings(
        id=SETTINGS_ID,
        server_name="Test Server",
        registration_enabled=False,
        admin_user_id=user.id,
        setup_completed_at=utc_now(),
    )
    db.add(row)
    db.commit()
    return user


@pytest.fixture
def admin_client(client, admin):
    response = client.post(
        f"{API}/auth/login",
        json={"email": admin.email, "password": "TestPassword123"},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"X-CSRF-Token": client.cookies.get("pfc_csrf")})
    return client


# --------------------------------------------------------------------- defaults
def test_defaults_are_teller_primary_and_plaid_secondary(db):
    provider_config.ensure_defaults(db)
    states = provider_config.resolve_all(db)
    assert [s.name for s in states] == ["teller", "plaid"]
    assert states[0].priority == 10
    assert states[1].priority == 20
    # Both are enabled by default; neither is configured without credentials.
    assert all(s.enabled for s in states)
    assert not any(s.configured for s in states)
    assert provider_config.auto_select_enabled(db) is True


def test_environment_variables_configure_a_provider(monkeypatch, db):
    monkeypatch.setattr(settings, "plaid_client_id", "client-from-env")
    monkeypatch.setattr(settings, "plaid_secret", "secret-from-env")
    state = provider_config.resolve(db, "plaid")
    assert state.configured is True
    assert state.source == "environment"
    assert provider_config.credentials_for(db, "plaid") == {
        "client_id": "client-from-env",
        "secret": "secret-from-env",
    }


# ----------------------------------------------------------------- credentials
def test_admin_saved_credentials_are_encrypted_and_masked(db, admin):
    provider_config.ensure_defaults(db)
    provider_config.update_provider(
        db,
        admin,
        "plaid",
        credentials={"client_id": "client-abc", "secret": "super-secret-value"},
    )
    db.commit()

    row = db.get(ProviderConfig, "plaid")
    assert row is not None and row.credentials_ciphertext
    assert "super-secret-value" not in row.credentials_ciphertext
    stored = json.loads(decrypt_text(row.credentials_ciphertext))
    assert stored["secret"] == "super-secret-value"

    described = provider_config.describe(db, "plaid")
    serialized = json.dumps(described, default=str)
    assert "super-secret-value" not in serialized
    secret_field = next(f for f in described["fields"] if f["key"] == "secret")
    assert secret_field["value"] is None
    assert secret_field["present"] is True
    assert secret_field["hint"] and secret_field["hint"] != "super-secret-value"
    public_field = next(f for f in described["fields"] if f["key"] == "client_id")
    assert public_field["value"] == "client-abc"
    assert described["configured"] is True


def test_database_credentials_win_over_environment(monkeypatch, db, admin):
    monkeypatch.setattr(settings, "plaid_client_id", "env-client")
    monkeypatch.setattr(settings, "plaid_secret", "env-secret")
    provider_config.update_provider(
        db, admin, "plaid", credentials={"client_id": "db-client", "secret": "db-secret"}
    )
    state = provider_config.resolve(db, "plaid")
    assert state.source == "database"
    assert provider_config.credentials_for(db, "plaid")["client_id"] == "db-client"


def test_partial_update_keeps_the_unmentioned_secret(db, admin):
    provider_config.update_provider(
        db, admin, "plaid", credentials={"client_id": "c1", "secret": "s1"}
    )
    provider_config.update_provider(db, admin, "plaid", credentials={"client_id": "c2"})
    values = provider_config.credentials_for(db, "plaid")
    assert values == {"client_id": "c2", "secret": "s1"}


def test_empty_value_clears_a_credential(db, admin):
    provider_config.update_provider(
        db, admin, "plaid", credentials={"client_id": "c1", "secret": "s1"}
    )
    provider_config.update_provider(db, admin, "plaid", credentials={"secret": ""})
    values = provider_config.credentials_for(db, "plaid")
    assert "secret" not in values
    assert provider_config.resolve(db, "plaid").configured is False


def test_unreadable_ciphertext_is_reported_not_crashed(db, admin):
    provider_config.ensure_defaults(db)
    row = db.get(ProviderConfig, "plaid")
    assert row is not None
    row.credentials_ciphertext = "v1:not-actually-ciphertext"
    db.commit()

    state = provider_config.resolve(db, "plaid")
    assert state.configured is False
    assert state.problem
    described = provider_config.describe(db, "plaid")
    assert described["problem"]


def test_only_the_administrator_may_change_configuration(db, user):
    with pytest.raises(ForbiddenError):
        provider_config.update_provider(db, user, "plaid", enabled=False)
    with pytest.raises(ForbiddenError):
        provider_config.set_auto_select(db, user, False)


def test_invalid_environment_is_rejected(db, admin):
    with pytest.raises(ValidationError):
        provider_config.update_provider(db, admin, "teller", environment="moon")
    with pytest.raises(ValidationError):
        provider_config.update_provider(db, admin, "teller", priority=99_999)
    with pytest.raises(ValidationError):
        provider_config.update_provider(db, admin, "teller", credentials={"nope": "x"})


def test_disabled_provider_is_not_usable(db, admin):
    provider_config.update_provider(
        db, admin, "teller", credentials={"application_id": "app_x"}
    )
    assert provider_config.usable(db, "teller") is True
    provider_config.update_provider(db, admin, "teller", enabled=False)
    assert provider_config.usable(db, "teller") is False


def test_priority_can_be_reordered_without_code(db, admin):
    provider_config.update_provider(db, admin, "teller", priority=50)
    provider_config.update_provider(db, admin, "plaid", priority=5)
    order = [s.name for s in provider_config.resolve_all(db)]
    assert order == ["plaid", "teller"]


# ------------------------------------------------------------------------- HTTP
def test_admin_endpoints_require_the_administrator(auth_client):
    response = auth_client.get(f"{API}/server/providers")
    assert response.status_code == 403
    response = auth_client.patch(f"{API}/server/providers/plaid", json={"enabled": False})
    assert response.status_code == 403


def test_admin_can_read_and_update_providers(admin_client, db):
    listed = admin_client.get(f"{API}/server/providers")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert [p["name"] for p in body["providers"]] == ["teller", "plaid"]
    assert body["auto_select"] is True
    assert "credentials" not in json.dumps(body.get("providers"), default=str)

    saved = admin_client.patch(
        f"{API}/server/providers/plaid",
        json={
            "enabled": True,
            "priority": 30,
            "environment": "sandbox",
            "credentials": {"client_id": "abc", "secret": "shh-shh-shh"},
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["priority"] == 30
    assert "shh-shh-shh" not in saved.text

    toggled = admin_client.patch(
        f"{API}/server/providers/selection", json={"auto_select": False}
    )
    assert toggled.status_code == 200
    assert toggled.json()["auto_select"] is False
    assert provider_config.auto_select_enabled(db) is False


def test_test_endpoint_reports_missing_configuration(admin_client):
    response = admin_client.post(f"{API}/server/providers/teller/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert "not configured" in body["message"].lower()
    # The failure is remembered so the screen can show it after a reload.
    assert body["provider"]["last_test"]["ok"] is False


def test_test_endpoint_uses_a_real_probe(admin_client, monkeypatch):
    class StubAdapter:
        def check_connection(self):
            return {"provider": "teller", "institutions": 42, "message": "Reached Teller."}

    monkeypatch.setattr("app.api.provider_admin.build_adapter", lambda *a, **k: StubAdapter())
    # The probe only runs once the provider looks configured.
    monkeypatch.setattr(
        "app.api.provider_admin.provider_config.resolve",
        lambda db, name: provider_config.ProviderState(
            name="teller",
            label="Teller",
            enabled=True,
            priority=10,
            environment="sandbox",
            public={"application_id": "app_x"},
            secret={},
            source="database",
            configured=True,
        ),
    )
    response = admin_client.post(f"{API}/server/providers/teller/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["detail"]["institutions"] == 42


def test_coverage_endpoint_requires_nothing_provider_specific(admin_client):
    response = admin_client.get(f"{API}/server/providers/coverage?names=USAA,Cash App")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["query"] for row in body["institutions"]] == ["USAA", "Cash App"]
    # Both providers are reported, even those that are not usable on this server.
    for row in body["institutions"]:
        assert {p["provider"] for p in row["providers"]} >= {"teller", "plaid"}


def test_admin_configuration_does_not_expose_another_users_data(db, admin):
    """Administering the server is not permission to read anyone's finances."""
    from app.models import ProviderLink, User as UserModel
    from app.services.sync import list_links

    other = UserModel(
        email="someone-else@example.com",
        password_hash="x",
        display_name="Someone Else",
        timezone="America/New_York",
    )
    db.add(other)
    db.flush()
    db.add(
        ProviderLink(
            user_id=other.id,
            provider="teller",
            external_item_id="enr_other",
            institution_name="Their Bank",
        )
    )
    db.commit()

    assert list_links(db, admin.id) == []
    listed = db.scalars(select(ProviderLink).where(ProviderLink.user_id == admin.id)).all()
    assert listed == []
