"""Automatic provider selection: primary, fallback, unavailable, and the sandbox path."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from app.config import settings
from app.models.enums import SyncTrigger
from app.providers.base import (
    LinkResult,
    ProviderAccountData,
    ProviderError,
    ProviderInstitution,
    ProviderTransactionData,
    TransactionDelta,
)
from app.services import provider_config, provider_selection
from app.services.errors import ValidationError
from app.services.sync import list_links


@dataclass
class FakeAdapter:
    name: str
    institutions: list[ProviderInstitution]
    configured: bool = True
    created_tokens: int = 0
    last_institution: str | None = None
    failure: ProviderError | None = None
    calls: int = 0

    def is_configured(self) -> bool:
        return self.configured

    def list_institutions(self, query: str | None = None):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        needle = (query or "").lower()
        return [i for i in self.institutions if needle in i.name.lower()]

    def create_link_token(self, user_id: str, institution_id: str | None = None):
        self.created_tokens += 1
        self.last_institution = institution_id
        return {
            "provider": self.name,
            "mode": "fake",
            "link_token": f"tok-{self.name}",
            "application_id": "app_public",
            "nonce": "nonce-123",
        }

    def check_connection(self):
        return {"provider": self.name, "message": "ok"}


@dataclass
class FakeWorld:
    adapters: dict[str, FakeAdapter]
    states: list[provider_config.ProviderState] = field(default_factory=list)


def _state(name: str, priority: int, *, enabled: bool = True, configured: bool = True):
    return provider_config.ProviderState(
        name=name,
        label=name.title(),
        enabled=enabled,
        priority=priority,
        environment="sandbox",
        public={},
        secret={},
        source="database",
        configured=configured,
    )


def _institution(provider: str, name: str, *, transactions=True, balances=True, iid=None):
    products = []
    if transactions:
        products.append("transactions")
    if balances:
        products.append("balance")
    return ProviderInstitution(
        provider=provider,
        institution_id=iid or f"{provider}-{name.lower().replace(' ', '-')}",
        name=name,
        products=tuple(products),
        supports_transactions=transactions,
        supports_balances=balances,
    )


@pytest.fixture
def world(monkeypatch):
    teller = FakeAdapter("teller", [])
    plaid = FakeAdapter("plaid", [])
    adapters = {"teller": teller, "plaid": plaid}
    states = [_state("teller", 10), _state("plaid", 20)]
    monkeypatch.setattr(provider_config, "resolve_all", lambda db: states)
    monkeypatch.setattr(provider_selection, "adapter_for", lambda db, name: adapters[name])
    monkeypatch.setattr(settings, "sandbox_provider_enabled", False)
    provider_selection.clear_cache()
    yield FakeWorld(adapters=adapters, states=states)
    provider_selection.clear_cache()


def test_teller_is_chosen_when_it_supports_the_institution(db, world):
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    world.adapters["plaid"].institutions = [_institution("plaid", "USAA")]

    catalog = provider_selection.catalog(db, "USAA")
    assert len(catalog.entries) == 1
    entry = catalog.entries[0]
    assert entry.available is True
    assert entry.provider == "teller"

    selection = provider_selection.select(db, "USAA")
    assert selection.provider == "teller"
    assert selection.institution.institution_id == "teller-usaa"


def test_falls_back_to_plaid_when_teller_cannot_serve_the_institution(db, world):
    world.adapters["teller"].institutions = [
        _institution("teller", "Cash App", transactions=False)
    ]
    world.adapters["plaid"].institutions = [_institution("plaid", "Cash App")]

    selection = provider_selection.select(db, "Cash App")
    assert selection.provider == "plaid"
    assert selection.institution.supports_transactions is True


def test_an_institution_no_provider_can_serve_is_explained_not_offered(db, world):
    world.adapters["teller"].institutions = [
        _institution("teller", "Hometown Loans", transactions=False, balances=True)
    ]
    world.adapters["plaid"].institutions = [
        _institution("plaid", "Hometown Loans", transactions=False, balances=False)
    ]

    catalog = provider_selection.catalog(db, "Hometown Loans")
    entry = catalog.entries[0]
    assert entry.available is False
    assert "transaction history" in (entry.reason or "")

    with pytest.raises(ValidationError) as exc:
        provider_selection.select(db, "Hometown Loans")
    assert "transaction history" in exc.value.message


def test_auto_selection_can_be_pinned_to_one_provider(db, world, monkeypatch):
    world.adapters["teller"].institutions = [
        _institution("teller", "Cash App", transactions=False)
    ]
    world.adapters["plaid"].institutions = [_institution("plaid", "Cash App")]
    monkeypatch.setattr(provider_config, "auto_select_enabled", lambda db: False)

    entry = provider_selection.catalog(db, "Cash App").entries[0]
    assert entry.available is False
    assert "pinned" in (entry.reason or "")
    with pytest.raises(ValidationError):
        provider_selection.select(db, "Cash App")


def test_disabled_provider_is_skipped(db, world):
    world.states.clear()
    world.states.extend([_state("teller", 10, enabled=False), _state("plaid", 20)])
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    world.adapters["plaid"].institutions = [_institution("plaid", "USAA")]

    # Teller is disabled, so the priority loop never reaches it.
    entry = provider_selection.catalog(db, "USAA").entries[0]
    assert entry.provider == "plaid"


def test_unconfigured_provider_is_skipped(db, world):
    world.states.clear()
    world.states.extend([_state("teller", 10, configured=False), _state("plaid", 20)])
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    world.adapters["plaid"].institutions = [_institution("plaid", "USAA")]

    entry = provider_selection.catalog(db, "USAA").entries[0]
    assert entry.provider == "plaid"


def test_configured_describes_the_server_not_the_search_query(db, world):
    """A bank the directory does not carry must not read as "no provider configured".

    The user-facing flag drives a message that blames the administrator, so it may only
    be false when the server genuinely has nothing to connect with.
    """
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    world.adapters["plaid"].institutions = []

    assert provider_selection.catalog(db, "Cash App").entries == []
    assert provider_selection.configured(db) is True


def test_configured_is_false_only_when_nothing_is_usable(db, world):
    world.states.clear()
    world.states.extend(
        [_state("teller", 10, enabled=False), _state("plaid", 20, configured=False)]
    )

    # The `world` fixture also switches the simulated provider off.
    assert provider_selection.configured(db) is False


def test_catalog_does_not_reveal_the_provider(db, world):
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    payload = provider_selection.catalog(db, "USAA").as_dict()
    serialized = str(payload).lower()
    assert "teller" not in serialized
    assert "plaid" not in serialized
    assert payload["institutions"][0]["name"] == "USAA"


def test_same_institution_is_listed_once_across_providers(db, world):
    world.adapters["teller"].institutions = [
        _institution("teller", "USAA Federal Savings Bank")
    ]
    world.adapters["plaid"].institutions = [_institution("plaid", "USAA")]
    entries = provider_selection.catalog(db, "USAA").entries
    assert len(entries) == 1


def test_start_link_returns_the_flow_without_secrets(db, world):
    world.adapters["teller"].institutions = [_institution("teller", "USAA", iid="usaa")]
    started = provider_selection.start_link(db, "user-1", "USAA")
    assert started["provider"] == "teller"
    assert started["mode"] == "fake"
    assert started["flow"]["link_token"] == "tok-teller"
    assert world.adapters["teller"].last_institution == "usaa"
    # The provider identity itself is returned only for server-side routing; the
    # institution payload the UI renders carries nothing provider-specific.
    assert set(started["connection"]) == {"key", "name", "available", "reason"}


def test_finish_link_routes_to_the_selected_provider(db, world, monkeypatch):
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    captured: dict = {}

    def fake_connect(db, user, provider, token, *, payload=None):
        captured.update(provider=provider, token=token, payload=payload)
        raise ValidationError("stop here")

    monkeypatch.setattr("app.services.sync.connect_institution", fake_connect)

    class AnyUser:
        id = uuid.uuid4()

    with pytest.raises(ValidationError):
        provider_selection.finish_link(
            db,
            AnyUser(),
            "USAA",
            public_token="tok-abc",
            payload={"nonce": "n"},
        )
    assert captured["provider"] == "teller"
    assert captured["token"] == "tok-abc"
    assert captured["payload"]["institution_id"] == "teller-usaa"
    assert captured["payload"]["institution_name"] == "USAA"


def test_unknown_institution_key_is_rejected(db, world):
    world.adapters["teller"].institutions = [_institution("teller", "USAA")]
    with pytest.raises(ValidationError):
        provider_selection.select(db, "USAA", key="inst_notarealhash")


def test_sandbox_institution_connects_end_to_end_through_selection(db, user, monkeypatch):
    """The simulated institution proves the whole flow without any credentials."""
    monkeypatch.setattr(settings, "sandbox_provider_enabled", True)
    provider_selection.clear_cache()

    catalog = provider_selection.catalog(db, "Sandbox")
    assert catalog.entries and catalog.entries[0].available is True
    assert catalog.entries[0].simulated is True

    started = provider_selection.start_link(
        db, str(user.id), "Sandbox Credit Union", key=catalog.entries[0].key
    )
    assert started["provider"] == "sandbox"

    link, accounts, run = provider_selection.finish_link(
        db,
        user,
        "Sandbox Credit Union",
        key=catalog.entries[0].key,
        public_token=str(started["flow"]["link_token"]),
    )
    assert link.institution_name == "Sandbox Credit Union"
    assert len(accounts) == 3
    assert run.trigger == SyncTrigger.MANUAL.value
    assert run.added > 0
    assert len(list_links(db, user.id)) == 1
    provider_selection.clear_cache()


def test_a_failed_directory_is_not_retried_on_every_request(db, world):
    """One unreachable provider must not make every catalogue request wait for it."""
    world.adapters["teller"].failure = ProviderError(
        "Could not reach Teller.", code="network_error"
    )
    world.adapters["plaid"].institutions = [_institution("plaid", "USAA")]

    first = provider_selection.catalog(db, "USAA")
    assert any("could not be reached" in w.lower() for w in first.warnings)
    assert first.entries[0].provider == "plaid"
    calls_after_first = world.adapters["teller"].calls

    second = provider_selection.catalog(db, "USAA")
    assert any("could not be reached" in w.lower() for w in second.warnings)
    assert world.adapters["teller"].calls == calls_after_first, (
        "the remembered failure must be reused"
    )

    # Clearing the cache (an admin saved a credential) forgets it deliberately.
    provider_selection.clear_cache()
    provider_selection.catalog(db, "USAA")
    assert world.adapters["teller"].calls > calls_after_first


def test_coverage_reports_every_provider_including_unusable_ones(db, world):
    world.states.clear()
    world.states.extend([_state("teller", 10), _state("plaid", 20, enabled=False)])
    world.adapters["teller"].institutions = [
        _institution("teller", "USAA Federal Savings Bank", iid="usaa")
    ]

    report = provider_selection.coverage(db, ["USAA"])
    rows = {row["provider"]: row for row in report["institutions"][0]["providers"]}
    assert rows["teller"]["match"]["institution_id"] == "usaa"
    assert rows["teller"]["match"]["transactions"] is True
    assert rows["plaid"]["available"] is False
    assert "disabled" in (rows["plaid"]["reason"] or "")
