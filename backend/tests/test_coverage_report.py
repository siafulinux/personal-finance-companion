"""The coverage table must never turn "could not ask" into "does not carry it".

``not listed`` is a claim about an institution: the provider's directory answered and has
no entry for it. When a *configured* provider's directory cannot be reached, the honest
row is ``not available``. Rendering the two the same way would let a network fault look
like proof that USAA or Cash App is unsupported, which is exactly the mistake this table
exists to prevent.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.config import settings
from app.providers.base import ProviderError, ProviderInstitution
from app.services import provider_config, provider_selection

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_coverage_report():
    """Load the generator by path: ``backend/scripts`` is a scripts directory, not a package."""
    path = BACKEND_ROOT / "scripts" / "coverage_report.py"
    spec = importlib.util.spec_from_file_location("coverage_report_under_test", path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


coverage_report = _load_coverage_report()


@dataclass
class _Directory:
    """A provider directory that either answers or fails — nothing else."""

    institutions: list[ProviderInstitution] = field(default_factory=list)
    failure: ProviderError | None = None

    def list_institutions(self, query: str | None = None) -> list[ProviderInstitution]:
        if self.failure is not None:
            raise self.failure
        needle = (query or "").lower()
        return [row for row in self.institutions if needle in row.name.lower()]


def _configured(name: str, priority: int) -> provider_config.ProviderState:
    return provider_config.ProviderState(
        name=name,
        label=name.title(),
        enabled=True,
        priority=priority,
        environment="sandbox",
        public={},
        secret={},
        source="database",
        configured=True,
    )


@pytest.fixture
def directories(monkeypatch):
    """Both providers configured and enabled, with stubbed directories."""
    adapters = {"teller": _Directory(), "plaid": _Directory()}
    states = [_configured("teller", 10), _configured("plaid", 20)]
    monkeypatch.setattr(provider_config, "resolve_all", lambda db: states)
    monkeypatch.setattr(provider_config, "auto_select_enabled", lambda db: True)
    monkeypatch.setattr(provider_selection, "adapter_for", lambda db, name: adapters[name])
    monkeypatch.setattr(settings, "sandbox_provider_enabled", False)
    provider_selection.clear_cache()
    yield adapters
    provider_selection.clear_cache()


def _row(report: dict, provider: str) -> dict:
    rows = {row["provider"]: row for row in report["institutions"][0]["providers"]}
    return rows[provider]


def _cells(document: str, institution: str = "USAA") -> list[str]:
    line = next(
        line for line in document.splitlines() if line.startswith(f"| {institution} |")
    )
    # "| Institution | Teller | Plaid | Sandbox |" -> indices 2, 3, 4.
    return [cell.strip() for cell in line.split("|")[1:-1]]


def test_unreachable_directory_is_not_available_rather_than_not_listed(db, directories):
    directories["teller"].failure = ProviderError(
        "Could not reach Teller.", code="network_error"
    )
    # Plaid answered and genuinely has no USAA entry — the one honest "not listed".
    directories["plaid"].institutions = []

    report = provider_selection.coverage(db, ["USAA"])

    teller = _row(report, "teller")
    assert teller["available"] is False, "an unreachable directory did not answer"
    assert "network_error" in (teller["reason"] or "")
    assert teller["match"] is None

    plaid = _row(report, "plaid")
    assert plaid["available"] is True
    assert plaid["reason"] == "not listed"

    document = coverage_report.render(report, ["USAA"])
    _, teller_cell, plaid_cell, _ = _cells(document)

    assert "not listed" not in teller_cell, (
        "an unreachable directory must never be reported as an institution the provider "
        f"does not carry; got {teller_cell!r}"
    )
    assert teller_cell.startswith("not available —"), teller_cell
    assert "network_error" in teller_cell

    # The distinction is only useful if the genuine case still reads "not listed".
    assert plaid_cell == "not listed"


def test_unreachable_directory_keeps_the_table_unverified(db, directories):
    directories["teller"].failure = ProviderError("Teller rejected it.", code="invalid_token")
    directories["plaid"].failure = ProviderError("Could not reach Plaid.", code="network_error")

    report = provider_selection.coverage(db, ["USAA"])
    state, reasons = coverage_report._status(report)

    assert state == "not verified"
    assert any("unreachable" in reason and "network_error" in reason for reason in reasons)
    assert any("invalid_token" in reason for reason in reasons)

    document = coverage_report.render(report, ["USAA"])
    assert "**Status: not verified.**" in document
    assert "not listed" not in " ".join(_cells(document))


def test_an_unconfigured_provider_is_not_available_not_not_listed(db, directories, monkeypatch):
    """A provider this server never asked must not appear to have answered "no"."""
    states = [
        _configured("teller", 10),
        provider_config.ProviderState(
            name="plaid",
            label="Plaid",
            enabled=False,
            priority=20,
            environment="sandbox",
            public={},
            secret={},
            source="none",
            configured=False,
            missing=("client_id", "secret"),
        ),
    ]
    monkeypatch.setattr(provider_config, "resolve_all", lambda db: states)
    directories["teller"].institutions = []

    report = provider_selection.coverage(db, ["USAA"])
    _, teller_cell, plaid_cell, _ = _cells(coverage_report.render(report, ["USAA"]))

    # Teller answered with nothing: that is a real "not listed".
    assert teller_cell == "not listed"
    assert plaid_cell.startswith("not available —")
    assert "not listed" not in plaid_cell
